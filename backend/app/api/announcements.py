# app/api/announcements.py
# v3.6.0 融合：公告草稿/发布分离（status: draft / published）
# 校园公告改版：图文富文本内容、详情页浏览计数、发布时站内+邮件推送所有活跃用户
import os
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from ..config import settings
from ..database import get_db_connection, add_notification
from ..dependencies.auth import get_current_admin, verify_token
from ..utils.email_utils import send_email
from ..utils.file import allowed_file
from ..utils.time_utils import format_beijing_time
from ..logger import logger

router = APIRouter(prefix="/announcements", tags=["公告"])

MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024)


def _valid_status(value) -> str:
    value = value or "draft"
    if value not in ("draft", "published"):
        raise HTTPException(400, "status 必须为 draft 或 published")
    return value


def _resolve_admin_id(request: Request):
    """从 Authorization 头解析管理员 id（无/非法 → None）。"""
    token = request.headers.get('Authorization', '')
    if not token.startswith('Bearer '):
        return None
    payload = verify_token(token.replace('Bearer ', ''))
    if not payload:
        return None
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute('SELECT role FROM users WHERE id=?', (payload['user_id'],))
        u = cur.fetchone()
    return payload['user_id'] if u and u['role'] == 'admin' else None


def _push_published_announcement(ann_id: int, title: str, content: str):
    """发布公告 → 站内通知 + 邮件推送所有活跃用户（含管理员）。"""
    with get_db_connection() as conn:
        users = conn.cursor().execute(
            "SELECT id, username, email FROM users WHERE status = 'active'"
        ).fetchall()

    link = f"/announcements/{ann_id}"
    notif_title = f"校园公告：{title}"
    # 邮件/站内正文用纯文本摘要（富文本内容剥离标签）
    plain = re.sub(r"<[^>]+>", "", content or "").strip()
    summary = plain[:120] + ("…" if len(plain) > 120 else "")

    for u in users:
        try:
            add_notification(u["id"], notif_title, summary or "点击查看公告详情", link)
        except Exception as e:
            logger.error(f"公告站内通知失败 (用户 {u['id']}): {e}")
        if u["email"]:
            try:
                body = (
                    f'<div style="font-size:14px;color:#333;">'
                    f'<h2 style="color:#2c3e50;margin:0 0 12px;">{title}</h2>'
                    f'<div>{content}</div>'
                    f'<p style="margin-top:16px;">'
                    f'<a href="{settings.BASE_URL}{link}" '
                    f'style="display:inline-block;padding:10px 24px;background:#667eea;color:#fff;'
                    f'text-decoration:none;border-radius:8px;">查看公告详情</a></p></div>'
                )
                send_email(u["email"], f"【校园失物检索】校园公告：{title}", body, html=True)
            except Exception as e:
                logger.error(f"公告邮件推送失败 (用户 {u['id']}): {e}")


@router.get("")
async def list_announcements(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
    all: bool = Query(False, description="管理员传 all=true 看全部（含草稿）"),
):
    """公告列表（公开：仅已发布；管理端传 all=true 看全量含草稿；置顶优先、最新在前）"""
    can_see_all = bool(all and _resolve_admin_id(request))

    with get_db_connection() as conn:
        cur = conn.cursor()
        if can_see_all:
            cur.execute("SELECT COUNT(*) FROM announcements")
            total = cur.fetchone()[0]
            offset = (page - 1) * size
            cur.execute(
                "SELECT id, title, content, is_pinned, target_role, status, view_count, created_at "
                "FROM announcements ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?",
                (size, offset),
            )
        else:
            cur.execute(
                "SELECT COUNT(*) FROM announcements WHERE target_role IN ('all','user') AND status='published'"
            )
            total = cur.fetchone()[0]
            offset = (page - 1) * size
            cur.execute(
                "SELECT id, title, content, is_pinned, target_role, status, view_count, created_at "
                "FROM announcements WHERE target_role IN ('all','user') AND status='published' "
                "ORDER BY is_pinned DESC, created_at DESC LIMIT ? OFFSET ?",
                (size, offset),
            )
        items = [dict(r) for r in cur.fetchall()]

    for item in items:
        item["created_at"] = format_beijing_time(item.get("created_at"))
    return {"announcements": items, "total": total, "page": page, "size": size}


@router.get("/{ann_id:int}")
async def get_announcement(ann_id: int, request: Request):
    """公告详情（公开：仅已发布且面向用户/全部；管理员可见任意）；访问自增浏览数"""
    admin_id = _resolve_admin_id(request)

    with get_db_connection() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, title, content, is_pinned, target_role, status, view_count, created_at "
            "FROM announcements WHERE id=?",
            (ann_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "公告不存在")

        visible = bool(admin_id) or (
            row["status"] == "published" and row["target_role"] in ("all", "user")
        )
        if not visible:
            raise HTTPException(404, "公告不存在")

        # 可见即自增（不可见 404 不计数）；回读新值让响应包含本次访问
        cur.execute("UPDATE announcements SET view_count = view_count + 1 WHERE id=?", (ann_id,))
        cur.execute("SELECT view_count FROM announcements WHERE id=?", (ann_id,))
        row = dict(row)
        row["view_count"] = cur.fetchone()["view_count"]

    row["created_at"] = format_beijing_time(row.get("created_at"))
    return {"announcement": row}


@router.post("/upload")
async def upload_announcement_image(
    image: UploadFile = File(...),
    current_admin: dict = Depends(get_current_admin),
):
    """上传公告配图（富文本编辑器插图用；ann_ 前缀持久文件，复用 /items/uploads/ 静态路由）"""
    if not image or not image.filename:
        raise HTTPException(400, "请选择图片")
    content = await image.read()
    if not allowed_file(image.filename, content):
        raise HTTPException(400, "文件类型不支持")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE // 1024 // 1024}MB")

    ext = os.path.splitext(image.filename)[1][1:].lower()
    filename = f"ann_{uuid.uuid4().hex}.{ext}" if ext else f"ann_{uuid.uuid4().hex}"
    file_path = os.path.join(settings.UPLOAD_FOLDER, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"公告配图保存失败: {e}")
        raise HTTPException(500, "文件保存失败")

    return {"path": filename, "success": True}


@router.post("")
async def create_announcement(
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """新建公告（管理员；默认存为草稿，传 status='published' 直接发布并推送）"""
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
        ann_id = cur.lastrowid

    if status == "published":
        _push_published_announcement(ann_id, title, content)
    return {"success": True, "id": ann_id}


@router.put("/{ann_id}")
async def update_announcement(
    ann_id: int,
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """编辑公告（管理员；可同时改状态；仅编辑，不重复推送）"""
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
    """发布公告（草稿 → 已发布；首次发布时站内+邮件推送所有活跃用户）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT title, content, status FROM announcements WHERE id=?", (ann_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "公告不存在")
        was_published = row["status"] == "published"
        cur.execute("UPDATE announcements SET status='published' WHERE id=?", (ann_id,))

    if not was_published:
        _push_published_announcement(ann_id, row["title"], row["content"])
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
