"""消融脚本契约回归测试。

背景（2026-10-15，论文选题《基于加权融合相似度算法的校园失物检索系统》）
----------------------------------------------------------------------
论文算法章需要「单通道 vs 融合」的消融证据，否则「加权融合」只是口号。
本文件锁死 ``ablation_study.py`` 的结构契约：

1. 变体表固定为 6 行（3 单通道 + 等权 + 主辅加权 + 线上口径）；
2. ``run_ablation`` 每行输出 Recall@1/3/5/10 与手动/自动阈值口径指标；
3. ``channel_means`` 输出正/负样本各通道均值（尺度映射锚点验证素材）。

用 ``FakeEncoder``（确定性假向量，**不打开真实图片**）跑结构校验；
真实数字必须在真实 cn_clip 权重上重跑（``scripts/ablation_study.py``）。
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibrate_thresholds import _EncoderCache, _FakeEncoder  # noqa: E402
from ablation_study import (  # noqa: E402
    VARIANTS,
    channel_means,
    run_ablation,
    write_report,
)


def _make_eval_set() -> dict:
    """内联小评测集（路径不要求真实存在：FakeEncoder 只 hash 字符串）。"""
    return {
        "version": "test",
        "pairs": [
            {
                "id": "P01", "label": 1,
                "query": {"image": "uploads/q1.jpg", "text": "黑色保温杯"},
                "target": {"item_id": 1, "item_ref": "uploads/t1.jpg",
                           "text": "黑色保温杯 图书馆三楼"},
            },
            {
                "id": "P02", "label": 0,
                "query": {"image": "uploads/q2.jpg", "text": "校园卡"},
                "target": {"item_id": 2, "item_ref": "uploads/t2.jpg", "text": "蓝色雨伞"},
            },
            {
                "id": "P03", "label": 1,
                "query": {"image": None, "text": "无线耳机 白色"},
                "target": {"item_id": 3, "item_ref": "uploads/t3.jpg",
                           "text": "白色无线耳机 操场"},
            },
            {
                "id": "P04", "label": 1,
                "query": {"image": "uploads/q4.jpg", "text": None},
                "target": {"item_id": 3, "item_ref": None, "text": "白色无线耳机 操场"},
            },
        ],
    }


# --------------------------------------------------------------------------- #
# 1. 变体表契约
# --------------------------------------------------------------------------- #
def test_variant_table_locked():
    """变体表固定 6 行：3 单通道 + 等权 + 主辅加权 + 线上口径。"""
    names = [n for n, _, _ in VARIANTS]
    assert names == [
        "text_only",
        "img_only",
        "cross_only",
        "equal_fusion",
        "fused",
        "fused_online",
    ]


def test_variant_weights_are_zero_one():
    """非线上变体必须用 0/1 极值权重，保证「单通道」语义纯净。"""
    for name, weights, _ in VARIANTS:
        if weights is None:
            assert name in ("fused", "fused_online")
            continue
        assert set(weights.values()) <= {0.0, 1.0}
        assert set(weights.keys()) == {"text_text", "cross", "img_img"}


# --------------------------------------------------------------------------- #
# 2. run_ablation 输出契约
# --------------------------------------------------------------------------- #
def test_run_ablation_returns_one_row_per_variant():
    cache = _EncoderCache(_FakeEncoder())
    rows = run_ablation(_make_eval_set(), cache)
    assert [r["variant"] for r in rows] == [n for n, _, _ in VARIANTS]
    for r in rows:
        assert set(r["recall"].keys()) == {"recall@1", "recall@3", "recall@5", "recall@10"}
        for v in r["recall"].values():
            assert 0.0 <= v <= 1.0
        assert "manual_threshold" in r and "auto_threshold" in r
    # 融合类变体存在（论文对照的核心行）
    assert any(x["variant"] == "fused" for x in rows)
    assert any(x["variant"] == "fused_online" for x in rows)


def test_run_ablation_skips_degenerate_pairs():
    """同图自比退化对不得进入消融（sim_ii ≡ 1.0 虚高 Recall）。"""
    eval_set = _make_eval_set()
    eval_set["pairs"].append({
        "id": "P99", "label": 1, "degenerate_self": True,
        "query": {"image": "uploads/same.jpg", "text": None},
        "target": {"item_id": 99, "item_ref": "uploads/same.jpg", "text": None},
    })
    cache = _EncoderCache(_FakeEncoder())
    rows = run_ablation(eval_set, cache)
    # 结构上不可观测「被剔除」本身，但必须不崩且仍返回全变体（防御性契约）
    assert len(rows) == len(VARIANTS)


# --------------------------------------------------------------------------- #
# 3. channel_means 输出契约
# --------------------------------------------------------------------------- #
def test_channel_means_structure():
    cache = _EncoderCache(_FakeEncoder())
    means = channel_means(_make_eval_set(), cache)
    assert set(means.keys()) == {"positive", "negative"}
    for side in means.values():
        # 跨模态均值必须存在（尺度映射锚点验证的关键素材）
        assert "sim_cross" in side
        for v in side.values():
            assert -1.0 <= v <= 1.0


def test_channel_means_all_one_with_constant_vectors():
    """FakeEncoder 输出常向量 → 一切余弦 = 1.0（桩的已知性质，锁死以防换桩无感）。"""
    cache = _EncoderCache(_FakeEncoder())
    means = channel_means(_make_eval_set(), cache)
    for side in means.values():
        for v in side.values():
            assert abs(v - 1.0) < 1e-6


# --------------------------------------------------------------------------- #
# 4. 报告写出
# --------------------------------------------------------------------------- #
def test_write_report_smoke(tmp_path):
    cache = _EncoderCache(_FakeEncoder())
    rows = run_ablation(_make_eval_set(), cache)
    means = channel_means(_make_eval_set(), cache)
    out = tmp_path / "ablation.md"
    write_report(str(out), rows, means, fake_encoder=True)
    text = out.read_text(encoding="utf-8")
    assert "通道消融实验报告" in text
    assert "--fake-encoder" in text
    for name, _, _ in VARIANTS:
        assert name in text
    assert "尺度映射锚点验证" in text
