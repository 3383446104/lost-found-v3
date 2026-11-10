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


# --------------------------------------------------------------------------- #
# 发布者撤销已同意的认领（v3.7.0 补的回路）
# --------------------------------------------------------------------------- #
def _approved_claim(client, owner, claimer, item_id):
    """建一条「已同意」的申请，返回 claim_id（物品此时为 claiming）。"""
    resp = _apply_claim(client, claimer, item_id, claim_reason="我的")
    assert resp.status_code == 201
    cid = _claim_id_by_item(db_module, item_id, claimer["id"])
    assert client.post(f"/api/claims/{cid}/approve", headers=owner["headers"]).status_code == 200
    return cid


def test_revoke_restores_item_to_active(client, make_user, create_item, approve_item):
    """撤销后：申请作废（status=4）、物品重新上架（active）、申请人收到通知。"""
    owner = make_user(username="rv_owner")
    claimer = make_user(username="rv_claimer")
    item_id = create_item(owner["headers"], title="撤销用耳机")
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    with db_module.get_db_connection() as conn:
        assert conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"] == "claiming"

    resp = client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["item_status"] == "active"

    with db_module.get_db_connection() as conn:
        assert conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"] == "active"
        assert conn.execute("SELECT status FROM claims WHERE id=?", (cid,)).fetchone()["status"] == 4

    # 物品重新出现在公共列表（不再被 status='active' 过滤掉）
    ids = [it["id"] for it in client.get("/api/items/").json()["items"]]
    assert item_id in ids

    # 申请人收到撤销通知
    notifs = client.get("/api/notifications/unread", headers=claimer["headers"]).json()
    titles = [n["title"] for n in notifs.get("notifications", notifs.get("items", []))]
    assert any("撤销" in t for t in titles)


def test_revoke_by_stranger_403(client, make_user, create_item, approve_item):
    owner = make_user(username="rv_owner2")
    claimer = make_user(username="rv_claimer2")
    stranger = make_user(username="rv_stranger")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    resp = client.post(f"/api/claims/{cid}/revoke", headers=stranger["headers"])
    assert resp.status_code == 403


def test_revoke_after_complete_400(client, make_user, create_item, approve_item):
    """交接已完成（item=claimed）后不可撤销 —— 否则会把已归还的物品重新挂出去。"""
    owner = make_user(username="rv_owner3")
    claimer = make_user(username="rv_claimer3")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)
    assert client.post(f"/api/claims/{cid}/complete", headers=owner["headers"]).status_code == 200

    resp = client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"])
    assert resp.status_code == 400


def test_revoke_twice_400(client, make_user, create_item, approve_item):
    owner = make_user(username="rv_owner4")
    claimer = make_user(username="rv_claimer4")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    assert client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"]).status_code == 200
    assert client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"]).status_code == 400


# --------------------------------------------------------------------------- #
# 发布者撤销已同意的认领（v3.7.0 补的回路）
# --------------------------------------------------------------------------- #
def _approved_claim(client, owner, claimer, item_id):
    """建一条「已同意」的申请，返回 claim_id（物品此时为 claiming）。"""
    resp = _apply_claim(client, claimer, item_id, claim_reason="我的")
    assert resp.status_code == 201
    cid = _claim_id_by_item(db_module, item_id, claimer["id"])
    assert client.post(f"/api/claims/{cid}/approve", headers=owner["headers"]).status_code == 200
    return cid


def test_revoke_restores_item_to_active(client, make_user, create_item, approve_item):
    """撤销后：申请作废（status=4）、物品重新上架（active）、申请人收到通知。"""
    owner = make_user(username="rv_owner")
    claimer = make_user(username="rv_claimer")
    item_id = create_item(owner["headers"], title="撤销用耳机")
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    with db_module.get_db_connection() as conn:
        assert conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"] == "claiming"

    resp = client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"])
    assert resp.status_code == 200
    assert resp.json()["item_status"] == "active"

    with db_module.get_db_connection() as conn:
        assert conn.execute("SELECT status FROM items WHERE id=?", (item_id,)).fetchone()["status"] == "active"
        assert conn.execute("SELECT status FROM claims WHERE id=?", (cid,)).fetchone()["status"] == 4

    # 物品重新出现在公共列表（不再被 status='active' 过滤掉）
    ids = [it["id"] for it in client.get("/api/items/").json()["items"]]
    assert item_id in ids

    # 申请人收到撤销通知
    notifs = client.get("/api/notifications/unread", headers=claimer["headers"]).json()
    titles = [n["title"] for n in notifs.get("notifications", notifs.get("items", []))]
    assert any("撤销" in t for t in titles)


def test_revoke_by_stranger_403(client, make_user, create_item, approve_item):
    owner = make_user(username="rv_owner2")
    claimer = make_user(username="rv_claimer2")
    stranger = make_user(username="rv_stranger")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    resp = client.post(f"/api/claims/{cid}/revoke", headers=stranger["headers"])
    assert resp.status_code == 403


def test_revoke_after_complete_400(client, make_user, create_item, approve_item):
    """交接已完成（item=claimed）后不可撤销 —— 否则会把已归还的物品重新挂出去。"""
    owner = make_user(username="rv_owner3")
    claimer = make_user(username="rv_claimer3")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)
    assert client.post(f"/api/claims/{cid}/complete", headers=owner["headers"]).status_code == 200

    resp = client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"])
    assert resp.status_code == 400


