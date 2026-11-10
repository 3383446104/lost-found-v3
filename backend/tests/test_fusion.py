# -*- coding: utf-8 -*-
"""加权融合算法（`app/services/fusion.py`）单元测试。

本模块是论文式 (4-1) ~ (4-4) 的**唯一实现**，因此测试直接对着公式断言：

1. 式 4-3 的缺通道归一化 —— 分母只累加可用通道；
2. 式 4-2 的仿射映射 —— 三点定标、且**不截断**（>1 与 <0 都保留）；
3. 式 4-1 的标题门控 —— 未字面命中时退回全文；
4. 式 4-4 的封顶与先验；
5. 与 `clip_service.compute_score_v2` 的**数值一致性**（防止重构后两处漂移）。
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.services import fusion  # noqa: E402


# --------------------------------------------------------------------------- #
# 式 4-2：跨模态仿射映射
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,expected", [
    (0.194, 0.0),                    # 下锚点
    (0.298, 1.0),                    # 上锚点
    (0.246, 0.5),                    # 中点
    (0.142, pytest.approx(-0.5)),    # 低于 LO：保留负值（不截断）
    (0.400, pytest.approx(1.9808, abs=1e-3)),   # 高于 HI：不封顶
])
def test_affine_cross_keeps_ordering(value, expected):
    got = fusion.affine_cross(value, 0.194, 0.298)
    assert got == pytest.approx(expected, abs=1e-4)


def test_affine_cross_none_passthrough():
    assert fusion.affine_cross(None, 0.194, 0.298) is None


# --------------------------------------------------------------------------- #
# 式 4-1：标题通道与门控
# --------------------------------------------------------------------------- #
def test_text_channel_takes_max_when_literal():
    ch = fusion.channels_from_sims(
        sim_tt=0.7569, sim_title=1.0, literal=1.0)
    assert ch.text == pytest.approx(1.0)


def test_text_channel_falls_back_to_full_when_not_literal():
    """未字面命中：标题余弦视为噪声（短标题各向异性），退回全文。"""
    ch = fusion.channels_from_sims(
        sim_tt=0.4571, sim_title=0.7783, literal=0.0)
    assert ch.text == pytest.approx(0.4571)


def test_text_channel_gate_can_be_disabled():
    ch = fusion.channels_from_sims(
        sim_tt=0.4571, sim_title=0.7783, literal=0.0,
        weights=fusion.with_overrides(fusion.DEFAULT_WEIGHTS, title_gate="always"))
    assert ch.text == pytest.approx(0.7783)


def test_text_channel_survives_missing_full_vector():
    """目标无全文向量时兜底用标题（title_vector 是全文的细化）。"""
    ch = fusion.channels_from_sims(sim_tt=None, sim_title=0.66, literal=0.0)
    assert ch.text == pytest.approx(0.66)


def test_no_text_at_all():
    ch = fusion.channels_from_sims(sim_tt=None, sim_title=None)
    assert ch.text is None and ch.available() == ()


# --------------------------------------------------------------------------- #
# 式 4-3：缺通道动态归一化
# --------------------------------------------------------------------------- #
def test_base_score_single_channel_equals_itself():
    ch = fusion.Channels(text=0.9, img=None, cross=None)
    assert fusion.base_score(ch) == pytest.approx(0.9)


def test_base_score_two_channels_normalized():
    ch = fusion.Channels(text=1.0, img=None, cross=0.0)
    assert fusion.base_score(ch) == pytest.approx(0.8)


def test_base_score_three_channels_weights():
    ch = fusion.Channels(text=1.0, img=1.0, cross=1.0)
    assert fusion.base_score(ch) == pytest.approx(1.0)
    ch2 = fusion.Channels(text=1.0, img=1.0, cross=0.0)
    assert fusion.base_score(ch2) == pytest.approx(1.6 / 1.8)


def test_base_score_empty_is_zero():
    assert fusion.base_score(fusion.Channels(text=None, img=None, cross=None)) == 0.0


def test_zero_weight_channel_is_excluded():
    w = fusion.with_overrides(fusion.DEFAULT_WEIGHTS, w_cross=0.0)
    ch = fusion.Channels(text=1.0, img=None, cross=-0.5)
    assert fusion.base_score(ch, w) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 式 4-4：先验、字面加分与封顶
# --------------------------------------------------------------------------- #
def test_category_and_location_priors():
    base = fusion.Channels(text=0.5, img=None, cross=None, cat_same=True, loc_same=True)
    assert fusion.fuse(base) == pytest.approx(0.5 + 0.03 + 0.02)

    diff = fusion.Channels(text=0.5, img=None, cross=None, cat_same=False, loc_same=False)
    assert fusion.fuse(diff) == pytest.approx(0.5 - 0.05 - 0.03)


def test_prior_skipped_when_unknown():
    ch = fusion.Channels(text=0.5, img=None, cross=None)
    assert fusion.fuse(ch) == pytest.approx(0.5)


def test_literal_bonus_and_scale():
    ch = fusion.Channels(text=0.5, img=None, cross=None, literal=1.0, literal_scale=1.0)
    assert fusion.fuse(ch) == pytest.approx(0.65)
    alias = fusion.Channels(text=0.5, img=None, cross=None, literal=0.8, literal_scale=0.3)
    assert fusion.fuse(alias) == pytest.approx(0.5 + 0.15 * 0.8 * 0.3)


def test_score_is_clamped_and_rounded():
    ch = fusion.Channels(text=1.0, img=None, cross=None, literal=1.0)
    assert fusion.fuse(ch) == 1.0
    ch2 = fusion.Channels(text=-5.0, img=None, cross=None)
    assert fusion.fuse(ch2) == 0.0
    assert isinstance(fusion.fuse(ch2), float)


def test_weights_are_immutable():
    w = fusion.DEFAULT_WEIGHTS
    with pytest.raises(Exception):
        w.w_text = 0.1  # frozen dataclass


# --------------------------------------------------------------------------- #
# 与 clip_service 的一致性（重构护栏）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("sim_tt,sim_title,sim_cross,literal", [
    (0.7569, 1.0, 0.1908, 1.0),
    (0.4571, 0.7783, 0.1420, 0.0),
    (None, 0.66, 0.246, 0.0),
])
def test_compute_score_v2_matches_fusion(sim_tt, sim_title, sim_cross, literal, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "V2_TITLE_GATE", "literal")
    # sim_cross 是**原始余弦**，compute_score_v2 内部自行做仿射
    got = clip_service.compute_score_v2(
        sim_tt=sim_tt, sim_title=sim_title, sim_ii=None,
        sim_t2i=sim_cross, sim_i2t=None, literal=literal,
    )
    expected = fusion.fuse_sims(
        sim_tt=sim_tt, sim_title=sim_title, sim_t2i=sim_cross,
        literal=literal,
        lo=float(settings.MATCH_CROSS_REF_LO), hi=float(settings.MATCH_CROSS_REF_HI),
    )
    assert got == pytest.approx(expected, abs=1e-6)
