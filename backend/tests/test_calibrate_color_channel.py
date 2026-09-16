"""三通道打分口径回归测试（2026-09-16 修订：颜色通道**已废弃**）。

背景
----
用户决策（2026-09-16）：打分通道收敛为三个 —— ①文-文 ②图文跨模态（双向合并）
③图-图；**各自独立、等权**（``MATCH_W_* = 1.0``，缺通道按可用集合动态归一化 →
数学上等价于「可用通道的算术平均」）。**颜色通道彻底废弃**：
``compute_weighted_similarity`` 仍保留 ``color1/color2/color_weight`` 形参以兼容
冻结接口与既有调用点，但**内部一律忽略**。

本文件锁死两点：
  A. **服务层**：
     - 三通道等权 ⇒ 得分 = 可用通道的算术平均；
     - 缺通道不进入分母；
     - **颜色向量即使传入也不影响任何得分**（废弃生效的守卫）。
  B. **标定层**：``score_pair`` / ``score_pair_vs_target`` 与线上同口径
     （三通道、无颜色）；得分**不随** ``color`` 权重变化。

历史注记
--------
v3.5.0 期间本文件守卫的是反方向命题（「颜色通道必须传入，否则 ``W_COLOR`` 惰性」，
源于一次「桩路径掩盖真实路径」的缺陷）。颜色通道整体移除后，该守卫**方向反转**为
「颜色不参与打分」——断言强度不变，仍是精确值比较（不放宽 tolerance）。

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

from calibrate_thresholds import (  # noqa: E402
    _EncoderCache,
    score_pair,
    score_pair_vs_target,
)

# 正交构造，使各通道取值互不相同、便于精确断言：
#   查询文 = [1,0]、目标文 = [1,0] → sim_tt   = 1.0
#   查询图 = [0,1]、目标图 = [0,1] → sim_ii   = 1.0
#   t2i = 查询文·目标图 = 0.0；i2t = 查询图·目标文 = 0.0 → sim_cross = 0.0
_TEXT_VEC = np.array([1.0, 0.0], dtype=np.float32)
_IMG_VEC = np.array([0.0, 1.0], dtype=np.float32)


class _OrthogonalEncoder:
    """文/图两个模态取正交向量，使 sim_tt 与 sim_ii 可精确区分、cross 恒 0。"""

    name = "three-channel-fake"
    model_name = "three-channel-fake"

    def encode_text(self, text):
        return _TEXT_VEC.copy()

    def encode_image(self, path):
        return _IMG_VEC.copy()


def _pair_full():
    """三通道全可用（查询图文 + 目标图文）。"""
    return {
        "id": "T-full",
        "label": 1,
        "query": {"image": "uploads/q.jpg", "text": "白色耳机"},
        "target": {"item_id": 1, "item_ref": "uploads/t.jpg", "text": "蓝牙耳机"},
    }


def _pair_text_only_query():
    """纯文查询（无查询图）→ 只有 文-文 与 图文跨模态 两个通道可用。"""
    return {
        "id": "T-text",
        "label": 1,
        "query": {"image": None, "text": "白色耳机"},
        "target": {"item_id": 1, "item_ref": "uploads/t.jpg", "text": "蓝牙耳机"},
    }


@pytest.fixture
def no_penalty(monkeypatch):
    """关闭跨模态一致性惩罚，使断言只针对「三通道等权」本身。

    注意：开启惩罚时，本文件的构造会让 cc=0（cross 恒 0）且 sim_tt=1.0 ≥ 0.55
    → 得分被 ×0.5（见 test_penalty_applies_on_top_of_three_channels）。
    """
    from app.config import settings

    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)


# --------------------------------------------------------------------------- #
# A. 服务层语义
# --------------------------------------------------------------------------- #
def test_service_three_channels_arithmetic_mean(no_penalty):
    """三通道全可用且等权 ⇒ 得分 = (sim_tt + sim_cross + sim_ii) / 3 = (1+0+1)/3。"""
    from app.clip_service import clip_service

    s = clip_service.compute_weighted_similarity(
        _IMG_VEC, _TEXT_VEC, _IMG_VEC, _TEXT_VEC
    )
    assert abs(s - 2.0 / 3.0) < 1e-6, (
        f"三通道等权口径不符：期望 (1+0+1)/3={2.0 / 3.0:.6f}，实得 {s}"
    )


def test_service_missing_channel_excluded_from_denominator(no_penalty):
    """纯文查询（无查询图）⇒ 仅 文-文 与 图文跨模态 可用 ⇒ (1.0 + 0.0)/2 = 0.5。"""
    from app.clip_service import clip_service

    s = clip_service.compute_weighted_similarity(None, _TEXT_VEC, _IMG_VEC, _TEXT_VEC)
    assert abs(s - 0.5) < 1e-6, f"缺通道动态归一化口径不符：期望 0.5，实得 {s}"


def test_service_color_vectors_ignored_after_deprecation(no_penalty):
    """**废弃守卫**：传入颜色向量且 ``color_weight`` 拉满，得分必须**完全不变**。

    若颜色通道被误恢复为参与打分，本断言会失败（这正是它存在的意义）。
    """
    from app.clip_service import clip_service

    cq = np.array([1.0, 0.0], dtype=np.float32)
    ct = np.array([0.0, 1.0], dtype=np.float32)  # sim_col = 0（与 img/text 正交）
    s_without = clip_service.compute_weighted_similarity(
        _IMG_VEC, _TEXT_VEC, _IMG_VEC, _TEXT_VEC
    )
    s_with = clip_service.compute_weighted_similarity(
        _IMG_VEC, _TEXT_VEC, _IMG_VEC, _TEXT_VEC,
        color1=cq, color2=ct, color_weight=0.9,
    )
    assert s_without == s_with, (
        "颜色通道已废弃，但其向量/权重仍影响了得分 —— 废弃未生效"
        f"（不含色={s_without}, 含色={s_with}）"
    )
    # 服务层返回 round(base, 6)，故用容差比较而非精确 ==
    assert abs(s_without - 2.0 / 3.0) < 1e-6, f"三通道等权口径不符：{s_without}"


def test_service_no_channel_available_returns_zero():
    """全通道缺失 → 0.0（既有语义不变）。"""
    from app.clip_service import clip_service

    assert clip_service.compute_weighted_similarity(None, None, None, None) == 0.0


# --------------------------------------------------------------------------- #
# B. 标定层契约（与线上同口径）
# --------------------------------------------------------------------------- #
def test_score_pair_matches_three_channel_semantics(no_penalty):
    """``score_pair`` 三通道全可用 ⇒ (1+0+1)/3，与线上口径一致。"""
    cache = _EncoderCache(_OrthogonalEncoder())
    s = score_pair(cache, _pair_full())
    assert abs(s - 2.0 / 3.0) < 1e-6, f"score_pair 三通道口径不符：{s}"


def test_score_pair_vs_target_matches_three_channel_semantics(no_penalty):
    """``score_pair_vs_target``（Recall@K 排序用）与 :func:`score_pair` 同口径。"""
    cache = _EncoderCache(_OrthogonalEncoder())
    q = {"image": "uploads/q.jpg", "text": "白色耳机"}
    t = {"item_id": 1, "item_ref": "uploads/t.jpg", "text": "蓝牙耳机"}
    s = score_pair_vs_target(cache, q, t)
    assert abs(s - 2.0 / 3.0) < 1e-6, f"score_pair_vs_target 三通道口径不符：{s}"


def test_calibrate_scores_insensitive_to_color_weight():
    """标定层得分**不随** ``color`` 权重变化（颜色已废弃 ⇒ 传不传都无影响）。"""
    cache = _EncoderCache(_OrthogonalEncoder())
    w_color0 = {"text_text": 1.0, "cross": 1.0, "img_img": 1.0, "color": 0.0}
    w_color9 = {"text_text": 1.0, "cross": 1.0, "img_img": 1.0, "color": 0.9}
    assert score_pair(cache, _pair_full(), w_color0) == score_pair(cache, _pair_full(), w_color9)


def test_text_only_query_uses_two_channels_in_calibration(no_penalty):
    """纯文查询在标定层同样只走两通道 ⇒ (sim_tt + sim_t2i)/2 = (1.0 + 0.0)/2。"""
    cache = _EncoderCache(_OrthogonalEncoder())
    s = score_pair(cache, _pair_text_only_query())
    assert abs(s - 0.5) < 1e-6, f"纯文查询两通道口径不符：{s}"


def test_penalty_applies_on_top_of_three_channels():
    """阶段5 惩罚仍在工作：三通道等权 base=2/3，cc=0 且 sim_tt=1.0≥0.55 → ×0.5 = 1/3。"""
    from app.clip_service import clip_service

    s = clip_service.compute_weighted_similarity(
        _IMG_VEC, _TEXT_VEC, _IMG_VEC, _TEXT_VEC
    )
    assert abs(s - (2.0 / 3.0) * 0.5) < 1e-6, f"阶段5 惩罚未按预期作用：{s}"
