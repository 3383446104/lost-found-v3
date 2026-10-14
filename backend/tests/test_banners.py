"""轮播图回归测试（v3.6.0 融合）。

覆盖：公开列表仅启用且按 sort_no 升序、admin CRUD 全链路、非 admin 403、上传文件头校验。
"""
import io

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(client, admin, filename="b.png"):
    return client.post(
        "/api/banners/upload",
        files={"image": (filename, io.BytesIO(PNG_1X1), "image/png")},
        headers=admin["headers"],
    )


def _create(client, admin, image_path, **kwargs):
    body = {"title": "开学季活动", "image_path": image_path, "sort_no": 0, "status": 1, **kwargs}
    return client.post("/api/banners/admin", json=body, headers=admin["headers"])


def test_public_list_only_enabled_sorted(client, make_admin):
    admin = make_admin(username="bn_admin")
    p1 = _upload(client, admin).json()["path"]
    p2 = _upload(client, admin).json()["path"]

    _create(client, admin, p1, title="后", sort_no=2)
    _create(client, admin, p2, title="前", sort_no=1)
    _create(client, admin, p2, title="停用", sort_no=0, status=0)

    resp = client.get("/api/banners").json()["banners"]
    assert [b["title"] for b in resp] == ["前", "后"]


def test_admin_crud_flow(client, make_admin):
    admin = make_admin(username="bn_admin2")
    path = _upload(client, admin).json()["path"]

    bid = _create(client, admin, path, title="第一张").json()["id"]

    # 改
    resp = client.put(
        f"/api/banners/admin/{bid}",
        json={"title": "改名", "sort_no": 5},
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    admin_list = client.get("/api/banners/admin", headers=admin["headers"]).json()["banners"]
    row = next(b for b in admin_list if b["id"] == bid)
    assert row["title"] == "改名" and row["sort_no"] == 5

    # 空更新 400
    assert client.put(f"/api/banners/admin/{bid}", json={}, headers=admin["headers"]).status_code == 400

    # 删
    assert client.delete(f"/api/banners/admin/{bid}", headers=admin["headers"]).status_code == 200
    assert client.get("/api/banners/admin", headers=admin["headers"]).json()["banners"] == []


def test_non_admin_403(client, make_user):
    user = make_user(username="bn_user")
    assert client.get("/api/banners/admin", headers=user["headers"]).status_code == 403
    assert client.post("/api/banners/upload", headers=user["headers"]).status_code == 403
    assert client.post("/api/banners/admin", json={}, headers=user["headers"]).status_code == 403
    assert client.put("/api/banners/admin/1", json={}, headers=user["headers"]).status_code == 403
    assert client.delete("/api/banners/admin/1", headers=user["headers"]).status_code == 403


def test_upload_rejects_bad_file(client, make_admin):
    admin = make_admin(username="bn_admin3")
    resp = client.post(
        "/api/banners/upload",
        files={"image": ("evil.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers=admin["headers"],
    )
    assert resp.status_code == 400


def test_upload_without_auth_401(client):
    assert client.post("/api/banners/upload").status_code in (401, 403)
