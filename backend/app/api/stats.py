# app/api/stats.py
from fastapi import APIRouter, Depends
from ..database import get_db_connection
from ..dependencies.auth import get_current_user
from datetime import datetime

router = APIRouter(prefix="/stats", tags=["数据统计"])


@router.get("/dashboard")
async def dashboard(current_user: dict = Depends(get_current_user)):
    """首页数据看板（需登录）

    返回:
    - active_count: 当前展示中的物品数（status=active + review_status=approved）
    - today_lost: 今日新增失物（仅已审核通过且活跃的）
    - today_found: 今日新增拾物（仅已审核通过且活跃的）
    - total_claimed: 总计找回数（status='claimed' 的累计值）
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        cur = conn.cursor()

        # 展示中物品总数（已审核 + 活跃）
        cur.execute(
            "SELECT COUNT(*) FROM items WHERE status='active' AND review_status='approved'"
        )
        active_count = cur.fetchone()[0]

        # 今日新增失物 — 仅统计已审核通过且活跃的物品
        cur.execute(
            "SELECT COUNT(*) FROM items WHERE created_at LIKE ? AND type='lost'"
            " AND review_status='approved' AND status='active'",
            (f"{today_str}%",)
        )
        today_lost = cur.fetchone()[0]

        # 今日新增拾物 — 仅统计已审核通过且活跃的物品
        cur.execute(
            "SELECT COUNT(*) FROM items WHERE created_at LIKE ? AND type='found'"
            " AND review_status='approved' AND status='active'",
            (f"{today_str}%",)
        )
        today_found = cur.fetchone()[0]

        # 总计找回（持久化计数器，不受物品删除影响）
        try:
            cur.execute("SELECT value FROM stats_counters WHERE key='total_claimed'")
            total_claimed = cur.fetchone()[0]
        except Exception:
            cur.execute("SELECT COUNT(*) FROM items WHERE status='claimed'")
            total_claimed = cur.fetchone()[0]

        # 分类占比（活跃物品）
        cur.execute("SELECT category, COUNT(*) as c FROM items WHERE status='active' AND review_status='approved' GROUP BY category ORDER BY c DESC")
        categories = [{"name": r["category"] or "其他", "count": r["c"]} for r in cur.fetchall()]

    return {
        "success": True,
        "data": {
            "active_count": active_count,
            "today_lost": today_lost,
            "today_found": today_found,
            "total_claimed": total_claimed,
            "categories": categories
        }
    }
