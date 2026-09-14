# backend/scripts/backfill_color_vectors.py
"""一次性回填 ``items.color_vector``（R4 颜色向量持久化）。

用法（在 ``backend`` 目录下执行）::

    venv\\Scripts\\python.exe scripts\\backfill_color_vectors.py

特性：
- **幂等**：仅处理 ``color_vector IS NULL`` 且 ``image_path`` 非空的行；``UPDATE``
  语句亦带 ``color_vector IS NULL`` 守卫，重复运行不会重复写。
- **读路径只读**：本脚本只负责历史数据的批量回填；匹配热路径保持只读语义
  （缺失时回退实时计算），不回写。
- 颜色直方图仅依赖 ``PIL`` / ``numpy``（``clip_service.get_color_histogram``），
  **不会**加载 CLIP 模型。
"""
import os
import sys

# 允许脚本独立运行：把 backend 目录加入 sys.path（app 包所在目录）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import get_db_connection, vector_to_json, DB_PATH  # noqa: E402
from app.clip_service import clip_service  # noqa: E402
from app.logger import logger  # noqa: E402


def backfill(limit: int | None = None) -> dict:
    """回填所有缺失的 ``color_vector``。

    Args:
        limit: 可选，最多处理的行数（便于分批/调试）。

    Returns:
        统计字典：``{"scanned": int, "updated": int, "skipped": int}``。
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        sql = (
            "SELECT id, image_path FROM items "
            "WHERE color_vector IS NULL AND image_path IS NOT NULL AND image_path != ''"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        cur.execute(sql)
        rows = cur.fetchall()

    scanned = len(rows)
    updated = 0
    skipped = 0

    for row in rows:
        item_id = row["id"]
        image_path = row["image_path"]
        if not image_path or not os.path.exists(image_path):
            logger.warning(f"跳过物品 {item_id}：图片不存在 {image_path}")
            skipped += 1
            continue
        try:
            hist = clip_service.get_color_histogram(image_path)
        except Exception as e:  # 单条失败不影响整体回填
            logger.warning(f"跳过物品 {item_id}：颜色直方图计算失败 {e}")
            skipped += 1
            continue
        if hist is None:
            skipped += 1
            continue

        with get_db_connection() as conn:
            conn.execute(
                "UPDATE items SET color_vector = ? WHERE id = ? AND color_vector IS NULL",
                (vector_to_json(hist), item_id),
            )
        updated += 1

    logger.info(f"颜色向量回填完成：扫描 {scanned}，更新 {updated}，跳过 {skipped}")
    return {"scanned": scanned, "updated": updated, "skipped": skipped}


def main() -> None:
    result = backfill()
    print(
        f"数据库 {DB_PATH} 回填完成："
        f"扫描 {result['scanned']}，更新 {result['updated']}，跳过 {result['skipped']}"
    )


if __name__ == "__main__":
    main()
