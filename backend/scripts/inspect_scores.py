# backend/scripts/inspect_scores.py
"""打印某个查询在真实库上的打分拆解（答辩演示 / 调参排错用）。

为什么需要
----------
线上日志只打印一个综合分，排错时无法回答「它为什么排第一」「哪个通道在拖后腿」。
本脚本用**与 ``/match`` 完全相同的代码路径**（``compute_match_detail``）逐条打分，
把每个通道的原始余弦、字面命中、判定分、排序分全部打出来。

用法（在 ``backend`` 目录或任意目录均可）::

    venv\\Scripts\\python.exe scripts\\inspect_scores.py --text 房卡 --type lost
    venv\\Scripts\\python.exe scripts\\inspect_scores.py --text 笔记本 --type found --top 10
    venv\\Scripts\\python.exe scripts\\inspect_scores.py --text 房卡 --mode legacy   # 对照旧口径
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any, List, Optional

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from app.config import settings, match_threshold  # noqa: E402
from app.database import json_to_vector  # noqa: E402
from app.clip_service import clip_service  # noqa: E402
from app.utils.time_utils import days_since_utc  # noqa: E402


def _rows(db_path: str, target_type: str) -> List[sqlite3.Row]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            """SELECT id, type, title, description, category, location, created_at,
                      image_vector, text_vector, title_vector
               FROM items
               WHERE type=? AND status='active' AND review_status='approved'
               ORDER BY id""",
            (target_type,),
        ).fetchall()
    finally:
        conn.close()


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="打印查询的打分拆解")
    p.add_argument("--text", required=True, help="查询文本")
    p.add_argument("--type", default="found", choices=["lost", "found"], help="目标类型")
    p.add_argument("--mode", default=None, choices=["v2", "legacy"], help="打分口径（默认取配置）")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--db", default=None)
    return _run(p.parse_args(argv), p)


def _run(args: Any, parser: argparse.ArgumentParser) -> int:
    from app.database import DB_PATH

    mode = str(args.mode or settings.MATCH_SCORING_MODE).lower()
    threshold = (match_threshold("manual") if mode == "v2"
                 else float(settings.MATCH_THRESHOLD_MANUAL))

    rows = _rows(args.db or DB_PATH, args.type)
    if not rows:
        print(f"[空] type={args.type} 没有可匹配物品")
        return 0

    q_text = clip_service.get_text_feature(args.text)
    print(f"口径={mode}  查询={args.text!r}  目标类型={args.type}  "
          f"候选={len(rows)}  门槛={threshold:.4f}")
    print("-" * 108)
    header = (f"{'id':>4} {'title':<14} {'判分(旧)':>9} {'title':>7} {'full':>7} "
              f"{'img':>7} {'t2i':>7} {'字面':>5} {'排序分':>7} {'过?':>4}")
    print(header)
    print("-" * 108)

    out = []
    for r in rows:
        d = clip_service.compute_match_detail(
            None, q_text,
            json_to_vector(r["image_vector"]), json_to_vector(r["text_vector"]),
            cat1="", cat2=r["category"] or "",
            loc1="", loc2=r["location"] or "",
            days_old=days_since_utc(r["created_at"]),
            title_vec2=json_to_vector(r["title_vector"]),
            query_text=args.text,
            target_title=r["title"] or "",
            target_desc=r["description"] or "",
            scoring_mode=mode,
        )
        ch = d["channels"]

        def fmt(v, w=7):
            return f"{v:>{w}.4f}" if isinstance(v, float) else f"{'-':>{w}}"

        out.append((d["score"], d, r))
        print(f"{r['id']:>4} {(r['title'] or '')[:14]:<14} {fmt(d['content_score'], 9)} "
              f"{fmt(ch.get('sim_text_title'))} {fmt(ch.get('sim_text_text'))} "
              f"{fmt(ch.get('sim_img_img'))} {fmt(ch.get('sim_t2i'))} "
              f"{d.get('literal_hit', 0.0):>5.2f} {fmt(d.get('ranking_score'), 7)} "
              f"{'Y' if d['content_score'] >= threshold else '':>4}")

    out.sort(key=lambda x: -x[0])
    print("-" * 108)
    print("按判定分排序 Top{}：".format(args.top))
    for score, d, r in out[: args.top]:
        print(f"  {score:.4f}  #{r['id']} {(r['title'] or '')[:20]}  "
              f"[{d['level']}] {'+'.join(d['basis']) or '无依据'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
