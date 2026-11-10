# app/services/notification_service.py
from ..database import add_notification
from ..utils import email_utils
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

    邮件用 HTML 版式（``email_utils.render_email_html``），并附带纯文本副本：
    2026-11-10 之前这里直接把纯文本塞进 ``MIMEText(..., 'plain')``，
    认领/审核/撤销等通知邮件**全都没有任何格式**（用户反馈）。
    """
    # 站内消息
    add_notification(user_id, title, content, link)

    # 邮件
    if send_mail and email:
        try:
            # 注意：用模块属性调用而非 `from ... import send_email`，
            # 否则测试里的 monkeypatch 打不中（模块级引用是独立绑定）。
            html_body = email_utils.render_email_html(
                title, content, link=link, cta="查看详情")
            email_utils.send_email(email, title, html_body, html=True, text=content)
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")