"""跨模态打分单测（T05）——不加载真实模型。

覆盖设计 §5.1：
- 纯文搜命中「仅图无文」目标（核心修复：``q_text · t_img``）；
- 纯图 / 图文混合三输入分支；
- 缺维度动态归一化（剔除不可用通道，权重和恒为 1，全缺 → 0.0）；
- 跨模态方向内权重（``w_cross_t2i`` / ``w_cross_i2t``）；
- 缺图缺文不抛异常。
"""
import numpy as np
import pytest

from app.clip_service import clip_service
from app.config import settings


def _u(*coords):
    """构造 512 维单位向量：在指定下标（0-based）上放 1.0。"""
    v = np.zeros(512, dtype=np.float32)
    for c in coords:
        v[c] = 1.0
    return v / np.linalg.norm(v)


def _mix(i, j, cosine):
    """构造位于 e_i / e_j 张成平面、与 e_i 夹角余弦 = cosine 的 512 维单位向量。"""
    v = np.zeros(512, dtype=np.float32)
    v[i] = cosine
    v[j] = float(np.sqrt(max(0.0, 1.0 - cosine * cosine)))
    return v / np.linalg.norm(v)


@pytest.fixture
def no_penalty(monkeypatch):
    """关闭阶段5 惩罚，隔离出「跨模态合成 + 动态归一化」的纯效果。"""
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)


# --------------------------------------------------------------------------- #
# 三输入分支
# --------------------------------------------------------------------------- #
def test_text_only_hits_image_only_target():
    """纯文搜：目标仅有图片（无 text_vector）→ 调用 q_text·t_img 仍能命中。"""
    q_text = _u(0)
    t_img = _u(0)          # 与 q_text 完全对齐 → sim_cross_t2i = 1.0
    score = clip_service.compute_weighted_similarity(
        None, q_text, t_img, None,
    )
    assert score == pytest.approx(1.0, abs=1e-6)


def test_image_only_query_against_text_target():
    """纯图搜：目标仅有文字 → 调用 q_img·t_text 仍能命中。"""
    q_img = _u(1)
    t_text = _u(1)
    score = clip_service.compute_weighted_similarity(
        q_img, None, None, t_text,
    )
    assert score == pytest.approx(1.0, abs=1e-6)


def test_image_only_query_against_image_only_target(no_penalty):
    """纯图搜仅图目标：``sim_img_img`` 通道接通 → 1.0。

    对应评测集 R1 结论——「同图自比」恒为 1.0，故该 6 对已从标定计算剔除，
    本用例仅证明 ``sim_ii`` 通道被正确触发。
    """
    q_img = _u(2)
    t_img = _u(2)
    score = clip_service.compute_weighted_similarity(
        q_img, None, t_img, None,
    )
    assert score == pytest.approx(1.0, abs=1e-6)


def test_mixed_input_uses_all_channels(no_penalty):
    """图文混合：四通道融合。构造 img_img=1.0、text_text=1.0、cross=0、color 缺。

    R-T2（v3.5.0）：手算锁定 expected 为**字面常量**，不再 ``settings.*`` 镜像引用——
    若有人误改 ``MATCH_W_*`` 而忘记同步测试，期望值会与代码**不一致**地报错。
    """
    q_img = _u(0)
    t_img = _u(0)
    q_text = _u(1)
    t_text = _u(1)
    score = clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
    )
    # 公式手算（**主辅权重**，2026-09-21 修订；颜色通道已废弃）：
    #   主证据：文-文 0.75、图-图 0.75；辅助：跨模态 0.25（先做尺度映射）
    #   sim_ii        = q_img·e0 · t_img·e0   = 1.0
    #   sim_tt        = q_text·e1 · t_text·e1  = 1.0
    #   sim_cross     = 0（t2i=i2t=0；映射后仍 0，低于 LO 被夹到 0）
    #   阶段1 cat/loc 全空 → 加分 0；阶段5 已被 no_penalty 关闭
    #   ⇒ expected = (0.75*1 + 0.75*1 + 0.25*0) / (0.75+0.75+0.25)
    #              = 1.5 / 1.75 = 6/7 ≈ 0.8571428571
    expected = 6 / 7
    assert score == pytest.approx(expected, abs=1e-6)


