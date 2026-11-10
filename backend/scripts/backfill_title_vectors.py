# backend/scripts/backfill_title_vectors.py
"""回填 ``items.title_vector``（v3.7.0 打分口径 v2 的一次性迁移）。

为什么需要
----------
v3.7.0 之前，物品只存 ``text_vector = encode(title + ' ' + description)``。
全文向量会被描述稀释成「嵌合体」——实测物品 67 标题「房卡」、描述
「丢失一个宿舍钥匙」，全文向量对查询「房卡」只有 **0.7569**，而标题独立向量是
**1.0000**。v2 打分用标题向量做文本通道主证据，故历史数据必须回填。

与 ``reembed_all_vectors.py`` 的分工
------------------------------------
- ``reembed``：换模型时**全量重算**（图 + 全文 + 标题），会重新编码图片，慢；
- ``backfill``：**只补标题向量**，只对 ``title_vector IS NULL`` 的行走一次文本编码，
  不动图片、不动全文向量 —— 十几条数据秒级完成，可安全反复执行（幂等）。

用法（在 ``backend`` 目录下执行）::

    venv\\Scripts\\python.exe scripts\\backfill_title_vectors.py --dry-run
    venv\\Scripts\\python.exe scripts\\backfill_title_vectors.py
    venv\\Scripts\\python.exe scripts\\backfill_title_vectors.py --all   # 强制重算全部
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import Any, List, Optional

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
# ``app.config`` 以「相对 CWD」加载 .env，且 DATABASE 是相对路径 —— 固定到 backend/
# 目录，使脚本在任意 CWD 下都能读到 SECRET_KEY 与正确的库文件。
os.chdir(BACKEND_DIR)

from app.database import vector_to_json  # noqa: E402
from app.logger import logger  # noqa: E402


def _to_ndarray(vec: Any) -> np.ndarray:
    return vec if isinstance(vec, np.ndarray) else np.asarray(vec, dtype=np.float32)


def backfill(db_path: str, encoder: Any, *, dry_run: bool = False,
             only_missing: bool = True, limit: Optional[int] = None) -> dict:
    """回填标题向量。

    Args:
        db_path: SQLite 库路径。
        encoder: 需提供 ``encode_text(text)``（生产传 ``_ServiceEncoderAdapter``）。
        dry_run: 只统计不写库。
        only_missing: True 只补 NULL/空串；False 全量重算。
        limit: 最多处理 N 行（冒烟）。

    Returns:
        ``{"total", "pending", "ok", "failed", "skipped"}``
    """
    stats = {"total": 0, "pending": 0, "ok": 0, "failed": 0, "skipped": 0}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(items)")}
        if "title_vector" not in columns:
            raise RuntimeError(
                "items 表缺少 title_vector 列 —— 请先启动一次应用（init_db 会做迁移），"
                "或手工执行 ALTER TABLE items ADD COLUMN title_vector TEXT"
            )

        sql = "SELECT id, title, title_vector FROM items ORDER BY id ASC"
        rows = conn.execute(sql).fetchall()
        stats["total"] = len(rows)

        pending = [
            r for r in rows
            if not only_missing or not (r["title_vector"] or "").strip()
        ]
        if limit:
            pending = pending[: int(limit)]
        stats["pending"] = len(pending)
        stats["skipped"] = stats["total"] - stats["pending"]

        for row in pending:
            title = (row["title"] or "").strip()
            if not title:
                stats["failed"] += 1
                logger.warning(f"物品 {row['id']} 标题为空，跳过")
                continue
            try:
                vec = _to_ndarray(encoder.encode_text(title))
            except Exception as e:
                stats["failed"] += 1
                logger.warning(f"物品 {row['id']} 标题编码失败: {e}")
                continue
            stats["ok"] += 1
            if not dry_run:
                conn.execute(
                    "UPDATE items SET title_vector=? WHERE id=?",
                    (vector_to_json(vec), int(row["id"])),
                )

        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="回填 items.title_vector（v3.7.0）")
    p.add_argument("--db", default=None, help="SQLite 库路径（默认取 app.database.DB_PATH）")
    p.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    p.add_argument("--all", action="store_true", help="强制重算全部（默认只补缺失）")
    p.add_argument("--limit", type=int, default=None, help="最多处理 N 行（冒烟）")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    from app.database import DB_PATH
    from app.clip_service import clip_service
    from reembed_all_vectors import _ServiceEncoderAdapter

    db_path = args.db or DB_PATH
    stats = backfill(
        db_path,
        _ServiceEncoderAdapter(clip_service),
        dry_run=args.dry_run,
        only_missing=not args.all,
        limit=args.limit,
    )
    print("=" * 56)
    print("标题向量回填" + ("（dry-run，未写库）" if args.dry_run else ""))
    print("=" * 56)
    for k, v in stats.items():
        print(f"  {k:<10}: {v}")
    print("=" * 56)
    if stats["failed"]:
        print(f"[FAIL] {stats['failed']} 条编码失败 —— 请检查日志后重跑")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
