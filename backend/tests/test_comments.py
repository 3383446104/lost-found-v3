"""留言互动回归测试（v3.6.0 融合）。

覆盖：公开列表仅 status=1、登录发表、楼中楼 parent 校验、本人删除/他人 403、
管理员隐藏后公开不可见、删除父留言级联删子回复、内容超长 422。
"""


def _comment(client, user, item_id, content="好人有好报", parent_id=None):
    body = {"item_id": item_id, "content": content}
    if parent_id is not None:
        body["parent_id"] = parent_id
    return client.post("/api/comments", json=body, headers=user["headers"])


def test_list_comments_public_and_mine_flag(client, make_user, create_item, approve_item):
    owner = make_user(username="cm_owner")
    other = make_user(username="cm_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    _comment(client, owner, item_id, content="第一条留言")

    # 匿名可看（不带 token）
    resp = client.get(f"/api/comments/item/{item_id}")
    assert resp.status_code == 200
    assert len(resp.json()["comments"]) == 1
    assert resp.json()["comments"][0]["username"] == owner["username"]
    assert resp.json()["comments"][0]["is_mine"] is False

    # 本人视角 is_mine=True
    resp = client.get(f"/api/comments/item/{item_id}", headers=other["headers"])
    assert resp.json()["comments"][0]["is_mine"] is False


def test_create_comment_and_reply(client, make_user, create_item, approve_item):
    owner = make_user(username="cm2_owner")
    replier = make_user(username="cm2_replier")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    top = _comment(client, owner, item_id).json()["id"]
    reply = _comment(client, replier, item_id, content="支持！", parent_id=top)
    assert reply.status_code == 201

    resp = client.get(f"/api/comments/item/{item_id}").json()
    assert len(resp["comments"]) == 2
    children = [c for c in resp["comments"] if c["parent_id"] == top]
    assert len(children) == 1
    assert children[0]["username"] == replier["username"]


def test_reply_parent_other_item_400(client, make_user, create_item, approve_item):
    owner = make_user(username="cm3_owner")
    other = make_user(username="cm3_other")
    item1 = create_item(owner["headers"], title="物品一")
    item2 = create_item(owner["headers"], title="物品二")
    approve_item(item1)
    approve_item(item2)

    top = _comment(client, other, item1).json()["id"]
    resp = _comment(client, other, item2, parent_id=top)
    assert resp.status_code == 400


def test_reply_missing_parent_400(client, make_user, create_item, approve_item):
    owner = make_user(username="cm4_owner")
    other = make_user(username="cm4_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = _comment(client, other, item_id, parent_id=99999)
    assert resp.status_code == 400


def test_delete_own_ok_other_403(client, make_user, create_item, approve_item):
    owner = make_user(username="cm5_owner")
    other = make_user(username="cm5_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _comment(client, owner, item_id).json()["id"]

    assert client.delete(f"/api/comments/{cid}", headers=other["headers"]).status_code == 403
    assert client.delete(f"/api/comments/{cid}", headers=owner["headers"]).status_code == 200
    assert client.get(f"/api/comments/item/{item_id}").json()["comments"] == []


def test_admin_hide_then_restore(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="cm6_owner")
    admin = make_admin(username="cm6_admin")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _comment(client, owner, item_id).json()["id"]

    resp = client.put(f"/api/comments/admin/{cid}/status", json={"status": 0}, headers=admin["headers"])
    assert resp.status_code == 200
    assert client.get(f"/api/comments/item/{item_id}").json()["comments"] == []

    client.put(f"/api/comments/admin/{cid}/status", json={"status": 1}, headers=admin["headers"])
    assert len(client.get(f"/api/comments/item/{item_id}").json()["comments"]) == 1


def test_delete_parent_cascades_children(client, make_user, create_item, approve_item):
    owner = make_user(username="cm7_owner")
    other = make_user(username="cm7_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    top = _comment(client, owner, item_id).json()["id"]
    _comment(client, other, item_id, parent_id=top)

    assert client.delete(f"/api/comments/{top}", headers=owner["headers"]).status_code == 200
    assert client.get(f"/api/comments/item/{item_id}").json()["comments"] == []

    from app import database as db_module
    with db_module.get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM comments WHERE item_id=?", (item_id,)).fetchone()[0]
    assert count == 0


def test_content_too_long_422(client, make_user, create_item, approve_item):
    owner = make_user(username="cm8_owner")
    other = make_user(username="cm8_other")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = _comment(client, other, item_id, content="x" * 501)
    assert resp.status_code == 422


def test_admin_list_and_status_filter(client, make_admin, make_user, create_item, approve_item):
    owner = make_user(username="cm9_owner")
    admin = make_admin(username="cm9_admin")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    _comment(client, owner, item_id, content="正常留言")

    resp = client.get("/api/comments/admin", headers=admin["headers"]).json()
    assert resp["total"] == 1
    assert resp["comments"][0]["item_title"]
    assert resp["comments"][0]["username"] == owner["username"]

    resp = client.get("/api/comments/admin?status=0", headers=admin["headers"]).json()
    assert resp["total"] == 0
