"""标定脚本「候选集」契约回归测试。

背景（v3.5.0 真实权重首次可用时才暴露的缺陷）
------------------------------------------------
``calibrate_thresholds._candidates()`` 原按 ``item_ref or text`` 去重。
但**同一条物品在评测集不同 pair 里的表达方式不同**：

- 纯文查询对（如 P01~P04）给的是 ``target.item_ref``（图片）；
- 图片查询对（如 P21~P24）给的是 ``target.text``（且 ``item_ref=null``）,
  因为它们要单独压 ``sim_cross_i2t``。

于是**同一条物品被拆成两个候选**（实测 10 个候选 = 6 条物品 + 4 条幻影重复），
两个副本可用通道不同 → 打分不同 → **正确的目标被自己的幻影副本挤出 Top-3**
→ Recall@1/@3 被算成 **0.0**（真实为 0.7917 / 1.0），并触发了一次**错误的**
「🚨 阻塞性发现：Recall@3 < 0.90」。

该缺陷**只在真实编码器下才显现**：``--fake-encoder --limit 6`` 冒烟时前 6 对全是
image-keyed，压根造不出重复 —— 又一个「桩路径掩盖真实路径」的实例。

本文件锁死修复后的契约：
  1. ``_candidate_key`` 以 ``item_id`` 为身份键；
  2. ``_candidates`` 按身份去重**并合并**同一条物品的字段（补图 / 补文）；
  3. 真实评测集上的候选数 == 去重后的物品数（直接锁住那次回归）。

作者：team-lead（齐活林）—— 修复者自留守卫。
"""
import json
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibrate_thresholds import (  # noqa: E402
    DEFAULT_EVAL_SET,
    _candidate_key,
    _candidates,
    _target_key,
    load_eval_set,
)


# --------------------------------------------------------------------------- #
# 1. 身份键
# --------------------------------------------------------------------------- #
def test_candidate_key_prefers_item_id():
    """有 item_id 时以 item_id 为身份（即便 item_ref 不同）。"""
    a = {"item_id": 64, "item_ref": "uploads/a.jpg", "text": "蓝牙耳机"}
    b = {"item_id": 64, "item_ref": None, "text": "蓝牙耳机"}
    assert _candidate_key(a) == 64
    assert _candidate_key(b) == 64
    assert _candidate_key(a) == _candidate_key(b)  # 同一物品 → 同一身份


def test_candidate_key_falls_back_to_target_key():
    """无 item_id 时退回 ``_target_key``（向后兼容）。"""
    t = {"item_id": None, "item_ref": "uploads/x.jpg", "text": "伞"}
    assert _candidate_key(t) == _target_key(t) == "uploads/x.jpg"


# --------------------------------------------------------------------------- #
# 2. 合成评测集：复现原缺陷的病理形态（同一物品：一次带图、一次只带文）
# --------------------------------------------------------------------------- #
def _synthetic_eval_set():
    return {
        "pairs": [
            # 物品 1：带图
            {"id": "P01", "label": 1,
             "query": {"text": "白色耳机", "image": None},
             "target": {"item_id": 1, "item_ref": "uploads/1.jpg", "text": "蓝牙耳机"}},
            # 物品 1：只带文（item_ref=null）→ 修复前会产生幻影副本
            {"id": "P02", "label": 1,
             "query": {"text": None, "image": "uploads/1.jpg"},
             "target": {"item_id": 1, "item_ref": None, "text": "蓝牙耳机"}},
            # 物品 2：只带文
            {"id": "P03", "label": 0,
             "query": {"text": "学生证", "image": None},
             "target": {"item_id": 2, "item_ref": None, "text": "学生证"}},
        ]
    }


def test_candidates_not_duplicated_for_same_item():
    """同一条物品不得因表达方式不同而被拆成两个候选（原缺陷的直接回归）。"""
    cands = _candidates(_synthetic_eval_set())
    keys = [c["item_id"] for c in cands]
    assert keys == [1, 2], "同一 item_id 必须只出现一次，实际 %r" % (keys,)
    assert len(cands) == 2


def test_candidates_merge_fields_from_all_pairs():
    """去重后须补全字段：既要有图（来自 P01）又要有文（来自 P02）。"""
    cands = _candidates(_synthetic_eval_set())
    item1 = next(c for c in cands if c["item_id"] == 1)
    assert item1["item_ref"] == "uploads/1.jpg"   # 图片被补上
    assert item1["text"] == "蓝牙耳机"             # 文字保留
    item2 = next(c for c in cands if c["item_id"] == 2)
    assert item2["item_ref"] is None and item2["text"] == "学生证"


# --------------------------------------------------------------------------- #
# 3. 真实评测集：候选数 == 去重物品数（锁住那次 0.0 → 1.0 的回归）
# --------------------------------------------------------------------------- #
def test_real_eval_set_candidate_count_matches_distinct_items():
    """真实评测集上候选数必须等于去重后的物品数（修复前为 10 vs 6）。"""
    if not os.path.isfile(DEFAULT_EVAL_SET):
        pytest.skip("评测集不存在")
    es = load_eval_set(DEFAULT_EVAL_SET)

    cands = _candidates(es)
    distinct = {p["target"]["item_id"] for p in es["pairs"]}
    assert len(cands) == len(distinct), (
        "候选数 %d != 去重物品数 %d —— 候选集出现重复计数（Recall@K 会被低估）"
        % (len(cands), len(distinct))
    )


def test_real_eval_set_every_positive_target_is_a_candidate():
    """每个正样本的 own 身份必须存在于候选集中，否则其 rank 必为 len+1（虚低）。"""
    if not os.path.isfile(DEFAULT_EVAL_SET):
        pytest.skip("评测集不存在")
    es = load_eval_set(DEFAULT_EVAL_SET)
    keys = {_candidate_key(c) for c in _candidates(es)}
    missing = [
        p["id"] for p in es["pairs"]
        if int(p.get("label", 0)) == 1 and _candidate_key(p["target"]) not in keys
    ]
    assert not missing, "以下正样本的目标不在候选集中：%r" % (missing,)


def test_candidates_are_json_serializable_unique():
    """候选身份唯一（防御性：合并逻辑不得引入重复）。"""
    if not os.path.isfile(DEFAULT_EVAL_SET):
        pytest.skip("评测集不存在")
    es = json.loads(json.dumps(load_eval_set(DEFAULT_EVAL_SET)))
    keys = [_candidate_key(c) for c in _candidates(es)]
    assert len(keys) == len(set(map(str, keys)))
