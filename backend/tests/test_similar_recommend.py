"""相似推荐与推荐位回归测试（v3.6.0 融合）。

覆盖：similar 排除自身、仅反类型 active+approved、未审核目标 404、
recommend 仅 is_recommend=1、审核带 is_recommend 落库 / 不带不改。
"""
import json

import numpy as np

from app import database as db_module
from app.config import settings


def _unit_vec(dim):
    v = np.ones(dim, dtype=np.float32)
    return json.dumps((v / np.linalg.norm(v)).tolist())


def _insert_item_with_vectors(user_id, type, image_vector=None, text_vector=None,
                              status="active", review_status="approved", title="物品"):
    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO items (type, title, description, category, location, status,
                                  review_status, user_id, image_vector, text_vector)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (type, title, "", "其他", "", status, review_status, user_id,
             image_vector, text_vector),
        )
        return cur.lastrowid


def test_similar_returns_opposite_type_only(client, make_user):
    dim = int(settings.CLIP_CN_EMBED_DIM)
    owner = make_user(username="sr_owner")
    vec = _unit_vec(dim)

    target = _insert_item_with_vectors(owner["id"], "lost", image_vector=vec, text_vector=vec)
    # 同类型同向量（本应命中但被反类型条件排除）
    _insert_item_with_vectors(owner["id"], "lost", image_vector=vec, text_vector=vec, title="同类")
    # 反类型同向量 → 图-图余弦 1.0，必过阈值
    hit = _insert_item_with_vectors(owner["id"], "found", image_vector=vec, text_vector=vec, title="招领")

    resp = client.get(f"/api/items/{target}/similar")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == hit
    assert "level" in items[0]


def test_similar_excludes_pending_target_404(client, make_user):
    dim = int(settings.CLIP_CN_EMBED_DIM)
    owner = make_user(username="sr_owner2")
    vec = _unit_vec(dim)
    target = _insert_item_with_vectors(owner["id"], "lost", image_vector=vec,
                                       status="pending", review_status="pending")

    resp = client.get(f"/api/items/{target}/similar")
    assert resp.status_code == 404


def test_similar_requires_vectors(client, make_user):
    """无向量的目标（图/文向量均为空）返回空列表不报错。"""
    owner = make_user(username="sr_owner3")
    target = _insert_item_with_vectors(owner["id"], "lost")
    _insert_item_with_vectors(owner["id"], "found", title="无向量招领")

    resp = client.get(f"/api/items/{target}/similar")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_recommend_latest_approved_first(client, make_user, create_item_row):
    """推荐位新口径：自动展示最近审核通过的物品（review_time 降序），无需手动勾选。"""
    owner = make_user(username="sr_owner4")
    early = create_item_row(owner["id"], type="lost", status="active", review_status="approved", title="先通过")
    late = create_item_row(owner["id"], type="lost", status="active", review_status="approved", title="后通过")
    pending = create_item_row(owner["id"], type="lost", status="pending", review_status="pending", title="未审核")

    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE items SET review_time='2026-10-01 00:00:00' WHERE id=?", (early,))
        conn.execute("UPDATE items SET review_time='2026-10-02 00:00:00' WHERE id=?", (late,))

    resp = client.get("/api/items/recommend")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [late, early], f"应按最近通过排序: {[i['id'] for i in items]}"
    assert pending not in [i["id"] for i in items]

    # 类型过滤
    resp = client.get("/api/items/recommend?type=found")
    assert resp.json()["items"] == []
    resp = client.get("/api/items/recommend?type=bad")
    assert resp.status_code == 400


def test_review_payload_sets_recommend(client, make_admin, make_user, create_item):
    admin = make_admin(username="sr_admin")
    owner = make_user(username="sr_owner5")
    item_id = create_item(owner["headers"])

    resp = client.put(
        f"/api/admin/reviews/{item_id}",
        json={"action": "approved", "is_recommend": True},
        headers=admin["headers"],
    )
    assert resp.status_code == 200

    with db_module.get_db_connection() as conn:
        row = conn.execute("SELECT is_recommend FROM items WHERE id=?", (item_id,)).fetchone()
    assert row["is_recommend"] == 1

    # 不带字段 → 不改
    item2 = create_item(owner["headers"], title="第二个")
    resp = client.put(
        f"/api/admin/reviews/{item2}",
        json={"action": "approved"},
        headers=admin["headers"],
    )
    assert resp.status_code == 200
    with db_module.get_db_connection() as conn:
        row = conn.execute("SELECT is_recommend FROM items WHERE id=?", (item2,)).fetchone()
    assert row["is_recommend"] == 0


def test_admin_items_list_includes_recommend(client, make_admin, make_user, create_item):
    admin = make_admin(username="sr_admin2")
    user = make_user(username="sr_owner6")
    item_id = create_item(user["headers"])

    resp = client.get("/api/admin/items", headers=admin["headers"]).json()
    row = next(i for i in resp["items"] if i["id"] == item_id)
    assert "is_recommend" in row
    assert "images" in row
