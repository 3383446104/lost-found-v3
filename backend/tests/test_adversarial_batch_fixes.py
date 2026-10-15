"""对抗性验证 E（#8 收口）：C1/C2/R4/R6/R9 + 迁移幂等的补充对抗用例。

覆盖团队长 #8 清单中在本轮新落的对抗用例：
- O2 自锁保护（管理员不得禁用/删除自己；可禁用其他管理员）
- C1 补充（deleted 用户经公开接口按匿名对待）
- R6 路由顺序（静态路径不被 :int 参数路由吞；非数字 id → 404 而非 500/422）
- R9 请求模型错误码契约（宽松模型不把 400 变成 422）
- 迁移幂等（init_db 连跑两次无副作用 + PRAGMA 列存在 + 旧库 role→status 映射）

仅断言行为，不依赖实现细节；不修改 ``app/`` 任何产品代码。
"""
import sqlite3

from app import database as db_module


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _role_status(user_id):
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT role, status FROM users WHERE id=?", (user_id,)
        ).fetchone()
    return row["role"], row["status"]


# --------------------------------------------------------------------------- #
# O2：自锁保护
# --------------------------------------------------------------------------- #
def test_o2_admin_cannot_toggle_own_status_400(client, make_admin):
    """管理员对**自己**执行 toggle_status → 400，且状态不被改动（防自锁）。"""
    admin = make_admin(username="o2_self")
    resp = client.put(
        f"/api/admin/users/{admin['id']}",
        json={"action": "toggle_status"},
        headers=admin["headers"],
    )
    assert resp.status_code == 400, f"禁用自己应被拒绝(400)，实得 {resp.status_code}"
    role, status = _role_status(admin["id"])
    assert status == "active", "自锁保护失效：自己的 status 被改动"

    # 自己仍可正常访问管理端
    assert client.get("/api/admin/users", headers=admin["headers"]).status_code == 200


def test_o2_admin_cannot_delete_self_400(client, make_admin):
    """管理员删除**自己** → 400，且账号未被软删除。"""
    admin = make_admin(username="o2_del_self")
    resp = client.delete(f"/api/admin/users/{admin['id']}", headers=admin["headers"])
    assert resp.status_code == 400, f"删除自己应被拒绝(400)，实得 {resp.status_code}"

    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT status, username FROM users WHERE id=?", (admin["id"],)
        ).fetchone()
    assert row["status"] == "active"
    assert not row["username"].endswith(f"_deleted_{admin['id']}")


def test_o2_admin_can_disable_other_admin_200(client, make_admin):
    """管理员禁用**另一个**管理员 → 200；被禁者 role 保留 admin、旧 token 立即 403。"""
    actor = make_admin(username="o2_actor")
    target = make_admin(username="o2_target")

    resp = client.put(
        f"/api/admin/users/{target['id']}",
        json={"action": "toggle_status"},
        headers=actor["headers"],
    )
    assert resp.status_code == 200

    role, status = _role_status(target["id"])
    assert status == "disabled"
    assert role == "admin", "C2：禁用其他管理员不应改动其 role"
    assert client.get("/api/admin/users", headers=target["headers"]).status_code == 403


# --------------------------------------------------------------------------- #
# C1：deleted 用户公开接口按匿名对待
# --------------------------------------------------------------------------- #
def test_c1_deleted_user_public_endpoints_treated_as_anonymous(
    client, make_user, create_item
):
    """deleted 用户旧 token 访问公开接口 → 按匿名处理：列表 200 且看不到自己 pending，详情 404、非 500。"""
    user = make_user(username="c1_deleted")
    item_id = create_item(user["headers"], title="注销用户的待审物品")

    # 前置：注销前属主可见自己的 pending 物品（说明下面「看不到」确由 status 降级导致）
    assert client.get(f"/api/items/{item_id}", headers=user["headers"]).status_code == 200

    # 注销（软删除 → status='deleted'）
    assert client.delete("/api/me", headers=user["headers"]).status_code == 200

    # 受保护接口已被拒绝
    assert client.get("/api/me", headers=user["headers"]).status_code == 403

    # 公开列表：降级为匿名，仍 200，但看不到自己那条物品
    list_resp = client.get("/api/items/", headers=user["headers"])
    assert list_resp.status_code == 200
    assert item_id not in {it["id"] for it in list_resp.json()["items"]}

    # 公开详情：按匿名「未审核不可见」→ 404，且绝不 500
    detail_resp = client.get(f"/api/items/{item_id}", headers=user["headers"])
    assert detail_resp.status_code == 404, (
        f"C1 未生效：deleted 用户仍以属主身份看到自己的物品（实得 {detail_resp.status_code}）"
    )
    assert detail_resp.status_code != 500


