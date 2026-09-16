"""QA 独立回归（v3.5.0）——跨模态打分数学 & 阶段5 一致性惩罚。

策略：不依赖任何「桩向量语义」，直接对纯函数 ``compute_weighted_similarity`` /
``_cross_penalty`` 注入**小维度合成向量**并**手算期望值**对拍，从而能发现
「工程师测试与实现互相镜像（copy 同一公式）」掩盖的算法错误。

作者：yan-qa（独立验证，不修改任何源码）。
"""
import numpy as np
import pytest

from app.clip_service import clip_service
from app.config import settings

DIM = 512
CDIM = 27


# --------------------------------------------------------------------------- #
# 合成向量工具
# --------------------------------------------------------------------------- #
def _e(i: int, dim: int = DIM) -> np.ndarray:
    """第 i 个基向量（单位）。"""
    v = np.zeros(dim, dtype=np.float32)
    v[i] = 1.0
    return v


def _mix(i: int, j: int, cosine: float, dim: int = DIM) -> np.ndarray:
    """与 e_i 夹角余弦 = cosine 的单位向量（位于 e_i/e_j 平面）。"""
    v = np.zeros(dim, dtype=np.float32)
    v[i] = cosine
    v[j] = float(np.sqrt(max(0.0, 1.0 - cosine * cosine)))
    return v / np.linalg.norm(v)


@pytest.fixture
def no_penalty(monkeypatch):
    """关闭阶段5，隔离「跨模态合成 + 缺维度归一化」的纯效果。"""
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)


# --------------------------------------------------------------------------- #
# A. 通道可用性与手算对拍
# --------------------------------------------------------------------------- #
def test_A_text_query_vs_text_and_image_target(no_penalty):
    """纯文查询 × (有图有文) 目标：只走 has_tt + has_t2i（不含 ii/i2t）。

    手算（**三通道等权**，2026-09-16 修订）：q_text=e0, t_img=e0(→t2i=1), t_text=e1(→tt=0)
    仅 文-文 与 图文跨模态 两通道可用且等权 → (1*1 + 1*0)/2 = 0.5。
    """
    q_text, t_img, t_text = _e(0), _e(0), _e(1)
    score = clip_service.compute_weighted_similarity(None, q_text, t_img, t_text)
    assert score == pytest.approx(0.5, abs=1e-6)
    # 若实现误把跨模态挂在 img1 上（要求 has_ii），此处会退化为 0.0
    assert score > 0.49


def test_A_image_query_vs_text_and_image_target(no_penalty):
    """纯图查询 × (有图有文) 目标：只走 has_ii + has_i2t。

    手算：q_img=e0, t_img=e0(→ii=1), t_text=e1(→i2t=0)。
    (0.35*1 + 0.35*0)/(0.7) = 0.5。
    """
    q_img, t_img, t_text = _e(0), _e(0), _e(1)
    score = clip_service.compute_weighted_similarity(q_img, None, t_img, t_text)
    w_ii, w_cross = settings.MATCH_W_IMG_IMG, settings.MATCH_W_CROSS
    assert score == pytest.approx((w_ii * 1.0 + w_cross * 0.0) / (w_ii + w_cross), abs=1e-6)
    assert score == pytest.approx(0.5, abs=1e-6)


def test_A_mixed_query_vs_mixed_target_all_four(no_penalty):
    """图文查询 × 图文目标：四方向全通。(0.35*1 + 0.35*0 + 0.15*1)/(0.85)。"""
    score = clip_service.compute_weighted_similarity(_e(0), _e(1), _e(0), _e(1))
    w_ii, w_cross, w_tt = (
        settings.MATCH_W_IMG_IMG,
        settings.MATCH_W_CROSS,
        settings.MATCH_W_TEXT_TEXT,
    )
    expected = (w_ii * 1.0 + w_cross * 0.0 + w_tt * 1.0) / (w_ii + w_cross + w_tt)
    assert score == pytest.approx(expected, abs=1e-6)


def test_A_all_channels_missing_returns_zero_not_nan():
    """全缺 → 0.0，不抛异常、不 NaN。"""
    v = clip_service.compute_weighted_similarity(None, None, None, None)
    assert v == 0.0
    assert not np.isnan(v)


def test_A_single_channel_equals_its_own_similarity(no_penalty):
    """缺维度动态归一化：只通 has_ii（sim=0.8）→ 结果必须**恰为 0.8**。

    这是最容易被算错的地方——若分母没有剔除不可用通道，结果会被 w_ii=0.35 稀释成 0.28。
    """
    q_img, t_img = _e(0), _mix(0, 1, 0.8)
    assert clip_service.compute_weighted_similarity(q_img, None, t_img, None) == pytest.approx(0.8, abs=1e-6)


