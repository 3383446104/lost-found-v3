"""认证与鉴权回归测试。

覆盖：注册 / 登录（成功、密码错误、被禁用）/ 当前用户；
以及 R1：被禁用用户的已签发 JWT 仍可越权访问（P0）。
"""
from app import database as db_module


def test_register_returns_201_and_token(client):
    resp = client.post(
        "/api/register",
        json={"username": "newuser", "password": "pass1234", "phone": "13800000001"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["token"]
    assert body["user"]["username"] == "newuser"
    assert isinstance(body["user"]["id"], int)


def test_login_success_returns_token_and_role(client, make_user):
    user = make_user(username="loginuser")
    resp = client.post(
        "/api/login", json={"username": "loginuser", "password": user["password"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"]
    assert body["user"]["role"] == "user"


def test_login_wrong_password_401(client, make_user):
    make_user(username="pwuser")
    resp = client.post("/api/login", json={"username": "pwuser", "password": "wrongpass"})
    assert resp.status_code == 401


def test_login_disabled_user_403(client, make_user):
    # C2：禁用态由独立列 status 表达（role 收敛为 user/admin）
    make_user(username="disabledlogin", status="disabled")
    resp = client.post(
        "/api/login", json={"username": "disabledlogin", "password": "pass1234"}
    )
    assert resp.status_code == 403


def test_get_me_ok(client, make_user):
    user = make_user(username="meuser")
    resp = client.get("/api/me", headers=user["headers"])
    assert resp.status_code == 200
    assert resp.json()["user"]["username"] == "meuser"


def test_disabled_user_old_token_is_rejected(client, make_user):
    """【R1 回归守护】用户被管理员禁用后，其已签发的 JWT 必须立即失效。

    C2 之后禁用态落在独立的 ``users.status`` 列（``role`` 仅表授权角色）。
    ``get_current_user`` 读取 ``status`` 并对 ``disabled`` 返回 403，故旧 token 立即失效。
    本用例现为纯回归守护（原为暴露缺陷的红灯用例）。
    """
    user = make_user(username="victim")

    # 前置：禁用前旧 token 正常可用（模拟用户已登录持有 7 天 JWT）
    assert client.get("/api/me", headers=user["headers"]).status_code == 200

    # 管理员禁用该用户（C2：写入 status 列）
    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE users SET status='disabled' WHERE id=?", (user["id"],))

    # 旧 token 再次访问受保护接口，期望 403
    resp = client.get("/api/me", headers=user["headers"])
    assert resp.status_code == 403, (
        f"[R1] 被禁用用户的旧 token 仍可访问受保护接口，实际返回 {resp.status_code}；"
        "期望 403（get_current_user 依 status='disabled' 拦截）"
    )


def test_deleted_user_token_is_rejected(client, make_user):
    """注销（``status='deleted'``）用户的 token 必须被拒绝（C2 后由 status 表达）。"""
    user = make_user(username="deleter")
    assert client.delete("/api/me", headers=user["headers"]).status_code == 200
    resp = client.get("/api/me", headers=user["headers"])
    assert resp.status_code == 403


def test_protected_endpoint_without_token_is_rejected(client):
    """HTTPBearer 无凭证访问受保护接口应被拒绝。"""
    resp = client.get("/api/me")
    assert resp.status_code in (401, 403)
