# app/api/admin.py
import logging
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field, model_validator

from ..database import get_db_connection
from ..dependencies.auth import get_current_admin
from ..services.match_service import auto_match_and_notify
from ..utils.time_utils import format_beijing_time
from ..models.common import PagedResponse   # 新增导入


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["管理员"])


# ---------- 枚举与请求模型 ----------
class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewAction(BaseModel):
    action: ReviewStatus
    reason: Optional[str] = Field(None, max_length=200, description="驳回理由（驳回时必填）")

    @model_validator(mode='after')
    def require_reason_for_reject(self):
        if self.action == ReviewStatus.REJECTED and not self.reason:
            raise ValueError('驳回时必须填写驳回理由')
        return self


class ReviewResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


# ---------- 接口实现 ----------
@router.get("/reviews")
async def get_pending_items(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    current_admin: dict = Depends(get_current_admin),
):
    """分页获取待审核物品列表（仅返回必要字段，隐藏联系方式等敏感信息）"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        offset = (page - 1) * size

        # 查询总数
        cursor.execute(
            "SELECT COUNT(*) AS total FROM items WHERE review_status = ?",
            (ReviewStatus.PENDING.value,),
        )
        total = cursor.fetchone()["total"]

        # 分页查询（不返回 contact 和 user_id）
        cursor.execute(
            """
            SELECT id, type, title, description, category, image_path,
                   location, created_at
            FROM items
            WHERE review_status = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (ReviewStatus.PENDING.value, size, offset),
        )
        items = [dict(row) for row in cursor.fetchall()]

    # 时间格式化
    for item in items:
        item["created_at"] = format_beijing_time(item.get("created_at"))

    # 返回分页数据
    return {"total": total, "page": page, "size": size, "items": items}


# ---------- 批量审核 ----------
@router.post("/reviews/batch-approve")
async def batch_approve_items(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_current_admin),
):
    """批量审核通过（驳回不支持批量，需逐一填写理由）"""
    item_ids = payload.get("item_ids", [])
    if not item_ids:
        raise HTTPException(400, "请提供要审核的物品 ID 列表")
    if len(item_ids) > 50:
        raise HTTPException(400, "单次最多批量审核 50 条")

    approved = 0
    failed = []

    for item_id in item_ids:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT type, review_status FROM items WHERE id = ?", (item_id,)
                )
                row = cursor.fetchone()
                if not row or row["review_status"] != "pending":
                    failed.append(item_id)
                    continue

                cursor.execute(
                    """UPDATE items
                       SET review_status = 'approved',
                           reviewer_id = ?,
                           review_time = CURRENT_TIMESTAMP,
                           status = 'active'
                       WHERE id = ? AND review_status = 'pending'""",
                    (current_admin["user_id"], item_id),
                )

                if cursor.rowcount == 0:
                    failed.append(item_id)
                    continue

                approved += 1
                background_tasks.add_task(auto_match_and_notify, item_id, row["type"])
        except Exception:
            failed.append(item_id)

    logger.info(
        f"管理员 {current_admin['user_id']} 批量审核通过 {approved} 件，失败 {len(failed)} 件"
    )
    return {
        "success": True,
        "message": f"已批量通过 {approved} 件物品",
        "approved_count": approved,
        "failed_ids": failed,
    }


