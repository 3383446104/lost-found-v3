# -*- coding: utf-8 -*-
"""同义词/别名词典（v3.7.0）回归测试。

覆盖四件事：

1. 词典本身的结构约束（单字、跨组重复、组内包含 —— 任一出现都会让规则静默失效）；
2. ``alias_hit`` 的语义：同组不同词才算命中，同词不算，跨组不串；
3. 与 ``_literal_hit`` 的接口：同义命中记 0.8（能放行 V2_TITLE_GATE），
   仅描述同义记 0.4；
4. ``V2_SYNONYM_ENABLED=false`` 能整口径关掉，便于消融。
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import settings  # noqa: E402
from app.utils import synonyms  # noqa: E402


# --------------------------------------------------------------------------- #
# A. 词典结构
# --------------------------------------------------------------------------- #
def test_every_term_has_at_least_two_chars():
    for t in synonyms.all_terms():
        assert len(t) >= 2, f"单字词条会把无关项卷进来: {t!r}"


def test_no_term_belongs_to_two_groups():
    total = sum(len(g) for g in synonyms.SYNONYM_GROUPS)
    assert total == len(synonyms.all_terms()), "存在跨组重复词条"


def test_no_group_member_is_substring_of_another():
    """同组内若 A 是 B 的子串，子串逻辑会先命中，词典规则形同虚设。"""
    for g in synonyms.SYNONYM_GROUPS:
        for a in g:
            for b in g:
                if a != b:
                    assert a not in b, f"{a!r} 是 {b!r} 的子串"


def test_canonical_maps_to_group_head():
    assert synonyms.canonical("一卡通") == "校园卡"
    assert synonyms.canonical("课本") == "教材"
    assert synonyms.canonical("外套") == "外套", "词典外的词应原样返回"


# --------------------------------------------------------------------------- #
# B. alias_hit 语义
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("q,t", [
    ("校园卡", "一卡通"),
    ("饭卡", "一卡通"),
    ("课本", "高等数学教材"),
    ("充电宝", "移动电源"),
    ("耳机仓", "白盒子耳机盒"),
    ("折叠伞", "蓝色雨伞"),
    ("书包", "黑色双肩包"),
    ("我的校园卡丢了", "一卡通"),          # 整句查询
])
def test_alias_hit_positive(q, t):
    assert synonyms.alias_hit(q, t) is True


@pytest.mark.parametrize("q,t", [
    ("校园卡", "校园卡"),                  # 同词——由子串/完全匹配处理
    ("校园卡", "学生证"),                  # 不同实物，词典里不该有关系
    ("充电线", "充电宝"),                  # 同前缀不同物
    ("水杯", "水杯套"),                    # 目标包含查询 → 子串逻辑负责
    ("宿舍钥匙", "房卡"),                  # 无关
])
def test_alias_hit_negative(q, t):
    assert synonyms.alias_hit(q, t) is False


def test_hit_detail_explains_pair():
    hit, why = synonyms.hit_detail("课本", "高等数学教材")
    assert hit and "≡" in why


# --------------------------------------------------------------------------- #
# C. 与 _literal_hit 的接口
# --------------------------------------------------------------------------- #
def test_literal_hit_alias_on_title_is_08(monkeypatch):
    monkeypatch.setattr(settings, "V2_SYNONYM_ENABLED", True)
    assert clip_service._literal_hit("校园卡", "一卡通", "") == 0.8


def test_literal_hit_alias_on_desc_is_04(monkeypatch):
    monkeypatch.setattr(settings, "V2_SYNONYM_ENABLED", True)
    assert clip_service._literal_hit("课本", "一卡通", "内含高数课本一本") == 0.4


def test_literal_hit_exact_still_wins(monkeypatch):
    monkeypatch.setattr(settings, "V2_SYNONYM_ENABLED", True)
    assert clip_service._literal_hit("校园卡", "校园卡", "") == 1.0


def test_synonym_switch_off(monkeypatch):
    """关掉词典后回到纯子串语义（消融用）。"""
    monkeypatch.setattr(settings, "V2_SYNONYM_ENABLED", False)
    assert clip_service._literal_hit("校园卡", "一卡通", "") == 0.0
    assert clip_service._literal_hit("校园卡", "校园卡", "") == 1.0


# --------------------------------------------------------------------------- #
# D. 门控联动：同义命中要能放行标题向量
# --------------------------------------------------------------------------- #
def test_alias_bonus_is_discounted(monkeypatch):
    """同义命中：强度 0.8（放行门控），但加分系数只有 0.3。

    2026-11-10 实测：词典对同类负样本同样命中（课本×办公软件教材），
    全额加分把「同类负样本最高分」从 0.7774 抬到 0.8554，越过邮件阈值 0.85。
    故只放行通道，不放大加分。
    """
    monkeypatch.setattr(settings, "V2_SYNONYM_ENABLED", True)
    level, scale = clip_service.literal_features("校园卡", "一卡通", "")
    assert level == 0.8
    assert scale == pytest.approx(0.3)
    # 确定性字面不打折
    assert clip_service.literal_features("校园卡", "校园卡", "")[1] == 1.0
    assert clip_service.literal_features("房卡", "蓝色房卡套", "")[1] == 1.0


def test_alias_bonus_smaller_than_contains_bonus():
    """同样的 base：包含命中 +0.12，同义命中只有 +0.036。"""
    common = dict(sim_tt=0.60, sim_title=None, sim_ii=None)
    s_alias = clip_service.compute_score_v2(**common, literal=0.8, literal_scale=0.3)
    s_contains = clip_service.compute_score_v2(**common, literal=0.8, literal_scale=1.0)
    assert s_alias == pytest.approx(0.636, abs=1e-3)
    assert s_contains == pytest.approx(0.720, abs=1e-3)
    assert s_contains - s_alias > 0.08


def test_alias_hit_opens_title_gate(monkeypatch):
    """查询「校园卡」× 标题「一卡通」：同义命中 → 标题向量参与打分。"""
    import numpy as np

    monkeypatch.setattr(settings, "MATCH_SCORING_MODE", "v2")
    monkeypatch.setattr(settings, "V2_TITLE_GATE", "literal")
    monkeypatch.setattr(settings, "V2_SYNONYM_ENABLED", True)

    e0 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    weak = np.array([0.45, float(np.sqrt(1 - 0.45 ** 2)), 0.0, 0.0], dtype=np.float32)

    d = clip_service.compute_match_detail(
        None, e0, None, weak,
        title_vec2=e0,                       # 标题余弦 1.0
        query_text="校园卡", target_title="一卡通", target_desc="",
    )
    assert d["literal_hit"] == 0.8
    assert d["channels"]["sim_text_title"] == pytest.approx(1.0, abs=1e-6)
    # 文本通道取 max(1.0, 0.45)=1.0，加字面加分后封顶
    assert d["score"] > 0.8