# --------------------------------------------------------------------------- #
# 动态归一化
# --------------------------------------------------------------------------- #
def test_missing_dimension_reweights_to_one(no_penalty):
    """缺颜色维度：权重按比例分摊给可用通道，效果 = 加权平均。"""
    q_img, t_img = _u(0), _u(2)      # img_img = 0.0
    q_text, t_text = _u(1), _u(1)    # text_text = 1.0
    score = clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)
    w_ii, w_tt, w_cross = (
        settings.MATCH_W_IMG_IMG,
        settings.MATCH_W_TEXT_TEXT,
        settings.MATCH_W_CROSS,
    )
    # cross: t2i = q_text·t_img = e1·e2 = 0；i2t = q_img·t_text = e0·e1 = 0 → cross = 0
    expected = (w_ii * 0.0 + w_cross * 0.0 + w_tt * 1.0) / (w_ii + w_cross + w_tt)
    assert score == pytest.approx(expected, abs=1e-6)


def test_all_channels_missing_returns_zero():
    """全缺（查询与目标都无图无文无颜色）→ 0.0，不抛异常。"""
    assert clip_service.compute_weighted_similarity(None, None, None, None) == 0.0


def test_color_channel_only():
    """仅颜色输入 → **0.0**（2026-09-16：颜色通道已废弃，不产生任何得分）。

    原语义为「仅颜色可用 → 退回颜色余弦（1.0）」；颜色通道整体废弃后本用例方向反转，
    用于守卫「颜色不得再参与打分」——若颜色被误恢复，此处会退回 1.0 而失败。
    """
    c = np.ones(27, dtype=np.float32)
    c = c / np.linalg.norm(c)
    assert clip_service.compute_weighted_similarity(color1=c, color2=c) == pytest.approx(0.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# 跨模态方向内权重
# --------------------------------------------------------------------------- #
def test_cross_direction_weights(no_penalty):
    """cross 内 t2i/i2t 方向按权重加权平均。

    构造：t2i = 1.0、i2t = 0.0；外层仅保留 cross（其余权重置 0）。

    ⚠️ 2026-09-21 口径变更：跨模态值现在会先做**尺度映射**（0.194→0、0.298→1），
    本构造的原始 cross = 0.7×1 + 0.3×0 = 0.7 已**越过 HI 而饱和到 1.0**。
    因此本用例断言 1.0；内部方向权重的**线性**效果由
    ``test_calibrate_color_channel.py::test_cross_mapping_*`` 覆盖（用落在映射区间内的余弦）。
    """
    q_text, t_img = _u(0), _u(0)     # t2i = 1.0
    q_img, t_text = _u(1), _u(0)     # i2t = q_img·t_text = e1·e0 = 0
    score = clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
        img_weight=0.0, text_weight=0.0, color_weight=0.0, cross_weight=1.0,
        w_cross_t2i=0.7, w_cross_i2t=0.3,
    )
    # 公式手算：
    #   sim_cross_t2i = q_text·e0 · t_img·e0  = 1.0
    #   sim_cross_i2t = q_img·e1 · t_text·e0  = 0
    #   sim_cross     = (0.7*1 + 0.3*0) / (0.7+0.3) = 0.7
    #   尺度映射：(0.7 - 0.194) / (0.298 - 0.194) = 4.87 → 夹到 1.0
    #   img/text 全置 0 ⇒ 最终 score = mapped(sim_cross) = 1.0
    expected = 1.0
    assert score == pytest.approx(expected, abs=1e-6)


def test_weights_are_keyword_only():
    """新增跨模态权重必须是关键字专用（位置参数不得错位）。"""
    with pytest.raises(TypeError):
        # 试图以位置参数传入 cross_weight（位于 ``*`` 之后）应报错
        clip_service.compute_weighted_similarity(
            None, None, None, None, "", "", "", "", 0, None, None, None, None, None, 0.5
        )
