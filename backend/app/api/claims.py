# app/api/claims.py
# 认领闭环（v3.6.0 融合：双向审批 + 防冒领特征核验 + 互斥 + 可撤销 + 状态联动）
#
# 设计要点（移植自参考项目 campus-lost-and-found-ai 的认领闭环）：
# - claim.status: 0待审核 / 1已通过 / 2已拒绝 / 3已完成 / 4已撤销
# - 申请时需填物品特征描述（防冒领核验依据）+ 可选证明图片（限 1 张）
# - 发布者审批：同意时**同一事务**内自动拒绝同物品其他待审核申请（互斥），
#   物品 status active → claiming（认领中，公共列表自动不可见）
# - 确认归还：物品 claiming → claimed，计入 total_claimed 计数器
# - 申请人可撤销待审核申请；被拒绝/已撤销后可重新申请
import os
import uuid
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field

from ..config import settings
from ..database import get_db_connection, increment_counter
from ..dependencies.auth import get_current_user
from ..services.notification_service import send_notification
from ..utils.file import allowed_file
from ..utils.time_utils import format_beijing_time
from ..logger import logger


router = APIRouter(prefix="/claims", tags=["认领"])

MAX_UPLOAD_SIZE = getattr(settings, "MAX_UPLOAD_SIZE", 5 * 1024 * 1024)

# claim.status 枚举（与数据库注释一致）
CLAIM_PENDING = 0
CLAIM_APPROVED = 1
CLAIM_REJECTED = 2
CLAIM_COMPLETED = 3
CLAIM_CANCELLED = 4

# 互斥自动拒绝时写入的系统文案
AUTO_REJECT_REMARK = "已有其他申请通过，系统自动拒绝"


# ---------- 请求模型 ----------
class ClaimCreate(BaseModel):
    item_id: int
    claim_reason: Optional[str] = Field(None, max_length=500, description="认领说明")
    feature_description: Optional[str] = Field(None, max_length=200, description="物品特征描述（防冒领核验依据）")
    contact_phone: Optional[str] = Field(None, max_length=20, description="联系电话（缺省取用户资料电话）")
    proof_image: Optional[str] = Field(None, max_length=255, description="证明图片文件名（proof_ 前缀）")


class ClaimReject(BaseModel):
    review_remark: str = Field(..., min_length=1, max_length=200, description="拒绝理由（必填）")


# ---------- 辅助函数 ----------


def _claim_row_to_dict(row, *, time_fields=("created_at", "reviewed_at", "completed_at")) -> dict:
    d = dict(row)
    for f in time_fields:
        if f in d:
            d[f] = format_beijing_time(d.get(f))
    return d


def _item_action_word(item_type: str) -> str:
    """lost=失物(发布者丢了东西)→别人捡到要「归还」；found=拾物→别人来「认领」。"""
    return "归还" if item_type == "lost" else "认领"


# ---------- 接口 ----------
@router.post("/proof-upload")
async def proof_upload(
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """上传认领证明图片（持久存储；**不可复用 /items/temp-upload**，temp_ 文件会被匹配流程删除）"""
    if not image or not image.filename:
        raise HTTPException(400, "请选择图片")
    content = await image.read()
    if not allowed_file(image.filename, content):
        raise HTTPException(400, "文件类型不支持")
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, f"图片大小不能超过 {MAX_UPLOAD_SIZE//1024//1024}MB")

    ext = os.path.splitext(image.filename)[1][1:].lower()
    filename = f"proof_{uuid.uuid4().hex}.{ext}" if ext else f"proof_{uuid.uuid4().hex}"
    file_path = os.path.join(settings.UPLOAD_FOLDER, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"证明图保存失败: {e}")
        raise HTTPException(500, "文件保存失败")

    return {"path": filename, "success": True}


