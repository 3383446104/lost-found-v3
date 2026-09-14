"""阶段5 跨模态一致性惩罚单测（T05）——纯数学，不加载真实模型。

覆盖设计 §5.2 硬约束：只降权、罚值 ∈ [FLOOR, 1.0]、对 cc 单调、开关可关。
"""
import numpy as np
import pytest

from app.clip_service import clip_service
from app.config import settings


def _u(idx):
    v = np.zeros(512, dtype=np.float32)
    v[idx] = 1.0
    return v


def _mix(i, j, cosine):
    v = np.zeros(512, dtype=np.float32)
    v[i] = cosine
    v[j] = float(np.sqrt(max(0.0, 1.0 - cosine * cosine)))
    return v


# --------------------------------------------------------------------------- #
# 纯函数：罚值范围 / 单调 / 开关
# --------------------------------------------------------------------------- #
def test_penalty_within_floor_and_one():
    """cc 从 0 扫到 1，罚值始终 ∈ [FLOOR, 1.0]。"""
    floor = settings.CROSS_PENALTY_FLOOR
    for cc in [i / 100.0 for i in range(0, 101)]:
        p = clip_service._cross_penalty(1.0, 1.0, cc, cc)
        assert floor - 1e-9 <= p <= 1.0 + 1e-9


def test_penalty_monotonic_in_cc():
    """cc 增大 ⇒ 罚值不减（单调）。"""
    prev = -1.0
    for cc in [i / 100.0 for i in range(0, 61)]:
        p = clip_service._cross_penalty(1.0, 1.0, cc, cc)
        assert p >= prev - 1e-12
        prev = p


def test_penalty_uses_min_of_directions():
    """cc = min(两方向)：更不一致的方向决定惩罚。"""
    p_low = clip_service._cross_penalty(1.0, 1.0, 0.0, 0.9)
    p_high = clip_service._cross_penalty(1.0, 1.0, 0.9, 0.9)
    assert p_low < p_high
    assert p_low == pytest.approx(settings.CROSS_PENALTY_FLOOR, abs=1e-9)


def test_penalty_disabled_returns_one(monkeypatch):
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    assert clip_service._cross_penalty(1.0, 1.0, 0.0, 0.0) == 1.0


def test_penalty_no_trigger_when_self_low(monkeypatch):
    """同模态自相似未达触发门限 → 不惩罚。"""
    monkeypatch.setattr(settings, "CROSS_PENALTY_SELF_HIGH", 0.99)
    assert clip_service._cross_penalty(0.1, 0.1, 0.0, 0.0) == 1.0


def test_penalty_missing_cross_returns_one():
    """跨模态方向缺失（无法判定一致性）→ 不惩罚。"""
    assert clip_service._cross_penalty(1.0, 1.0, None, None) == 1.0


# --------------------------------------------------------------------------- #
# 集成：只降权（不增分）
# --------------------------------------------------------------------------- #
def _base_score(inputs):
    return clip_service.compute_weighted_similarity(*inputs)


def test_only_reduces_score(monkeypatch):
    """开启惩罚后的总分 ≤ 关闭时（只降权，绝不给物品加分）。"""
    # q_img·t_img = 1.0（self 高，触发）；cross 两方向 = 0.0（cc=0 → 触底）
    q_img = np.zeros(512, dtype=np.float32); q_img[0] = 1.0
    t_img = np.zeros(512, dtype=np.float32); t_img[0] = 1.0
    q_text = np.zeros(512, dtype=np.float32); q_text[1] = 1.0
    t_text = np.zeros(512, dtype=np.float32); t_text[1] = 1.0
    inputs = (q_img, q_text, t_img, t_text)

    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    base_off = _base_score(inputs)
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", True)
    base_on = _base_score(inputs)

    assert base_on <= base_off + 1e-12
    assert base_on == pytest.approx(base_off * settings.CROSS_PENALTY_FLOOR, abs=1e-6)


def test_penalty_zero_when_consistent(monkeypatch):
    """图文一致（cc 高）→ 不惩罚，与关闭时结果一致。"""
    q_img = np.zeros(512, dtype=np.float32); q_img[0] = 1.0
    q_text = np.zeros(512, dtype=np.float32); q_text[0] = 1.0
    t_img = np.zeros(512, dtype=np.float32); t_img[0] = 1.0
    t_text = np.zeros(512, dtype=np.float32); t_text[0] = 1.0
    inputs = (q_img, q_text, t_img, t_text)

    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    base_off = _base_score(inputs)
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", True)
    base_on = _base_score(inputs)

    assert base_on == pytest.approx(base_off, abs=1e-9)
