# -*- coding: utf-8 -*-
"""打分口径 v2（v3.7.0）回归测试。

覆盖四件事（均为 2026-11-09 实测问题的回归锁）：

1. **单分数**：``score`` / ``content_score`` / ``reference_score`` 同源，
   杜绝「展示 0.7569、判定 0.5677」的双口径打架；
2. **标题独立向量优先**：全文向量被描述稀释时（房卡：标题 1.0000 / 全文 0.7569），
   取「更优者」而不是加权平均；但**仅在字面命中时启用**（V2_TITLE_GATE），
   否则短标题的各向异性会把「一个手机」顶到 0.7783；
3. **字面命中**：短文本各向异性下唯一确定性证据，分级 1.0 / 0.8 / 0.4 / 0；
4. **时间只进排序**：``ranking_score`` 随天数衰减，``score`` 不变
   （否则老物品会被阈值系统性挡掉）。

另含两条**兼容性**约束：
- ``text2 is None``（仅有图片的目标）时，标题通道必须整条关闭，
  否则残留 title_vector 会以 0 分稀释跨模态命中；
- ``MATCH_SCORING_MODE="legacy"`` 时旧三分数语义不变（可回滚）。
"""
import os
import sys

import numpy as np
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import settings, match_threshold  # noqa: E402

# 正交基：e0=文本方向、e2=图像方向、e3=无关方向
E0 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
E2 = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)
E3 = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)


def _unit(x: float) -> np.ndarray:
    """在与 E0 夹角余弦为 ``x`` 的方向上构造单位向量。"""
    return np.array([x, float(np.sqrt(max(0.0, 1.0 - x * x))), 0.0, 0.0], dtype=np.float32)


@pytest.fixture
def v2(monkeypatch):
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    return settings


# --------------------------------------------------------------------------- #
# A. 单分数
# --------------------------------------------------------------------------- #
def test_v2_single_score_three_fields_identical(v2):
    """v2 下三个分数字段必须完全一致（只有一个分数）。"""
    d = clip_service.compute_match_detail(
        None, E0, E2, E0, days_old=120,
        target_title="房卡", query_text="房卡",
    )
    assert d["scoring_mode"] == "v2"
    assert d["score"] == d["content_score"] == d["reference_score"]
    # 排序分因时间衰减严格更小，但那是**排序**口径，不是第二个判定分
    assert d["ranking_score"] <= d["score"]


def test_v2_empty_channels_returns_zero(v2):
    d = clip_service.compute_match_detail(None, None, None, None)
    assert d["score"] == 0.0


# --------------------------------------------------------------------------- #
# B. 标题独立向量：取更优者，而非平均
# --------------------------------------------------------------------------- #
def test_v2_title_beats_diluted_full_text(v2):
    """标题 1.0000 + 全文 0.7569 → 文本通道取 1.0000（不是 0.8785 的平均）。

    复刻房卡（id=67）：描述「丢失一个宿舍钥匙」把标题稀释成嵌合体。
    """
    title_vec = E0                 # sim_title = 1.0
    text2 = _unit(0.7569)          # sim_text_text = 0.7569
    d = clip_service.compute_match_detail(
        None, E0, None, text2,
        title_vec2=title_vec,
        query_text="房卡", target_title="房卡", target_desc="丢失一个宿舍钥匙",
    )
    assert abs(d["channels"]["sim_text_title"] - 1.0) < 1e-6
    assert abs(d["channels"]["sim_text_text"] - 0.7569) < 1e-6
    # 只有文本通道可用 → base = 1.0；字面完全命中 → +0.15，封顶 1.0
    assert d["score"] == pytest.approx(1.0, abs=1e-6)


def test_v2_title_channel_gated_when_no_text_vector(v2):
    """目标无 text_vector 时，残留 title_vector **不得**以 0 分稀释跨模态命中。"""
    d = clip_service.compute_match_detail(
        None, E0, E0, None,
        title_vec2=E3,             # 与查询正交（若参与会拉低）
        query_text="黑色钱包", target_title="仅图目标",
    )
    assert d["channels"]["sim_text_title"] is None
    # 仅跨模态 t2i = 1.0 → 缺通道归一化后 base = 1.0
    assert d["score"] == pytest.approx(1.0, abs=1e-6)


