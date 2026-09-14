# app/api/stats.py
from fastapi import APIRouter, Depends
from ..database import get_db_connection
from ..dependencies.auth import get_current_user
from datetime import datetime, timedelta, timezone

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
    # 「今日」以北京时间（UTC+8）为口径计算。items.created_at 由 SQLite
    # CURRENT_TIMESTAMP 写入，存的是 UTC（固定宽度 "YYYY-MM-DD HH:MM:SS"）。
    # 因此需要显式换算北京时间当日的 [00:00, 24:00) 半开区间对应的 UTC 边界，
    # 再用字符串字典序范围比较（对该固定格式正确且高效），避免东八区
    # 00:00–08:00 时段因本地日期与 UTC 日期相差一天而漏计。
    BEIJING = timezone(timedelta(hours=8))
    now_bj = datetime.now(BEIJING)
    start_bj = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_bj.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    start_str = start_utc.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_utc.strftime("%Y-%m-%d %H:%M:%S")

    with get_db_connection() as conn:
        cur = conn.cursor()

        # 展示中物品总数（已审核 + 活跃）
        cur.execute(
            "SELECT COUNT(*) FROM items WHERE status='active' AND review_status='approved'"
        )
        active_count = cur.fetchone()[0]

        # 今日新增失物 — 仅统计已审核通过且活跃的物品
        cur.execute(
            "SELECT COUNT(*) FROM items WHERE created_at >= ? AND created_at < ?"
            " AND type='lost' AND review_status='approved' AND status='active'",
            (start_str, end_str)
        )
        today_lost = cur.fetchone()[0]

        # 今日新增拾物 — 仅统计已审核通过且活跃的物品
        cur.execute(
            "SELECT COUNT(*) FROM items WHERE created_at >= ? AND created_at < ?"
            " AND type='found' AND review_status='approved' AND status='active'",
            (start_str, end_str)
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
