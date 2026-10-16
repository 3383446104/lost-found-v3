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


# --------------------------------------------------------------------------- #
# v3.7.0：类型 / 封面 / 浏览计数
# --------------------------------------------------------------------------- #
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_v370_type_default_and_invalid(client, make_admin):
    admin = make_admin(username="an_v370_type")
    _create(client, admin)  # 未传 type → 默认 system
    assert client.get("/api/announcements?all=true", headers=admin["headers"]).json()["announcements"][0]["type"] == "system"

    assert _create(client, admin, type="weather").status_code == 400

    ann2 = _create(client, admin, type="lost").json()["id"]
    client.put(f"/api/announcements/{ann2}/publish", headers=admin["headers"])
    public = client.get("/api/announcements").json()
    assert [a for a in public["announcements"] if a["id"] == ann2][0]["type"] == "lost"


def test_v370_cover_image_on_create_and_update(client, make_admin):
    admin = make_admin(username="an_v370_cover")
    ann_id = _create(client, admin, cover_image="ann_test.jpg").json()["id"]
    item = client.get("/api/announcements?all=true", headers=admin["headers"]).json()["announcements"][0]
    assert item["cover_image"] == "ann_test.jpg"

    client.put(f"/api/announcements/{ann_id}",
               json={"title": "T", "content": "C", "status": "draft", "cover_image": "ann_new.jpg"},
               headers=admin["headers"])
    item = client.get("/api/announcements?all=true", headers=admin["headers"]).json()["announcements"][0]
    assert item["cover_image"] == "ann_new.jpg"


def test_v370_detail_visibility_and_view_count(client, make_admin):
    """草稿详情公开 404 / 管理员可见；已发布详情每次访问自增，列表同步展示。"""
    admin = make_admin(username="an_v370_detail")
    draft_id = _create(client, admin).json()["id"]  # 草稿
    pub_id = _create(client, admin, status="published").json()["id"]

    assert client.get(f"/api/announcements/{draft_id}").status_code == 404
    assert client.get(f"/api/announcements/{draft_id}", headers=admin["headers"]).status_code == 200

    d1 = client.get(f"/api/announcements/{pub_id}").json()["announcement"]
    assert d1["view_count"] == 1
    d2 = client.get(f"/api/announcements/{pub_id}").json()["announcement"]
    assert d2["view_count"] == 2

    public = client.get("/api/announcements").json()
    row = [a for a in public["announcements"] if a["id"] == pub_id][0]
    assert row["view_count"] == 2
    assert row["type"] == "system"


def test_v370_upload_cover_image(client, make_admin):
    admin = make_admin(username="an_v370_upload")
    resp = client.post(
        "/api/announcements/upload",
        files={"image": ("cover.png", PNG_1X1, "image/png")},
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    assert resp.json()["path"].startswith("ann_")