# --------------------------------------------------------------------------- #
# C. 字面命中分级
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("query,title,desc,expected", [
    ("房卡", "房卡", "丢失一个宿舍钥匙", 1.0),      # 完全一致
    ("房卡", "蓝色房卡套", "", 0.8),                # 标题包含
    ("宿舍钥匙", "蓝色宿舍钥匙扣", "", 0.8),        # 标题包含（无需分词）
    ("房卡", "学生证", "捡到一张房卡", 0.4),         # 仅描述命中
    ("房卡", "学生证", "捡到一张卡片", 0.0),         # 无重合
    ("", "房卡", "", 0.0),                          # 空查询
])
def test_v2_literal_hit_levels(query, title, desc, expected):
    assert clip_service._literal_hit(query, title, desc) == expected


def test_v2_literal_bonus_is_capped(v2):
    """基础分已接近 1 时，字面加分不得越界。"""
    d = clip_service.compute_match_detail(
        None, E0, E0, E0, title_vec2=E0,
        query_text="房卡", target_title="房卡",
    )
    assert d["score"] <= 1.0


# --------------------------------------------------------------------------- #
# D. 时间只影响排序
# --------------------------------------------------------------------------- #
def test_v2_time_decay_only_affects_ranking(v2):
    fresh = clip_service.compute_match_detail(None, E0, None, E0, days_old=0,
                                              query_text="x", target_title="x")
    old = clip_service.compute_match_detail(None, E0, None, E0, days_old=200,
                                            query_text="x", target_title="x")
    assert old["score"] == fresh["score"], "判定分不得随时间变化"
    assert old["ranking_score"] < fresh["ranking_score"], "排序分应体现时效"
    floor = float(settings.V2_TIME_DECAY_FLOOR)
    assert old["ranking_score"] == pytest.approx(old["score"] * floor, abs=1e-6)


# --------------------------------------------------------------------------- #
# E. 阈值按口径分派
# --------------------------------------------------------------------------- #
def test_v2_legend_uses_v2_thresholds(monkeypatch):
    from app.api.items import resolve_legend
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "MATCH_LEGEND_HIGH", None)
    monkeypatch.setattr(settings, "MATCH_LEGEND_MID", None)
    monkeypatch.setattr(settings, "V2_THRESHOLD_AUTO", 0.66)
    monkeypatch.setattr(settings, "V2_THRESHOLD_MANUAL", 0.44)
    assert resolve_legend() == {"high": 0.66, "mid": 0.44}
    assert match_threshold("manual") == 0.44
    assert match_threshold("auto") == 0.66


def test_threshold_rejects_unknown_kind(v2):
    with pytest.raises(KeyError):
        match_threshold("nope")


# --------------------------------------------------------------------------- #
# F. legacy 口径可回滚（三分数语义不变）
# --------------------------------------------------------------------------- #
def test_legacy_mode_keeps_three_distinct_scores(monkeypatch):
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "legacy")
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    d = clip_service.compute_match_detail(None, E0, None, E0, days_old=120)
    assert d["scoring_mode"] == "legacy"
    # 旧口径：score 含时间衰减，content_score 不含 → 两者不同
    assert d["score"] < d["content_score"]
    assert d["ranking_score"] == d["score"]


# --------------------------------------------------------------------------- #
# G. 标题通道信任门槛（V2_TITLE_GATE）
# --------------------------------------------------------------------------- #
def test_v2_title_gate_default_is_literal():
    """默认必须是字面门控（真实库 FP 61.9% → 19.0%，见 config 注释）。"""
    assert settings.V2_TITLE_GATE == "literal"


def test_v2_title_gate_blocks_nonliteral_title_vector(monkeypatch):
    """复刻「搜房卡带出一个手机」：未字面命中时标题余弦 0.7783 不得参与。

    标题通道给 0.7783，全文只有 0.4571 —— 常开时会越过手动阈值（旧 0.6919），
    门控后退回全文 0.4571，明确落在阈值之下。
    """
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_TITLE_GATE", "literal")
    d = clip_service.compute_match_detail(
        None, E0, None, _unit(0.4571),
        title_vec2=_unit(0.7783),
        query_text="房卡", target_title="一个手机", target_desc="",
    )
    assert d["literal_hit"] == 0.0
    assert d["score"] == pytest.approx(0.4571, abs=1e-4)
    assert d["score"] < settings.V2_THRESHOLD_MANUAL