@router.put("/reviews/{item_id}")
async def review_item(
    item_id: int,
    payload: ReviewAction,
    background_tasks: BackgroundTasks,
    current_admin: dict = Depends(get_current_admin),
):
    """
    审核物品（通过/驳回）
    - 使用条件更新防止并发重复审核
    - 通过后异步执行匹配通知（避免阻塞响应）
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 先查询物品类型（用于后续匹配），同时检查是否存在
        cursor.execute(
            "SELECT type, review_status FROM items WHERE id = ?", (item_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(404, "物品不存在")

        if row["review_status"] != ReviewStatus.PENDING.value:
            raise HTTPException(400, "该物品已审核，不可重复操作")

        # 计算新状态
        new_status = (
            ReviewStatus.APPROVED.value
            if payload.action == ReviewStatus.APPROVED
            else ReviewStatus.REJECTED.value
        )

        # 在 UPDATE 语句中增加 status 列
        cursor.execute(
            """
            UPDATE items
            SET review_status = ?,
                reviewer_id = ?,
                review_time = CURRENT_TIMESTAMP,
                reject_reason = ?,
                status = CASE
                            WHEN ? = 'approved' THEN 'active'
                            WHEN ? = 'rejected' THEN 'rejected'
                            ELSE status
                         END
            WHERE id = ? AND review_status = ?
            """,
            (
                new_status,
                current_admin["user_id"],
                payload.reason,
                new_status,
                new_status,
                item_id,
                ReviewStatus.PENDING.value,
            ),
        )

        if cursor.rowcount == 0:
            # 状态已被其他管理员修改
            raise HTTPException(409, "审核冲突，请刷新后重试")

        # 记录审计日志（在事务内）
        logger.info(
            f"管理员 {current_admin['user_id']} 对物品 {item_id} 执行 {new_status}，"
            f"驳回理由: {payload.reason}"
        )

    # 通过：异步匹配通知
    if new_status == ReviewStatus.APPROVED.value:
        background_tasks.add_task(auto_match_and_notify, item_id, row["type"])

    # 驳回：站内通知 + 邮件
    if new_status == ReviewStatus.REJECTED.value:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute('SELECT user_id, title, email, username FROM items JOIN users ON items.user_id=users.id WHERE items.id=?', (item_id,))
            item_info = cur.fetchone()
            if item_info:
                notif_title = f"[审核驳回] 您的物品 '{item_info['title']}' 未通过审核"
                notif_content = f"驳回理由：{payload.reason or '未填写'}"
                cur.execute(
                    'INSERT INTO notifications (user_id, title, content, link) VALUES (?,?,?,?)',
                    (item_info['user_id'], notif_title, notif_content, f"/items/{item_id}")
                )
                # 邮件通知
                if item_info['email']:
                    try:
                        from ..utils.email_utils import send_email
                        body = f"""<html><body style="font-family:Arial,sans-serif;padding:20px;background:#f4f7fc;">
                        <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:30px;box-shadow:0 4px 12px rgba(0,0,0,0.05);">
                        <h2 style="color:#D32F2F;">审核结果通知</h2>
                        <p>亲爱的 <strong>{item_info['username']}</strong>：</p>
                        <p>您发布的物品 <strong>"{item_info['title']}"</strong> 未通过审核。</p>
                        <p><strong>驳回理由：</strong>{payload.reason or '未填写'}</p>
                        <p>物品已退回草稿箱，您可以在发布页面重新编辑后提交。</p>
                        <p style="margin:24px 0;"><a href="{settings.BASE_URL}/publish?edit={item_id}" style="display:inline-block;padding:10px 24px;background:#D32F2F;color:#fff;text-decoration:none;border-radius:8px;">重新编辑</a></p>
                        </div></body></html>"""
                        send_email(item_info['email'], f"【失物寻回】您的物品 '{item_info['title']}' 未通过审核", body, html=True)
                    except Exception as e:
                        logger.warning(f"驳回邮件发送失败: {e}")

    return ReviewResponse(
        success=True,
        message=f"审核成功，状态变为 {new_status}",
        data={"status": new_status},
    )


# ---------- 用户管理 ----------
@router.get("/users")
async def get_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_admin: dict = Depends(get_current_admin),
):
    """管理员查看用户列表"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as total FROM users")
        total = cur.fetchone()["total"]
        offset = (page - 1) * size
        cur.execute(
            "SELECT id, username, role, phone, email, created_at FROM users ORDER BY id DESC LIMIT ? OFFSET ?",
            (size, offset)
        )
        users = [dict(r) for r in cur.fetchall()]
    return {"total": total, "page": page, "size": size, "users": users}


@router.put("/users/{user_id}")
async def update_user(
    user_id: int,
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """管理员修改用户角色或禁用"""
    action = payload.get("action")
    if action not in ("set_role", "toggle_status"):
        raise HTTPException(400, "action 必须为 set_role 或 toggle_status")

    with get_db_connection() as conn:
        cur = conn.cursor()
        if action == "set_role":
            role = payload.get("role", "user")
            if role not in ("user", "admin"):
                raise HTTPException(400, "role 必须为 user 或 admin")
            cur.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        elif action == "toggle_status":
            cur.execute("SELECT role FROM users WHERE id=?", (user_id,))
            u = cur.fetchone()
            if not u:
                raise HTTPException(404, "用户不存在")
            new_role = "user" if u["role"] == "disabled" else "disabled"
            cur.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "用户不存在")
    return {"success": True, "message": "操作成功"}


@router.post("/users")
async def create_user(
    payload: dict,
    current_admin: dict = Depends(get_current_admin),
):
    """管理员新增用户"""
    username = payload.get("username", "").strip()
    password = payload.get("password", "").strip()
    if len(username) < 2 or len(username) > 20:
        raise HTTPException(400, "用户名长度 2-20 位")
    if len(password) < 6 or len(password) > 30:
        raise HTTPException(400, "密码长度 6-30 位")
    role = payload.get("role", "user")
    if role not in ("user", "admin"):
        raise HTTPException(400, "role 必须为 user 或 admin")

    import bcrypt
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, phone, email, role) VALUES (?,?,?,?,?)",
                (username, password_hash, payload.get("phone", ""), payload.get("email", ""), role)
            )
            user_id = cur.lastrowid
        except Exception:
            raise HTTPException(400, "用户名已存在")
    return {"success": True, "user": {"id": user_id, "username": username, "role": role}}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_admin: dict = Depends(get_current_admin),
):
    """管理员删除用户（软删除）"""
    if user_id == current_admin["user_id"]:
        raise HTTPException(400, "不能删除自己")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
        u = cur.fetchone()
        if not u:
            raise HTTPException(404, "用户不存在")
        if u["username"].endswith("_deleted_" + str(user_id)):
            raise HTTPException(400, "用户已删除")

        cur.execute("UPDATE items SET status='closed' WHERE user_id=? AND status IN ('active','pending')", (user_id,))
        cur.execute(
            "UPDATE users SET username=username || '_deleted_' || id, role='deleted' WHERE id=?",
            (user_id,)
        )
    return {"success": True, "message": f"用户 {u['username']} 已删除"}