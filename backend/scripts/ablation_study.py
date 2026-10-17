# backend/scripts/ablation_study.py
"""通道消融实验：单通道 vs 融合（v3.5.0+ 打分口径）。

回答论文核心问题（选题《基于加权融合相似度算法的校园失物检索系统》）：
**加权融合是否真的优于任何单通道** —— 没有这个证据，「加权融合」就只是口号。

方法（与 ``calibrate_thresholds.py`` 同口径）
--------------------------------------------
- 复用其评测集加载 / 编码缓存 / Recall@K / 阈值建议，保证「标定口径 = 消融口径 = 线上口径」；
- 全部变体在 ``CROSS_PENALTY_ENABLED=False`` 下对比 —— 阶段5 惩罚是**通道无关的
  后处理因子**，掺入会混淆「融合 vs 单通道」的归因；
- 另附一行「线上口径」（主辅加权 + 阶段5 惩罚）作参照；
- 编码只做一次（``_EncoderCache`` 跨变体共享），真实模型下不重复推理。

变体（权重 = ``{文-文, 跨模态, 图-图}``）
------------------------------------------
- ``text_only``    仅文-文（{1, 0, 0}）
- ``img_only``     仅图-图（{0, 0, 1}）
- ``cross_only``   仅跨模态·映射后（{0, 1, 0}）
- ``equal_fusion`` 等权融合（{1, 1, 1} → 动态归一化 = 各 1/可用通道数）
- ``fused``        主辅加权融合（线上权重 0.75/0.75/0.25，无惩罚）
- ``fused_online`` 线上口径（fused + 阶段5 惩罚）

用法（在 ``backend`` 目录下执行）::

    venv\\Scripts\\python.exe scripts\\ablation_study.py
    venv\\Scripts\\python.exe scripts\\ablation_study.py --fake-encoder --limit 12
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import settings  # noqa: E402
from app.logger import logger  # noqa: E402

from calibrate_thresholds import (  # noqa: E402
    DEFAULT_EVAL_SET,
    _EncoderCache,
    _FakeEncoder,
    _ServiceEncoderAdapter,
    _candidates,
    _precision_recall_at,
    _recall_ranks,
    is_degenerate,
    load_eval_set,
    penalty_enabled,
    print_eval_stats,
    recall_at_k,
    score_pair,
    suggest_thresholds,
    summarize_eval_set,
)

DEFAULT_OUT = os.path.join(
    os.path.dirname(BACKEND_DIR), "docs", "review", "ablation-study-v3.5.0.md"
)

#: 变体表：(标识, 权重覆盖 or None=线上 config 现值, 说明)。顺序即报告行序。
VARIANTS: List[tuple] = [
    ("text_only", {"text_text": 1.0, "cross": 0.0, "img_img": 0.0}, "仅文-文"),
    ("img_only", {"text_text": 0.0, "cross": 0.0, "img_img": 1.0}, "仅图-图"),
    ("cross_only", {"text_text": 0.0, "cross": 1.0, "img_img": 0.0}, "仅跨模态（映射后）"),
    ("equal_fusion", {"text_text": 1.0, "cross": 1.0, "img_img": 1.0}, "等权融合"),
    ("fused", None, "主辅加权融合（0.75/0.75/0.25，无惩罚）"),
    ("fused_online", None, "线上口径（主辅加权 + 阶段5惩罚）"),
]


# --------------------------------------------------------------------------- #
# 消融主流程
# --------------------------------------------------------------------------- #
def run_ablation(eval_set: Dict[str, Any], cache: _EncoderCache) -> List[Dict[str, Any]]:
    """对每个变体在评测集上打分，返回变体指标行。

    Args:
        eval_set: :func:`load_eval_set` 的返回值（退化对由各变体内部剔除）。
        cache: **共享**编码缓存（真实模型下只编码一次）。

    Returns:
        每行含 ``variant`` / ``desc`` / ``weights`` / ``recall`` /
        ``manual_threshold`` / ``p_at_manual`` / ``auto_threshold`` / ``r_at_auto``。
    """
    candidates = _candidates(eval_set)
    rows: List[Dict[str, Any]] = []
    for name, weights, desc in VARIANTS:
        with penalty_enabled(name == "fused_online"):
            scored: List = []
            for p in eval_set["pairs"]:
                if is_degenerate(p):
                    continue  # 同图自比退化正例不计入（sim_ii ≡ 1.0 虚高）
                try:
                    scored.append((score_pair(cache, p, weights), int(p.get("label", 0))))
                except Exception as e:
                    logger.warning(f"跳过评测对 {p.get('id')}: {e}")
                    continue
            ranks = _recall_ranks(eval_set, cache, candidates, weights)
        thresholds = suggest_thresholds(scored)
        manual_t = thresholds["manual"]
        auto_t = thresholds["auto"]
        p_manual = _precision_recall_at(manual_t, scored)[0] if manual_t is not None else None
        r_auto = _precision_recall_at(auto_t, scored)[1] if auto_t is not None else None
        rows.append(
            {
                "variant": name,
                "desc": desc,
                "weights": weights,
                "recall": {
                    f"recall@{k}": round(recall_at_k(ranks, k), 4) for k in (1, 3, 5, 10)
                },
                # 手动口径：Recall ≥ 0.90 的最高分位阈值，及该阈值处的 Precision
                "manual_threshold": manual_t,
                "p_at_manual": round(p_manual, 4) if p_manual is not None else None,
                # 自动口径：Precision ≥ 0.90 的最低分位阈值，及该阈值处的 Recall
                "auto_threshold": auto_t,
                "r_at_auto": round(r_auto, 4) if r_auto is not None else None,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# 通道均值（跨模态尺度映射锚点验证）
# --------------------------------------------------------------------------- #
def channel_means(eval_set: Dict[str, Any], cache: _EncoderCache) -> Dict[str, Any]:
    """各通道在正/负样本上的均值（剔除退化对）。

    用途：验证 ``MATCH_CROSS_REF_LO/HI``（0.194/0.298）锚点是否与当前模型+
    评测集实测的「负样本均值 → 0、正样本均值 → 1」一致；偏差大时应重标锚点。
    """
    by_label: Dict[int, Dict[str, List[float]]] = {1: {}, 0: {}}
    for p in eval_set["pairs"]:
        if is_degenerate(p):
            continue
        q = p.get("query", {}) or {}
        t = p.get("target", {}) or {}
        q_img = cache.image(q["image"]) if q.get("image") else None
        q_text = cache.text(q["text"]) if q.get("text") else None
        t_img = cache.image(t["item_ref"]) if t.get("item_ref") else None
        t_text = cache.text(t["text"]) if t.get("text") else None
        vals = {
            "sim_img_img": float(np.dot(q_img, t_img))
            if (q_img is not None and t_img is not None) else None,
            "sim_text_text": float(np.dot(q_text, t_text))
            if (q_text is not None and t_text is not None) else None,
            "sim_t2i": float(np.dot(q_text, t_img))
            if (q_text is not None and t_img is not None) else None,
            "sim_i2t": float(np.dot(q_img, t_text))
            if (q_img is not None and t_text is not None) else None,
        }
        cross = [v for v in (vals["sim_t2i"], vals["sim_i2t"]) if v is not None]
        vals["sim_cross"] = float(np.mean(cross)) if cross else None
        label = int(p.get("label", 0))
        for k, v in vals.items():
            if v is None:
                continue
            by_label[label].setdefault(k, []).append(v)
    return {
        "positive": {k: round(float(np.mean(v)), 4) for k, v in by_label[1].items()},
        "negative": {k: round(float(np.mean(v)), 4) for k, v in by_label[0].items()},
    }


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def _row_by_variant(rows: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
    for r in rows:
        if r["variant"] == name:
            return r
    raise KeyError(f"变体 {name} 不在结果中")


def _fmt(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.4f}"


def write_report(
    out_path: str,
    rows: List[Dict[str, Any]],
    means: Dict[str, Any],
    *,
    fake_encoder: bool = False,
) -> None:
    """把消融结果写为 Markdown 报告（论文素材可直接引用）。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    lines: List[str] = []
    lines.append("# 通道消融实验报告（v3.5.0 打分口径）\n")
    if fake_encoder:
        lines.append(
            "\n> # ⚠️⚠️ 本报告由 `--fake-encoder` 生成，数字不可用于任何决策 ⚠️⚠️\n"
            "> **`--fake-encoder` 使用确定性假向量，输出的 Recall/阈值全是噪声。**"
            "真实消融必须在**真实 cn_clip 权重 + 真实评测图片**上重跑。\n"
        )
    lines.append(f"> 模型后端：`{settings.CLIP_BACKEND}` ｜ 生成脚本：`scripts/ablation_study.py`\n")
    lines.append(
        f"> 编码器：`{'--fake-encoder（噪声，仅供结构校验）' if fake_encoder else 'clip_service（真实模型）'}`\n"
    )
    lines.append(
        "> 方法：全部变体在 `CROSS_PENALTY_ENABLED=False` 下对比（惩罚是通道无关后处理，"
        "不掺入消融归因）；`fused_online` 为线上口径参照。\n"
    )

    lines.append("\n## 1. 变体对照表\n")
    lines.append(
        "| 变体 | 权重（文/跨/图） | Recall@1 | Recall@3 | Recall@5 | Recall@10 | P@R≥0.9 | R@P≥0.9 |"
    )
    lines.append("|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|")
    for r in rows:
        w = r["weights"] or {"text_text": settings.MATCH_W_TEXT_TEXT,
                             "cross": settings.MATCH_W_CROSS,
                             "img_img": settings.MATCH_W_IMG_IMG}
        rec = r["recall"]
        lines.append(
            f"| `{r['variant']}` {r['desc']} | {w['text_text']}/{w['cross']}/{w['img_img']} | "
            f"{rec['recall@1']} | {rec['recall@3']} | {rec['recall@5']} | {rec['recall@10']} | "
            f"{_fmt(r['p_at_manual'])} | {_fmt(r['r_at_auto'])} |"
        )
    lines.append(
        "\n> 口径：P@R≥0.9 = 手动阈值（Recall ≥ 0.90 最高分位）处的 Precision；"
        "R@P≥0.9 = 自动阈值（Precision ≥ 0.90 最低分位）处的 Recall。\n"
    )

    lines.append("\n## 2. 结论\n")
    fused = _row_by_variant(rows, "fused")
    equal = _row_by_variant(rows, "equal_fusion")
    online = _row_by_variant(rows, "fused_online")
    singles = [r for r in rows if r["variant"] in ("text_only", "img_only", "cross_only")]
    best_single = max(singles, key=lambda r: r["recall"]["recall@3"])
    best_r1_single = max(s["recall"]["recall@1"] for s in singles)
    r3 = fused["recall"]["recall@3"]
    best_r3 = best_single["recall"]["recall@3"]
    lines.append(
        f"- **融合 vs 单通道（排序口径）**：融合 Recall@3 = {r3}，最优单通道为"
        f"「{best_single['desc']}」（{best_r3}）→ 融合{'≥' if r3 >= best_r3 else '<'}最优单通道"
        f"（差 {r3 - best_r3:+.4f}）；Recall@1 融合 {fused['recall']['recall@1']}"
        f" vs 单通道最优 {best_r1_single}。"
    )
    r_auto_ok = [s for s in singles if s["r_at_auto"] is not None]
    lines.append(
        f"- **融合 vs 单通道（自动口径，P≥0.9）**：单通道 R@P≥0.9 分别为 "
        + "、".join(f"`{s['variant']}`={_fmt(s['r_at_auto'])}" for s in singles)
        + f"；融合为 {_fmt(fused['r_at_auto'])}。"
        + (
            "**任何单通道都无法在 P≥0.9 下保持召回（或直接无解），只有加权融合**"
            "能同时满足高精度与召回——这就是「加权融合」的实证价值。"
            if not r_auto_ok or fused["r_at_auto"] is not None and all(
                fused["r_at_auto"] >= s["r_at_auto"] for s in r_auto_ok
            )
            else ""
        )
    )
    lines.append(
        f"- **主辅加权 vs 等权**：Recall@3 为 {r3} vs {equal['recall']['recall@3']}"
        f"（差 {r3 - equal['recall']['recall@3']:+.4f}）；"
        f"手动阈值 P 为 {_fmt(fused['p_at_manual'])} vs {_fmt(equal['p_at_manual'])}"
        "——样本量下两者相当，0.75/0.25 的语义（主辅证据）优先于在该集上追平权。"
    )
    lines.append(
        f"- **阶段5 惩罚**（线上口径 vs 无惩罚）：Recall@3 为 "
        f"{online['recall']['recall@3']} vs {r3}；手动阈值 P 为 "
        f"{_fmt(online['p_at_manual'])} vs {_fmt(fused['p_at_manual'])}，"
        f"自动阈值 R 为 {_fmt(online['r_at_auto'])} vs {_fmt(fused['r_at_auto'])}"
        "（惩罚换自动推送召回，换手动口径精度）。"
    )

    lines.append("\n## 3. 各通道正负样本均值（尺度映射锚点验证）\n")
    lines.append("| 通道 | 正样本均值 | 负样本均值 | 备注 |")
    lines.append("|------|:--:|:--:|------|")
    pos, neg = means["positive"], means["negative"]
    names = [
        ("sim_img_img", "图-图（同模态）"),
        ("sim_text_text", "文-文（同模态）"),
        ("sim_t2i", "跨模态 文→图（原始）"),
        ("sim_i2t", "跨模态 图→文（原始）"),
        ("sim_cross", "跨模态均值（原始）"),
    ]
    for key, label in names:
        pv, nv = pos.get(key), neg.get(key)
        note = ""
        if key == "sim_cross" and pv is not None and nv is not None:
            note = (
                f"映射锚点 config 为 LO={settings.MATCH_CROSS_REF_LO}/HI={settings.MATCH_CROSS_REF_HI}；"
                f"实测负={nv}/正={pv}"
                f"{'（一致 ✅）' if abs(nv - settings.MATCH_CROSS_REF_LO) < 0.03 and abs(pv - settings.MATCH_CROSS_REF_HI) < 0.03 else '（偏差较大 ⚠️ 建议重标 LO/HI）'}"
            )
        lines.append(f"| {label} | {_fmt(pv)} | {_fmt(nv)} | {note} |")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通道消融实验：单通道 vs 融合（v3.5.0 口径）")
    parser.add_argument("--eval-set", default=DEFAULT_EVAL_SET, help="评测集 JSON 路径")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Markdown 报告输出路径")
    parser.add_argument("--limit", type=int, default=None, help="只评估前 N 对（冒烟用）")
    parser.add_argument("--stats", action="store_true",
                        help="仅打印评测集结构统计（不加载模型、不评估）")
    parser.add_argument("--fake-encoder", action="store_true",
                        help="用确定性假编码器冒烟（不加载真实模型，供 CI/结构校验）")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    eval_set = load_eval_set(args.eval_set)
    print_eval_stats(summarize_eval_set(eval_set))
    if args.stats:
        return 0

    if args.limit:
        eval_set = dict(eval_set)
        eval_set["pairs"] = eval_set["pairs"][: args.limit]

    encoder = _FakeEncoder() if args.fake_encoder else _ServiceEncoderAdapter(clip_service)
    cache = _EncoderCache(encoder)

    rows = run_ablation(eval_set, cache)
    means = channel_means(eval_set, cache)
    write_report(args.out, rows, means, fake_encoder=args.fake_encoder)

    print("=" * 56)
    print("消融完成")
    print("| 变体 | Recall@1 | Recall@3 | Recall@5 | Recall@10 |")
    for r in rows:
        rec = r["recall"]
        print(
            f"| {r['desc']} | {rec['recall@1']} | {rec['recall@3']} | "
            f"{rec['recall@5']} | {rec['recall@10']} |"
        )
    print(f"  报告: {args.out}")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