def test_v2_title_gate_literal_hit_keeps_title_channel(monkeypatch):
    """字面命中（≥0.8）时标题通道照常生效 —— 门控不是把通道关死。"""
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_TITLE_GATE", "literal")
    d = clip_service.compute_match_detail(
        None, E0, None, _unit(0.7569),
        title_vec2=E0,                      # 标题余弦 1.0
        query_text="房卡", target_title="房卡", target_desc="丢失一个宿舍钥匙",
    )
    assert d["literal_hit"] == 1.0
    assert d["channels"]["sim_text_title"] == pytest.approx(1.0, abs=1e-6)
    assert d["score"] > d["channels"]["sim_text_text"]


def test_v2_title_gate_always_restores_old_behavior():
    """``title_gate="always"`` 精确复现门控前的行为（消融对比用）。"""
    common = dict(sim_tt=0.4571, sim_title=0.7783, sim_ii=None, literal=0.0)
    gated = clip_service.compute_score_v2(**common, title_gate="literal")
    always = clip_service.compute_score_v2(**common, title_gate="always")
    assert gated == pytest.approx(0.4571, abs=1e-4)
    assert always == pytest.approx(0.7783, abs=1e-4)


# --------------------------------------------------------------------------- #
# H. 等级与判定分同源（v3.7.0 修复「69% + 高度疑似」）
# --------------------------------------------------------------------------- #
def test_level_follows_score_bands(monkeypatch):
    """v2 的 level 由判定分决定，与三档阈值一一对应。"""
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_THRESHOLD_MANUAL", 0.60)
    monkeypatch.setattr(settings, "V2_THRESHOLD_AUTO", 0.75)
    monkeypatch.setattr(settings, "V2_THRESHOLD_EMAIL", 0.85)
    assert clip_service._level_from_score(0.90) == "confirmed"
    assert clip_service._level_from_score(0.80) == "high_suspect"
    assert clip_service._level_from_score(0.65) == "related"
    assert clip_service._level_from_score(0.40) == "reference"


def test_weak_match_is_not_labelled_high_suspect(monkeypatch):
    """回归：文-文 0.68（> 证据阈值 0.606）但判定分只有 0.68 时不得标「高度疑似」。

    复刻「笔记本 × 学生证」：短标题余弦虚高（0.84）让旧 build_evidence 判成
    high_suspect，而单一判定分只有 0.697 —— 界面自相矛盾。
    """
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_THRESHOLD_MANUAL", 0.6763)
    monkeypatch.setattr(settings, "V2_THRESHOLD_AUTO", 0.7685)
    monkeypatch.setattr(settings, "V2_THRESHOLD_EMAIL", 0.85)

    d = clip_service.compute_match_detail(
        None, E0, None, _unit(0.68),   # sim_tt = 0.68
        query_text="笔记本", target_title="学生证", target_desc="",
    )
    assert d["score"] < settings.V2_THRESHOLD_AUTO
    assert d["level"] == "related", f"score={d['score']} 不应标高度疑似"


# --------------------------------------------------------------------------- #
# H. 等级与判定分同源（v3.7.0 修复「69% + 高度疑似」）
# --------------------------------------------------------------------------- #
def test_level_follows_score_bands(monkeypatch):
    """v2 的 level 由判定分决定，与三档阈值一一对应。"""
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_THRESHOLD_MANUAL", 0.60)
    monkeypatch.setattr(settings, "V2_THRESHOLD_AUTO", 0.75)
    monkeypatch.setattr(settings, "V2_THRESHOLD_EMAIL", 0.85)
    assert clip_service._level_from_score(0.90) == "confirmed"
    assert clip_service._level_from_score(0.80) == "high_suspect"
    assert clip_service._level_from_score(0.65) == "related"
    assert clip_service._level_from_score(0.40) == "reference"


def test_weak_match_is_not_labelled_high_suspect(monkeypatch):
    """回归：文-文 0.68（> 证据阈值 0.606）但判定分只有 0.68 时不得标「高度疑似」。

    复刻「笔记本 × 学生证」：短标题余弦虚高（0.84）让旧 build_evidence 判成
    high_suspect，而单一判定分只有 0.697 —— 界面自相矛盾。
    """
    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_THRESHOLD_MANUAL", 0.6763)
    monkeypatch.setattr(settings, "V2_THRESHOLD_AUTO", 0.7685)
    monkeypatch.setattr(settings, "V2_THRESHOLD_EMAIL", 0.85)

    d = clip_service.compute_match_detail(
        None, E0, None, _unit(0.68),   # sim_tt = 0.68
        query_text="笔记本", target_title="学生证", target_desc="",
    )
    assert d["score"] < settings.V2_THRESHOLD_AUTO
    assert d["level"] == "related", f"score={d['score']} 不应标高度疑似"
