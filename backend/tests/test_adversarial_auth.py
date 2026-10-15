"""对抗性验证 A：R1 鉴权修复的边界（尝试证伪）。

目标：确认「禁用即失效」在更多路径上成立，且未把 401/403 语义弄混。
"""
from app import database as db_module


def test_disabled_admin_old_token_403_not_500(client, make_admin):
    """被禁用的管理员：旧 token 访问管理端应 403，且绝不能退化为 500。

    说明（保留原样，不改）：本用例把 ``role`` 写成非法值 ``'disabled'``（C2 之后
    ``role`` 只应为 user/admin）。它依旧通过 —— 因为老 token 的「失去管理员身份」
    由 ``get_current_admin`` 的 ``role != 'admin'`` 分支拦下，不依赖 ``status``。
    C2 真正语义（role 保留 admin、status=disabled）的守护见
    ``test_disabled_admin_true_status_403_not_500``。
    """
    admin = make_admin(username="adv_admin")
    # 前置：禁用前该 token 可访问管理端
    assert client.get("/api/admin/users", headers=admin["headers"]).status_code == 200

    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE users SET role='disabled' WHERE id=?", (admin["id"],))

    resp = client.get("/api/admin/users", headers=admin["headers"])
    assert resp.status_code == 403, f"期望 403，实得 {resp.status_code}"
    assert resp.status_code != 500


def test_disabled_admin_true_status_403_not_500(client, make_admin):
    """C2 语义守护：``role`` 保留 ``admin``、``status`` 置 ``disabled`` 的管理员，旧 token 应 403 且非 500。"""
    admin = make_admin(username="adv_admin_status")

    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE users SET status='disabled' WHERE id=?", (admin["id"],))
        row = conn.execute(
            "SELECT role, status FROM users WHERE id=?", (admin["id"],)
        ).fetchone()
    assert row["role"] == "admin" and row["status"] == "disabled"

    resp = client.get("/api/admin/users", headers=admin["headers"])
    assert resp.status_code == 403, f"期望 403，实得 {resp.status_code}"
    assert resp.status_code != 500


def test_disabled_user_token_write_endpoint_403(client, make_user):
    """被禁用用户的旧 token 调写接口（发布物品）应 403。"""
    user = make_user(username="adv_writer")
    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE users SET status='disabled' WHERE id=?", (user["id"],))

    resp = client.post(
        "/api/items/",
        data={
            "type": "lost",
            "title": "禁用后仍想发布",
            "description": "x",
            "category": "其他",
            "contact": "",
            "location": "",
        },
        headers=user["headers"],
    )
    assert resp.status_code == 403, f"期望 403，实得 {resp.status_code}"


def test_physically_deleted_user_token_401(client, make_user):
    """用户行被物理删除后，旧 token 应返回 401（用户不存在），不得与 403 分支混淆。"""
    user = make_user(username="adv_ghost")
    assert client.get("/api/me", headers=user["headers"]).status_code == 200

    with db_module.get_db_connection() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user["id"],))

    resp = client.get("/api/me", headers=user["headers"])
    assert resp.status_code == 401, f"期望 401（用户不存在），实得 {resp.status_code}"


def test_login_disabled_user_still_403_after_fix(client, make_user):
    """回归：登录环节对禁用用户的 403 拦截未被修复破坏。"""
    make_user(username="adv_login_disabled", status="disabled")
    resp = client.post(
        "/api/login",
        json={"username": "adv_login_disabled", "password": "pass1234"},
    )
    assert resp.status_code == 403


def test_disabled_user_token_downgraded_by_public_item_endpoints_c1(
    client, make_user, create_item
):
    """【C1 回归守护】公开物品接口必须把 disabled 用户降级为匿名。

    修复前（残留缺陷）：``GET /api/items/`` 与 ``GET /api/items/{id}`` 只用
    ``verify_token`` 解析 viewer 身份、不校验账号状态，导致被禁用用户仍以「属主」
    身份看到自己未审核的物品。

    C1 之后：两处统一改用 ``resolve_optional_viewer``（``dependencies/auth.py:89``），
    ``status != 'active'`` 一律返回 ``None``（匿名）。因此被禁用用户：
      - 公开列表看不到自己那条 pending 物品；
      - 公开详情对自己的 pending 物品返回 **404**（按匿名「未审核不可见」规则），
        而不是 200；且任何情况都不得 500。
    """
    user = make_user(username="adv_residual")
    item_id = create_item(user["headers"], title="禁用用户自己的待审物品")

    # 前置佐证：禁用前，属主可见自己的 pending 物品（说明下面「看不到」确由 status 降级导致）
    assert client.get(f"/api/items/{item_id}", headers=user["headers"]).status_code == 200

    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE users SET status='disabled' WHERE id=?", (user["id"],))

    # 受保护接口已被正确拦截（R1 修复生效）
    assert client.get("/api/me", headers=user["headers"]).status_code == 403

    # 公开列表：降级为匿名 → 看不到自己那条 pending 物品，且不报错
    list_resp = client.get("/api/items/", headers=user["headers"])
    assert list_resp.status_code == 200
    assert item_id not in {it["id"] for it in list_resp.json()["items"]}

    # 公开详情：对自己 pending 物品按匿名对待 → 404（不再是 200），且绝不 500
    detail_resp = client.get(f"/api/items/{item_id}", headers=user["headers"])
    assert detail_resp.status_code == 404, (
        f"C1 未生效：禁用用户仍以属主身份看到自己的 pending 物品（实得 {detail_resp.status_code}）"
    )
    assert detail_resp.status_code != 500
