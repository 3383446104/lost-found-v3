# -*- coding: utf-8 -*-
"""打分口径回归测试（2026-09-21 修订：按查询形态分三种检索模式 + 跨模态尺度映射）。

口径变化（本轮）
----------------
1. **权重从「三通道等权」改为「主证据 + 辅助证据」**：
   同模态通道（图-图 / 文-文）各 0.75 为**主证据**，跨模态 0.25 为**辅助证据**。
   配合既有的「缺通道动态归一化」，三种检索模式自动成形 —— 无需分支代码：

   | 查询形态 | 可用通道 | 归一化后 |
   |---|---|---|
   | 文字检索 | 文-文 + 跨模态 | 0.75 / 0.25 |
   | 图片检索 | 图-图 + 跨模态 | 0.75 / 0.25 |
   | 图文混合 | 图-图 + 文-文 + 跨模态 | 0.43 / 0.43 / 0.14 |

2. **跨模态通道做「尺度映射」**：原生余弦只落在 0.15~0.35（CLIP 固有特性），
   按其实测分布（负样本均值 → 0、正样本均值 → 1）线性拉伸到可读尺度。
   仅作用于**外层加权**；阶段5 惩罚仍用原始余弦。

3. **跨模态一致性惩罚的触发条件收窄**：仅当「文-文高 **且** 图-图不高」时触发
   （真正的「文本撞车」场景）。图-图同样高说明图像证据独立支持，不再误伤。

另锁死「颜色通道已废弃」与「证据链（等级/依据/展示分）」语义。

作者：team-lead（齐活林）—— 口径变更自留守卫。
"""
import os
import sys

import numpy as np
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.config import settings  # noqa: E402
from app.clip_service import clip_service  # noqa: E402
from calibrate_thresholds import (  # noqa: E402
    _EncoderCache,
    score_pair,
    score_pair_vs_target,
)

# 正交构造：文=[1,0]、图=[0,1] → sim_tt=1.0、sim_ii=1.0、跨模态=0
_TEXT = np.array([1.0, 0.0], dtype=np.float32)
_IMG = np.array([0.0, 1.0], dtype=np.float32)


class _OrthoEncoder:
    name = "ortho-fake"
    model_name = "ortho-fake"

    def encode_text(self, text):
        return _TEXT.copy()

    def encode_image(self, path):
        return _IMG.copy()


def _pair_full():
    return {"id": "P-full", "label": 1,
            "query": {"image": "uploads/q.jpg", "text": "描述"},
            "target": {"item_id": 1, "item_ref": "uploads/t.jpg", "text": "目标描述"}}


def _pair_text_only():
    return {"id": "P-text", "label": 1,
            "query": {"image": None, "text": "描述"},
            "target": {"item_id": 1, "item_ref": "uploads/t.jpg", "text": "目标描述"}}


@pytest.fixture
def no_penalty(monkeypatch):
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)


# --------------------------------------------------------------------------- #
# A. 主辅权重与三种检索模式（由缺通道归一化自动成形）
# --------------------------------------------------------------------------- #
def test_three_channels_main_aux_weighting(no_penalty):
    """三通道全可用：文-文(0.75,1.0) + 图-图(0.75,1.0) + 跨模态(0.25,0) = 1.5/1.75。"""
    s = clip_service.compute_weighted_similarity(_IMG, _TEXT, _IMG, _TEXT)
    assert abs(s - 1.5 / 1.75) < 1e-6, f"主辅加权口径不符：期望 6/7，实得 {s}"


def test_text_search_mode_two_channels(no_penalty):
    """文字检索（无查询图）⇒ 文-文 主(0.75) + 跨模态 辅(0.25) ⇒ (0.75*1 + 0.25*0)/1 = 0.75。"""
    s = clip_service.compute_weighted_similarity(None, _TEXT, _IMG, _TEXT)
    assert abs(s - 0.75) < 1e-6, f"文字检索模式口径不符：期望 0.75，实得 {s}"


def test_image_search_mode_two_channels(no_penalty):
    """图片检索（无查询文）⇒ 图-图 主(0.75) + 跨模态 辅(0.25)。

    跨模态仅 i2t 可用 = q_img·t_text = [0,1]·[1,0] = 0 → 映射后 0。
    """
    s = clip_service.compute_weighted_similarity(_IMG, None, _IMG, _TEXT)
    assert abs(s - 0.75) < 1e-6, f"图片检索模式口径不符：期望 0.75，实得 {s}"


