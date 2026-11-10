# -*- coding: utf-8 -*-
"""邮件版式回归测试（2026-11-10）。

背景：``send_notification`` 原先用 ``MIMEText(content, 'plain')`` 发信，
认领 / 审核 / 撤销 / 举报等**所有通知邮件都没有格式**（用户反馈）。
本文件锁三件事：

1. 统一模板 ``render_email_html`` 的结构、转义与按钮链接；
2. ``send_email(html=True)`` 必须构造 ``multipart/alternative``（HTML + 纯文本降级），
   否则部分客户端会把 HTML 当纯文本渲染，反而更难读；
3. ``send_notification`` 必须走 HTML 通道，而不是继续发纯文本。
"""
import email as email_lib
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.utils import email_utils  # noqa: E402
from app.utils.email_utils import (  # noqa: E402
    html_to_text, render_email_html, send_email as real_send_email,
)
from app.services.notification_service import send_notification  # noqa: E402


# --------------------------------------------------------------------------- #
# 模板
# --------------------------------------------------------------------------- #
def test_render_email_html_structure():
    body = render_email_html("收到认领申请", "物品 A 收到一条申请。", link="/items/1")
    assert body.startswith("<!doctype html>")
    assert "#0F6E56" in body, "必须使用品牌色"
    assert "收到认领申请" in body
    assert "/items/1" in body and "查看详情" in body
    assert "此邮件由系统自动发送" in body


def test_render_email_html_absolute_link_kept():
    body = render_email_html("t", "c", link="https://example.com/items/9")
    assert 'href="https://example.com/items/9"' in body


def test_render_email_html_without_link_has_no_button():
    body = render_email_html("仅通知", "没有跳转")
    assert "<a href=" not in body


def test_render_email_escapes_user_content():
    """站内通知内容含用户输入（物品标题等），必须转义，防 HTML 注入。"""
    body = render_email_html("标题", "<script>alert(1)</script>")
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_render_email_keeps_trusted_html():
    """公告正文是富文本，escape=False 时保留标签。"""
    body = render_email_html("公告", "<p>正文<strong>加粗</strong></p>", escape=False)
    assert "<strong>加粗</strong>" in body


def test_newlines_become_breaks():
    body = render_email_html("t", "第一行\n第二行")
    assert "第一行<br>第二行" in body


def test_html_to_text_strips_tags_and_entities():
    text = html_to_text("<p>你好&nbsp;<strong>世界</strong></p><br><div>第二段</div>")
    assert "<" not in text and "&nbsp;" not in text
    assert "你好" in text and "世界" in text and "第二段" in text


# --------------------------------------------------------------------------- #
# 发送：multipart/alternative
# --------------------------------------------------------------------------- #
class _FakeSMTP:
    sent = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def login(self, *args):
        return None

    def sendmail(self, sender, to, msg):
        _FakeSMTP.sent.append(msg)


@pytest.fixture
def fake_smtp(monkeypatch):
    monkeypatch.setattr(email_utils.settings, "MAIL_USERNAME", "noreply@test.local")
    monkeypatch.setattr(email_utils.settings, "MAIL_PASSWORD", "x")
    monkeypatch.setattr(email_utils.smtplib, "SMTP_SSL", _FakeSMTP)
    _FakeSMTP.sent = []
    return _FakeSMTP


def test_send_email_html_is_multipart(fake_smtp):
    body = render_email_html("标题", "正文", link="/items/1")
    assert real_send_email("a@b.com", "主题", body, html=True, text="纯文本正文") is True

    msg = email_lib.message_from_string(fake_smtp.sent[0])
    assert msg.get_content_type() == "multipart/alternative"
    parts = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in parts and "text/html" in parts
    plain = next(p for p in msg.walk() if p.get_content_type() == "text/plain")
    assert "纯文本正文" in plain.get_payload(decode=True).decode("utf-8")


def test_send_email_plain_stays_single_part(fake_smtp):
    assert real_send_email("a@b.com", "主题", "纯文本", html=False) is True
    msg = email_lib.message_from_string(fake_smtp.sent[0])
    assert msg.get_content_type() == "text/plain"


# --------------------------------------------------------------------------- #
# send_notification 必须走 HTML
# --------------------------------------------------------------------------- #
def test_send_notification_uses_html_template(monkeypatch, make_user):
    user = make_user(username="mail_user", email="mail_user@example.com")
    addr = "mail_user@example.com"
    captured = {}

    def _fake_send(to, subject, body, html=False, text=None):
        captured.update(to=to, subject=subject, body=body, html=html, text=text)
        return True

    # autouse 的 stub_email 已把该属性替换成 lambda，这里再覆盖一次
    monkeypatch.setattr(email_utils, "send_email", _fake_send)

    send_notification(user["id"], "收到认领申请", "物品 A 收到一条申请。", link="/items/1",
                      email=addr)

    assert captured["html"] is True, "通知邮件必须走 HTML 通道"
    assert captured["body"].startswith("<!doctype html>")
    assert "/items/1" in captured["body"]
    assert captured["text"] == "物品 A 收到一条申请。", "纯文本副本应保留原文"