# --------------------------------------------------------------------------- #
# R6：路由顺序（结构性保证）
# --------------------------------------------------------------------------- #
def test_r6_categories_not_swallowed(client):
    """静态路径 /api/items/categories 必须可达（未被 /{item_id:int} 吞掉）。"""
    resp = client.get("/api/items/categories")
    assert resp.status_code == 200
    cats = resp.json().get("categories")
    assert isinstance(cats, list) and len(cats) > 0


def test_r6_non_int_item_id_404_not_500(client):
    """非数字 item_id 由 :int 转换器排除 → 404，绝不能 500。"""
    resp = client.get("/api/items/abc")
    assert resp.status_code == 404, f"期望 404，实得 {resp.status_code}"
    assert resp.status_code != 500


def test_r6_non_int_admin_user_id_404_not_422(client, make_admin):
    """非数字 user_id 走不到位（:int 转换器）→ 404，而非 422。"""
    admin = make_admin(username="r6_admin")
    resp = client.put(
        "/api/admin/users/abc", json={"action": "set_role"}, headers=admin["headers"]
    )
    assert resp.status_code == 404, f"期望 404，实得 {resp.status_code}"


def test_r6_review_non_int_id_404_not_422(client, make_admin):
    """PUT /admin/reviews/{item_id:int} 对非数字 id → 404（而非 422/500）。"""
    admin = make_admin(username="r6_review_admin")
    resp = client.put(
        "/api/admin/reviews/abc", json={"action": "approved"}, headers=admin["headers"]
    )
    assert resp.status_code == 404, f"期望 404，实得 {resp.status_code}"


# --------------------------------------------------------------------------- #
# R9：请求模型错误码契约（宽松模型不把 400 变 422）
# --------------------------------------------------------------------------- #
def test_r9_update_profile_empty_body_400_not_422(client, make_user):
    """PUT /api/me 空对象 → 400（「没有需要更新的字段」），不是 422。"""
    user = make_user(username="r9_me")
    resp = client.put("/api/me", json={}, headers=user["headers"])
    assert resp.status_code == 400, f"期望 400，实得 {resp.status_code}"


def test_r9_update_profile_illegal_value_400_not_422(client, make_user):
    """PUT /api/me 非法值（用户名过短）→ 由 handler 判 400，不是模型 422。"""
    user = make_user(username="r9_me2")
    resp = client.put("/api/me", json={"username": "a"}, headers=user["headers"])
    assert resp.status_code == 400, f"期望 400，实得 {resp.status_code}"


def test_r9_admin_user_update_bad_action_400_not_422(client, make_admin, make_user):
    """PUT /admin/users/{id} action 非二值 → 400，不是 422。"""
    admin = make_admin(username="r9_admin")
    target = make_user(username="r9_target")
    resp = client.put(
        f"/api/admin/users/{target['id']}",
        json={"action": "bogus"},
        headers=admin["headers"],
    )
    assert resp.status_code == 400, f"期望 400，实得 {resp.status_code}"


