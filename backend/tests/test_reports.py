"""举报体系回归测试（v3.6.0 融合）。

覆盖：提交校验（原因必填/类型越界/重复待处理拦截）、我的举报进度、
管理端列表筛选、详情并排数据包、处理留痕 + 举报人通知、权限矩阵。
"""


def _report(client, reporter, item_id, **kwargs):
    body = {"item_id": item_id, "report_type": 1, "report_reason": "信息不实", **kwargs}
    return client.post("/api/reports", json=body, headers=reporter["headers"])


def test_create_report_ok(client, make_user, create_item, approve_item):
    owner = make_user(username="rp_owner")
    reporter = make_user(username="rp_reporter")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = _report(client, reporter, item_id, report_type=2, report_reason="内容低俗")
    assert resp.status_code == 201

    mine = client.get("/api/reports/mine", headers=reporter["headers"]).json()
    assert mine["total"] == 1
    assert mine["reports"][0]["report_type"] == 2
    assert mine["reports"][0]["handle_status"] == 0
    assert mine["reports"][0]["item_title"]


def test_create_report_missing_reason_422(client, make_user, create_item, approve_item):
    owner = make_user(username="rp2_owner")
    reporter = make_user(username="rp2_reporter")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = _report(client, reporter, item_id, report_reason="")
    assert resp.status_code == 422


def test_create_report_type_out_of_range_422(client, make_user, create_item, approve_item):
    owner = make_user(username="rp3_owner")
    reporter = make_user(username="rp3_reporter")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = _report(client, reporter, item_id, report_type=9)
    assert resp.status_code == 422


def test_create_report_duplicate_pending_400(client, make_user, create_item, approve_item):
    owner = make_user(username="rp4_owner")
    reporter = make_user(username="rp4_reporter")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    assert _report(client, reporter, item_id).status_code == 201
    assert _report(client, reporter, item_id).status_code == 400


def test_create_report_after_handled_allowed(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="rp5_owner")
    reporter = make_user(username="rp5_reporter")
    admin = make_admin(username="rp5_admin")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    rid = _report(client, reporter, item_id).json()["id"]
    resp = client.put(
        f"/api/reports/admin/{rid}/handle",
        json={"handle_status": 2, "handle_result": "内容核实无误"},
        headers=admin["headers"],
    )
    assert resp.status_code == 200

    # 已驳回后可再次举报
    assert _report(client, reporter, item_id).status_code == 201


def test_handle_report_requires_result(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="rp6_owner")
    reporter = make_user(username="rp6_reporter")
    admin = make_admin(username="rp6_admin")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    rid = _report(client, reporter, item_id).json()["id"]

    resp = client.put(
        f"/api/reports/admin/{rid}/handle",
        json={"handle_status": 1, "handle_result": ""},
        headers=admin["headers"],
    )
    assert resp.status_code == 422

    resp = client.put(
        f"/api/reports/admin/{rid}/handle",
        json={"handle_status": 1, "handle_result": "已下架该物品"},
        headers=admin["headers"],
    )
    assert resp.status_code == 200

    # 留痕：handler_id + handle_time 落库
    from app import database as db_module
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT handle_status, handle_result, handler_id, handle_time FROM reports WHERE id=?",
            (rid,),
        ).fetchone()
    assert row["handle_status"] == 1
    assert row["handle_result"] == "已下架该物品"
    assert row["handler_id"] == admin["id"]
    assert row["handle_time"]

    # 举报人收到处理通知
    notifs = client.get("/api/notifications/unread", headers=reporter["headers"]).json()
    titles = [n["title"] for n in notifs.get("notifications", notifs.get("items", []))]
    assert any("举报" in t for t in titles)


def test_handle_report_twice_400(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="rp7_owner")
    reporter = make_user(username="rp7_reporter")
    admin = make_admin(username="rp7_admin")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    rid = _report(client, reporter, item_id).json()["id"]

    payload = {"handle_status": 1, "handle_result": "处理"}
    assert client.put(f"/api/reports/admin/{rid}/handle", json=payload, headers=admin["headers"]).status_code == 200
    assert client.put(f"/api/reports/admin/{rid}/handle", json=payload, headers=admin["headers"]).status_code == 400


def test_admin_list_filters(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="rp8_owner")
    r1 = make_user(username="rp8_r1")
    r2 = make_user(username="rp8_r2")
    admin = make_admin(username="rp8_admin")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    rid1 = _report(client, r1, item_id, report_type=4, report_reason="重复发布").json()["id"]
    _report(client, r2, item_id, report_type=1)

    # 按类型筛选
    resp = client.get("/api/reports/admin?report_type=4", headers=admin["headers"]).json()
    assert resp["total"] == 1
    assert resp["reports"][0]["id"] == rid1
    assert resp["reports"][0]["reporter_username"] == r1["username"]

    # 按状态筛选
    resp = client.get("/api/reports/admin?handle_status=0", headers=admin["headers"]).json()
    assert resp["total"] == 2

    # 详情并排数据包
    detail = client.get(f"/api/reports/admin/{rid1}", headers=admin["headers"]).json()
    assert detail["report"]["report_type"] == 4
    assert detail["item"]["id"] == item_id
    assert detail["item"]["title"]


def test_admin_endpoints_require_admin(client, make_user, create_item, approve_item):
    owner = make_user(username="rp9_owner")
    reporter = make_user(username="rp9_reporter")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    rid = _report(client, reporter, item_id).json()["id"]

    assert client.get("/api/reports/admin", headers=reporter["headers"]).status_code == 403
    assert client.get(f"/api/reports/admin/{rid}", headers=reporter["headers"]).status_code == 403
    resp = client.put(
        f"/api/reports/admin/{rid}/handle",
        json={"handle_status": 1, "handle_result": "x"},
        headers=reporter["headers"],
    )
    assert resp.status_code == 403
