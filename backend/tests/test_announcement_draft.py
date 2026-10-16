"""公告草稿/发布分离回归测试（v3.6.0 融合）。

覆盖：默认存草稿公开不可见、发布后可见、all=true 管理员可见草稿、
publish/unpublish 流转、既有字段（置顶/定向）回归。
"""


def _create(client, admin, **kwargs):
    body = {"title": "测试公告", "content": "公告内容", **kwargs}
    return client.post("/api/announcements", json=body, headers=admin["headers"])


def test_draft_invisible_public_visible_after_publish(client, make_admin):
    admin = make_admin(username="an_admin")

    ann_id = _create(client, admin).json()["id"]  # 默认草稿
    assert client.get("/api/announcements").json()["total"] == 0

    assert client.put(f"/api/announcements/{ann_id}/publish", headers=admin["headers"]).status_code == 200
    public = client.get("/api/announcements").json()
    assert public["total"] == 1
    assert public["announcements"][0]["status"] == "published"

    # 下架后公开不可见
    client.put(f"/api/announcements/{ann_id}/unpublish", headers=admin["headers"])
    assert client.get("/api/announcements").json()["total"] == 0


def test_direct_publish_on_create(client, make_admin):
    admin = make_admin(username="an_admin2")
    _create(client, admin, status="published")
    assert client.get("/api/announcements").json()["total"] == 1


def test_admin_all_sees_draft(client, make_admin):
    admin = make_admin(username="an_admin3")
    _create(client, admin)  # 草稿

    resp = client.get("/api/announcements?all=true", headers=admin["headers"]).json()
    assert resp["total"] == 1
    assert resp["announcements"][0]["status"] == "draft"


def test_ordinary_user_all_flag_no_effect(client, make_admin, make_user):
    admin = make_admin(username="an_admin4")
    user = make_user(username="an_user")
    _create(client, admin)  # 草稿

    resp = client.get("/api/announcements?all=true", headers=user["headers"]).json()
    assert resp["total"] == 0


def test_invalid_status_400(client, make_admin):
    admin = make_admin(username="an_admin5")
    resp = _create(client, admin, status="archived")
    assert resp.status_code == 400


def test_pinned_target_role_regression(client, make_admin):
    admin = make_admin(username="an_admin6")
    ann_id = _create(client, admin, status="published", is_pinned=1, target_role="all").json()["id"]

    public = client.get("/api/announcements").json()
    assert public["total"] == 1
    assert public["announcements"][0]["is_pinned"] == 1
    assert public["announcements"][0]["target_role"] == "all"

    # 编辑保留原字段
    client.put(
        f"/api/announcements/{ann_id}",
        json={"title": "改名", "content": "新内容", "is_pinned": 0, "target_role": "all", "status": "published"},
        headers=admin["headers"],
    )
    public = client.get("/api/announcements").json()
    assert public["announcements"][0]["title"] == "改名"
    assert public["announcements"][0]["is_pinned"] == 0
