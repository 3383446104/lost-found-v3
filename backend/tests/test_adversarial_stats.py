"""对抗性验证 B：R2 时区修复的边界（尝试证伪）。

统一按 UTC 字符串（库内格式 YYYY-MM-DD HH:MM:SS）写入 created_at，
用北京时间锚定构造边界；验证「今日」半开区间 [北京今天 00:00, 明天 00:00) 正确。
"""
from datetime import datetime, timedelta, timezone

from app import database as db_module

BEIJING_TZ = timezone(timedelta(hours=8))


def _bj_to_utc_str(dt_bj: datetime) -> str:
    """北京时间 datetime（aware）→ 库内 UTC 字符串。"""
    return dt_bj.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _bj_midnight_today() -> datetime:
    return datetime.now(BEIJING_TZ).replace(hour=0, minute=0, second=0, microsecond=0)


def test_today_lost_utc_boundaries(client, make_user, create_item_row):
    """today_lost 边界：今天 00:00 / 今天 23:59:59 计入；昨天 23:59:59 / 明天 00:00 不计。"""
    user = make_user(username="adv_bj_lost")
    midnight = _bj_midnight_today()
    cases = {
        "today_000000": midnight,                                        # 计入
        "today_235959": midnight + timedelta(hours=23, minutes=59, seconds=59),  # 计入
        "yesterday_235959": midnight - timedelta(seconds=1),             # 不计
        "tomorrow_000000": midnight + timedelta(days=1),                 # 不计
    }
    for name, dt_bj in cases.items():
        create_item_row(
            user["id"], type="lost", title=f"L-{name}", status="active",
            review_status="approved", created_at=_bj_to_utc_str(dt_bj),
        )

    data = client.get("/api/stats/dashboard", headers=user["headers"]).json()["data"]
    assert data["today_lost"] == 2, (
        f"today_lost 边界错误：期望 2（今天 00:00 与 23:59:59），实得 {data['today_lost']}"
    )
    # 口径未变：4 件均为 active+approved，active_count 不受时间边界影响
    assert data["active_count"] == 4


def test_today_found_utc_boundaries(client, make_user, create_item_row):
    """today_found 同样覆盖 4 条边界。"""
    user = make_user(username="adv_bj_found")
    midnight = _bj_midnight_today()
    cases = {
        "today_000000": midnight,
        "today_235959": midnight + timedelta(hours=23, minutes=59, seconds=59),
        "yesterday_235959": midnight - timedelta(seconds=1),
        "tomorrow_000000": midnight + timedelta(days=1),
    }
    for name, dt_bj in cases.items():
        create_item_row(
            user["id"], type="found", title=f"F-{name}", status="active",
            review_status="approved", created_at=_bj_to_utc_str(dt_bj),
        )

    data = client.get("/api/stats/dashboard", headers=user["headers"]).json()["data"]
    assert data["today_found"] == 2, (
        f"today_found 边界错误：期望 2，实得 {data['today_found']}"
    )


def test_today_counts_real_current_timestamp(client, make_user, create_item, approve_item):
    """防止「矫枉过正」：真实 CURRENT_TIMESTAMP（UTC 当下）写入的物品必须计入 today_lost。"""
    user = make_user(username="adv_now")
    item_id = create_item(user["headers"], type="lost", title="刚刚丢失")
    approve_item(item_id)

    data = client.get("/api/stats/dashboard", headers=user["headers"]).json()["data"]
    assert data["today_lost"] == 1, (
        f"真实 CURRENT_TIMESTAMP 写入的物品被漏计（today_lost={data['today_lost']}）"
    )


def test_active_count_and_total_claimed_semantics_unchanged(client, make_user, create_item_row):
    """确认 active_count / total_claimed 口径未随修复改变。"""
    user = make_user(username="adv_unchanged")
    midnight = _bj_midnight_today()
    for i, off in enumerate([timedelta(hours=1), timedelta(days=-1), timedelta(days=1)]):
        create_item_row(
            user["id"], type="lost", title=f"A{i}", status="active",
            review_status="approved", created_at=_bj_to_utc_str(midnight + off),
        )
    # 1 件 pending：不计入 active_count
    create_item_row(
        user["id"], type="lost", title="A-pending", status="pending",
        review_status="pending",
    )
    db_module.increment_counter("total_claimed", 3)

    data = client.get("/api/stats/dashboard", headers=user["headers"]).json()["data"]
    assert data["active_count"] == 3
    assert data["total_claimed"] == 3