def test_A_single_channel_only_color(no_penalty):
    """只通颜色通道 → **0.0**（2026-09-16：颜色通道已废弃，不产生任何得分）。

    原断言为「恰为颜色余弦（0.5）」；废弃后方向反转，守卫颜色不得参与打分。
    """
    score = clip_service.compute_weighted_similarity(color1=_e(0, CDIM), color2=_mix(0, 1, 0.5, CDIM))
    assert score == pytest.approx(0.0, abs=1e-6)


def test_A_cross_not_diluted_after_color_deprecation(no_penalty):
    """纯文 × 仅图目标且**颜色向量传入**：颜色已废弃 → 不得稀释跨模态得分。

    2026-09-16 修订：原用例断言颜色把 t2i 稀释到 (0.35/0.5)=0.7；颜色通道废弃后
    只剩 cross 一个可用通道 → 得分恰为 t2i = 1.0。
    """
    q_text, t_img = _e(0), _e(0)
    col_a, col_b = _e(0, CDIM), _e(1, CDIM)  # 颜色向量传入但应被完全忽略
    score = clip_service.compute_weighted_similarity(
        None, q_text, t_img, None, color1=col_a, color2=col_b
    )
    assert score == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# A. 权重来源：None→settings / 传参覆盖 / 跨模态内权重
# --------------------------------------------------------------------------- #
def test_A_weights_default_from_settings_then_override(no_penalty):
    """默认权重来自 settings；显式覆盖后行为随之改变。"""
    q_img, q_text = _e(0), _e(1)
    t_img, t_text = _e(0), _e(2)  # ii=1.0；tt=0；cross=0
    base = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
    w_ii, w_cross, w_tt = (
        settings.MATCH_W_IMG_IMG,
        settings.MATCH_W_CROSS,
        settings.MATCH_W_TEXT_TEXT,
    )
    assert base == pytest.approx(w_ii / (w_ii + w_cross + w_tt), abs=1e-6)

    heavy = clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
        img_weight=1.0, text_weight=0.0, color_weight=0.0, cross_weight=0.0,
    )
    assert heavy == pytest.approx(1.0, abs=1e-6)


def test_A_cross_inner_default_weights_are_arithmetic_mean(no_penalty):
    """只覆盖 cross_weight、w_cross_t2i/i2t 用默认 → 跨模态内取两方向**算术平均**。

    t2i=0.2, i2t=0.8 → 平均 0.5（默认 w_t2i=w_i2t=0.5）。
    """
    q_text = _e(0)
    t_img = _mix(0, 1, 0.2)   # t2i = q_text·t_img = 0.2
    q_img = _e(0)
    t_text = _mix(0, 1, 0.8)  # i2t = q_img·t_text = 0.8
    score = clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
        img_weight=0.0, text_weight=0.0, color_weight=0.0, cross_weight=1.0,
    )
    assert score == pytest.approx(0.5, abs=1e-6)


def test_A_cross_inner_weights_override(no_penalty):
    """跨模态内权重覆盖：t2i=1、i2t=0、w=(0.7,0.3) → 0.7。"""
    score = clip_service.compute_weighted_similarity(
        _e(1), _e(0), _e(0), _e(0),
        img_weight=0.0, text_weight=0.0, color_weight=0.0, cross_weight=1.0,
        w_cross_t2i=0.7, w_cross_i2t=0.3,
    )
    assert score == pytest.approx(0.7, abs=1e-6)


# --------------------------------------------------------------------------- #
# B. 阶段5 惩罚
# --------------------------------------------------------------------------- #
def test_B_penalty_range_and_monotonic_full_sweep():
    """cc∈[0,1] 全扫：罚值 ∈ [FLOOR,1] 且对 cc 单调不减。"""
    floor = settings.CROSS_PENALTY_FLOOR
    prev = -1.0
    for i in range(0, 101):
        cc = i / 100.0
        p = clip_service._cross_penalty(1.0, 1.0, cc, cc)
        assert floor - 1e-9 <= p <= 1.0 + 1e-9, f"cc={cc} p={p}"
        assert p >= prev - 1e-12, f"非单调 @ cc={cc}"
        prev = p


