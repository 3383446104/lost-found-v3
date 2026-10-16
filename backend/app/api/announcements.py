# app/api/announcements.py
# v3.6.0 融合：公告草稿/发布分离（status: draft / published）
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..database import get_db_connection
from ..dependencies.auth import get_current_admin, verify_token
from ..utils.time_utils import format_beijing_time

router = APIRouter(prefix="/announcements", tags=["公告"])


def _valid_status(value) -> str:
    value = value or "draft"
    if value not in ("draft", "published"):
        raise HTTPException(400, "status 必须为 draft 或 published")
    return value


@router.get("")
async def list_announcements(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    all: bool = Query(False, description="管理员传 all=true 看全部（含草稿）"),
):
    """公告列表（公开：仅已发布；管理端传 all=true 看全量含草稿）"""
    # 只有 admin 传 all=true 时才看全部
    can_see_all = False
    if all:
        token = request.headers.get('Authorization', '')
        if token.startswith('Bearer '):
            payload = verify_token(token.replace('Bearer ', ''))
            if payload:
                with get_db_connection() as conn:
                    cur = conn.cursor()
                    cur.execute('SELECT role FROM users WHERE id=?', (payload['user_id'],))
                    u = cur.fetchone()
                    if u and u['role'] == 'admin':
                        can_see_all = True

    with get_db_connection() as conn:
        cur = conn.cursor()
        if can_see_all:
            cur.execute("SELECT COUNT(*) FROM announcements")
            total = cur.fetchone()[0]
            offset = (page - 1) * size
            cur.execute(
                "SELECT id, title, content, is_pinned, target_role, status, created_at FROM announcements ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM announcements WHERE target_role IN ('all','user') AND status='published'"
            )
            total = cur.fetchone()[0]
            offset = (page - 1) * size
            cur.execute(
                "SELECT id, title, content, is_pinned, target_role, status, created_at FROM announcements WHERE target_role IN ('all','user') AND status='published' ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
        items = [dict(r) for r in cur.fetchall()]

    for item in items:
        item["created_at"] = format_beijing_time(item.get("created_at"))
    return {"announcements": items, "total": total, "page": page, "size": size}


@router.post("")
async def create_announcement(
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """新建公告（管理员；默认存为草稿，传 status='published' 直接发布）"""
    title = payload.get("title", "").strip()
    content = payload.get("content", "").strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    if not content:
        raise HTTPException(400, "内容不能为空")
    status = _valid_status(payload.get("status"))

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO announcements (title, content, is_pinned, target_role, status, admin_id) VALUES (?,?,?,?,?,?)",
            (title, content, payload.get("is_pinned", 0), payload.get("target_role", "all"), status, current_admin["user_id"])
        )
    return {"success": True, "id": cur.lastrowid}


@router.put("/{ann_id}")
async def update_announcement(
    ann_id: int,
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """编辑公告（管理员；可同时改状态）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM announcements WHERE id=?", (ann_id,))
        if not cur.fetchone():
            raise HTTPException(404, "公告不存在")
        status = _valid_status(payload.get("status"))
        cur.execute(
            "UPDATE announcements SET title=?, content=?, is_pinned=?, target_role=?, status=? WHERE id=?",
            (payload.get("title", ""), payload.get("content", ""), payload.get("is_pinned", 0),
             payload.get("target_role", "all"), status, ann_id)
        )
    return {"success": True}


@router.put("/{ann_id}/publish")
async def publish_announcement(
    ann_id: int,
    current_admin: dict = Depends(get_current_admin),
):
    """发布公告（草稿 → 已发布）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM announcements WHERE id=?", (ann_id,))
        if not cur.fetchone():
            raise HTTPException(404, "公告不存在")
        cur.execute("UPDATE announcements SET status='published' WHERE id=?", (ann_id,))
    return {"success": True}


@router.put("/{ann_id}/unpublish")
async def unpublish_announcement(
    ann_id: int,
    current_admin: dict = Depends(get_current_admin),
):
    """下架公告（已发布 → 草稿）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM announcements WHERE id=?", (ann_id,))
        if not cur.fetchone():
            raise HTTPException(404, "公告不存在")
        cur.execute("UPDATE announcements SET status='draft' WHERE id=?", (ann_id,))
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
