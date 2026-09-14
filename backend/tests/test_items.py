"""物品模块回归测试。

覆盖：
- 列表可见性（仅「已审核+活跃」对他人可见，自己的物品对自己可见）
- ``get_item``（items.py:221）的可见性与字段裁剪（防信息泄露）
- 发布物品的初始状态
- R6：路由顺序守护（静态路径不被参数化路径吞掉）
- 认领 / 标记已找回
"""
from app import database as db_module

# 最小合法 1x1 PNG（供 temp-upload 的 imghdr 文件头校验使用）
PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


# --------------------------------------------------------------------------- #
# 列表可见性
# --------------------------------------------------------------------------- #
def test_list_items_only_approved_active_for_others(client, make_user, create_item, approve_item):
    owner = make_user(username="owner_list")
    other = make_user(username="other_list")

    pending_id = create_item(owner["headers"], title="未审核物品")
    approved_id = create_item(owner["headers"], title="已审核物品")
    approve_item(approved_id)

    # 匿名：看不到未审核物品，能看到已审核+活跃物品
    anon = client.get("/api/items/")
    assert anon.status_code == 200
    anon_ids = {it["id"] for it in anon.json()["items"]}
    assert pending_id not in anon_ids
    assert approved_id in anon_ids

    # 其他登录用户：同样看不到未审核物品
    other_ids = {it["id"] for it in client.get("/api/items/", headers=other["headers"]).json()["items"]}
    assert pending_id not in other_ids
    assert approved_id in other_ids

    # 属主：可以看到自己的未审核物品
    owner_ids = {it["id"] for it in client.get("/api/items/", headers=owner["headers"]).json()["items"]}
    assert pending_id in owner_ids


# --------------------------------------------------------------------------- #
# get_item（items.py:221）逐条覆盖
# --------------------------------------------------------------------------- #
def test_get_item_not_found_404(client):
    assert client.get("/api/items/999999").status_code == 404