def test_revoke_twice_400(client, make_user, create_item, approve_item):
    owner = make_user(username="rv_owner4")
    claimer = make_user(username="rv_claimer4")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    assert client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"]).status_code == 200
    assert client.post(f"/api/claims/{cid}/revoke", headers=owner["headers"]).status_code == 400


# --------------------------------------------------------------------------- #
# 认领中物品的可见性（2026-11-10 修复：申请人从认领中心点进来 404）
# --------------------------------------------------------------------------- #
def test_claimer_can_open_claiming_item_with_full_contact(
        client, make_user, create_item, approve_item):
    """同意认领后：申请人能打开详情页，且能看到发布者**完整**联系方式。

    旧规则 `status='active'` 把申请人挡在门外（404），
    导致「认领通过 → 详情页显示完整联系方式」这条业务链路在页面上走不到。
    """
    owner = make_user(username="vis_owner")
    claimer = make_user(username="vis_claimer")
    item_id = create_item(owner["headers"], title="认领中可见", contact="13800138000")
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)

    # 申请人可打开详情页（物品此时为 claiming）
    resp = client.get(f"/api/items/{item_id}", headers=claimer["headers"])
    assert resp.status_code == 200
    body = resp.json()["item"]
    # 详情页上的 contact 仍脱敏；完整号码走 claims 接口（分级可见）
    assert body["contact"] == "138****8000"

    claim = client.get(f"/api/claims/{cid}", headers=claimer["headers"]).json()["claim"]
    assert claim["owner_contact"] == "13800138000"

    # 详情页的两个子请求也不能 404（否则前端会弹「物品不存在」）
    assert client.get(f"/api/items/{item_id}/similar", headers=claimer["headers"]).status_code == 200
    assert client.get(f"/api/comments/item/{item_id}", headers=claimer["headers"]).status_code == 200


def test_stranger_cannot_open_claiming_item(client, make_user, create_item, approve_item):
    """无关用户仍不可见（不是所有人都能围观认领中的物品）。"""
    owner = make_user(username="vis_owner2")
    claimer = make_user(username="vis_claimer2")
    stranger = make_user(username="vis_stranger")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    _approved_claim(client, owner, claimer, item_id)

    assert client.get(f"/api/items/{item_id}", headers=stranger["headers"]).status_code == 404
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_owner_can_open_claiming_item_and_similar(client, make_user, create_item, approve_item):
    """发布者打开认领中物品：详情 + 相似推荐 + 留言都应为 200（旧实现弹窗的根因）。"""
    owner = make_user(username="vis_owner3")
    claimer = make_user(username="vis_claimer3")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    _approved_claim(client, owner, claimer, item_id)

    assert client.get(f"/api/items/{item_id}", headers=owner["headers"]).status_code == 200
    assert client.get(f"/api/items/{item_id}/similar", headers=owner["headers"]).status_code == 200
    assert client.get(f"/api/comments/item/{item_id}", headers=owner["headers"]).status_code == 200


def test_after_complete_both_parties_can_still_view(client, make_user, create_item, approve_item):
    """交接完成后（claimed）双方仍能回看，避免历史通知里的链接变成 404。"""
    owner = make_user(username="vis_owner4")
    claimer = make_user(username="vis_claimer4")
    item_id = create_item(owner["headers"])
    approve_item(item_id)
    cid = _approved_claim(client, owner, claimer, item_id)
    assert client.post(f"/api/claims/{cid}/complete", headers=owner["headers"]).status_code == 200

    assert client.get(f"/api/items/{item_id}", headers=claimer["headers"]).status_code == 200
    assert client.get(f"/api/items/{item_id}", headers=owner["headers"]).status_code == 200


def test_claim_notifications_link_to_valid_item_route(
        client, make_user, create_item, approve_item):
    """通知链接必须是**存在的路由**，否则 router.push 静默失败（点了没反应）。

    2026-11-10 反馈：发布者从消息界面点「收到认领申请」无法跳转，申请人却能跳。
    根因：发布者通知写的是 `/claims/received`——前端没有这个路由（只有
    `/claims` + `?tab=received`）；而申请人通知一直用的是 `/items/{id}`，所以正常。
    """
    owner = make_user(username="lk_owner")
    claimer = make_user(username="lk_claimer")
    item_id = create_item(owner["headers"], title="通知链接测试")
    approve_item(item_id)

    # 1) 收到申请 → 发布者通知指向物品详情
    assert _apply_claim(client, claimer, item_id, claim_reason="我的").status_code == 201
    notifs = client.get("/api/notifications/unread", headers=owner["headers"]).json()
    rows = notifs.get("notifications", notifs.get("items", []))
    assert any(n["link"] == f"/items/{item_id}" for n in rows), \
        f"发布者通知链接错误: {[n.get('link') for n in rows]}"

    # 2) 撤销申请 → 发布者通知同样指向物品详情（原先也是坏链接）
    cid = _claim_id_by_item(db_module, item_id, claimer["id"])
    assert client.post(f"/api/claims/{cid}/cancel", headers=claimer["headers"]).status_code == 200
    notifs = client.get("/api/notifications/unread", headers=owner["headers"]).json()
    rows = notifs.get("notifications", notifs.get("items", []))
    assert any(n["link"] == f"/items/{item_id}" for n in rows)
    assert all(n["link"] != "/claims/received" for n in rows)
