# app/services/notification_service.py
from ..database import add_notification
from ..utils.email_utils import send_email
from ..logger import logger


def send_notification(
    user_id: int,
    title: str,
    content: str,
    link: str = None,
    email: str = None,
    send_mail: bool = True
) -> None:
    """
    发送通知（站内消息 + 可选邮件）
    """
    # 站内消息
    add_notification(user_id, title, content, link)

    # 邮件
    if send_mail and email:
        try:
            send_email(email, title, content, html=False)
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")