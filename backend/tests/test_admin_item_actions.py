# -*- coding: utf-8 -*-
"""管理后台物品处置口径（v3.7.0）。

背景：`status='closed'` 曾被**手动关闭**与**账号注销兜底**两条路径共用。
用户确认「手动关闭」并不在设计里，故移除：

- 管理员不能再把物品设为 `closed`（单个 / 批量都不行）；
- 但**系统兜底必须保留** —— 删除用户时其物品仍要自动下架，
  否则会变成挂在已注销账号下的僵尸帖，且联系方式永久失联。
"""
from app import database as db_module


def _status_of(item_id):
    with db_module.get_db_connection() as conn:
        return conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"]


def test_admin_cannot_manually_close_item(client, make_admin, make_user,
                                          create_item, approve_item):
    admin = make_admin(username="adm_close")
    owner = make_user(username="own_close")
    item_id = create_item(owner["headers"], title="不许手动下架")
    approve_item(item_id)

    resp = client.put(f"/api/admin/items/{item_id}/status",
                      json={"status": "closed"}, headers=admin["headers"])
    assert resp.status_code == 400
    assert _status_of(item_id) == "active", "被拒绝时不得改动数据"


def test_batch_close_is_rejected(client, make_admin, make_user, create_item, approve_item):
    admin = make_admin(username="adm_batch")
    owner = make_user(username="own_batch")
    item_id = create_item(owner["headers"], title="批量关闭已移除")
    approve_item(item_id)

    resp = client.post("/api/admin/items/batch",
                       json={"ids": [item_id], "action": "close"},
                       headers=admin["headers"])
    assert resp.status_code == 400
    assert _status_of(item_id) == "active"


def test_delete_user_still_closes_their_items(client, make_admin, make_user,
                                              create_item, approve_item):
    """兜底不可丢：删用户 → 其 active 物品自动 closed（保留数据、停止展示）。"""
    admin = make_admin(username="adm_deluser")
    owner = make_user(username="own_deluser")
    item_id = create_item(owner["headers"], title="注销后自动下架")
    approve_item(item_id)
    assert _status_of(item_id) == "active"

    resp = client.delete(f"/api/admin/users/{owner['id']}", headers=admin["headers"])
    assert resp.status_code == 200
    assert _status_of(item_id) == "closed"


def test_admin_can_still_set_claimed(client, make_admin, make_user,
                                    create_item, approve_item):
    """移除的只是 closed，'标记已找回/归还' 仍应可用（防止误删过头）。"""
    admin = make_admin(username="adm_claimed")
    owner = make_user(username="own_claimed")
    item_id = create_item(owner["headers"], title="仍可标记已找回")
    approve_item(item_id)

    resp = client.put(f"/api/admin/items/{item_id}/status",
                      json={"status": "claimed"}, headers=admin["headers"])
    assert resp.status_code == 200
    assert _status_of(item_id) == "claimed"
