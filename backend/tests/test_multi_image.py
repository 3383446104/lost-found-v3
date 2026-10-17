"""多图上传与多图匹配回归测试（v3.6.0 融合）。

覆盖：发布 3 图（首图封面、images JSON 有序）、4 图 400、编辑 keep 重排换封面
（向量重算）、无图编辑保原状、多图匹配聚合（归一化均值再归一化）、单图回归。
"""
import io
import json

import numpy as np

from app import database as db_module

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _png(name="a.png"):
    return (name, io.BytesIO(PNG_1X1), "image/png")


def _post_images(client, headers, n, **fields):
    files = [("images", _png(f"img{i}.png")) for i in range(n)]
    data = {"type": "lost", "title": "多图物品", "description": "测试", "category": "其他",
            "contact": "", "location": "图书馆", **fields}
    return client.post("/api/items/", data=data, files=files, headers=headers)


def test_publish_three_images(client, make_user):
    user = make_user(username="mi_user")
    resp = _post_images(client, user["headers"], 3)
    assert resp.status_code == 201, resp.text
    item_id = resp.json()["id"]

    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT image_path, cover_image, images FROM items WHERE id=?", (item_id,)
        ).fetchone()
    names = json.loads(row["images"])
    assert len(names) == 3
    assert row["cover_image"] == names[0]
    assert row["image_path"].endswith(names[0])


def test_publish_four_images_400(client, make_user):
    user = make_user(username="mi_user2")
    resp = _post_images(client, user["headers"], 4)
    assert resp.status_code == 400


def test_publish_single_image_compat(client, make_user):
    """旧单图字段 image 仍可用，images 回填为单元素列表。"""
    user = make_user(username="mi_user3")
    resp = client.post(
        "/api/items/",
        data={"type": "found", "title": "单图", "description": "", "category": "其他",
              "contact": "", "location": ""},
        files={"image": _png("single.png")},
        headers=user["headers"],
    )
    assert resp.status_code == 201
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT image_path, cover_image, images FROM items WHERE id=?",
            (resp.json()["id"],),
        ).fetchone()
    names = json.loads(row["images"])
    assert len(names) == 1
    assert row["cover_image"] == names[0]


def test_update_keep_reorder_changes_cover(client, make_user):
    user = make_user(username="mi_user4")
    item_id = _post_images(client, user["headers"], 2).json()["id"]

    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT image_vector, images FROM items WHERE id=?", (item_id,)
        ).fetchone()
    names = json.loads(row["images"])
    old_vector = row["image_vector"]

    # keep 反转顺序 → 封面变成第二张，向量重算
    keep = json.dumps([names[1], names[0]])
    resp = client.put(
        f"/api/items/{item_id}",
        data={"title": "改名", "description": "", "category": "其他",
              "contact": "", "location": "", "keep": keep},
        headers=user["headers"],
    )
    assert resp.status_code == 200, resp.text

    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT image_path, cover_image, images, image_vector FROM items WHERE id=?",
            (item_id,),
        ).fetchone()
    assert row["cover_image"] == names[1]
    assert row["image_path"].endswith(names[1])
    assert json.loads(row["images"]) == [names[1], names[0]]
    # 封面变化 → 向量按新封面文件重算（stub 由路径派生，与旧向量不同）
    assert row["image_vector"] != old_vector


def test_update_without_images_preserves_list(client, make_user):
    user = make_user(username="mi_user5")
    item_id = _post_images(client, user["headers"], 2).json()["id"]

    resp = client.put(
        f"/api/items/{item_id}",
        data={"title": "只改标题", "description": "", "category": "其他",
              "contact": "", "location": ""},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    with db_module.get_db_connection() as conn:
        row = conn.execute("SELECT images FROM items WHERE id=?", (item_id,)).fetchone()
    assert len(json.loads(row["images"])) == 2


def test_update_keep_invalid_file_400(client, make_user):
    user = make_user(username="mi_user6")
    item_id = _post_images(client, user["headers"], 2).json()["id"]

    resp = client.put(
        f"/api/items/{item_id}",
        data={"title": "x", "description": "", "category": "其他",
              "contact": "", "location": "", "keep": json.dumps(["not_exist.png"])},
        headers=user["headers"],
    )
    assert resp.status_code == 400


def test_aggregate_query_vectors_math():
    """聚合 = 各向量归一化 → 均值 → 再归一化（正交向量均值后模长为 1/√2 → 归一化回 1）。"""
    from app.api.items import _aggregate_query_vectors

    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    out = _aggregate_query_vectors([v1, v2])
    assert abs(float(np.linalg.norm(out)) - 1.0) < 1e-6
    # 两个标准基向量的均值归一化 = 对角方向
    assert out[0] == out[1]
    assert abs(out[2]) < 1e-6


def test_match_with_image_paths(client, make_user, create_item, approve_item):
    """多图匹配：两张临时图命中目标（stub 图向量由路径派生，跨模态通道兜底命中）。"""
    user = make_user(username="mi_user7")
    owner = make_user(username="mi_owner")
    item_id = create_item(owner["headers"], type="found", title="黑色钱包")
    approve_item(item_id)

    # 上传两张临时图
    paths = []
    for i in range(2):
        r = client.post(
            "/api/items/temp-upload",
            files={"image": _png(f"t{i}.png")},
            headers=user["headers"],
        )
        assert r.status_code == 200
        paths.append(r.json()["path"])

    resp = client.post(
        "/api/items/match",
        json={"image_paths": paths, "text": "黑色钱包", "target_type": "found",
              "threshold": 0.0},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    data = resp.json()
    # 图文混合模式（文字命中目标文字向量）
    ids = [m["id"] for m in data["matches"]]
    assert item_id in ids
    hit = next(m for m in data["matches"] if m["id"] == item_id)
    assert hit["match_source"] == "mixed"


def test_match_image_paths_more_than_3_422(client, make_user):
    user = make_user(username="mi_user8")
    resp = client.post(
        "/api/items/match",
        json={"image_paths": ["a", "b", "c", "d"], "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 422
