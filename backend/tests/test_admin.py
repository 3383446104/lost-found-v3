"""管理员审核与用户管理回归测试。

覆盖：权限门禁、审核通过/重复审核（并发安全）、驳回必填理由、
管理员不能删除自己。
"""
from app import database as db_module


def test_normal_user_cannot_access_users(client, make_user):
    user = make_user(username="plain_user")
    resp = client.get("/api/admin/users", headers=user["headers"])
    assert resp.status_code == 403


def test_approve_sets_approved_and_active(client, make_user, make_admin, create_item):
    user = make_user(username="ap_user")
    admin = make_admin(username="ap_admin")
    item_id = create_item(user["headers"])

    resp = client.put(
        f"/api/admin/reviews/{item_id}", json={"action": "approved"}, headers=admin["headers"]
    )
    assert resp.status_code == 200

    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT review_status, status FROM items WHERE id=?", (item_id,)
        ).fetchone()
    assert row["review_status"] == "approved"
    assert row["status"] == "active"


def test_approve_twice_is_not_silently_accepted(client, make_user, make_admin, create_item):
    """【并发防重复】同一物品连续两次审核通过，第二次必须显式报错（400/409）。"""
    user = make_user(username="dup_user")
    admin = make_admin(username="dup_admin")
    item_id = create_item(user["headers"])

    first = client.put(
        f"/api/admin/reviews/{item_id}", json={"action": "approved"}, headers=admin["headers"]
    )
    assert first.status_code == 200

    second = client.put(
        f"/api/admin/reviews/{item_id}", json={"action": "approved"}, headers=admin["headers"]
    )
    assert second.status_code in (400, 409), (
        f"重复审核返回 {second.status_code}，不得静默成功"
    )


def test_reject_without_reason_is_rejected(client, make_user, make_admin, create_item):
    user = make_user(username="rej_user")
    admin = make_admin(username="rej_admin")
    item_id = create_item(user["headers"])

    resp = client.put(
        f"/api/admin/reviews/{item_id}", json={"action": "rejected"}, headers=admin["headers"]
    )
    assert resp.status_code in (400, 422)


def test_admin_cannot_delete_self_400(client, make_admin):
    admin = make_admin(username="self_admin")
    resp = client.delete(f"/api/admin/users/{admin['id']}", headers=admin["headers"])
    assert resp.status_code == 400
