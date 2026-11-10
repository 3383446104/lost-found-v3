# backend/scripts/fit_fusion_weights.py
"""加权融合权重搜索与验证（v3.7.0）。

为什么需要这个脚本（论文「参数确定」一节）
------------------------------------------
``w_text = w_img = 0.80、w_cross = 0.20、γ = 0.15`` 目前是**设计取值**：
依据是「同模态是主证据、跨模态是辅证」，但答辩一定会问「为什么是 0.8 不是 0.75」。

本脚本给出可复现的回答：在标注评测集上做**网格搜索**，报告

1. 目标函数（排序能力）：``J = ½·(Recall@1 + Recall@3)`` —— 与阈值无关，只反映排序；
2. 最优权重与**平台区**（附近 ±0.1 内 J 的变化），说明设计取值不在尖锐极值上；
3. 用最优权重重新标定三档阈值，给出 P/R；
4. 与当前设计取值的逐项对照。

为什么不用梯度/逻辑回归拟合
--------------------------
图像通道**没有正样本**（评测集里每件物品只有一张照片，无法构造真实的 img→img 正例），
最小二乘/逻辑回归会把 ``w_img`` 拟合到「只在负样本上出现过」的方向，得到负权重。
因此采用**带约束的网格搜索**：``w_text = w_img``（同模态对等，设计约束），
只搜索 ``(w_modality, w_cross, γ)``，图像权重不被单独拟合。这一取舍写进论文的局限性。

用法（backend 目录）::

    venv\\Scripts\\python.exe scripts\\fit_fusion_weights.py
    venv\\Scripts\\python.exe scripts\\fit_fusion_weights.py --eval-set eval\\eval_set_v3.5.0.json
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
os.chdir(BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import fusion  # noqa: E402

from calibrate_thresholds import (  # noqa: E402
    _candidate_key, _candidates, _EncoderCache, is_degenerate, load_eval_set,
)

DEFAULT_EVAL_SET = os.path.join(BACKEND_DIR, "eval", "eval_set_v3.7.0.json")
DEFAULT_OUT = os.path.join(BACKEND_DIR, "..", "docs", "review", "fusion-weights-fit.md")

#: 搜索网格（受约束：w_text = w_img = w_modality）
GRID_MODALITY = (0.60, 0.70, 0.80, 0.90, 1.00)
GRID_CROSS = (0.10, 0.15, 0.20, 0.30, 0.40)
GRID_LITERAL = (0.00, 0.10, 0.15, 0.20, 0.30)

#: 特征矩阵列序（与 fusion.Channels 对应）
COL_TEXT, COL_IMG, COL_CROSS, COL_LIT, COL_SCALE = 0, 1, 2, 3, 4
COL_CAT, COL_LOC = 5, 6
COL_MT, COL_MI, COL_MC = 7, 8, 9
N_COLS = 10


def _dot(a, b) -> Optional[float]:
    if a is None or b is None:
        return None
    return float(np.dot(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))


def _feat_row(q_text_vec, q_img_vec, target: Dict[str, Any], cache: _EncoderCache,
              query_text: str) -> np.ndarray:
    """把一对 (query, target) 压成一行特征（供向量化 fuse 使用）。"""
    t_text = cache.text(target["text"]) if target.get("text") else None
    t_img = cache.image(target["item_ref"]) if target.get("item_ref") else None
    title, desc = ("", "")
    if target.get("text"):
        title, _, tail = str(target["text"]).partition(" ")
        desc = tail
    t_title = cache.text(title) if (title and t_text is not None) else None

    lit, scale = clip_service.literal_features(query_text, title, desc)
    ch = fusion.channels_from_sims(
        sim_tt=_dot(q_text_vec, t_text),
        sim_title=_dot(q_text_vec, t_title),
        sim_ii=_dot(q_img_vec, t_img),
        sim_t2i=_dot(q_text_vec, t_img),
        sim_i2t=_dot(q_img_vec, t_text),
        literal=lit, literal_scale=scale,
        lo=float(settings.MATCH_CROSS_REF_LO), hi=float(settings.MATCH_CROSS_REF_HI),
    )

    row = np.zeros(N_COLS, dtype=np.float64)
    if ch.text is not None:
        row[COL_TEXT], row[COL_MT] = ch.text, 1.0
    if ch.img is not None:
        row[COL_IMG], row[COL_MI] = ch.img, 1.0
    if ch.cross is not None:
        row[COL_CROSS], row[COL_MC] = ch.cross, 1.0
    row[COL_LIT] = ch.literal
    row[COL_SCALE] = ch.literal_scale
    row[COL_CAT] = 0.0 if ch.cat_same is None else (1.0 if ch.cat_same else -1.0)
    row[COL_LOC] = 0.0 if ch.loc_same is None else (1.0 if ch.loc_same else -1.0)
    return row


def _fuse_matrix(F: np.ndarray, w_mod: float, w_cross: float, gamma: float,
                 w_lit_cat: fusion.FusionWeights = fusion.DEFAULT_WEIGHTS) -> np.ndarray:
    """向量化 ``fusion.fuse``：一次算出整批分数。"""
    W = np.array([w_mod, w_mod, w_cross], dtype=np.float64)
    S = F[:, [COL_TEXT, COL_IMG, COL_CROSS]]
    M = F[:, [COL_MT, COL_MI, COL_MC]]
    num = (S * M * W).sum(axis=1)
    den = (M * W).sum(axis=1)
    base = np.divide(num, den, out=np.zeros_like(num), where=den > 0)

    cat = np.where(F[:, COL_CAT] > 0, w_lit_cat.cat_same,
                   np.where(F[:, COL_CAT] < 0, w_lit_cat.cat_diff, 0.0))
    loc = np.where(F[:, COL_LOC] > 0, w_lit_cat.loc_same,
                   np.where(F[:, COL_LOC] < 0, w_lit_cat.loc_diff, 0.0))
    score = base + cat + loc + gamma * F[:, COL_LIT] * F[:, COL_SCALE]
    return np.clip(score, 0.0, 1.0)


def _build_matrices(eval_set, cache) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """返回 (P/R 用特征, P/R 标签, 排序用 (特征, 每组候选数))。

    排序矩阵按「每个正样本查询 × 全部候选」展开，行序为 query-major。
    """
    # --- P/R：与 calibrate_v2 同口径（排除退化对与字面查询）---
    rows, labels = [], []
    for p in eval_set["pairs"]:
        if is_degenerate(p) or p.get("literal_query") or int(p.get("label", 0)) not in (0, 1):
            continue
        q, t = p.get("query") or {}, p.get("target") or {}
        q_text_vec = cache.text(q["text"]) if q.get("text") else None
        q_img_vec = cache.image(q["image"]) if q.get("image") else None
        rows.append(_feat_row(q_text_vec, q_img_vec, t, cache, q.get("text") or ""))
        labels.append(int(p["label"]))
    F_pr = np.vstack(rows) if rows else np.zeros((0, N_COLS))
    y_pr = np.array(labels, dtype=np.int64)

    # --- 排序：正样本查询 × 全部候选 ---
    cands = _candidates(eval_set)
    per_q = []
    for p in eval_set["pairs"]:
        if int(p.get("label", 0)) != 1 or is_degenerate(p) or p.get("literal_query"):
            continue
        q = p.get("query") or {}
        if not q.get("text"):
            continue
        q_text_vec = cache.text(q["text"])
        own = _candidate_key(p.get("target") or {})
        block = np.vstack([
            _feat_row(q_text_vec, None, c, cache, q["text"]) for c in cands
        ])
        per_q.append((block, [1 if _candidate_key(c) == own else 0 for c in cands]))
    return F_pr, y_pr, per_q


def _rank_scores(block: np.ndarray, w_mod: float, w_cross: float, gamma: float) -> np.ndarray:
    return _fuse_matrix(block, w_mod, w_cross, gamma)


def _eval_combo(per_q, w_mod, w_cross, gamma, ks=(1, 3)) -> Dict[str, float]:
    out = {}
    for k in ks:
        hits = 0
        for block, labels in per_q:
            s = _rank_scores(block, w_mod, w_cross, gamma)
            order = np.argsort(-s)
            hits += 1 if any(labels[i] for i in order[:k]) else 0
        out[f"recall@{k}"] = hits / len(per_q) if per_q else 0.0
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="加权融合权重网格搜索")
    ap.add_argument("--eval-set", default=DEFAULT_EVAL_SET)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    eval_set = load_eval_set(args.eval_set)
    from reembed_all_vectors import _ServiceEncoderAdapter
    adapter = _ServiceEncoderAdapter(clip_service)
    cache = _EncoderCache(adapter)

    F_pr, y_pr, per_q = _build_matrices(eval_set, cache)
    print(f"评测集 {os.path.basename(args.eval_set)}：P/R 样本 {len(y_pr)}"
          f"（正 {int(y_pr.sum())}）｜ 排序查询 {len(per_q)} 组")

    d = fusion.DEFAULT_WEIGHTS
    base_metric = _eval_combo(per_q, d.w_text, d.w_cross, d.literal_bonus)
    base_j = 0.5 * (base_metric["recall@1"] + base_metric["recall@3"])

    results = []
    for wm in GRID_MODALITY:
        for wc in GRID_CROSS:
            for gl in GRID_LITERAL:
                m = _eval_combo(per_q, wm, wc, gl)
                results.append({
                    "w_modality": wm, "w_cross": wc, "gamma": gl,
                    "r1": m["recall@1"], "r3": m["recall@3"],
                    "J": 0.5 * (m["recall@1"] + m["recall@3"]),
                })
    results.sort(key=lambda x: (-x["J"], -x["r1"]))
    best = results[0]

    def row(name, metric, J):
        return (f"| {name} | {metric['recall@1']:.4f} | {metric['recall@3']:.4f} | {J:.4f} |")

    lines = [
        "# 加权融合权重搜索（v3.7.0）",
        "",
        f"> 评测集：`{os.path.relpath(args.eval_set, BACKEND_DIR)}`"
        f" ｜ 编码器：`{adapter.name}` / `{adapter.model_name}`",
        "> 生成脚本：`scripts/fit_fusion_weights.py`",
        "",
        "## 1. 目标函数与约束",
        "",
        "`J = ½·(Recall@1 + Recall@3)` —— 只反映**排序能力**，与阈值无关"
        "（阈值由 `scripts/calibrate_v2.py` 单独标定，两者不混在一起优化）。",
        "",
        "约束：`w_text = w_img = w_modality`（同模态对等）。**图像权重不单独拟合**——",
        "评测集每件物品只有一张照片，无法构造真实的 img→img 正样本，单独拟合会把",
        "`w_img` 学到负样本方向（负权重）。这是本方法的已知局限。",
        "",
        "## 2. 结果",
        "",
        "| 权重方案 | R@1 | R@3 | J |",
        "|---|:--:|:--:|:--:|",
        row(f"设计取值（{d.w_text:.2f}/{d.w_cross:.2f}/{d.literal_bonus:.2f}）", base_metric, base_j),
        row(f"搜索最优（{best['w_modality']:.2f}/{best['w_cross']:.2f}/{best['gamma']:.2f}）",
            {"recall@1": best["r1"], "recall@3": best["r3"]}, best["J"]),
        "",
        "## 3. 前 10 名组合（含并列）",
        "",
        "| # | w_modality | w_cross | γ | R@1 | R@3 | J |",
        "|:--:|:--:|:--:|:--:|:--:|:--:|:--:|",
    ]
    for i, r in enumerate(results[:10], 1):
        lines.append(f"| {i} | {r['w_modality']:.2f} | {r['w_cross']:.2f} | {r['gamma']:.2f} "
                     f"| {r['r1']:.4f} | {r['r3']:.4f} | {r['J']:.4f} |")

    # 平台区：J 不低于最优值 0.5pp 的组合占比与跨度
    near = [r for r in results if r["J"] >= best["J"] - 0.005]
    lines += [
        "",
        "## 4. 平台区（J 落在最优值 0.5pp 内的组合）",
        "",
        f"- 组合数：**{len(near)} / {len(results)}**（{len(near) / len(results):.0%}）",
        f"- `w_modality` 范围：{min(r['w_modality'] for r in near):.2f} ~ {max(r['w_modality'] for r in near):.2f}",
        f"- `w_cross` 范围：{min(r['w_cross'] for r in near):.2f} ~ {max(r['w_cross'] for r in near):.2f}",
        f"- `γ` 范围：{min(r['gamma'] for r in near):.2f} ~ {max(r['gamma'] for r in near):.2f}",
        "",
        "平台区越宽，说明目标函数对该参数越不敏感 —— 设计取值落在平台内即属合理，",
        "不必追求网格上的最优点（小样本下的最优点往往是噪声）。",
        "",
    ]
    report = "\n".join(lines)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"[输出] {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
