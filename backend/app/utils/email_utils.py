# app/utils/email_utils.py
import html as html_lib
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from typing import Optional
from ..config import settings
from ..logger import logger

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_END_RE = re.compile(r"(?is)<br\s*/?>|</p\s*>|</div\s*>|</h[1-6]\s*>|</li\s*>")


def html_to_text(body: str) -> str:
    """把 HTML 压成可读纯文本，作为 multipart/alternative 的降级副本。

    WHY：只发 text/html 时，部分客户端（企业邮箱、移动端精简模式）会把它当纯文本
    渲染，用户看到一堆标签；同时提供 text/plain 才能保证「至少可读」。
    """
    text = re.sub(r"(?is)<(script|style)\b.*?</\1\s*>", "", body)
    text = _BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\u3000]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def render_email_html(
    title: str,
    content: str,
    link: Optional[str] = None,
    cta: str = "查看详情",
    escape: bool = True,
) -> str:
    """统一邮件版式（600px 卡片 + 品牌色 + 可选按钮）。

    2026-11-10：此前 ``send_notification`` 直接把纯文本塞进 ``MIMEText(..., 'plain')``，
    认领/审核/撤销等**所有通知邮件都没有任何格式**（用户反馈）。现统一走本模板。

    Args:
        content: 正文。``escape=True`` 时按纯文本处理（转义 + 换行转 ``<br>``）；
            ``escape=False`` 时视为已可信的 HTML（如公告富文本）。
        link: 站内相对路径（``/items/1``）或完整 URL；为空则不渲染按钮。
    """
    body = html_lib.escape(content).replace("\n", "<br>") if escape else content
    button = ""
    if link:
        url = link if link.startswith(("http://", "https://")) else f"{settings.BASE_URL}{link}"
        button = (
            f'<p style="margin:24px 0 8px;">'
            f'<a href="{html_lib.escape(url)}" style="display:inline-block;padding:11px 26px;'
            f'background:#0F6E56;color:#ffffff;text-decoration:none;border-radius:8px;'
            f'font-size:14px;font-weight:500;">{html_lib.escape(cta)}</a></p>'
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<body style="margin:0;padding:24px 12px;background:#F5F4F1;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;border:1px solid #E8E6E1;border-radius:12px;padding:26px 30px;font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
    <div style="font-size:12px;letter-spacing:.6px;color:#0F6E56;font-weight:500;">校园失物检索平台</div>
    <h1 style="margin:8px 0 14px;font-size:18px;line-height:1.45;color:#1F1F1D;font-weight:500;">{html_lib.escape(title)}</h1>
    <div style="font-size:14px;line-height:1.85;color:#3F3D39;">{body}</div>
    {button}
    <div style="margin-top:26px;padding-top:14px;border-top:1px solid #EFEDE8;font-size:12px;color:#9A9690;line-height:1.7;">
      此邮件由系统自动发送，请勿直接回复。<br>校园失物检索平台 · 自动通知
    </div>
  </div>
</body>
</html>"""


def send_email(
    to_email: str,
    subject: str,
    body: str,
    html: bool = False,
    text: Optional[str] = None,
) -> bool:
    """发送邮件。``html=True`` 时构造 multipart/alternative（HTML + 纯文本降级）。

    Args:
        text: 纯文本副本。不传则从 HTML 自动抽取（:func:`html_to_text`）。
    """
    if not to_email:
        logger.info("邮件跳过：收件地址为空")
        return False
    if not settings.MAIL_USERNAME or not settings.MAIL_PASSWORD:
        logger.warning("邮件服务未配置（用户名或密码为空），请在 .env 中设置 MAIL_USERNAME 和 MAIL_PASSWORD")
        return False
    logger.info(f"正在发送邮件 → {to_email} 主题: {subject[:30]}...")
    try:
        if html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(text if text is not None else html_to_text(body), "plain", "utf-8"))
            msg.attach(MIMEText(body, "html", "utf-8"))
        else:
            msg = MIMEText(body, "plain", "utf-8")
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


def send_match_notification(
    email: str, username: str, item_title: str, similarity: float, link: str,
    level_text: str = "", basis_text: str = "",
) -> bool:
    """发送匹配通知邮件（HTML 格式）。

    2026-09-21：新增 ``level_text``（证据等级，如「高度疑似」）与 ``basis_text``
    （命中依据，如图像完全一致），让收件人不只看到一个百分比，还知道**凭什么说像**。
    ``similarity`` 现为「参考相似度」（最强证据通道），不再是多通道平均分。
    """
    subject = f"【校园失物检索】您的物品 '{item_title}' 有新匹配！"
    # 2026-11-10：改用统一版式（与认领/公告邮件同源），此前是另一套蓝色模板，
    # 且按旧口径显示「参考相似度」——现文案明确写「判定分」，与界面一致。
    parts = [
        f'<p style="margin:0 0 12px;">亲爱的 <strong>{html_lib.escape(username)}</strong>：</p>',
        f'<p style="margin:0 0 12px;">系统发现一条与您发布的物品 '
        f'<strong>“{html_lib.escape(item_title)}”</strong> 高度相似的匹配。</p>',
    ]
    if level_text:
        parts.append(
            f'<p style="margin:0 0 8px;"><strong>匹配等级：</strong>'
            f'<span style="color:#0F6E56;font-weight:500;">{html_lib.escape(level_text)}</span></p>')
    parts.append(f'<p style="margin:0 0 8px;"><strong>判定分：</strong>{similarity:.2%}</p>')
    if basis_text:
        parts.append(
            f'<p style="margin:0;color:#6B6862;"><strong>命中依据：</strong>'
            f'{html_lib.escape(basis_text)}</p>')
    body = render_email_html(
        "您发布的物品有新匹配", "".join(parts),
        link=link, cta="查看匹配详情", escape=False)
    return send_email(email, subject, body, html=True,
                      text=f"{username}，您的物品「{item_title}」有新匹配（判定分 {similarity:.0%}）。")