# --------------------------------------------------------------------------- #
# B. 跨模态尺度映射
# --------------------------------------------------------------------------- #
def test_cross_mapping_lifts_low_cosine():
    """映射把「正样本均值」(HI) 抬到 1.0、把「负样本均值」(LO) 压到 0.0。"""
    lo, hi = settings.MATCH_CROSS_REF_LO, settings.MATCH_CROSS_REF_HI
    assert abs(clip_service._map_cross(hi) - 1.0) < 1e-9
    assert abs(clip_service._map_cross(lo) - 0.0) < 1e-9
    assert abs(clip_service._map_cross((lo + hi) / 2) - 0.5) < 1e-9
    # 评测集实测：正样本最小值 0.2474 → 映射后应显著高于原值
    assert clip_service._map_cross(0.2474) > 0.2474


def test_cross_mapping_clips_out_of_range():
    """越界夹紧：低于 LO → 0；高于 HI → 1；None 透传。"""
    lo, hi = settings.MATCH_CROSS_REF_LO, settings.MATCH_CROSS_REF_HI
    assert clip_service._map_cross(lo - 0.1) == 0.0
    assert clip_service._map_cross(hi + 0.5) == 1.0
    assert clip_service._map_cross(None) is None


def test_cross_mapping_affects_outer_weighting(no_penalty):
    """映射后的跨模态值参与外层加权（构造原始余弦 = HI，应被抬到满值）。"""
    hi = settings.MATCH_CROSS_REF_HI
    q_text = np.array([1.0, 0.0], dtype=np.float32)
    t_img = np.array([hi, float(np.sqrt(1 - hi ** 2))], dtype=np.float32)
    s = clip_service.compute_weighted_similarity(
        None, q_text, t_img, None,
        img_weight=0.0, text_weight=0.0, cross_weight=1.0,
    )
    assert abs(s - 1.0) < 1e-5, f"跨模态映射未进入外层加权：{s}"


# --------------------------------------------------------------------------- #
# C. 颜色通道废弃（沿用既有守卫）
# --------------------------------------------------------------------------- #
def test_color_vectors_ignored_after_deprecation(no_penalty):
    """传入颜色向量且 color_weight 拉满，得分必须**完全不变**。"""
    cq = np.array([1.0, 0.0], dtype=np.float32)
    ct = np.array([0.0, 1.0], dtype=np.float32)
    s_without = clip_service.compute_weighted_similarity(_IMG, _TEXT, _IMG, _TEXT)
    s_with = clip_service.compute_weighted_similarity(
        _IMG, _TEXT, _IMG, _TEXT, color1=cq, color2=ct, color_weight=0.9,
    )
    assert s_without == s_with == pytest.approx(1.5 / 1.75, abs=1e-6)


# --------------------------------------------------------------------------- #
# D. 跨模态一致性惩罚的触发条件（2026-09-21 收窄）
# --------------------------------------------------------------------------- #
def test_penalty_triggers_when_text_high_but_image_low():
    """真·文本撞车：文-文高 + 图-图低 → 惩罚生效（触底 ×0.5）。

    构造：t_text = q_text（文-文=1.0）；t_img ⟂ q_img（图-图=0）；
    cc = min(t2i, i2t) = 0 ≤ CC_LOW → 触底。
    """
    old = settings.CROSS_PENALTY_ENABLED
    settings.CROSS_PENALTY_ENABLED = False
    try:
        s_off = clip_service.compute_weighted_similarity(_TEXT, _TEXT, _IMG, _TEXT)
    finally:
        settings.CROSS_PENALTY_ENABLED = old
    s_on = clip_service.compute_weighted_similarity(_TEXT, _TEXT, _IMG, _TEXT)
    assert s_on < s_off, f"文本撞车未被惩罚（on={s_on}, off={s_off}）"
    assert abs(s_on - s_off * settings.CROSS_PENALTY_FLOOR) < 1e-6