@router.post("", status_code=201)
async def create_claim(
    payload: ClaimCreate,
    current_user: dict = Depends(get_current_user)
):
    """申请认领/归还物品（含防冒领特征描述与证明图；通知+邮件给发布者）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, title, status, review_status, type FROM items WHERE id = ?",
            (payload.item_id,),
        )
        item = cur.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")
        if item["user_id"] == user_id:
            raise HTTPException(400, "不能申请自己的物品")
        if item["status"] != "active" or item["review_status"] != "approved":
            raise HTTPException(400, "该物品当前不可申请")

        # 防重：同一申请人同一物品已有待审核/已通过的申请
        cur.execute(
            "SELECT id FROM claims WHERE claimer_id=? AND item_id=? AND status IN (0, 1)",
            (user_id, payload.item_id),
        )
        if cur.fetchone():
            raise HTTPException(400, "已发送申请，请等待回复")

        # 电话快照：优先请求体，缺省取用户资料
        contact_phone = (payload.contact_phone or "").strip() or None
        if not contact_phone:
            cur.execute("SELECT phone FROM users WHERE id=?", (user_id,))
            u = cur.fetchone()
            contact_phone = u["phone"] if u else None

        cur.execute(
            """INSERT INTO claims (item_id, claimer_id, claim_reason, feature_description,
                                   proof_image, contact_phone, status)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (payload.item_id, user_id, payload.claim_reason,
             payload.feature_description, payload.proof_image, contact_phone),
        )
        claim_id = cur.lastrowid

        # 发布者与申请人信息（通知文案用）
        cur.execute("SELECT username, phone FROM users WHERE id=?", (user_id,))
        claimer = cur.fetchone()
        cur.execute("SELECT username, email FROM users WHERE id=?", (item["user_id"],))
        owner = cur.fetchone()

    action_word = _item_action_word(item["type"])
    title = f"[{action_word}申请] 用户 '{claimer['username']}' 想要{action_word}您的物品"
    content_lines = [f"物品 '{item['title']}' 收到{action_word}申请。"]
    if payload.feature_description:
        content_lines.append(f"申请人描述物品特征：{payload.feature_description}")
    content_lines.append(f"申请人联系方式：{contact_phone or '未填写'}。请及时处理。")
    content = "".join(content_lines)

    # 站内 + 邮件双发（send_notification 内部已捕获邮件异常）
    send_notification(
        item["user_id"], title, content,
        link=f"/claims/received",
        email=owner["email"] if owner else None,
    )

    logger.info(f"用户 {user_id} 对物品 {payload.item_id} 发起认领申请 {claim_id}")
    return {"success": True, "id": claim_id, "message": f"{action_word}申请已发送，请等待物品发布者确认"}


@router.get("/mine")
async def my_claims(
    status: Optional[int] = Query(None, ge=0, le=4, description="按状态过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """我的认领申请（联查物品信息）"""
    user_id = current_user["user_id"]
    where = "WHERE c.claimer_id = ?"
    params: List = [user_id]
    if status is not None:
        where += " AND c.status = ?"
        params.append(status)

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) AS total FROM claims c {where}", params)
        total = cur.fetchone()["total"]
        offset = (page - 1) * size
        cur.execute(
            f"""SELECT c.id, c.item_id, c.status, c.claim_reason, c.feature_description,
                       c.proof_image, c.contact_phone, c.review_remark, c.reviewed_at,
                       c.completed_at, c.created_at,
                       i.title, i.type, i.image_path, i.status AS item_status
                FROM claims c JOIN items i ON c.item_id = i.id
                {where}
                ORDER BY c.created_at DESC, c.id DESC
                LIMIT ? OFFSET ?""",
            params + [size, offset],
        )
        claims = [_claim_row_to_dict(r) for r in cur.fetchall()]

    return {"total": total, "page": page, "size": size, "claims": claims}


@router.get("/received")
async def received_claims(
    status: Optional[int] = Query(None, ge=0, le=4, description="按状态过滤"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """我发布物品收到的认领申请（联查申请人）"""
    user_id = current_user["user_id"]
    where = "WHERE i.user_id = ?"
    params: List = [user_id]
    if status is not None:
        where += " AND c.status = ?"
        params.append(status)

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT COUNT(*) AS total
                FROM claims c JOIN items i ON c.item_id = i.id
                {where}""",
            params,
        )
        total = cur.fetchone()["total"]
        offset = (page - 1) * size
        cur.execute(
            f"""SELECT c.id, c.item_id, c.claimer_id, c.status, c.claim_reason,
                       c.feature_description, c.proof_image, c.contact_phone,
                       c.review_remark, c.reviewed_at, c.completed_at, c.created_at,
                       i.title, i.type, i.image_path, i.status AS item_status,
                       u.username AS claimer_username
                FROM claims c
                JOIN items i ON c.item_id = i.id
                JOIN users u ON c.claimer_id = u.id
                {where}
                ORDER BY c.created_at DESC, c.id DESC
                LIMIT ? OFFSET ?""",
            params + [size, offset],
        )
        claims = [_claim_row_to_dict(r) for r in cur.fetchall()]

    return {"total": total, "page": page, "size": size, "claims": claims}


@router.get("/status/{item_id:int}")
async def claim_status(
    item_id: int,
    current_user: dict = Depends(get_current_user)
):
    """当前用户对该物品的最近一次申请状态（详情页按钮态用）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT id, status, reviewed_at, review_remark
               FROM claims WHERE item_id=? AND claimer_id=?
               ORDER BY id DESC LIMIT 1""",
            (item_id, current_user["user_id"]),
        )
        row = cur.fetchone()
    if not row:
        return {"claim": None}
    return {"claim": _claim_row_to_dict(row)}


