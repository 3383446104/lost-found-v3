# app/api/stats.py
# v3.6.0 融合：新增管理端统计四端点（指标卡 / 找回率 / 发布趋势 / 分类占比）
from fastapi import APIRouter, Depends, Query
from ..database import get_db_connection, get_counter
from ..dependencies.auth import get_current_user, get_current_admin
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


# ===================================================================== #
# v3.6.0 融合：管理端统计（参考项目 4 接口思路：overview/recovery/trend/pie）
# ===================================================================== #
BEIJING = timezone(timedelta(hours=8))


def _bj_day_utc_range(day: datetime) -> tuple:
    """北京时区某日的 [00:00, 24:00) 对应 UTC 字符串区间（与 dashboard 口径一致）。"""
    start_bj = day.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_bj.astimezone(timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    return start_utc.strftime("%Y-%m-%d %H:%M:%S"), end_utc.strftime("%Y-%m-%d %H:%M:%S")


@router.get("/admin/overview")
async def admin_overview(current_admin: dict = Depends(get_current_admin)):
    """管理端指标卡：物品总数 / 待审核 / 已完成 / 用户数"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM items")
        item_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM items WHERE review_status='pending'")
        pending_review = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM items WHERE status='claiming'")
        claiming_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE status='active'")
        user_total = cur.fetchone()[0]

    # 已完成（计数器与实计数取 MAX，与 dashboard 口径一致）
    claimed_total = get_counter("total_claimed")
    with get_db_connection() as conn:
        claimed_total = max(
            claimed_total,
            conn.execute("SELECT COUNT(*) FROM items WHERE status='claimed'").fetchone()[0],
        )

    return {
        "success": True,
        "data": {
            "item_total": item_total,
            "pending_review": pending_review,
            "claiming_count": claiming_count,
            "claimed_total": claimed_total,
            "user_total": user_total,
        },
    }


@router.get("/admin/recovery")
async def admin_recovery(current_admin: dict = Depends(get_current_admin)):
    """找回率仪表盘：找回率 = 已完成 /（已完成 + 展示中 + 认领中），分母 0 → 0"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM items WHERE status='active' AND review_status='approved'")
        active_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM items WHERE status='claiming'")
        claiming_count = cur.fetchone()[0]
        cur.execute("SELECT type, COUNT(*) FROM items WHERE status='claimed' GROUP BY type")
        by_type_rows = {r["type"]: r["COUNT(*)"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM claims WHERE status=3")
        completed_claims = cur.fetchone()[0]

    # 计数器与实计数取 MAX（直插历史数据/测试数据的场景下两者可能不同步）
    claimed_total = max(
        get_counter("total_claimed"),
        by_type_rows.get("lost", 0) + by_type_rows.get("found", 0),
    )
    processed_total = claimed_total + active_count + claiming_count
    recovery_rate = round(claimed_total / processed_total, 4) if processed_total > 0 else 0.0

    return {
        "success": True,
        "data": {
            "recovery_rate": recovery_rate,
            "claimed_total": claimed_total,
            "processed_total": processed_total,
            "active_count": active_count,
            "claiming_count": claiming_count,
            "completed_claims": completed_claims,
            "by_type": {
                "lost": by_type_rows.get("lost", 0),
                "found": by_type_rows.get("found", 0),
            },
        },
    }


@router.get("/admin/publish-trend")
async def admin_publish_trend(
    days: int = Query(30, ge=1, le=90, description="统计最近 N 天"),
    current_admin: dict = Depends(get_current_admin),
):
    """近 N 天每日发布数（lost/found 拆分，北京时间口径）"""
    now_bj = datetime.now(BEIJING)
    today_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)

    trend = []
    with get_db_connection() as conn:
        cur = conn.cursor()
        for i in range(days - 1, -1, -1):
            day = today_start - timedelta(days=i)
            start_str, end_str = _bj_day_utc_range(day)
            cur.execute(
                "SELECT type, COUNT(*) FROM items WHERE created_at >= ? AND created_at < ? GROUP BY type",
                (start_str, end_str),
            )
            counts = {r["type"]: r["COUNT(*)"] for r in cur.fetchall()}
            trend.append({
                "date": day.strftime("%m-%d"),
                "lost": counts.get("lost", 0),
                "found": counts.get("found", 0),
            })

    return {"success": True, "data": {"days": days, "trend": trend}}


@router.get("/admin/category-pie")
async def admin_category_pie(current_admin: dict = Depends(get_current_admin)):
    """分类占比（活跃物品，与首页 dashboard 同口径）"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT category, COUNT(*) as c FROM items WHERE status='active' AND review_status='approved' GROUP BY category ORDER BY c DESC"
        )
        categories = [{"name": r["category"] or "其他", "count": r["c"]} for r in cur.fetchall()]

    return {"success": True, "data": {"categories": categories}}
