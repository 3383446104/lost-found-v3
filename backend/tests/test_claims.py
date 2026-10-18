"""认领闭环回归测试（v3.6.0 融合）。

覆盖：
- 创建申请：非本人可申请 / 本人 400 / 物品非 active 400 / 重复 status∈(0,1) 拦截
- 审批流：同意（互斥拒绝其他待审核 + 物品 claiming）/ 拒绝（理由必填）/ 完成（claimed + 计数器）/ 撤销
- 权限矩阵：非发布者审批 403 / 非本人撤销 403
- 隐私：申请人仅在已通过/完成后可见**脱敏**联系方式
- 闭环联动：mark-claimed 与已通过申请联动（claims 表口径）
"""
from app import database as db_module


def _apply_claim(client, claimer, item_id, **payload):
    body = {"item_id": item_id, **payload}
    return client.post("/api/claims", json=body, headers=claimer["headers"])


def _claim_id_by_item(db, item_id, claimer_id):
    with db.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM claims WHERE item_id=? AND claimer_id=? ORDER BY id DESC LIMIT 1",
            (item_id, claimer_id),
        )
        row = cur.fetchone()
        return row["id"] if row else None


# --------------------------------------------------------------------------- #
# 创建申请
# --------------------------------------------------------------------------- #
def test_create_claim_ok_and_notifies_owner(client, make_user, create_item, approve_item):
    owner = make_user(username="c_owner")
    claimer = make_user(username="c_claimer")
    item_id = create_item(owner["headers"], type="found")
    approve_item(item_id)

    resp = _apply_claim(client, claimer, item_id,
                        claim_reason="这是我的", feature_description="黑色，有划痕")
    assert resp.status_code == 201
    assert resp.json()["success"] is True

    # 落库 status=0
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT status, claim_reason, feature_description FROM claims WHERE item_id=?",
            (item_id,),
        ).fetchone()
    assert row["status"] == 0
    assert row["claim_reason"] == "这是我的"

    # 发布者收到站内通知
    notifs = client.get("/api/notifications/unread", headers=owner["headers"]).json()
    titles = [n["title"] for n in notifs.get("notifications", notifs.get("items", []))]
    assert any("认领" in t for t in titles)


def test_create_claim_own_item_400(client, make_user, create_item, approve_item):
    owner = make_user(username="c_own")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    resp = _apply_claim(client, owner, item_id)
    assert resp.status_code == 400


def test_create_claim_inactive_item_400(client, make_user, create_item):
    owner = make_user(username="c_inactive")
    claimer = make_user(username="c_inactive2")
    item_id = create_item(owner["headers"])  # 未审核
    resp = _apply_claim(client, claimer, item_id)
    assert resp.status_code == 400


