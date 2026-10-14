# app/api/comments.py
# 留言互动（v3.6.0 融合：物品详情留言区 + 楼中楼回复 + 管理员隐藏违规）
#
# 设计要点（移植自参考项目 campus-lost-and-found-ai 的留言设计）：
# - parent_id 指向被回复留言（楼中楼一层），NULL=顶层留言
# - 公开可看（仅 status=1 正常留言）、登录可发、本人可删、管理员可隐藏/恢复
# - 删除父留言时级联删除子回复（语义简单，避免孤儿回复）
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..database import get_db_connection
from ..dependencies.auth import get_current_user, get_current_admin, resolve_optional_viewer
from ..utils.time_utils import format_beijing_time
from ..logger import logger


router = APIRouter(prefix="/comments", tags=["留言"])

MAX_CONTENT_LEN = 500


# ---------- 请求模型 ----------
class CommentCreate(BaseModel):
    item_id: int
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_LEN, description="留言内容")
    parent_id: Optional[int] = Field(None, description="被回复留言 id（楼中楼），缺省为顶层留言")


class CommentStatusUpdate(BaseModel):
    status: int = Field(..., ge=0, le=1, description="1正常 / 0隐藏")


# ---------- 辅助函数 ----------
def _item_visible(item, viewer_id: Optional[int], is_admin: bool) -> bool:
    """与 items.py get_item 的可见性规则一致：未审核物品仅发布者/管理员可见。"""
    if is_admin or item["user_id"] == viewer_id:
        return True
    return item["review_status"] == "approved" and item["status"] == "active"


def _fmt(row: dict) -> dict:
    if "created_at" in row:
        row["created_at"] = format_beijing_time(row.get("created_at"))
    return row


# ---------- 接口 ----------
@router.get("/item/{item_id:int}")
async def list_comments(
    item_id: int,
    request: Request,
):
    """物品留言列表（公开；仅正常状态留言；扁平结构，前端组树）"""
    viewer = resolve_optional_viewer(request)
    viewer_id = viewer["user_id"] if viewer else None
    is_admin = bool(viewer and viewer["role"] == "admin")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, review_status, status FROM items WHERE id=?", (item_id,)
        )
        item = cur.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")
        if not _item_visible(item, viewer_id, is_admin):
            raise HTTPException(404, "物品不存在")

        cur.execute(
            """SELECT c.id, c.item_id, c.user_id, c.parent_id, c.content, c.created_at,
                      u.username
               FROM comments c JOIN users u ON c.user_id = u.id
               WHERE c.item_id = ? AND c.status = 1
               ORDER BY c.created_at ASC, c.id ASC""",
            (item_id,),
        )
        comments = []
        for r in cur.fetchall():
            d = _fmt(dict(r))
            d["is_mine"] = d.pop("user_id") == viewer_id if viewer_id else False
            comments.append(d)

    return {"comments": comments}


@router.post("", status_code=201)
async def create_comment(
    payload: CommentCreate,
    current_user: dict = Depends(get_current_user)
):
    """发表留言/回复（登录）"""
    user_id = current_user["user_id"]
    content = payload.content.strip()
    if not content:
        raise HTTPException(400, "留言内容不能为空")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, review_status, status FROM items WHERE id=?", (payload.item_id,))
        item = cur.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")
        if not _item_visible(item, user_id, False):
            raise HTTPException(404, "物品不存在")

        if payload.parent_id is not None:
            cur.execute(
                "SELECT id, item_id, status FROM comments WHERE id=?", (payload.parent_id,)
            )
            parent = cur.fetchone()
            if not parent or parent["item_id"] != payload.item_id:
                raise HTTPException(400, "回复的留言不存在")
            if parent["status"] != 1:
                raise HTTPException(400, "该留言已被隐藏，无法回复")

        cur.execute(
            "INSERT INTO comments (item_id, user_id, parent_id, content, status) VALUES (?, ?, ?, ?, 1)",
            (payload.item_id, user_id, payload.parent_id, content),
        )
        comment_id = cur.lastrowid

    logger.info(f"用户 {user_id} 在物品 {payload.item_id} 发表了留言 {comment_id}")
    return {"success": True, "id": comment_id}


@router.delete("/{comment_id:int}")
async def delete_comment(
    comment_id: int,
    current_user: dict = Depends(get_current_user)
):
    """删除留言（本人或管理员；父留言级联删除子回复）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, item_id FROM comments WHERE id=?", (comment_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "留言不存在")

        cur.execute("SELECT role FROM users WHERE id=?", (user_id,))
        u = cur.fetchone()
        if row["user_id"] != user_id and not (u and u["role"] == "admin"):
            raise HTTPException(403, "仅本人或管理员可删除")

        # 级联删除子回复
        cur.execute("DELETE FROM comments WHERE id=? OR parent_id=?", (comment_id, comment_id))

    logger.info(f"用户 {user_id} 删除了留言 {comment_id}")
    return {"success": True}


@router.put("/admin/{comment_id:int}/status")
async def set_comment_status(
    comment_id: int,
    payload: CommentStatusUpdate,
    current_admin: dict = Depends(get_current_admin)
):
    """管理员隐藏/恢复留言（status 0隐藏 / 1正常）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM comments WHERE id=?", (comment_id,))
        if not cur.fetchone():
            raise HTTPException(404, "留言不存在")

        cur.execute("UPDATE comments SET status=? WHERE id=?", (payload.status, comment_id))

    logger.info(f"管理员 {current_admin['user_id']} 将留言 {comment_id} 状态置为 {payload.status}")
    return {"success": True, "message": "操作成功"}


@router.get("/admin")
async def admin_comments(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索留言内容/用户名"),
    status: Optional[int] = Query(None, ge=0, le=1),
    item_id: Optional[int] = Query(None, description="按物品过滤"),
    current_admin: dict = Depends(get_current_admin)
):
    """管理端留言列表（分页 + 筛选）"""
    where = ["1=1"]
    params: List = []
    if keyword:
        where.append("(c.content LIKE ? OR u.username LIKE ?)")
        params.extend([f"%{keyword}%"] * 2)
    if status is not None:
        where.append("c.status = ?")
        params.append(status)
    if item_id is not None:
        where.append("c.item_id = ?")
        params.append(item_id)
    w = " AND ".join(where)

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT COUNT(*) AS total
                FROM comments c JOIN users u ON c.user_id = u.id
                WHERE {w}""",
            params,
        )
        total = cur.fetchone()["total"]
        offset = (page - 1) * size
        cur.execute(
            f"""SELECT c.id, c.item_id, c.parent_id, c.content, c.status, c.created_at,
                      u.username, i.title AS item_title
               FROM comments c
               JOIN users u ON c.user_id = u.id
               JOIN items i ON c.item_id = i.id
               WHERE {w}
               ORDER BY c.created_at DESC, c.id DESC
               LIMIT ? OFFSET ?""",
            params + [size, offset],
        )
        comments = [_fmt(dict(r)) for r in cur.fetchall()]

    return {"total": total, "page": page, "size": size, "comments": comments}
