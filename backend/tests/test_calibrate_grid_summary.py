"""标定脚本「网格并列退化」契约测试（纯函数，不加载模型）。

背景（v3.5.0 真实权重实测暴露的第三处缺陷）
-------------------------------------------
``grid_search`` 的目标「Precision≥0.90 处最大化 Recall@3」在真实评测集上**大面积并列**：
实测 103 个合格组合里 102 个并列 ``Recall@3 = 1.0``。此时 Top-N 的**顺序纯属并列类的
任意代表**（= 网格枚举顺序），把它当成「最优权重排名」会得出不可复现的伪结论。

本文件锁死 :func:`summarize_grid` 的契约：它必须如实暴露合格集合的结构
（合格数 / 满分召回数 / 颜色直方图 / 各维度取值集合），供报告以「集合」而非
「排名」的方式解读。

作者：team-lead（齐活林）—— 修复者自留守卫。
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibrate_thresholds import summarize_grid  # noqa: E402


def _row(img, cross, text, color, r1, r3):
    return {
        "weights": {"img_img": img, "cross": cross, "text_text": text, "color": color},
        "auto_threshold": 0.5,
        "recall@1": r1,
        "recall@3": r3,
    }


def test_summary_counts_qualified_and_full_recall():
    """合格数 / 满分召回数必须如实统计。"""
    rows = [
        _row(0.05, 0.0, 0.95, 0.0, 0.7917, 1.0),
        _row(0.10, 0.0, 0.90, 0.0, 0.7917, 1.0),
        _row(0.05, 0.10, 0.85, 0.0, 0.75, 1.0),
        _row(0.30, 0.30, 0.20, 0.20, 0.7083, 0.9),  # 非满分召回
    ]
    s = summarize_grid(rows)
    assert s["n_qualified"] == 4
    assert s["n_full_recall"] == 3


def test_summary_color_histogram_only_over_full_recall():
    """颜色直方图只统计「满分召回」子集（并列出单调递减的证据）。"""
    rows = [
        _row(0.05, 0.0, 0.95, 0.00, 0.7917, 1.0),
        _row(0.05, 0.0, 0.95, 0.00, 0.7917, 1.0),
        _row(0.05, 0.05, 0.90, 0.05, 0.7917, 1.0),
        _row(0.05, 0.10, 0.85, 0.15, 0.75, 1.0),
        _row(0.30, 0.30, 0.20, 0.20, 0.7083, 0.9),  # 不计入（recall@3 != 1.0）
    ]
    s = summarize_grid(rows)
    assert s["color_hist_full_recall"] == {0.0: 2, 0.05: 1, 0.15: 1}
    assert s["max_color_full_recall"] == 0.15


def test_summary_per_dim_values_cover_all_qualified():
    """各维度取值集合取自**全部合格组合**（含非满分召回者）。"""
    rows = [
        _row(0.05, 0.0, 0.95, 0.00, 0.7917, 1.0),
        _row(0.35, 0.35, 0.15, 0.15, 0.7083, 0.9),
    ]
    s = summarize_grid(rows)
    assert s["per_dim_values"]["img_img"] == [0.05, 0.35]
    assert s["per_dim_values"]["color"] == [0.0, 0.15]
    assert s["per_dim_values"]["cross"] == [0.0, 0.35]
    assert s["recall1_values"] == [0.7083, 0.7917]


def test_summary_empty_is_safe():
    """空集合不得抛异常（None 安全）。"""
    s = summarize_grid([])
    assert s["n_qualified"] == 0
    assert s["n_full_recall"] == 0
    assert s["color_hist_full_recall"] == {}
    assert s["max_color_full_recall"] is None