def test_create_claim_duplicate_pending_400(client, make_user, create_item, approve_item):
    owner = make_user(username="c_dup_owner")
    claimer = make_user(username="c_dup_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    assert _apply_claim(client, claimer, item_id).status_code == 201
    assert _apply_claim(client, claimer, item_id).status_code == 400


def test_create_claim_after_reject_allowed(client, make_user, create_item, approve_item):
    """被拒绝后可重新申请（防重只拦 status∈(0,1)）。"""
    owner = make_user(username="c_rej_owner")
    claimer = make_user(username="c_rej_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    cid = _apply_claim(client, claimer, item_id).json()["id"]
    resp = client.post(
        f"/api/claims/{cid}/reject",
        json={"review_remark": "特征不符"},
        headers=owner["headers"],
    )
    assert resp.status_code == 200

    assert _apply_claim(client, claimer, item_id).status_code == 201


# --------------------------------------------------------------------------- #
# 审批流
# --------------------------------------------------------------------------- #
def test_approve_mutual_exclusion_and_item_claiming(client, make_user, create_item, approve_item):
    owner = make_user(username="ap_owner")
    a = make_user(username="ap_a")
    b = make_user(username="ap_b")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    c1 = _apply_claim(client, a, item_id).json()["id"]
    c2 = _apply_claim(client, b, item_id).json()["id"]

    resp = client.post(f"/api/claims/{c1}/approve", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["item_status"] == "claiming"

    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM claims WHERE id=?", (c1,))
        assert cur.fetchone()["status"] == 1
        cur.execute("SELECT status, review_remark FROM claims WHERE id=?", (c2,))
        row = cur.fetchone()
        assert row["status"] == 2
        assert "自动拒绝" in row["review_remark"]
        cur.execute("SELECT status FROM items WHERE id=?", (item_id,))
        assert cur.fetchone()["status"] == "claiming"


def test_approve_non_owner_403(client, make_user, create_item, approve_item):
    owner = make_user(username="ap2_owner")
    claimer = make_user(username="ap2_claimer")
    stranger = make_user(username="ap2_stranger")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    resp = client.post(f"/api/claims/{cid}/approve", headers=stranger["headers"])
    assert resp.status_code == 403


def test_reject_requires_remark(client, make_user, create_item, approve_item):
    owner = make_user(username="rj_owner")
    claimer = make_user(username="rj_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    resp = client.post(f"/api/claims/{cid}/reject", json={"review_remark": ""}, headers=owner["headers"])
    assert resp.status_code == 422

    resp = client.post(f"/api/claims/{cid}/reject", json={"review_remark": "特征不符"}, headers=owner["headers"])
    assert resp.status_code == 200

    # 物品保持 active（拒绝不锁物品）
    with db_module.get_db_connection() as conn:
        status = conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"]
    assert status == "active"


def test_complete_claims_item_and_counter(client, make_user, create_item, approve_item):
    owner = make_user(username="cp_owner")
    claimer = make_user(username="cp_claimer")
    item_id = create_item(owner["headers"], type="lost")
    approve_item(item_id)

    cid = _apply_claim(client, claimer, item_id).json()["id"]
    assert client.post(f"/api/claims/{cid}/approve", headers=owner["headers"]).status_code == 200

    resp = client.post(f"/api/claims/{cid}/complete", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "claimed"

    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM claims WHERE id=?", (cid,))
        assert cur.fetchone()["status"] == 3
        cur.execute("SELECT status FROM items WHERE id=?", (item_id,))
        assert cur.fetchone()["status"] == "claimed"
    assert db_module.get_counter("total_claimed") == 1


def test_complete_before_approve_400(client, make_user, create_item, approve_item):
    owner = make_user(username="cp2_owner")
    claimer = make_user(username="cp2_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    resp = client.post(f"/api/claims/{cid}/complete", headers=owner["headers"])
    assert resp.status_code == 400


def test_cancel_pending_by_claimer(client, make_user, create_item, approve_item):
    owner = make_user(username="cc_owner")
    claimer = make_user(username="cc_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    resp = client.post(f"/api/claims/{cid}/cancel", headers=claimer["headers"])
    assert resp.status_code == 200

    with db_module.get_db_connection() as conn:
        status = conn.execute("SELECT status FROM claims WHERE id=?", (cid,)).fetchone()["status"]
    assert status == 4
    # 物品保持 active
    with db_module.get_db_connection() as conn:
        item_status = conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"]
    assert item_status == "active"


def test_cancel_by_non_claimer_403(client, make_user, create_item, approve_item):
    owner = make_user(username="cc2_owner")
    claimer = make_user(username="cc2_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    resp = client.post(f"/api/claims/{cid}/cancel", headers=owner["headers"])
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# 隐私与查询
# --------------------------------------------------------------------------- #
def test_contact_full_for_claimer_after_approve(client, make_user, create_item, approve_item):
    owner = make_user(username="pm_owner")
    claimer = make_user(username="pm_claimer")
    item_id = create_item(owner["headers"], contact="13812345678")
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    # 待审核：看不到联系方式
    resp = client.get(f"/api/claims/{cid}", headers=claimer["headers"])
    assert resp.status_code == 200
    assert resp.json()["claim"]["owner_contact"] is None

    # 通过后：可见发布者完整联系方式（线下交接用）
    client.post(f"/api/claims/{cid}/approve", headers=owner["headers"])
    resp = client.get(f"/api/claims/{cid}", headers=claimer["headers"])
    assert resp.json()["claim"]["owner_contact"] == "13812345678"

    # 发布者视角：可见申请人完整电话快照
    resp = client.get(f"/api/claims/{cid}", headers=owner["headers"])
    assert resp.json()["claim"]["contact_phone"] == claimer["phone"]


def test_get_claim_forbidden_for_stranger(client, make_user, create_item, approve_item):
    owner = make_user(username="pf_owner")
    claimer = make_user(username="pf_claimer")
    stranger = make_user(username="pf_stranger")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]

    resp = client.get(f"/api/claims/{cid}", headers=stranger["headers"])
    assert resp.status_code == 403


def test_mine_and_received_lists(client, make_user, create_item, approve_item):
    owner = make_user(username="ls_owner")
    claimer = make_user(username="ls_claimer")
    item_id = create_item(owner["headers"], type="found")
    approve_item(item_id)
    _apply_claim(client, claimer, item_id)

    mine = client.get("/api/claims/mine", headers=claimer["headers"]).json()
    assert mine["total"] == 1
    assert mine["claims"][0]["item_id"] == item_id
    assert mine["claims"][0]["title"]

    received = client.get("/api/claims/received", headers=owner["headers"]).json()
    assert received["total"] == 1
    assert received["claims"][0]["claimer_username"] == claimer["username"]

    # 状态过滤
    pending = client.get("/api/claims/received?status=0", headers=owner["headers"]).json()
    assert pending["total"] == 1
    done = client.get("/api/claims/received?status=3", headers=owner["headers"]).json()
    assert done["total"] == 0


# --------------------------------------------------------------------------- #
# mark-claimed 与认领闭环联动
# --------------------------------------------------------------------------- #
def test_mark_claimed_links_approved_claim(client, make_user, create_item, approve_item):
    owner = make_user(username="mk_owner")
    claimer = make_user(username="mk_claimer")
    item_id = create_item(owner["headers"], type="lost")
    approve_item(item_id)
    cid = _apply_claim(client, claimer, item_id).json()["id"]
    client.post(f"/api/claims/{cid}/approve", headers=owner["headers"])

    resp = client.put(f"/api/items/{item_id}/mark-claimed", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["new_status"] == "claimed"

    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM claims WHERE id=?", (cid,))
        assert cur.fetchone()["status"] == 3
    # 计数器只 +1（不因联动重复计数）
    assert db_module.get_counter("total_claimed") == 1


def test_claim_status_endpoint(client, make_user, create_item, approve_item):
    owner = make_user(username="cs_owner")
    claimer = make_user(username="cs_claimer")
    item_id = create_item(owner["headers"])
    approve_item(item_id)

    resp = client.get(f"/api/claims/status/{item_id}", headers=claimer["headers"])
    assert resp.json()["claim"] is None

    _apply_claim(client, claimer, item_id)
    resp = client.get(f"/api/claims/status/{item_id}", headers=claimer["headers"])
    assert resp.json()["claim"]["status"] == 0
