# -*- coding: utf-8 -*-
"""时间衰减回归守卫测试（2026-09-21 修复）。

缺陷回顾（「静默失败」家族又一实例）
----------------------------------
``api/items.py`` 与 ``services/match_service.py`` 各自用 ``try/except`` 解析
``created_at``：

    target_date = datetime.fromisoformat("2026-07-02 01:06:44")   # → naive，解析「成功」
    days_old = max(0, (datetime.now(timezone.utc) - target_date).days)
    #                    ^^^^^^^^^^^^^^^^^^^^^^^ aware 减 naive → TypeError
    except Exception:
        days_old = 0        # ← 异常被吞：衰减完全失效，且**无任何日志**

后果：所有物品都被当成「今天创建」，阶段2 时间衰减恒等于 ×1.0——老物品分数不降，
与「新物品优先」的产品设计相反，且外部完全无法察觉（分数看起来正常）。

本文件锁死三点：
  A. ``days_since_utc`` 对 SQLite 无时区格式返回**正确天数**（而非 0）；
  B. 衰减参数下的实际乘数符合配置（含下限）；
  C. 衰减**真的进入打分**（同内容不同天数 → 分数不同）。

作者：team-lead（齐活林）—— 修复者自留守卫。
"""
import datetime
import os
import sys

import numpy as np
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.config import settings  # noqa: E402
from app.utils.time_utils import days_since_utc  # noqa: E402


NOW = datetime.datetime(2026, 9, 21, 9, 0, 0, tzinfo=datetime.timezone.utc)


# --------------------------------------------------------------------------- #
# A. 解析层：naive 时间戳必须被正确解释为 UTC（本缺陷的核心）
# --------------------------------------------------------------------------- #
def test_sqlite_naive_timestamp_returns_real_days_not_zero():
    """**核心回归守卫**：SQLite 无时区格式（``YYYY-MM-DD HH:MM:SS``）必须算出真实天数。

    旧实现此处抛 TypeError 被兜底吞掉 → 返回 0（衰减失效）。若本用例失败，
    说明又回到了「静默不衰减」状态。
    """
    assert days_since_utc("2026-09-21 09:00:00", now=NOW) == 0
    assert days_since_utc("2026-09-20 09:00:00", now=NOW) == 1
    assert days_since_utc("2026-07-07 09:00:00", now=NOW) == 76


def test_iso_formats_with_and_without_timezone():
    """ISO 8601：带 Z / 带偏移 / 无偏移 三种都要正确。"""
    assert days_since_utc("2026-07-07T09:00:00Z", now=NOW) == 76
    assert days_since_utc("2026-07-07T17:00:00+08:00", now=NOW) == 76  # 等价 UTC 09:00
    assert days_since_utc("2026-07-07T09:00:00", now=NOW) == 76        # naive ISO → 视为 UTC


def test_microseconds_and_future_and_invalid():
    """微秒格式可解析；天数按「满 24 小时」取整；未来时间返回 0；非法输入返回 0 而非抛错。"""
    # 不满 24 小时 → 0 天（与 timedelta.days 语义一致，勿写成 1）
    assert days_since_utc("2026-09-20 09:00:00.123456", now=NOW) == 0
    assert days_since_utc("2026-09-19 09:00:00.123456", now=NOW) == 1
    assert days_since_utc("2026-12-31 00:00:00", now=NOW) == 0   # 未来 → 夹到 0
    assert days_since_utc("not-a-timestamp", now=NOW) == 0
    assert days_since_utc(None, now=NOW) == 0
    assert days_since_utc("", now=NOW) == 0


# --------------------------------------------------------------------------- #
# B. 衰减乘数：与配置一致且受下限约束
# --------------------------------------------------------------------------- #
def test_decay_multiplier_matches_config():
    """= max(FLOOR, 1 - days/DAYS)：验证 0 天不衰减、中段线性、超龄触底。"""
    days_cfg = settings.MATCH_DECAY_DAYS
    floor = settings.MATCH_DECAY_FLOOR

    def decay_of(d):
        return max(floor, 1.0 - d / float(days_cfg))

    # 当前配置（240 天 / 下限 0.6）下的关键点
    assert decay_of(0) == 1.0
    assert decay_of(76) == pytest.approx(1 - 76 / 240, abs=1e-9)   # ≈0.6833（未触底）
    assert decay_of(days_cfg) == floor                              # 恰好在边界触底
    assert decay_of(9999) == floor                                  # 超龄不得更低


