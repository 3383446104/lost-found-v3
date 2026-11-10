# backend/scripts/eval_literal_pairs.py
"""真实库「短标题查询」混淆度量：标题通道常开 vs 字面门控（v3.7.0）。

为什么需要它
------------
``eval_set_v3.5.0.json`` 的正样本查询被**人为约束**为「不得含目标 title 原词」，
所以它在结构上无法回答一个问题：**用户只输入两三个字（房卡 / 水杯 / 耳机）时，
系统会不会把无关条目顶过阈值？** 而这恰恰是校园失物招领最真实的查询形态。

实测反例（2026-11-09）：查询「房卡」对「一个手机」的
    标题余弦 0.7783 → 直接越过手动阈值 0.6919（全文余弦仅 0.4571）。
根因是 Chinese-CLIP 短文本的各向异性：两字词之间的余弦普遍落在 0.75~0.85。

本脚本怎么量
------------
遍历真实库里所有**标题互不相同**的物品对，用 A 的标题去查 B（双向），
记为一次「非字面配对」。统计：

    FP@手动阈值 = 分数 ≥ 阈值的非字面配对 / 全部非字面配对

这是一个**下界**（真实 FP 只会更多：还有措辞不同但语义无关的配对），
但它对「改不改门控」是最直接的决策依据 —— 同一批数据、同一套阈值口径。

用法（backend 目录下）::

    venv\\Scripts\\python.exe scripts\\eval_literal_pairs.py
    venv\\Scripts\\python.exe scripts\\eval_literal_pairs.py --threshold 0.6919
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import match_threshold, settings  # noqa: E402
from app.database import DB_PATH, json_to_vector  # noqa: E402


def _cos(a, b) -> Optional[float]:
    if a is None or b is None:
        return None
    import numpy as np
    return float(np.dot(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))


def _load_items(db_path: str) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT id, title, description, text_vector, title_vector
               FROM items
               WHERE status='active' AND review_status='approved'
               ORDER BY id"""
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        title = (r["title"] or "").strip()
        if not title:
            continue
        out.append({
            "id": r["id"],
            "title": title,
            "desc": r["description"] or "",
            "text_vector": json_to_vector(r["text_vector"]),
            "title_vector": json_to_vector(r["title_vector"]),
        })
    return out


def _scores(items: List[Dict[str, Any]]) -> Dict[str, List[Tuple[float, str]]]:
    """两种门控下，全部「非字面配对」的得分。

    只喂文本通道（不传图像/跨模态）—— 本脚本要量的是**文本通道本身**的
    各向异性，混入图像会掩盖问题。
    """
    out: Dict[str, List[Tuple[float, str]]] = {"always": [], "literal": []}
    for a, b in combinations(items, 2):
        for q, t in ((a, b), (b, a)):
            q_vec = clip_service.get_text_feature(q["title"])
            literal, lit_scale = clip_service.literal_features(q["title"], t["title"], t["desc"])
            if literal >= 0.8:
                continue          # 字面配对是「正确命中」，不计入 FP 分母
            for gate in ("always", "literal"):
                s = clip_service.compute_score_v2(
                    sim_tt=_cos(q_vec, t["text_vector"]),
                    sim_title=_cos(q_vec, t["title_vector"]),
                    sim_ii=None,
                    literal=literal,
                    literal_scale=lit_scale,
                    title_gate=gate,
                )
                out[gate].append((s, f"{q['title']}→{t['title']}"))
    return out


def _report(scored: List[Tuple[float, str]], threshold: float) -> str:
    if not scored:
        return "无样本"
    order = sorted(scored, key=lambda x: -x[0])
    hits = [x for x in order if x[0] >= threshold]
    vals = [s for s, _ in scored]
    mean = sum(vals) / len(vals)
    lines = [
        f"  非字面配对 {len(scored)} 对 ｜ 均值 {mean:.4f} ｜ "
        f"最高 {order[0][0]:.4f} ｜ FP@阈值 {len(hits)}/{len(scored)} "
        f"= {len(hits) / len(scored):.1%}",
    ]
    for s, name in hits[:5]:
        lines.append(f"    ! {s:.4f}  {name}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="短标题查询的跨条目混淆度量")
    p.add_argument("--db", default=None)
    p.add_argument("--threshold", type=float, default=None,
                   help="默认取当前口径的手动阈值")
    args = p.parse_args(argv)

    threshold = args.threshold
    if threshold is None:
        mode = str(settings.MATCH_SCORING_MODE).lower()
        threshold = match_threshold("manual") if mode == "v2" else settings.MATCH_THRESHOLD_MANUAL

    items = _load_items(args.db or DB_PATH)
    print(f"库内可用条目：{len(items)}  ｜ 手动阈值：{threshold:.4f}")
    print("（只统计标题互不包含的配对，即「理应不相关」的组合）\n")

    per_gate = _scores(items)
    for gate, label in (("always", "标题通道常开"), ("literal", "标题通道字面门控")):
        print(f"[{gate}] {label}")
        print(_report(per_gate[gate], threshold))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
