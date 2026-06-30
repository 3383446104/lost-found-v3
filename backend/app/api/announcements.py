# app/api/announcements.py
from fastapi import APIRouter, Depends, HTTPException
from ..database import get_db_connection
from ..dependencies.auth import get_current_admin, get_current_user
from ..utils.time_utils import format_beijing_time

router = APIRouter(prefix="/announcements", tags=["公告"])


@router.get("")
async def list_announcements():
    """公告列表（公开，置顶优先+时间倒序）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, content, is_pinned, created_at FROM announcements ORDER BY is_pinned DESC, created_at DESC LIMIT 20"
        )
        items = [dict(r) for r in cur.fetchall()]
    for item in items:
        item["created_at"] = format_beijing_time(item.get("created_at"))
    return {"announcements": items}


@router.post("")
async def create_announcement(
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """发布公告（管理员）"""
    title = payload.get("title", "").strip()
    content = payload.get("content", "").strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    if not content:
        raise HTTPException(400, "内容不能为空")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO announcements (title, content, is_pinned, admin_id) VALUES (?,?,?,?)",
            (title, content, payload.get("is_pinned", 0), current_admin["user_id"])
        )
    return {"success": True, "id": cur.lastrowid}


@router.put("/{ann_id}")
async def update_announcement(
    ann_id: int,
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """编辑公告（管理员）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM announcements WHERE id=?", (ann_id,))
        if not cur.fetchone():
            raise HTTPException(404, "公告不存在")
        cur.execute(
            "UPDATE announcements SET title=?, content=?, is_pinned=? WHERE id=?",
            (payload.get("title", ""), payload.get("content", ""), payload.get("is_pinned", 0), ann_id)
        )
    return {"success": True}


@router.delete("/{ann_id}")
async def delete_announcement(
    ann_id: int,
    current_admin: dict = Depends(get_current_admin),
):
    """删除公告（管理员）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "公告不存在")
    return {"success": True}