def test_r9_admin_user_update_missing_action_400_not_422(client, make_admin, make_user):
    """R9 契约：缺 action 应沿用旧行为的 **400**（宽松模型不引入新的必填约束）。

    ⚠️ 实测当前返回 422（``UserUpdateRequest.action: str`` 被声明为必填，Pydantic
    在进入 handler 前拦截）—— 与 R9「模型只做结构声明、不把 400 变 422」的原则相悖，
    且与同文件 ``BatchItemsRequest.action: str = ""`` 的写法不一致。详见验证报告 R9 偏差。
    """
    admin = make_admin(username="r9_admin2")
    target = make_user(username="r9_target2")
    resp = client.put(
        f"/api/admin/users/{target['id']}",
        json={},
        headers=admin["headers"],
    )
    assert resp.status_code == 400, (
        f"R9：缺 action 期望 400（旧行为），实得 {resp.status_code}"
        f"（models/admin.py 将 action 声明为必填，产生 422）"
    )


def test_r9_admin_batch_items_bad_action_400_not_422(client, make_admin):
    """POST /admin/items/batch 参数错误 → 400，不是 422。"""
    admin = make_admin(username="r9_admin3")
    resp = client.post(
        "/api/admin/items/batch",
        json={"ids": [], "action": "bogus"},
        headers=admin["headers"],
    )
    assert resp.status_code == 400, f"期望 400，实得 {resp.status_code}"


def test_r9_admin_item_status_bad_value_400_not_422(client, make_admin):
    """PUT /admin/items/{id}/status 非法状态值 → 400，不是 422。"""
    admin = make_admin(username="r9_admin4")
    resp = client.put(
        "/api/admin/items/1/status",
        json={"status": "bogus"},
        headers=admin["headers"],
    )
    assert resp.status_code == 400, f"期望 400，实得 {resp.status_code}"


# --------------------------------------------------------------------------- #
# 迁移幂等
# --------------------------------------------------------------------------- #
def test_migration_init_db_twice_no_side_effects(client, make_user, create_item):
    """同一库连续两次 init_db()：无异常、数据不变。"""
    user = make_user(username="mig_idem")
    create_item(user["headers"], title="迁移幂等物品")

    def snapshot():
        with db_module.get_db_connection() as conn:
            users = [dict(r) for r in conn.execute(
                "SELECT id, username, role, status FROM users ORDER BY id")]
            items = [dict(r) for r in conn.execute(
                "SELECT id, title, review_status, status FROM items ORDER BY id")]
        return users, items

    before = snapshot()
    db_module.init_db()
    db_module.init_db()
    after = snapshot()
    assert before == after, "init_db 重复执行改动了数据（迁移非幂等）"


def test_migration_schema_has_status_column(client):
    """PRAGMA 校验：users 含 status。"""
    with db_module.get_db_connection() as conn:
        users_cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    assert "status" in users_cols, f"users 缺 status 列：{users_cols}"


def test_migration_legacy_role_values_mapped_to_status(tmp_path, monkeypatch):
    """模拟旧库（无 status 列、role 存 disabled/deleted）：init_db 应完成一次性 role→status 映射。

    且重复 init_db 不得二次改写（幂等来源：映射写在「新增列」分支内）。
    """
    from app.config import settings

    legacy = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(legacy))
    conn.execute(
        """CREATE TABLE users (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT UNIQUE, password_hash TEXT, phone TEXT, email TEXT,
               role TEXT DEFAULT 'user', created_at TIMESTAMP)"""
    )
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('legacy_admin','x','disabled')")
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('legacy_del','x','deleted')")
    conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('legacy_user','x','user')")
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_module, "DB_PATH", str(legacy))
    up = tmp_path / "legacy_uploads"
    up.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(up))

    db_module.init_db()
    db_module.init_db()  # 再跑一次验证幂等（不应二次改写）

    with db_module.get_db_connection() as c:
        rows = {
            r["username"]: (r["role"], r["status"])
            for r in c.execute("SELECT username, role, status FROM users").fetchall()
        }
    assert rows["legacy_admin"] == ("user", "disabled"), rows["legacy_admin"]
    assert rows["legacy_del"] == ("user", "deleted"), rows["legacy_del"]
    assert rows["legacy_user"] == ("user", "active"), rows["legacy_user"]
