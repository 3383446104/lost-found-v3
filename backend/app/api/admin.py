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

    # 使用分页响应模型
    return PagedResponse(
        total=total,
        page=page,
        size=size,
        items=items
    )


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

    # 若审核通过，将匹配通知放入后台任务（避免阻塞）
    if new_status == ReviewStatus.APPROVED.value:
        background_tasks.add_task(auto_match_and_notify, item_id, row["type"])

    return ReviewResponse(
        success=True,
        message=f"审核成功，状态变为 {new_status}",
        data={"status": new_status},
    )