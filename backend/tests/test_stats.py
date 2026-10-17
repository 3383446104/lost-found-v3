"""数据统计回归测试。

覆盖：
- 需登录
- R2：北京时间今天凌晨发布的物品必须计入 today_lost（P0 时区口径缺陷）
- 未审核物品不计入统计
- total_claimed 来自持久化计数器而非实时 count
"""
from datetime import datetime, timedelta, timezone

from app import database as db_module

BEIJING_TZ = timezone(timedelta(hours=8))


def _beijing_today_2am_as_utc_str() -> str:
    """返回「北京时间今天凌晨 02:00」对应的 UTC 时间字符串（库内存储口径）。"""
    now_bj = datetime.now(BEIJING_TZ)
    beijing_2am = now_bj.replace(hour=2, minute=0, second=0, microsecond=0)
    return beijing_2am.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def test_dashboard_requires_auth(client):
    assert client.get("/api/stats/dashboard").status_code in (401, 403)


def test_today_lost_counts_beijing_early_morning_item(
    client, make_user, create_item_row
):
    """【R2 核心缺陷】北京时间今天凌晨发布的物品必须计入 today_lost。

    构造：物品在北京时间今天 02:00 发布 → 库内（UTC）存为「前一天 18:00」。
    缺陷位置：``app/api/stats.py:20`` 用本地 ``datetime.now()`` 生成 "今日" 前缀，
    而 SQLite ``CURRENT_TIMESTAMP`` 存的是 UTC，两者在东八区 00:00–08:00 相差一天。

    当前行为：该物品被漏计（today_lost == 0）。
    期望行为：today_lost == 1。→ 本用例预期失败，用于暴露该 P0 缺陷（修复前请保留为红）。
    """
    user = make_user(username="stat_user")
    created_utc = _beijing_today_2am_as_utc_str()
    create_item_row(
        user["id"],
        type="lost",
        title="凌晨丢失的钱包",
        status="active",
        review_status="approved",
        created_at=created_utc,
    )

    resp = client.get("/api/stats/dashboard", headers=user["headers"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["today_lost"] == 1, (
        f"[R2] 北京时间今天凌晨发布的物品未计入 today_lost（实际 {data['today_lost']}）；"
        f"库内 created_at(UTC)={created_utc}，stats.py:20 用本地日期前缀比较导致漏计"
    )


def test_unapproved_items_not_counted(client, make_user, create_item):
    user = make_user(username="pending_stat_user")
    create_item(user["headers"], type="lost", title="待审失物")
    create_item(user["headers"], type="found", title="待审拾物")

    data = client.get("/api/stats/dashboard", headers=user["headers"]).json()["data"]
    assert data["active_count"] == 0
    assert data["today_lost"] == 0
    assert data["today_found"] == 0


def test_total_claimed_comes_from_persistent_counter(client, make_user):
    user = make_user(username="counter_user")
    # 库中不存在任何 status='claimed' 物品，但计数器为 5
    db_module.increment_counter("total_claimed", 5)

    data = client.get("/api/stats/dashboard", headers=user["headers"]).json()["data"]
    assert data["total_claimed"] == 5
