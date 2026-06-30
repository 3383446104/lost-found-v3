# app/api/notifications.py
from fastapi import APIRouter, Depends, HTTPException, status
from ..database import get_db_connection, get_unread_count, get_unread_notifications, mark_notification_read
from ..dependencies.auth import get_current_user
from ..utils.time_utils import format_beijing_time

router = APIRouter(prefix="/notifications", tags=["消息通知"])


@router.get("/unread/count")
async def unread_count(current_user: dict = Depends(get_current_user)):
    """获取未读消息数量"""
    count = get_unread_count(current_user['user_id'])
    return {"count": count}


@router.get("/unread")
async def unread_list(current_user: dict = Depends(get_current_user)):
    """获取未读消息列表"""
    user_id = current_user['user_id']
    notifications = get_unread_notifications(user_id)
    for notif in notifications:
        notif['created_at'] = format_beijing_time(notif.get('created_at'))
    return {"notifications": notifications}


@router.put("/read-all")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    """一键标记所有未读消息为已读"""
    user_id = current_user['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0',
            (user_id,)
        )
        count = cursor.rowcount
    return {"success": True, "count": count}


@router.put("/{notif_id}/read")
async def mark_read(notif_id: int, current_user: dict = Depends(get_current_user)):
    """标记单条消息为已读"""
    user_id = current_user['user_id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?',
            (notif_id, user_id)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="消息不存在或无权操作")
    return {"success": True}