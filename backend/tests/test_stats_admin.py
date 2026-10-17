"""管理端统计回归测试（v3.6.0 融合）。

覆盖：三个 admin 端点权限（401/403）、overview 指标、
publish-trend 天数拆分（create_item_row 造特定 created_at）、
recovery 分母为 0 不炸、category-pie 口径。
"""
from datetime import datetime, timedelta, timezone

BEIJING = timezone(timedelta(hours=8))


def _utc_str(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def test_admin_stats_require_admin(client, make_user):
    user = make_user(username="st_user")
    assert client.get("/api/stats/admin/overview", headers=user["headers"]).status_code == 403
    assert client.get("/api/stats/admin/recovery", headers=user["headers"]).status_code == 403
    assert client.get("/api/stats/admin/publish-trend", headers=user["headers"]).status_code == 403
    assert client.get("/api/stats/admin/category-pie", headers=user["headers"]).status_code == 403
    assert client.get("/api/stats/admin/overview").status_code in (401, 403)


def test_overview_counts(client, make_admin, make_user, create_item_row):
    admin = make_admin(username="st_admin")
    owner = make_user(username="st_owner")

    create_item_row(owner["id"], review_status="pending", status="pending")
    create_item_row(owner["id"], review_status="approved", status="active")
    create_item_row(owner["id"], review_status="approved", status="claimed")

    resp = client.get("/api/stats/admin/overview", headers=admin["headers"]).json()["data"]
    assert resp["item_total"] == 3
    assert resp["pending_review"] == 1
    assert resp["claimed_total"] >= 1
    assert resp["user_total"] >= 2  # admin + owner


def test_publish_trend_days_split(client, make_admin, make_user, create_item_row):
    admin = make_admin(username="st_admin2")
    owner = make_user(username="st_owner2")

    now_bj = datetime.now(BEIJING)
    today_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)

    # 今天：1 lost + 2 found；昨天：1 lost
    create_item_row(owner["id"], type="lost", created_at=_utc_str(today_start + timedelta(hours=10)))
    create_item_row(owner["id"], type="found", created_at=_utc_str(today_start + timedelta(hours=11)))
    create_item_row(owner["id"], type="found", created_at=_utc_str(today_start + timedelta(hours=12)))
    create_item_row(owner["id"], type="lost", created_at=_utc_str(today_start - timedelta(hours=5)))

    resp = client.get("/api/stats/admin/publish-trend?days=7", headers=admin["headers"]).json()["data"]
    assert resp["days"] == 7
    assert len(resp["trend"]) == 7
    today = resp["trend"][-1]
    yesterday = resp["trend"][-2]
    assert today["lost"] == 1 and today["found"] == 2
    assert yesterday["lost"] == 1 and yesterday["found"] == 0


def test_recovery_empty_db_does_not_crash(client, make_admin):
    admin = make_admin(username="st_admin3")
    resp = client.get("/api/stats/admin/recovery", headers=admin["headers"])
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["recovery_rate"] == 0.0
    assert data["claimed_total"] == 0


def test_recovery_rate_math(client, make_admin, make_user, create_item_row):
    admin = make_admin(username="st_admin4")
    owner = make_user(username="st_owner4")

    # 1 claimed + 3 active → 找回率 1/4 = 0.25
    create_item_row(owner["id"], review_status="approved", status="claimed")
    for _ in range(3):
        create_item_row(owner["id"], review_status="approved", status="active")

    data = client.get("/api/stats/admin/recovery", headers=admin["headers"]).json()["data"]
    assert data["recovery_rate"] == 0.25
    assert data["by_type"]["lost"] >= 1
    assert data["active_count"] == 3


def test_category_pie_only_active_approved(client, make_admin, make_user, create_item_row):
    admin = make_admin(username="st_admin5")
    owner = make_user(username="st_owner5")

    create_item_row(owner["id"], category="电子产品", review_status="approved", status="active")
    create_item_row(owner["id"], category="电子产品", review_status="approved", status="active")
    create_item_row(owner["id"], category="书籍文具", review_status="approved", status="active")
    create_item_row(owner["id"], category="书籍文具", review_status="pending", status="pending")  # 不计入
    create_item_row(owner["id"], category="书籍文具", review_status="approved", status="claimed")  # 不计入

    cats = client.get("/api/stats/admin/category-pie", headers=admin["headers"]).json()["data"]["categories"]
    by_name = {c["name"]: c["count"] for c in cats}
    assert by_name["电子产品"] == 2
    assert by_name["书籍文具"] == 1
