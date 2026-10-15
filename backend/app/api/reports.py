# app/api/reports.py
# 举报体系（v3.6.0 融合：五类举报 + 处理留痕 + 举报人进度可见）
#
# 设计要点（移植自参考项目 campus-lost-and-found-ai）：
# - report_type: 1虚假信息 / 2不良内容 / 3联系方式异常 / 4重复发布 / 5其他
# - handle_status: 0待处理 / 1已处理 / 2已驳回
# - 处理时必填结论，记录处理人 + 时间；举报人可在「我的举报」跟踪进度
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import get_db_connection
from ..dependencies.auth import get_current_user, get_current_admin
from ..services.notification_service import send_notification
from ..utils.time_utils import format_beijing_time
from ..logger import logger


router = APIRouter(prefix="/reports", tags=["举报"])

REPORT_TYPES = {1: "虚假信息", 2: "不良内容", 3: "联系方式异常", 4: "重复发布", 5: "其他"}
HANDLE_STATUSES = {0: "待处理", 1: "已处理", 2: "已驳回"}


# ---------- 请求模型 ----------
class ReportCreate(BaseModel):
    item_id: int
    report_type: int = Field(..., ge=1, le=5, description="举报类型 1-5")
    report_reason: str = Field(..., min_length=1, max_length=500, description="举报原因（必填）")
    report_image: Optional[str] = Field(None, max_length=255, description="举报截图文件名（可选）")


class ReportHandle(BaseModel):
    handle_status: int = Field(..., ge=1, le=2, description="1已处理 / 2已驳回")
    handle_result: str = Field(..., min_length=1, max_length=500, description="处理结论（必填）")


# ---------- 辅助函数 ----------
def _fmt(row: dict) -> dict:
    for f in ("created_at", "handle_time"):
        if f in row:
            row[f] = format_beijing_time(row.get(f))
    return row


def _notify_reporter(reporter_id: int, item_title: str, handle_status: int, handle_result: str):
    label = "处理完成" if handle_status == 1 else "已驳回"
    send_notification(
        reporter_id,
        f"[举报{label}] 您举报的物品已处理",
        f"您举报的物品 '{item_title}' 处理结果：{HANDLE_STATUSES[handle_status]}。"
        f"处理结论：{handle_result}",
        link="/reports/mine",
    )