# --------------------------------------------------------------------------- #
# C. 集成：衰减必须真的影响打分
# --------------------------------------------------------------------------- #
def test_decay_actually_affects_score():
    """同内容、仅天数不同 → 分数必须按衰减乘数下降（证明阶段2 真的在作用）。"""
    from app.clip_service import clip_service

    q_text = np.array([1.0, 0.0], dtype=np.float32)
    t_text = np.array([1.0, 0.0], dtype=np.float32)  # sim_tt = 1.0
    t_img = np.array([0.0, 1.0], dtype=np.float32)   # 跨模态 0 → 会触发惩罚，故关闭

    old = settings.CROSS_PENALTY_ENABLED
    settings.CROSS_PENALTY_ENABLED = False
    try:
        s_new = clip_service.compute_weighted_similarity(None, q_text, t_img, t_text, days_old=0)
        s_old = clip_service.compute_weighted_similarity(None, q_text, t_img, t_text, days_old=76)
        s_floor = clip_service.compute_weighted_similarity(None, q_text, t_img, t_text, days_old=9999)
    finally:
        settings.CROSS_PENALTY_ENABLED = old

    expected_ratio = max(settings.MATCH_DECAY_FLOOR, 1 - 76 / float(settings.MATCH_DECAY_DAYS))
    assert s_old < s_new, "days_old 增大但分数未下降 —— 时间衰减又失效了"
    assert s_old / s_new == pytest.approx(expected_ratio, abs=1e-4)
    assert s_floor / s_new == pytest.approx(settings.MATCH_DECAY_FLOOR, abs=1e-4)


# --------------------------------------------------------------------------- #
# D. v3.7.0：发生时间 occurred_at 口径
# --------------------------------------------------------------------------- #
def test_date_only_occurred_at_parses():
    """occurred_at 纯日期（YYYY-MM-DD）必须可解析为 UTC 当日 0 点（不静默退化为 0）。"""
    assert days_since_utc("2026-09-21", now=NOW) == 0
    assert days_since_utc("2026-07-07", now=NOW) == 76
    assert days_since_utc("2026-07-07 09:00:00", now=NOW) == 76  # 带时间仍兼容


def test_match_decay_uses_occurred_at_first_then_created_at(client, make_user, monkeypatch):
    """/match 的时间衰减入参：有 occurred_at 用它；缺失回退 created_at。"""
    import json

    from app import database as db_module
    from app.api import items as items_module
    from app.clip_service import clip_service

    user = make_user(username="decay_v370")

    def _insert(occurred_at=None, created_at="2026-09-01 00:00:00"):
        with db_module.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO items (type,title,description,category,location,status,user_id,"
                "review_status,image_path,image_vector,text_vector,occurred_at,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("found", "衰减目标", "d", "其他", "图书馆", "active", user["id"], "approved",
                 None, json.dumps([0.01] * 512), json.dumps([0.01] * 512), occurred_at, created_at),
            )
            return cur.lastrowid

    with_occurred = _insert(occurred_at="2020-01-01")
    without_occurred = _insert(created_at="2026-08-01 00:00:00")

    seen = []

    def _fake_days(ts):
        seen.append(ts)
        return 0

    monkeypatch.setattr(items_module, "days_since_utc", _fake_days)
    # 查询向量 512 维，与库中目标一致 → 通过维度预检
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: np.ones(512, np.float32) / np.sqrt(512))

    resp = client.post(
        "/api/items/match",
        json={"text": "任意", "target_type": "found", "threshold": 0.0},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    hits = {m["id"] for m in resp.json()["matches"]}
    assert with_occurred in hits and without_occurred in hits
    assert "2020-01-01" in seen, f"occurred_at 未被用作衰减入参：{seen}"
    assert "2026-08-01 00:00:00" in seen, f"缺失 occurred_at 未回退 created_at：{seen}"