def test_penalty_not_triggered_when_image_also_high():
    """图-图同样高 → 图像证据独立支持，**不得惩罚**（原实现会误伤）。

    这正是「拿原图搜」与「图文混合」被无谓压低的原因。
    """
    old = settings.CROSS_PENALTY_ENABLED
    settings.CROSS_PENALTY_ENABLED = False
    try:
        s_off = clip_service.compute_weighted_similarity(_IMG, _TEXT, _IMG, _TEXT)
    finally:
        settings.CROSS_PENALTY_ENABLED = old
    s_on = clip_service.compute_weighted_similarity(_IMG, _TEXT, _IMG, _TEXT)
    assert s_on == s_off, f"图-图高时仍被惩罚（on={s_on}, off={s_off}）"


def test_penalty_disabled_returns_one():
    """总开关关闭 → 不惩罚。"""
    old = settings.CROSS_PENALTY_ENABLED
    settings.CROSS_PENALTY_ENABLED = False
    try:
        assert clip_service._cross_penalty(0.0, 1.0, 0.0, 0.0) == 1.0
    finally:
        settings.CROSS_PENALTY_ENABLED = old


# --------------------------------------------------------------------------- #
# E. 证据链（等级 / 依据 / 展示分）
# --------------------------------------------------------------------------- #
def test_evidence_confirmed_on_identical_image():
    """图-图 = 1.0 → 等级「确定为同一物品」，展示分 1.0，依据 image_match。"""
    ev = clip_service.build_evidence(1.0, None, 0.238)
    assert ev["level"] == "confirmed"
    assert ev["basis"] == ["image_match"]
    assert abs(ev["reference_score"] - 1.0) < 1e-9


def test_evidence_confirmed_on_identical_text():
    """文-文 = 1.0 → 等级 confirmed，展示分 1.0，依据 text_match。"""
    ev = clip_service.build_evidence(None, 1.0, 0.27)
    assert ev["level"] == "confirmed"
    assert ev["basis"] == ["text_match"]
    assert abs(ev["reference_score"] - 1.0) < 1e-9


def test_evidence_reference_score_is_strongest_channel():
    """展示分取**最强证据通道**（不被弱通道稀释）。"""
    ev = clip_service.build_evidence(0.80, 0.65, 0.2724)
    assert abs(ev["reference_score"] - 0.80) < 1e-9
    assert ev["level"] == "high_suspect"


def test_evidence_empty_channels_is_reference():
    """全通道缺失 → reference，展示分 0。"""
    ev = clip_service.build_evidence(None, None, None)
    assert ev["level"] == "reference"
    assert ev["reference_score"] == 0.0


def test_evidence_high_suspect_basis_excludes_low_image():
    """图-图 低（< MATCH_EVIDENCE_IMG_MIN）→ 依据**不得**含 image_match（2026-10-15 修复）。

    修复前 image_match 是「通道存在即进依据」：文-文 0.70 高、图-图 0.2 低时，
    用户会看到「文字描述高度吻合、图像高度一致」——后半句与事实相反。
    """
    ev = clip_service.build_evidence(0.2, 0.70, 0.21)
    assert ev["level"] == "high_suspect"
    assert ev["basis"] == ["text_match"]


def test_evidence_high_suspect_basis_includes_high_image():
    """图-图 高（≥ MATCH_EVIDENCE_IMG_MIN）→ 依据同时含 image_match 与 text_match。"""
    ev = clip_service.build_evidence(0.80, 0.65, 0.238)
    assert ev["level"] == "high_suspect"
    assert ev["basis"] == ["image_match", "text_match"]


# --------------------------------------------------------------------------- #
# F. 标定层与线上同口径
# --------------------------------------------------------------------------- #
def test_score_pair_matches_main_aux_semantics(no_penalty):
    cache = _EncoderCache(_OrthoEncoder())
    assert abs(score_pair(cache, _pair_full()) - 1.5 / 1.75) < 1e-6


def test_score_pair_vs_target_same_semantics(no_penalty):
    cache = _EncoderCache(_OrthoEncoder())
    q = {"image": "uploads/q.jpg", "text": "描述"}
    t = {"item_id": 1, "item_ref": "uploads/t.jpg", "text": "目标描述"}
    assert abs(score_pair_vs_target(cache, q, t) - 1.5 / 1.75) < 1e-6


def test_text_only_query_in_calibration(no_penalty):
    cache = _EncoderCache(_OrthoEncoder())
    assert abs(score_pair(cache, _pair_text_only()) - 0.75) < 1e-6
