# backend/scripts/calibrate_v2.py
"""打分口径 v2 标定与 A/B 对比（v3.7.0）。

做什么
------
在同一份评测集（``eval/eval_set_v3.5.0.json``）上，用**同一批向量**分别按
``legacy``（v3.6.x 五阶段）与 ``v2``（单分数 + 标题向量 + 字面命中）打分，输出：

1. ``Recall@1/3/5/10``（排序能力）
2. ``P@R>=0.90`` / ``R@P>=0.90``（业务阈值口径）
3. 两套建议阈值（手动 / 自动），回填 ``.env`` 用的就是它们
4. Markdown 报告，可直接作论文「消融实验」小节

为什么另起脚本而不改 ``calibrate_thresholds.py``
------------------------------------------------
旧脚本的 ``score_pair`` / ``score_pair_vs_target`` 被 4 个测试文件依赖（含
``test_scoring_regression.py`` 的 E 段），改签名会连带破坏 legacy 口径的回归锁。
本脚本**只读复用**其工具函数（``_EncoderCache`` / ``_candidates`` / ``is_degenerate``），
两套口径并存、互不污染 —— 这也正好是 A/B 对比需要的形态。

用法（在 ``backend`` 目录下执行）::

    venv\\Scripts\\python.exe scripts\\calibrate_v2.py
    venv\\Scripts\\python.exe scripts\\calibrate_v2.py --fake-encoder   # 不加载模型，冒烟
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
# ``app.config`` 以「相对 CWD」加载 .env（SECRET_KEY 必填）—— 固定到 backend/，
# 使脚本在任意 CWD 下可运行，避免「换个目录跑就 ValidationError」。
os.chdir(BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import settings  # noqa: E402

from calibrate_thresholds import (  # noqa: E402
    _candidate_key,
    _candidates,
    _EncoderCache,
    is_degenerate,
    load_eval_set,
)

DEFAULT_EVAL_SET = os.path.join(BACKEND_DIR, "eval", "eval_set_v3.5.0.json")
DEFAULT_OUT = os.path.join(BACKEND_DIR, "..", "docs", "review", "scoring-v2-ablation.md")

MODES = ("legacy", "v2", "v2_gate")

#: 口径 → 报告行名。``v2_gate`` 只比 ``v2`` 多一条「标题通道仅字面命中时生效」。
MODE_LABELS = {
    "legacy": "legacy（v3.6.x 五阶段）",
    "v2": "v2（单分数，标题通道常开）",
    "v2_gate": "v2+（单分数，标题通道字面门控）",
}


# --------------------------------------------------------------------------- #
# 特征
# --------------------------------------------------------------------------- #
def _dot(a, b) -> Optional[float]:
    if a is None or b is None:
        return None
    return float(np.dot(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))


def _split_title(target_text: Optional[str]) -> Tuple[str, str]:
    """评测集的 ``target.text`` = ``title + ' ' + description``，按首个空格切分。

    这是**近似**：评测集没有单独存 title 字段。切分偏保守（标题取首段），
    对「蓝牙耳机 白色蓝牙耳机」这类数据与生产一致。
    """
    text = (target_text or "").strip()
    if not text:
        return "", ""
    head, _, tail = text.partition(" ")
    return head, tail


def _score(mode: str, cache: _EncoderCache, query: Dict[str, Any],
           target: Dict[str, Any]) -> float:
    """按指定口径给一对 (query, target) 打分（纯内容尺度，不含类别/时间）。"""
    q_img = cache.image(query["image"]) if query.get("image") else None
    q_text = cache.text(query["text"]) if query.get("text") else None
    t_img = cache.image(target["item_ref"]) if target.get("item_ref") else None
    t_text = cache.text(target["text"]) if target.get("text") else None

    if mode == "legacy":
        return clip_service.compute_weighted_similarity(q_img, q_text, t_img, t_text)

    title, desc = _split_title(target.get("text"))
    # 与线上一致：目标无全文向量时整条文本通道关闭（title_vector 只是全文的细化）
    t_title_vec = cache.text(title) if (title and t_text is not None) else None
    lit, lit_scale = clip_service.literal_features(
        query.get("text") or "", title, desc)
    return clip_service.compute_score_v2(
        sim_tt=_dot(q_text, t_text),
        sim_title=_dot(q_text, t_title_vec),
        sim_ii=_dot(q_img, t_img),
        sim_t2i=_dot(q_text, t_img),
        sim_i2t=_dot(q_img, t_text),
        literal=lit,
        literal_scale=lit_scale,
        title_gate="literal" if mode == "v2_gate" else "always",
    )


# --------------------------------------------------------------------------- #
# 指标
# --------------------------------------------------------------------------- #
def _scored_rows(eval_set: Dict[str, Any], cache: _EncoderCache, mode: str):
    """逐对打分并保留元信息（标签 / 子类型 / 是否字面），供切片统计。"""
    rows = []
    for p in eval_set["pairs"]:
        if is_degenerate(p):
            continue
        rows.append({
            "score": _score(mode, cache, p.get("query", {}), p.get("target", {})),
            "label": int(p.get("label", 0)),
            "subtype": p.get("subtype") or ("literal" if p.get("literal_query") else "rewrite"),
            "literal": bool(p.get("literal_query")),
        })
    return rows


def _pair_scores(eval_set: Dict[str, Any], cache: _EncoderCache, mode: str,
                 *, include_literal: bool = False):
    """返回 ``[(score, label), ...]``（P/R 曲线用，跳过退化对）。

    v3.7.0：``literal_query`` 样本默认**排除**。它们的查询等于 title，
    分数天然接近 1.0，混进 P/R 会把 Precision 抬到接近 1、并把建议阈值压低
    （阈值随即在线上把改写查询全放进来）。字面查询的能力单独用
    「阈值通过率」度量（见 ``_literal_pass``），不参与阈值标定。
    """
    return [(r["score"], r["label"]) for r in _scored_rows(eval_set, cache, mode)
            if include_literal or not r["literal"]]


def _neg_slices(rows: List[Dict[str, Any]], threshold: Optional[float]) -> Dict[str, Any]:
    """负样本按子类型切片：均分 / 最高分 / 越阈值率（假阳性率）。

    为什么要切：跨类别负样本（一本书 vs 一副耳机）几乎不可能混淆，会把整体
    Precision 抬得好看；真正决定线上体验的是**同类负样本**（两副白色耳机盒）。
    只看总体 Precision，会得到「auto 阈值比 manual 还低」这种自相矛盾的结论。
    """
    out: Dict[str, Any] = {}
    for st in ("cross_category", "same_category", "image_query"):
        vals = [r["score"] for r in rows if r["label"] == 0 and r["subtype"] == st]
        if not vals:
            continue
        fp = sum(1 for v in vals if threshold is not None and v >= threshold)
        out[st] = {"n": len(vals), "mean": sum(vals) / len(vals), "max": max(vals),
                   "fp": fp, "fp_rate": fp / len(vals)}
    return out


def _literal_scores(eval_set: Dict[str, Any], cache: _EncoderCache, mode: str):
    """字面查询子集的得分（全为正样本）。"""
    return [
        _score(mode, cache, p.get("query", {}), p.get("target", {}))
        for p in eval_set["pairs"] if p.get("literal_query")
    ]


def _ranks(eval_set: Dict[str, Any], cache: _EncoderCache, mode: str,
           candidates: List[Dict[str, Any]]) -> List[int]:
    ranks = []
    for p in eval_set["pairs"]:
        if int(p.get("label", 0)) != 1 or is_degenerate(p) or p.get("literal_query"):
            continue
        query = p.get("query", {})
        own = _candidate_key(p.get("target", {}))
        scored = sorted(
            ((_score(mode, cache, query, c), _candidate_key(c)) for c in candidates),
            key=lambda x: x[0], reverse=True,
        )
        rank = len(scored) + 1
        for i, (_, key) in enumerate(scored, start=1):
            if key == own:
                rank = i
                break
        ranks.append(rank)
    return ranks


def _recall_at(ranks: List[int], k: int) -> float:
    return sum(1 for r in ranks if r <= k) / len(ranks) if ranks else 0.0


def _pr_at(scored: List[Tuple[float, int]], threshold: float) -> Tuple[float, float]:
    picked = [lab for s, lab in scored if s >= threshold]
    tp = sum(picked)
    precision = tp / len(picked) if picked else 0.0
    total_pos = sum(lab for _, lab in scored)
    recall = tp / total_pos if total_pos else 0.0
    return precision, recall


def _suggest(scored: List[Tuple[float, int]]) -> Dict[str, Optional[float]]:
    """按业务口径给阈值：manual = Recall≥0.90 的最高门槛；auto = Precision≥0.90 的最低门槛。"""
    grid = sorted({round(s, 6) for s, _ in scored}, reverse=True)
    manual = None
    for t in grid:                       # 从高到低，找第一个还满足 R≥0.9 的
        _, r = _pr_at(scored, t)
        if r >= 0.90:
            manual = t
            break
    auto = None
    for t in sorted(grid):               # 从低到高，找第一个满足 P≥0.9 的
        p, _ = _pr_at(scored, t)
        if p >= 0.90:
            auto = t
            break
    return {"manual": manual, "auto": auto}


def _evaluate(eval_set, cache, mode, candidates) -> Dict[str, Any]:
    rows = _scored_rows(eval_set, cache, mode)
    rewrite_rows = [r for r in rows if not r["literal"]]
    scored = [(r["score"], r["label"]) for r in rewrite_rows]
    ranks = _ranks(eval_set, cache, mode, candidates)
    sug = _suggest(scored)
    lit = [r["score"] for r in rows if r["literal"]]
    res = {
        "mode": mode,
        "n_pairs": len(scored),
        "n_items": len(candidates),
        "recall@1": _recall_at(ranks, 1),
        "recall@3": _recall_at(ranks, 3),
        "recall@5": _recall_at(ranks, 5),
        "recall@10": _recall_at(ranks, 10),
        "suggested": sug,
        "literal_n": len(lit),
        "literal_min": min(lit) if lit else None,
        "neg_slices": _neg_slices(rewrite_rows, sug["manual"]),
    }
    if sug["manual"] is not None:
        res["P@manual"], res["R@manual"] = _pr_at(scored, sug["manual"])
        if lit:
            res["literal_pass"] = sum(1 for s in lit if s >= sug["manual"]) / len(lit)
        # 「硬负样本 Precision」：只把同类负样本计入分母（跨类别负样本几乎不可能混淆，
        # 留在分母里等于给自己送分）。论文里报这个数比报总 Precision 诚实。
        thr = sug["manual"]
        tp = sum(1 for r in rewrite_rows if r["label"] == 1 and r["score"] >= thr)
        fp_same = sum(1 for r in rewrite_rows
                      if r["label"] == 0 and r["subtype"] == "same_category" and r["score"] >= thr)
        res["P_hard@manual"] = tp / (tp + fp_same) if (tp + fp_same) else None
    if sug["auto"] is not None:
        res["P@auto"], res["R@auto"] = _pr_at(scored, sug["auto"])
    return res


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def _fmt(x: Optional[float], digits: int = 4) -> str:
    return "—" if x is None else f"{x:.{digits}f}"


def render_markdown(results: Dict[str, Dict[str, Any]], eval_path: str,
                    backend_note: str) -> str:
    v2n = results["v2"]["n_pairs"]
    v2c = results["v2"].get("n_items", 0)
    lines = [
        "# 打分口径 A/B 对比（v2 单分数，v3.7.0）",
        "",
        f"> 评测集：`{os.path.relpath(eval_path, BACKEND_DIR)}` ｜ 编码器：{backend_note}",
        "> 生成脚本：`scripts/calibrate_v2.py`",
        "",
        "## 1. 指标对照",
        "",
        "| 口径 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | P@手动阈值 | R@自动阈值 |",
        "|---|:--:|:--:|:--:|:--:|:--:|:--:|",
    ]
    for mode in MODES:
        r = results[mode]
        lines.append(
            f"| {MODE_LABELS[mode]} | {_fmt(r['recall@1'])} | {_fmt(r['recall@3'])} | "
            f"{_fmt(r['recall@5'])} | {_fmt(r['recall@10'])} | "
            f"{_fmt(r.get('P@manual'))} | {_fmt(r.get('R@auto'))} |"
        )

    lines += [
        "",
        f"> 样本：{v2n} 对（**不含**字面查询子集）｜ 候选物品 {v2c} 件 ｜ "
        f"字面查询 {results['v2'].get('literal_n', 0)} 对（单独统计，见第 4 节）",
        "",
        "## 2. 建议阈值",
        "",
        "| 口径 | 手动（Recall ≥ 0.90） | 该点 Precision | 自动（Precision ≥ 0.90） | 该点 Recall |",
        "|---|:--:|:--:|:--:|:--:|",
    ]
    for mode in MODES:
        r = results[mode]
        lines.append(
            f"| {MODE_LABELS[mode]} | {_fmt(r['suggested']['manual'])} | {_fmt(r.get('P@manual'))} | "
            f"{_fmt(r['suggested']['auto'])} | {_fmt(r.get('R@auto'))} |"
        )

    # 自动阈值低于手动阈值 = 负样本太容易的典型信号，必须显式提示
    bad = [m for m in MODES
           if results[m]["suggested"]["auto"] is not None
           and results[m]["suggested"]["manual"] is not None
           and results[m]["suggested"]["auto"] < results[m]["suggested"]["manual"]]
    if bad:
        lines += [
            "",
            "> ⚠️ **自动阈值 < 手动阈值**（" + "、".join(MODE_LABELS[m].split("（")[0] for m in bad) + "）：",
            "> 说明本集的负样本偏易（跨类别占多数），`Precision ≥ 0.90` 在很低的分数就成立。",
            "> **不要**把本表的 auto 回填生产；生产阈值仍以 `eval_set_v3.5.0.json`（真实业务分布）为准。",
        ]

    lines += [
        "",
        "## 3. 负样本切片（越阈值率 = 假阳性率）",
        "",
        "跨类别负样本（一本书 vs 一副耳机）几乎不可能混淆，会把整体 Precision 抬得好看。",
        "真正决定线上体验的是**同类负样本**（两副白色耳机盒）。`P@硬负` 只把同类负样本计入分母。",
        "",
        "| 口径 | 跨类均分 | 跨类 FP | 同类均分 | 同类最高 | 同类 FP | P@硬负 |",
        "|---|:--:|:--:|:--:|:--:|:--:|:--:|",
    ]
    for mode in MODES:
        r = results[mode]
        ns = r.get("neg_slices") or {}
        cx = ns.get("cross_category") or {}
        sm = ns.get("same_category") or {}
        def _fp(d):
            return "—" if not d else f"{d['fp']}/{d['n']} ({d['fp_rate']:.1%})"
        lines.append(
            f"| {MODE_LABELS[mode]} | {_fmt(cx.get('mean'))} | {_fp(cx)} | "
            f"{_fmt(sm.get('mean'))} | {_fmt(sm.get('max'))} | {_fp(sm)} | "
            f"{_fmt(r.get('P_hard@manual'))} |"
        )

    lines += [
        "",
        "## 4. 字面查询子集（`literal_query=true`，**不参与阈值标定**）",
        "",
        "字面查询（用户直接输入「房卡」「蓝牙耳机」）的分数天然接近满分，混进 P/R 会把",
        "Precision 抬到接近 1、并把建议阈值压低。故单独度量：**手动阈值通过率**。",
        "",
        "| 口径 | 样本数 | 最低分 | 手动阈值通过率 |",
        "|---|:--:|:--:|:--:|",
    ]
    for mode in MODES:
        r = results[mode]
        lines.append(
            f"| {MODE_LABELS[mode]} | {r.get('literal_n', 0)} | "
            f"{_fmt(r.get('literal_min'))} | {_fmt(r.get('literal_pass'))} |"
        )

    lines += [
        "",
        "## 5. 口径差异（读表须知）",
        "",
        "- legacy：跨模态余弦经 `[LO, HI]` 线性映射后参与加权；时间衰减与跨模态惩罚为**乘法**后处理。",
        "- v2：跨模态用**仿射缩放但不截断**（`(x−LO)/(HI−LO)`）；文本通道取「标题 ∨ 全文」更优者；",
        "  字面命中加分；时间只进排序分，不影响判定分。",
        "- v2+：在 v2 基础上，标题向量**仅在字面命中时**才取代全文向量。"
        "依据是真实库上「一个手机」对查询「房卡」的标题余弦高达 0.7783（全文仅 0.4571），"
        "短标题的各向异性会把无关项顶过阈值。",
        "- 各口径**尺度不同**，只能比相对指标（Recall@K、P/R 曲线），不能直接比数值大小。",
        "",
        "## 6. 局限",
        "",
        "- 评测集正样本的改写查询被约束为「不得含目标 title 原词」，因此**字面特征在 P/R 上基本为 0**——",
        "  本报告**低估**了 v2 在真实字面查询上的收益；字面能力见第 3 节。",
        "- 有效样本量仍偏小，阈值属保守起点，须随数据增长复标。",
        "",
    ]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="打分口径 v2 标定与 A/B 对比")
    parser.add_argument("--eval-set", default=DEFAULT_EVAL_SET)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--fake-encoder", action="store_true", help="用确定性假编码器冒烟")
    args = parser.parse_args(argv)

    eval_set = load_eval_set(args.eval_set)
    candidates = _candidates(eval_set)

    if args.fake_encoder:
        from reembed_all_vectors import _ServiceEncoderAdapter  # noqa: F401
        class _Fake:
            name = "fake"
            model_name = "fake"

            def encode_text(self, text):
                seed = abs(hash(str(text))) % (2 ** 32)
                rng = np.random.default_rng(seed)
                v = rng.standard_normal(16).astype(np.float32)
                return v / np.linalg.norm(v)

            def encode_image(self, path):
                seed = abs(hash("img:" + str(path))) % (2 ** 32)
                rng = np.random.default_rng(seed)
                v = rng.standard_normal(16).astype(np.float32)
                return v / np.linalg.norm(v)

        encoder, note = _Fake(), "fake（冒烟，指标无意义）"
    else:
        from reembed_all_vectors import _ServiceEncoderAdapter
        adapter = _ServiceEncoderAdapter(clip_service)
        encoder = adapter
        note = f"`{adapter.name}` / `{adapter.model_name}`（真实模型）"

    cache = _EncoderCache(encoder)
    results = {mode: _evaluate(eval_set, cache, mode, candidates) for mode in MODES}

    report = render_markdown(results, args.eval_set, note)
    out_path = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\n[输出] {out_path}")

    print("\n[回填建议] 写入 .env（v2 口径）：")
    for mode in ("v2", "v2_gate"):
        r = results[mode]
        print(f"  # {MODE_LABELS[mode]}")
        print(f"  V2_THRESHOLD_MANUAL={_fmt(r['suggested']['manual'])}")
        print(f"  V2_THRESHOLD_AUTO={_fmt(r['suggested']['auto'])}")
        print(f"  V2_THRESHOLD_EMAIL={_fmt(r['suggested']['auto'])}  # 邮件更严，可按业务上调")
    print(f"\n[当前配置] MATCH_SCORING_MODE={settings.MATCH_SCORING_MODE} "
          f"V2_TITLE_GATE={getattr(settings, 'V2_TITLE_GATE', 'always')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