# ---------- 接口 ----------
@router.post("", status_code=201)
async def create_report(
    payload: ReportCreate,
    current_user: dict = Depends(get_current_user)
):
    """提交举报（同一人对同一物品有未处理举报时拦截）"""
    user_id = current_user["user_id"]

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title FROM items WHERE id=?", (payload.item_id,))
        item = cur.fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")

        cur.execute(
            "SELECT id FROM reports WHERE reporter_id=? AND item_id=? AND handle_status=0",
            (user_id, payload.item_id),
        )
        if cur.fetchone():
            raise HTTPException(400, "您已举报该物品，请等待处理")

        cur.execute(
            """INSERT INTO reports (item_id, reporter_id, report_type, report_reason,
                                    report_image, handle_status)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (payload.item_id, user_id, payload.report_type,
             payload.report_reason, payload.report_image),
        )
        report_id = cur.lastrowid

    logger.info(f"用户 {user_id} 举报了物品 {payload.item_id}（类型 {payload.report_type}），举报编号 {report_id}")
    return {"success": True, "id": report_id, "message": "举报已提交，管理员将尽快处理"}


@router.get("/mine")
async def my_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """我的举报（含处理进度与结论）"""
    user_id = current_user["user_id"]
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) AS total FROM reports WHERE reporter_id=?", (user_id,)
        )
        total = cur.fetchone()["total"]
        offset = (page - 1) * size
        cur.execute(
            """SELECT r.id, r.item_id, r.report_type, r.report_reason, r.handle_status,
                      r.handle_result, r.handle_time, r.created_at, i.title AS item_title
               FROM reports r JOIN items i ON r.item_id = i.id
               WHERE r.reporter_id = ?
               ORDER BY r.created_at DESC, r.id DESC
               LIMIT ? OFFSET ?""",
            (user_id, size, offset),
        )
        reports = [_fmt(dict(r)) for r in cur.fetchall()]

    return {"total": total, "page": page, "size": size, "reports": reports}


@router.get("/admin")
async def admin_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="搜索物品标题/举报原因/举报人"),
    report_type: Optional[int] = Query(None, ge=1, le=5),
    handle_status: Optional[int] = Query(None, ge=0, le=2),
    current_admin: dict = Depends(get_current_admin)
):
    """管理端举报列表（分页 + 筛选）"""
    where = ["1=1"]
    params: list = []
    if keyword:
        where.append("(i.title LIKE ? OR r.report_reason LIKE ? OR u.username LIKE ?)")
        params.extend([f"%{keyword}%"] * 3)
    if report_type is not None:
        where.append("r.report_type = ?")
        params.append(report_type)
    if handle_status is not None:
        where.append("r.handle_status = ?")
        params.append(handle_status)
    w = " AND ".join(where)

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""SELECT COUNT(*) AS total
                FROM reports r JOIN items i ON r.item_id = i.id
                JOIN users u ON r.reporter_id = u.id
                WHERE {w}""",
            params,
        )
        total = cur.fetchone()["total"]
        offset = (page - 1) * size
        cur.execute(
            f"""SELECT r.id, r.item_id, r.report_type, r.report_reason, r.handle_status,
                      r.handle_result, r.handle_time, r.created_at,
                      i.title AS item_title, u.username AS reporter_username,
                      h.username AS handler_username
               FROM reports r
               JOIN items i ON r.item_id = i.id
               JOIN users u ON r.reporter_id = u.id
               LEFT JOIN users h ON r.handler_id = h.id
               WHERE {w}
               ORDER BY (r.handle_status = 0) DESC, r.created_at DESC, r.id DESC
               LIMIT ? OFFSET ?""",
            params + [size, offset],
        )
        reports = [_fmt(dict(r)) for r in cur.fetchall()]

    return {"total": total, "page": page, "size": size, "reports": reports}


@router.get("/admin/{report_id:int}")
async def admin_report_detail(
    report_id: int,
    current_admin: dict = Depends(get_current_admin)
):
    """举报详情（并排数据包：举报全字段 + 被举报物品快照，供管理员核对后处理）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT r.*, u.username AS reporter_username, h.username AS handler_username
               FROM reports r
               JOIN users u ON r.reporter_id = u.id
               LEFT JOIN users h ON r.handler_id = h.id
               WHERE r.id = ?""",
            (report_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "举报不存在")

        cur.execute(
            """SELECT id, type, title, description, category, location, contact,
                      image_path, images, cover_image, status, review_status, created_at
               FROM items WHERE id = ?""",
            (row["item_id"],),
        )
        item = cur.fetchone()

    report = _fmt(dict(row))
    item_snapshot = dict(item) if item else None
    if item_snapshot:
        item_snapshot["created_at"] = format_beijing_time(item_snapshot.get("created_at"))

    return {"report": report, "item": item_snapshot}


@router.put("/admin/{report_id:int}/handle")
async def handle_report(
    report_id: int,
    payload: ReportHandle,
    current_admin: dict = Depends(get_current_admin)
):
    """处理举报（写处理结论 + 处理人 + 时间；通知举报人）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT r.id, r.item_id, r.reporter_id, r.handle_status, i.title
               FROM reports r JOIN items i ON r.item_id = i.id
               WHERE r.id = ?""",
            (report_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "举报不存在")
        if row["handle_status"] != 0:
            raise HTTPException(400, "该举报已处理，不可重复操作")

        cur.execute(
            """UPDATE reports SET handle_status=?, handle_result=?, handler_id=?,
               handle_time=CURRENT_TIMESTAMP
               WHERE id=? AND handle_status=0""",
            (payload.handle_status, payload.handle_result,
             current_admin["user_id"], report_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "举报状态已被修改，请刷新后重试")

    # 通知举报人（站内 + 邮件）
    _notify_reporter(row["reporter_id"], row["title"], payload.handle_status, payload.handle_result)

    logger.info(
        f"管理员 {current_admin['user_id']} 处理举报 {report_id}："
        f"状态 {payload.handle_status}，结论 {payload.handle_result}"
    )
    return {"success": True, "message": "处理完成"}
