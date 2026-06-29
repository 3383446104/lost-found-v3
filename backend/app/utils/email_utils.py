# app/utils/email_utils.py
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from ..config import settings
from ..logger import logger


def send_email(to_email: str, subject: str, body: str, html: bool = False) -> bool:
    if not to_email:
        return False
    required = ['MAIL_SERVER', 'MAIL_PORT', 'MAIL_USERNAME', 'MAIL_PASSWORD']
    if not all(hasattr(settings, attr) for attr in required):
        logger.error("邮件配置不完整，请检查 settings")
        return False
    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        logger.warning("邮件服务未配置（用户名或密码为空）")
        return False
    try:
        msg = MIMEText(body, 'html' if html else 'plain', 'utf-8')
        msg['From'] = formataddr((settings.APP_NAME, settings.MAIL_USERNAME))
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')
        with smtplib.SMTP_SSL(settings.MAIL_SERVER, settings.MAIL_PORT, timeout=10) as smtp:
            smtp.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
            smtp.sendmail(settings.MAIL_USERNAME, [to_email], msg.as_string())
        logger.info(f"邮件发送成功: {to_email}")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"SMTP错误: {e}")
        return False
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False


def send_match_notification(email: str, username: str, item_title: str, similarity: float, link: str) -> bool:
    """发送匹配通知邮件（HTML 格式）"""
    subject = f"【失物寻回】您的物品 '{item_title}' 有新匹配！"
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f7fc;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);">
            <h2 style="color: #2c3e50;">🔍 失物寻回系统</h2>
            <p style="font-size: 16px; color: #333;">亲爱的 <strong>{username}</strong>：</p>
            <p style="font-size: 15px; color: #444;">系统发现一条与您发布的物品 <strong>“{item_title}”</strong> 高度相似的匹配！</p>
            <p style="font-size: 15px; color: #444;"><strong>相似度：</strong>{similarity:.2%}</p>
            <p style="margin: 24px 0;">
                <a href="{link}" style="display: inline-block; padding: 10px 24px; background: #667eea; color: #fff; text-decoration: none; border-radius: 8px; font-weight: 500;">👉 查看详情</a>
            </p>
            <hr style="border: none; border-top: 1px solid #eaeef2; margin: 24px 0;">
            <p style="font-size: 12px; color: #999;">—— 校园失物智能寻回系统 · 自动通知 ——</p>
        </div>
    </body>
    </html>
    """
    return send_email(email, subject, body, html=True)