def test_B_penalty_piecewise_exact():
    """分段线性精确值：cc≤LO→floor；cc≥HI→1；中点为 floor+(1-floor)/2。"""
    lo, hi, floor = (
        settings.CROSS_PENALTY_CC_LOW,
        settings.CROSS_PENALTY_CC_HIGH,
        settings.CROSS_PENALTY_FLOOR,
    )
    assert clip_service._cross_penalty(1.0, 1.0, 0.0, 0.0) == pytest.approx(floor, abs=1e-9)
    assert clip_service._cross_penalty(1.0, 1.0, lo, lo) == pytest.approx(floor, abs=1e-9)
    assert clip_service._cross_penalty(1.0, 1.0, hi, hi) == pytest.approx(1.0, abs=1e-9)
    assert clip_service._cross_penalty(1.0, 1.0, 1.0, 1.0) == pytest.approx(1.0, abs=1e-9)
    mid = (lo + hi) / 2.0
    assert clip_service._cross_penalty(1.0, 1.0, mid, mid) == pytest.approx(
        floor + (1.0 - floor) * 0.5, abs=1e-9
    )


def test_B_penalty_continuous_near_thresholds():
    """CC_LOW / CC_HIGH 邻域连续（无跳变）。"""
    lo, hi = settings.CROSS_PENALTY_CC_LOW, settings.CROSS_PENALTY_CC_HIGH
    eps = 1e-6
    assert abs(
        clip_service._cross_penalty(1.0, 1.0, lo - eps, lo - eps)
        - clip_service._cross_penalty(1.0, 1.0, lo + eps, lo + eps)
    ) < 1e-4
    assert abs(
        clip_service._cross_penalty(1.0, 1.0, hi - eps, hi - eps)
        - clip_service._cross_penalty(1.0, 1.0, hi + eps, hi + eps)
    ) < 1e-4


def test_B_penalty_trigger_gate():
    """>=SELF_HIGH 才触发；低于门限恒 1.0（不干预）。"""
    high = settings.CROSS_PENALTY_SELF_HIGH
    assert clip_service._cross_penalty(high - 1e-6, high - 1e-6, 0.0, 0.0) == 1.0
    assert clip_service._cross_penalty(0.0, 0.0, 0.0, 0.0) == 1.0
    # 恰好等于门限 → 触发（cc=0 → 触底）
    assert clip_service._cross_penalty(high, high, 0.0, 0.0) == pytest.approx(
        settings.CROSS_PENALTY_FLOOR, abs=1e-9
    )


def test_B_penalty_missing_directions_identity():
    """跨模态缺失 / 自相似缺失 → 恒 1.0。"""
    assert clip_service._cross_penalty(1.0, 1.0, None, None) == 1.0
    assert clip_service._cross_penalty(None, None, 0.0, 0.0) == 1.0
    assert clip_service._cross_penalty(None, None, None, None) == 1.0


def test_B_penalty_disabled_is_identity(monkeypatch):
    """开关关闭 → 任何输入恒 1.0。"""
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    for cc in (0.0, 0.05, 0.2, 0.5, 1.0):
        assert clip_service._cross_penalty(1.0, 1.0, cc, cc) == 1.0


def test_B_penalty_uses_min_of_directions():
    """cc = min(两方向)，不一致方向主导惩罚。"""
    assert clip_service._cross_penalty(1.0, 1.0, 0.05, 0.9) == pytest.approx(
        settings.CROSS_PENALTY_FLOOR, abs=1e-9
    )


def test_B_penalty_never_inflates_score_on_nonneg_base(monkeypatch):
    """非负 base 下：开启惩罚后的分数 ≤ 关闭时（只降权）。"""
    rng = np.random.default_rng(20240913)
    for _ in range(100):
        vecs = []
        for _c in range(4):
            v = np.abs(rng.standard_normal(DIM).astype(np.float32)) + 1e-3
            vecs.append(v / np.linalg.norm(v))
        q_img, q_text, t_img, t_text = vecs
        monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
        off = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
        monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", True)
        on = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
        assert on <= off + 1e-9


def test_B_integration_halves_inconsistent_pair(monkeypatch):
    """图文各向同性一致（ii=tt=1）但跨模态全 0 → cc=0 → 恰好腰斩。

    base_off = (1*1 + 1*0 + 1*1)/3 = 2/3（三通道等权，2026-09-16 修订）。
    """
    q_img, q_text = _e(0), _e(1)
    t_img, t_text = _e(0), _e(1)
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    base_off = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", True)
    base_on = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
    assert base_off == pytest.approx(2 / 3, abs=1e-6)
    assert base_on == pytest.approx(base_off * settings.CROSS_PENALTY_FLOOR, abs=1e-6)


def test_A_cross_weights_are_keyword_only():
    """新增跨模态权重必须是关键字专用（位置参数不得错位）。

    位置形参共 14 个（img1..color2）；多传第 15 个位置实参必须触发 TypeError。
    """
    over_limit = [None] * 14 + [0.5]  # 15 个位置实参
    with pytest.raises(TypeError):
        clip_service.compute_weighted_similarity(*over_limit)
