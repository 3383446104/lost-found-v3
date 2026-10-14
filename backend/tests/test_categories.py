"""分类管理回归测试（v3.6.0 融合）。

覆盖：公开列表（表驱动 + 种子回退）、admin 增改删、使用中删除 400、
新增后公开列表包含新类、非 admin 403。
"""


def test_public_categories_seeded(client):
    resp = client.get("/api/items/categories")
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert len(cats) > 0
    assert "电子产品" in cats


def test_admin_create_and_public_list(client, make_admin):
    admin = make_admin(username="cat_admin")

    resp = client.post("/api/categories/admin", json={"name": "运动器材", "sort_no": 99}, headers=admin["headers"])
    assert resp.status_code == 201

    cats = client.get("/api/items/categories").json()["categories"]
    assert "运动器材" in cats


def test_admin_duplicate_name_400(client, make_admin):
    admin = make_admin(username="cat_admin2")
    resp = client.post("/api/categories/admin", json={"name": "电子产品"}, headers=admin["headers"])
    assert resp.status_code == 400


def test_admin_update_rename(client, make_admin):
    admin = make_admin(username="cat_admin3")
    cid = client.post("/api/categories/admin", json={"name": "数码配件", "sort_no": 1}, headers=admin["headers"]).json()["id"]

    resp = client.put(f"/api/categories/admin/{cid}", json={"name": "数码周边", "sort_no": 2}, headers=admin["headers"])
    assert resp.status_code == 200

    admin_list = client.get("/api/categories/admin", headers=admin["headers"]).json()["categories"]
    row = next(c for c in admin_list if c["id"] == cid)
    assert row["name"] == "数码周边" and row["sort_no"] == 2


def test_delete_used_category_400(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="cat_owner")
    admin = make_admin(username="cat_admin4")
    item_id = create_item(owner["headers"], category="电子产品")
    approve_item(item_id)

    # 找到「电子产品」的分类 id
    admin_list = client.get("/api/categories/admin", headers=admin["headers"]).json()["categories"]
    row = next(c for c in admin_list if c["name"] == "电子产品")

    resp = client.delete(f"/api/categories/admin/{row['id']}", headers=admin["headers"])
    assert resp.status_code == 400


def test_delete_unused_category_ok(client, make_admin):
    admin = make_admin(username="cat_admin5")
    cid = client.post("/api/categories/admin", json={"name": "临时分类"}, headers=admin["headers"]).json()["id"]

    assert client.delete(f"/api/categories/admin/{cid}", headers=admin["headers"]).status_code == 200
    assert "临时分类" not in client.get("/api/items/categories").json()["categories"]


def test_non_admin_403(client, make_user):
    user = make_user(username="cat_user")
    assert client.get("/api/categories/admin", headers=user["headers"]).status_code == 403
    assert client.post("/api/categories/admin", json={"name": "x"}, headers=user["headers"]).status_code == 403
    assert client.put("/api/categories/admin/1", json={"name": "x"}, headers=user["headers"]).status_code == 403
    assert client.delete("/api/categories/admin/1", headers=user["headers"]).status_code == 403
