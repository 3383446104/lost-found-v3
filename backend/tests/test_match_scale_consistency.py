# -*- coding: utf-8 -*-
"""匹配分数「尺度一致性」守卫（2026-09-21）。

背景
----
标定脚本刻意不传类别/位置/时间（「标定纯内容相似度，避免统一加分造成阈值漂移」），
因此 ``MATCH_THRESHOLD_AUTO`` / ``MATCH_THRESHOLD_EMAIL`` 是**内容分尺度**的阈值。

而 ``auto_match_and_notify`` 原先用 ``compute_weighted_similarity()`` 的返回值
（**含时间衰减**的排序分）与阈值比较 → 老物品被系统性挡住。实测：

    「蓝牙耳机 ↔ 蓝牙耳机」内容分 0.9377，81 天衰减后排序分仅 0.6278
    ＜ AUTO 阈值 0.733952 → **永不推送、不发邮件**

这是用户反馈「邮件通知没触发」在「灰度开关关闭」之外的第二重原因（隐藏缺陷）。

本文件锁死两点（防止回退）：
  A. 自动匹配的**判定**用 ``content_score``（而非含衰减的 ``score``）；
  B. 邮件的**触发**同样用 ``content_score``。

作者：team-lead（齐活林）—— 修复者自留守卫。
"""
import json
import os
import sys

from app import database as db_module
from app.clip_service import clip_service
from app.config import settings
from app.services import match_service
from app.services.match_service import auto_match_and_notify


def _j(dim):
    return json.dumps([0.01] * dim) if dim else None


def _insert_item(user_id, type_="found", iv_dim=512, tv_dim=512):
    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items (type,title,description,category,location,status,user_id,"
            "review_status,image_path,image_vector,text_vector,color_vector) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (type_, "尺度守卫", "d", "电子产品", "图书馆", "active", user_id,
             "approved", None, _j(iv_dim), _j(tv_dim), None),
        )
        return cur.lastrowid


def _count(table):
    with db_module.get_db_connection() as conn:
        return conn.cursor().execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def _set_email(user_id, email):
    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE users SET email=? WHERE id=?", (email, user_id))


def _detail(content, score, level="high_suspect", basis=("text_match",)):
    """构造 compute_match_detail 的返回契约。"""
    return {
        "score": score,
        "content_score": content,
        "reference_score": min(1.0, content),
        "level": level,
        "basis": list(basis),
        "channels": {
            "sim_img_img": None, "sim_text_text": content, "sim_t2i": None,
            "sim_i2t": None, "sim_cross": None, "sim_cross_mapped": None,
        },
    }


def test_auto_match_judges_by_content_score(make_user, monkeypatch):
    """**核心守卫**：内容分高于阈值、但含衰减的排序分低于阈值 → 仍应落库。

    若实现退回「用 score 判定」，本用例会失败（matches 表增加 0 条）。
    """
    user = make_user(username="scale_auto")
    new_id = _insert_item(user["id"], type_="lost")
    _insert_item(user["id"], type_="found")
    monkeypatch.setattr(settings, "AUTO_MATCH_ENABLED", True)

    th = settings.MATCH_THRESHOLD_AUTO
    # content 高于阈值、score 低于阈值（模拟 81 天衰减后的真实分布）
    monkeypatch.setattr(
        clip_service, "compute_match_detail",
        lambda *a, **k: _detail(content=th + 0.15, score=th - 0.30),
    )

    before = _count("matches")
    auto_match_and_notify(new_id, "lost")
    assert _count("matches") == before + 1, (
        "内容分达标但排序分（含衰减）未达标时未落库 —— "
        "说明判定退回用了 score，老物品会被时间衰减系统性挡住"
    )


def test_email_trigger_uses_content_score(make_user, monkeypatch):
    """邮件触发同样按 content_score 判定（而非含衰减的 score）。"""
    user = make_user(username="scale_mail")
    _set_email(user["id"], "scale_guard@example.com")
    new_id = _insert_item(user["id"], type_="lost")
    _insert_item(user["id"], type_="found")
    monkeypatch.setattr(settings, "AUTO_MATCH_ENABLED", True)

    th_mail = settings.MATCH_THRESHOLD_EMAIL
    monkeypatch.setattr(
        clip_service, "compute_match_detail",
        lambda *a, **k: _detail(content=th_mail + 0.05, score=th_mail - 0.30),
    )

    sent = []
    monkeypatch.setattr(
        match_service, "send_match_notification",
        lambda **kw: sent.append(kw) or True,
    )
    monkeypatch.setattr(settings, "MATCH_THRESHOLD_AUTO", th_mail - 0.10)

    auto_match_and_notify(new_id, "lost")
    assert sent, (
        "内容分达到 EMAIL 阈值时未尝试发邮件 —— 说明邮件触发退回用了含衰减的 score"
    )
    # 邮件里带等级与依据（新契约）
    assert any(kw.get("level_text") for kw in sent), "邮件缺少匹配等级文案"


def test_notification_text_includes_level(make_user, monkeypatch):
    """站内通知文案包含匹配等级（可读性契约）。"""
    user = make_user(username="scale_text")
    new_id = _insert_item(user["id"], type_="lost")
    _insert_item(user["id"], type_="found")
    monkeypatch.setattr(settings, "AUTO_MATCH_ENABLED", True)
    monkeypatch.setattr(
        clip_service, "compute_match_detail",
        lambda *a, **k: _detail(content=0.95, score=0.62, level="confirmed"),
    )

    captured = []
    monkeypatch.setattr(
        match_service, "send_match_notification", lambda **kw: True,
    )
    with db_module.get_db_connection() as conn:
        before = conn.cursor().execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"]
    auto_match_and_notify(new_id, "lost")
    with db_module.get_db_connection() as conn:
        rows = conn.cursor().execute(
            "SELECT title, content FROM notifications ORDER BY id DESC LIMIT 2"
        ).fetchall()
    assert len(rows) == 2, "应产生双向通知（发布者 + 目标所有者）"
    for r in rows:
        assert "高度确定" in r["content"], f"通知文案缺少等级：{r['content']}"