def test_get_item_pending_non_owner_404(client, make_user, create_item):
    owner = make_user(username="pend_owner")
    other = make_user(username="pend_other")
    item_id = create_item(owner["headers"])  # 默认 pending

    # 非属主（含匿名）访问未审核物品 → 404（防信息泄露，而非 403）
    assert client.get(f"/api/items/{item_id}", headers=other["headers"]).status_code == 404
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_get_item_pending_owner_200(client, make_user, create_item):
    owner = make_user(username="pend_owner2")
    item_id = create_item(owner["headers"])

    resp = client.get(f"/api/items/{item_id}", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["item"]["id"] == item_id


def test_get_item_approved_active_non_owner_hides_user_id(
    client, make_user, create_item, approve_item
):
    owner = make_user(username="appr_owner")
    other = make_user(username="appr_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = client.get(f"/api/items/{item_id}", headers=other["headers"])
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert "user_id" not in item
    # 任何情况下都不得暴露向量字段
    assert "image_vector" not in item
    assert "text_vector" not in item


def test_get_item_owner_includes_user_id(client, make_user, create_item, approve_item):
    owner = make_user(username="appr_owner2")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = client.get(f"/api/items/{item_id}", headers=owner["headers"])
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["user_id"] == owner["id"]
    assert "image_vector" not in item
    assert "text_vector" not in item


# --------------------------------------------------------------------------- #
# 发布物品初始状态
# --------------------------------------------------------------------------- #
def test_create_item_initial_pending(client, make_user):
    user = make_user(username="creator")
    resp = client.post(
        "/api/items/",
        data={
            "type": "lost",
            "title": "校园卡丢失",
            "description": "在食堂丢失",
            "category": "证件卡片",
            "contact": "",
            "location": "一食堂",
        },
        headers=user["headers"],
    )
    assert resp.status_code == 201
    item_id = resp.json()["id"]

    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT review_status, status FROM items WHERE id=?", (item_id,)
        ).fetchone()
    assert row["review_status"] == "pending"
    assert row["status"] == "pending"


# --------------------------------------------------------------------------- #
# R6：路由顺序守护（静态路径不得被参数化路径吞掉）
# --------------------------------------------------------------------------- #
def test_route_order_categories_not_swallowed(client):
    resp = client.get("/api/items/categories")
    assert resp.status_code == 200, (
        "R6: /api/items/categories 被 /{item_id} 吞掉（items.py 路由顺序被破坏）"
    )
    categories = resp.json().get("categories")
    assert isinstance(categories, list)
    assert len(categories) > 0


def test_route_order_match_not_swallowed(client, make_user):
    # v3.4.1 起 POST /match 需登录；带上普通用户 header，断言目标仍是「路由未被吞掉」
    user = make_user(username="route_match_user")
    resp = client.post(
        "/api/items/match",
        json={"text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code != 404, "R6: /api/items/match 被参数化路由吞掉"
    assert resp.status_code == 200
    assert "matches" in resp.json()


def test_route_order_temp_upload_not_swallowed(client, make_user):
    user = make_user(username="uploader")
    files = {"image": ("temp.png", PNG_1X1, "image/png")}
    resp = client.post("/api/items/temp-upload", files=files, headers=user["headers"])
    assert resp.status_code != 404, "R6: /api/items/temp-upload 被参数化路由吞掉"
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("success") is True
    assert body.get("path", "").startswith("temp_")


# --------------------------------------------------------------------------- #
# POST /api/items/match 鉴权契约（v3.4.1）
# --------------------------------------------------------------------------- #
def test_match_without_token_403_not_authenticated(client):
    """无 Authorization 头 → 403（HTTPBearer auto_error=True），detail='Not authenticated'。"""
    resp = client.post(
        "/api/items/match", json={"text": "黑色钱包", "target_type": "found"}
    )
    assert resp.status_code == 403, f"期望 403，实得 {resp.status_code}"
    assert resp.json().get("detail") == "Not authenticated"


def test_match_with_invalid_token_401(client):
    """带非法 token → 401，detail 含「无效或过期」（与「无凭证 403」区分）。"""
    resp = client.post(
        "/api/items/match",
        json={"text": "黑色钱包", "target_type": "found"},
        headers={"Authorization": "Bearer garbage"},
    )
    assert resp.status_code == 401, f"期望 401，实得 {resp.status_code}"
    assert "无效或过期" in resp.json().get("detail", "")


# --------------------------------------------------------------------------- #
# 认领 / 标记已找回
# --------------------------------------------------------------------------- #
def test_claim_own_item_400(client, make_user, create_item, approve_item):
    owner = make_user(username="claim_owner")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = client.post(f"/api/items/{item_id}/claim", headers=owner["headers"])
    assert resp.status_code == 400


def test_claim_same_item_twice_400(client, make_user, create_item, approve_item):
    owner = make_user(username="claim_owner2")
    other = make_user(username="claim_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    first = client.post(f"/api/items/{item_id}/claim", headers=other["headers"])
    assert first.status_code == 200

    second = client.post(f"/api/items/{item_id}/claim", headers=other["headers"])
    assert second.status_code == 400


def test_mark_claimed_by_owner(client, make_user, create_item, approve_item):
    owner = make_user(username="mark_owner")
    other = make_user(username="mark_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = client.put(f"/api/items/{item_id}/mark-claimed", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "claimed"

    # 状态落库为 claimed
    with db_module.get_db_connection() as conn:
        status = conn.execute(
            "SELECT status FROM items WHERE id=?", (item_id,)
        ).fetchone()["status"]
    assert status == "claimed"

    # 从他人列表中消失
    other_ids = {it["id"] for it in client.get("/api/items/", headers=other["headers"]).json()["items"]}
    assert item_id not in other_ids

    # 持久化计数器 total_claimed +1
    assert db_module.get_counter("total_claimed") == 1


def test_mark_claimed_non_owner_403(client, make_user, create_item, approve_item):
    owner = make_user(username="mark_owner2")
    other = make_user(username="mark_other2")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = client.put(f"/api/items/{item_id}/mark-claimed", headers=other["headers"])
    assert resp.status_code == 403
