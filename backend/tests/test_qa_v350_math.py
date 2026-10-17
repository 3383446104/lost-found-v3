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

    手算（**主辅权重**，2026-09-21 修订）：q_text=e0, t_img=e0(→t2i=1), t_text=e1(→tt=0)
    文字检索模式：文-文 主 0.75 × 0 + 跨模态 辅 0.25 × mapped(1.0)=1.0 ⇒ 0.25 / 1.0 = 0.25。
    """
    q_text, t_img, t_text = _e(0), _e(0), _e(1)
    score = clip_service.compute_weighted_similarity(None, q_text, t_img, t_text)
    assert score == pytest.approx(0.25, abs=1e-6)
    # 若实现误把跨模态挂在 img1 上（要求 has_ii），此处会退化为 0.0
    assert score > 0.24


def test_A_image_query_vs_text_and_image_target(no_penalty):
    """纯图查询 × (有图有文) 目标：只走 has_ii + has_i2t。

    手算（**主辅权重**，2026-09-21 修订）：q_img=e0, t_img=e0(→ii=1), t_text=e1(→i2t=0)
    图片检索模式：图-图 主 0.75 × 1.0 + 跨模态 辅 0.25 × mapped(0)=0 ⇒ 0.75 / 1.0 = 0.75。
    """
    q_img, t_img, t_text = _e(0), _e(0), _e(1)
    score = clip_service.compute_weighted_similarity(q_img, None, t_img, t_text)
    w_ii, w_cross = settings.MATCH_W_IMG_IMG, settings.MATCH_W_CROSS
    assert score == pytest.approx((w_ii * 1.0 + w_cross * 0.0) / (w_ii + w_cross), abs=1e-6)
    assert score == pytest.approx(0.75, abs=1e-6)


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
        img_weight=1.0, text_weight=0.0, cross_weight=0.0,
    )
    assert heavy == pytest.approx(1.0, abs=1e-6)


def test_A_cross_inner_default_weights_are_arithmetic_mean(no_penalty):
    """只覆盖 cross_weight、w_cross_t2i/i2t 用默认 → 跨模态内取两方向**算术平均**。

    t2i=0.2, i2t=0.8 → 平均 0.5（默认 w_t2i=w_i2t=0.5）。

    ⚠️ 2026-09-21：跨模态值先经**尺度映射**（0.194→0、0.298→1），
    本构造的 cross=0.5 已越过 HI 而**饱和到 1.0** ⇒ 断言 1.0。
    """
    q_text = _e(0)
    t_img = _mix(0, 1, 0.2)   # t2i = q_text·t_img = 0.2
    q_img = _e(0)
    t_text = _mix(0, 1, 0.8)  # i2t = q_img·t_text = 0.8
    score = clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
        img_weight=0.0, text_weight=0.0, cross_weight=1.0,
    )
    assert score == pytest.approx(1.0, abs=1e-6)


def test_A_cross_inner_weights_override(no_penalty):
    """跨模态内权重覆盖：t2i=1、i2t=0、w=(0.7,0.3) → cross=0.7 → 映射饱和到 1.0。

    ⚠️ 2026-09-21：0.7 越过映射上限 HI(0.298) ⇒ 断言 1.0（口径变更说明同上）。
    """
    score = clip_service.compute_weighted_similarity(
        _e(1), _e(0), _e(0), _e(0),
        img_weight=0.0, text_weight=0.0, cross_weight=1.0,
        w_cross_t2i=0.7, w_cross_i2t=0.3,
    )
    assert score == pytest.approx(1.0, abs=1e-6)


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
    # 2026-09-21：触发条件收窄为「文-文高 且 图-图不高」→ 第 1 参 sim_ii 传 0.0
    assert clip_service._cross_penalty(0.0, 1.0, 0.0, 0.0) == pytest.approx(floor, abs=1e-9)
    assert clip_service._cross_penalty(0.0, 1.0, lo, lo) == pytest.approx(floor, abs=1e-9)
    assert clip_service._cross_penalty(0.0, 1.0, hi, hi) == pytest.approx(1.0, abs=1e-9)
    assert clip_service._cross_penalty(0.0, 1.0, 1.0, 1.0) == pytest.approx(1.0, abs=1e-9)
    mid = (lo + hi) / 2.0
    assert clip_service._cross_penalty(0.0, 1.0, mid, mid) == pytest.approx(
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
    # 门限由「文-文」判定（2026-09-21 收窄）；sim_ii 固定传 0.0 以免触发「图-图高不罚」
    assert clip_service._cross_penalty(0.0, high - 1e-6, 0.0, 0.0) == 1.0
    assert clip_service._cross_penalty(0.0, 0.0, 0.0, 0.0) == 1.0
    # 恰好等于门限 → 触发（cc=0 → 触底）
    assert clip_service._cross_penalty(0.0, high, 0.0, 0.0) == pytest.approx(
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
    # 2026-09-21：sim_ii 传 0.0（图-图高会阻断惩罚），由 sim_tt 满足触发门限
    assert clip_service._cross_penalty(0.0, 1.0, 0.05, 0.9) == pytest.approx(
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
    """「文本撞车」场景：文-文=1.0 而 图-图=0 → 惩罚触发，恰好腰斩。

    2026-09-21 触发条件收窄：仅当「文-文高 **且** 图-图不高」时惩罚
    （图-图同样高说明图像证据独立支持，不再误伤）。
    构造：q_img=q_text=e0；t_img=e1（ii=0）、t_text=e0（tt=1.0）；
    t2i=e0·e1=0、i2t=e0·e0=1.0 → cross=0.5 → 映射饱和 1.0。
    base_off = (0.75*1 + 0.75*0 + 0.25*1) / 1.75 = 1/1.75 = 4/7。
    """
    q_img, q_text = _e(0), _e(0)
    t_img, t_text = _e(1), _e(0)
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    base_off = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", True)
    base_on = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
    assert base_off == pytest.approx(4 / 7, abs=1e-6)
    assert base_on == pytest.approx(base_off * settings.CROSS_PENALTY_FLOOR, abs=1e-6)


def test_A_cross_weights_are_keyword_only():
    """新增跨模态权重必须是关键字专用（位置参数不得错位）。

    位置形参共 11 个（img1..text_weight）；多传第 12 个位置实参必须触发 TypeError。
    """
    over_limit = [None] * 11 + [0.5]  # 12 个位置实参
    with pytest.raises(TypeError):
        clip_service.compute_weighted_similarity(*over_limit)