@router.get("/{claim_id:int}")
async def get_claim(
    claim_id: int,
    current_user: dict = Depends(get_current_user)
):
    """认领申请详情（申请人/发布者/管理员三方可见）

    隐私规则（分级可见）：
    - 申请人：status ∈ (1, 3) 时可见发布者**完整**联系方式（item.contact），此前为 null；
    - 发布者/管理员：可见申请人完整电话（contact_phone 快照）。
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.*, i.title, i.type, i.image_path, i.contact, i.user_id AS owner_id,
                      i.status AS item_status
               FROM claims c JOIN items i ON c.item_id = i.id
               WHERE c.id = ?""",
            (claim_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")

        cur.execute("SELECT role FROM users WHERE id=?", (current_user["user_id"],))
        u = cur.fetchone()
        is_admin = bool(u and u["role"] == "admin")
        is_owner = row["owner_id"] == current_user["user_id"]
        is_claimer = row["claimer_id"] == current_user["user_id"]
        if not (is_admin or is_owner or is_claimer):
            raise HTTPException(403, "无权查看该申请")

    result = _claim_row_to_dict(row)
    result["item"] = {
        "id": row["item_id"],
        "title": row["title"],
        "type": row["type"],
        "image_path": row["image_path"],
        "status": row["item_status"],
    }

    # 隐私裁剪
    if is_claimer:
        # 申请人视角：申请通过/完成后可见发布者**完整**联系方式（用于线下交接）
        if row["status"] in (CLAIM_APPROVED, CLAIM_COMPLETED):
            result["owner_contact"] = row["contact"]
        else:
            result["owner_contact"] = None
        result.pop("contact_phone", None)
    elif is_owner or is_admin:
        result["owner_contact"] = None  # 本人当然知道自己的联系方式
    result.pop("contact", None)

    return {"claim": result}


# ---------- 审批动作 ----------
@router.post("/{claim_id:int}/approve")
async def approve_claim(
    claim_id: int,
    current_user: dict = Depends(get_current_user)
):
    """发布者同意认领申请（同一事务内互斥拒绝其他待审核申请 + 物品置「认领中」）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.id, c.item_id, c.claimer_id, c.status,
                      i.user_id AS owner_id, i.status AS item_status, i.title, i.type
               FROM claims c JOIN items i ON c.item_id = i.id
               WHERE c.id = ?""",
            (claim_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")

        cur.execute("SELECT role FROM users WHERE id=?", (user_id,))
        u = cur.fetchone()
        if row["owner_id"] != user_id and not (u and u["role"] == "admin"):
            raise HTTPException(403, "仅物品发布者可审批")
        if row["status"] != CLAIM_PENDING:
            raise HTTPException(400, "该申请已处理，不可重复操作")
        if row["item_status"] != "active":
            raise HTTPException(400, "该物品已处理或不可操作")

        # 抢占式更新：rowcount 防止并发重复审批
        cur.execute(
            "UPDATE claims SET status=1, review_remark=NULL, reviewed_at=CURRENT_TIMESTAMP,"
            " updated_at=CURRENT_TIMESTAMP WHERE id=? AND status=0",
            (claim_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "申请状态已被修改，请刷新后重试")

        # 互斥：同物品其他待审核申请自动拒绝（同一事务）
        cur.execute(
            """UPDATE claims SET status=2, review_remark=?, reviewed_at=CURRENT_TIMESTAMP,
               updated_at=CURRENT_TIMESTAMP WHERE item_id=? AND status=0 AND id<>?""",
            (AUTO_REJECT_REMARK, row["item_id"], claim_id),
        )

        # 物品 → 认领中
        cur.execute(
            "UPDATE items SET status='claiming' WHERE id=? AND status='active'",
            (row["item_id"],),
        )

        # 申请人信息（通知用）
        cur.execute("SELECT email FROM users WHERE id=?", (row["claimer_id"],))
        claimer = cur.fetchone()

    action_word = _item_action_word(row["type"])
    send_notification(
        row["claimer_id"],
        f"[{action_word}通过] 您的{action_word}申请已通过",
        f"物品 '{row['title']}' 的发布者已同意您的{action_word}申请，请查看详情页获取联系方式并尽快完成交接。",
        link=f"/items/{row['item_id']}",
        email=claimer["email"] if claimer else None,
    )

    logger.info(f"用户 {user_id} 通过了认领申请 {claim_id}，物品 {row['item_id']} 进入认领中")
    return {"success": True, "message": "已同意申请，物品进入认领中", "item_status": "claiming"}


@router.post("/{claim_id:int}/reject")
async def reject_claim(
    claim_id: int,
    payload: ClaimReject,
    current_user: dict = Depends(get_current_user)
):
    """发布者拒绝认领申请（拒绝理由必填）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.id, c.item_id, c.claimer_id, c.status,
                      i.user_id AS owner_id, i.title, i.type
               FROM claims c JOIN items i ON c.item_id = i.id
               WHERE c.id = ?""",
            (claim_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")

        cur.execute("SELECT role FROM users WHERE id=?", (user_id,))
        u = cur.fetchone()
        if row["owner_id"] != user_id and not (u and u["role"] == "admin"):
            raise HTTPException(403, "仅物品发布者可审批")
        if row["status"] != CLAIM_PENDING:
            raise HTTPException(400, "该申请已处理，不可重复操作")

        cur.execute(
            "UPDATE claims SET status=2, review_remark=?, reviewed_at=CURRENT_TIMESTAMP,"
            " updated_at=CURRENT_TIMESTAMP WHERE id=? AND status=0",
            (payload.review_remark, claim_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "申请状态已被修改，请刷新后重试")

        cur.execute("SELECT email FROM users WHERE id=?", (row["claimer_id"],))
        claimer = cur.fetchone()

    action_word = _item_action_word(row["type"])
    send_notification(
        row["claimer_id"],
        f"[{action_word}被拒绝] 您的{action_word}申请未通过",
        f"物品 '{row['title']}' 的发布者拒绝了您的{action_word}申请。拒绝理由：{payload.review_remark}",
        link=f"/items/{row['item_id']}",
        email=claimer["email"] if claimer else None,
    )

    logger.info(f"用户 {user_id} 拒绝了认领申请 {claim_id}")
    return {"success": True, "message": "已拒绝该申请"}


@router.post("/{claim_id:int}/complete")
async def complete_claim(
    claim_id: int,
    current_user: dict = Depends(get_current_user)
):
    """发布者确认归还完成（物品 → claimed，计入找回计数器）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.id, c.item_id, c.claimer_id, c.status,
                      i.user_id AS owner_id, i.status AS item_status, i.title, i.type
               FROM claims c JOIN items i ON c.item_id = i.id
               WHERE c.id = ?""",
            (claim_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")

        cur.execute("SELECT role FROM users WHERE id=?", (user_id,))
        u = cur.fetchone()
        if row["owner_id"] != user_id and not (u and u["role"] == "admin"):
            raise HTTPException(403, "仅物品发布者可操作")
        if row["status"] != CLAIM_APPROVED:
            raise HTTPException(400, "仅已通过的申请可确认归还")
        if row["item_status"] != "claiming":
            raise HTTPException(400, "该物品当前不在认领中状态")

        cur.execute(
            "UPDATE claims SET status=3, completed_at=CURRENT_TIMESTAMP,"
            " updated_at=CURRENT_TIMESTAMP WHERE id=? AND status=1",
            (claim_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "申请状态已被修改，请刷新后重试")

        cur.execute(
            "UPDATE items SET status='claimed' WHERE id=? AND status='claiming'",
            (row["item_id"],),
        )
        cur.execute("SELECT email FROM users WHERE id=?", (row["claimer_id"],))
        claimer = cur.fetchone()

    # 计数器 +1（事务已提交后）
    increment_counter("total_claimed", 1)

    action_label = "已找回" if row["type"] == "lost" else "已归还"
    send_notification(
        row["claimer_id"],
        f"[{action_label}] 交接完成",
        f"物品 '{row['title']}' 已完成交接，感谢您的配合！",
        link=f"/items/{row['item_id']}",
        email=claimer["email"] if claimer else None,
    )

    logger.info(f"用户 {user_id} 确认认领申请 {claim_id} 完成，物品 {row['item_id']} 已{action_label}")
    return {"success": True, "message": f"物品已标记为{action_label}", "new_status": "claimed"}


@router.post("/{claim_id:int}/cancel")
async def cancel_claim(
    claim_id: int,
    current_user: dict = Depends(get_current_user)
):
    """申请人撤销待审核申请（物品保持 active，可重新申请）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT c.id, c.item_id, c.claimer_id, c.status, i.user_id AS owner_id, i.title, i.type
               FROM claims c JOIN items i ON c.item_id = i.id
               WHERE c.id = ?""",
            (claim_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "申请不存在")

        if row["claimer_id"] != user_id:
            raise HTTPException(403, "仅申请人可撤销")
        if row["status"] != CLAIM_PENDING:
            raise HTTPException(400, "仅待审核的申请可撤销")

        cur.execute(
            "UPDATE claims SET status=4, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status=0",
            (claim_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "申请状态已被修改，请刷新后重试")

    action_word = _item_action_word(row["type"])
    send_notification(
        row["owner_id"],
        f"[{action_word}申请已撤销]",
        f"物品 '{row['title']}' 的一条{action_word}申请已被申请人撤销。",
        link=f"/claims/received",
    )

    logger.info(f"用户 {user_id} 撤销了认领申请 {claim_id}")
    return {"success": True, "message": "申请已撤销"}
