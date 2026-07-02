# app/api/announcements.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from ..database import get_db_connection
from ..dependencies.auth import get_current_admin, verify_token
from ..utils.time_utils import format_beijing_time

router = APIRouter(prefix="/announcements", tags=["公告"])


@router.get("")
async def list_announcements(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    all: bool = Query(False, description="管理员传 all=true 看全部"),
):
    """公告列表（首页默认过滤，管理端传 all=true 看全量）"""
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
                "SELECT id, title, content, is_pinned, target_role, created_at FROM announcements ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?",
                (size, offset)
            )
        else:
            cur.execute("SELECT COUNT(*) FROM announcements WHERE target_role IN ('all','user')")
            total = cur.fetchone()[0]
            offset = (page - 1) * size
            cur.execute(
                "SELECT id, title, content, is_pinned, target_role, created_at FROM announcements WHERE target_role IN ('all','user') ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?",
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
            "INSERT INTO announcements (title, content, is_pinned, target_role, admin_id) VALUES (?,?,?,?,?)",
            (title, content, payload.get("is_pinned", 0), payload.get("target_role", "all"), current_admin["user_id"])
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
            "UPDATE announcements SET title=?, content=?, is_pinned=?, target_role=? WHERE id=?",
            (payload.get("title", ""), payload.get("content", ""), payload.get("is_pinned", 0), payload.get("target_role", "all"), ann_id)
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
