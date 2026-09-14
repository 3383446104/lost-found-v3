"""对抗性验证 D：C2 账户状态拆分——``toggle_status`` 必须保留 ``role``。

背景：C2 之前 ``toggle_status`` 会把 ``role`` 直接覆写为 ``'disabled'``，导致
「禁用管理员 → 重新启用」后管理员被降级为普通用户（role 丢失）。C2 引入独立
``users.status`` 列后，``toggle_status`` 只翻转 ``status``（active↔disabled），
``role`` 保持不变。

本文件由原「复现老 Bug」的特征化用例改写为「回归守护」：断言语义已反转。
"""
from app import database as db_module


def _role_status(user_id):
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT role, status FROM users WHERE id=?", (user_id,)
        ).fetchone()
    return row["role"], row["status"]


def test_toggle_status_preserves_admin_role(client, make_admin):
    """C2 回归守护：禁用→启用管理员，``role`` 始终为 ``admin``，仅 ``status`` 翻转。"""
    target = make_admin(username="tgt_admin")
    actor = make_admin(username="actor_admin")

    # 前置：目标管理员禁用前可访问管理端
    assert client.get("/api/admin/reviews", headers=target["headers"]).status_code == 200

    # 1) 禁用目标管理员
    r1 = client.put(
        f"/api/admin/users/{target['id']}",
        json={"action": "toggle_status"},
        headers=actor["headers"],
    )
    assert r1.status_code == 200
    role_after_disable, status_after_disable = _role_status(target["id"])
    # C2：status 被翻转为 disabled，但 role 必须保留 admin（不再是老 Bug 的 'user'）
    assert status_after_disable == "disabled", f"期望 status='disabled'，实得 {status_after_disable}"
    assert role_after_disable == "admin", (
        f"C2 回归：禁用管理员后 role 被改动（实得 {role_after_disable}），应保留 'admin'"
    )
    # 被禁用后旧 token 无法再访问管理端（R1 修复生效）
    assert client.get("/api/admin/reviews", headers=target["headers"]).status_code == 403

    # 2) 重新启用
    r2 = client.put(
        f"/api/admin/users/{target['id']}",
        json={"action": "toggle_status"},
        headers=actor["headers"],
    )
    assert r2.status_code == 200
    role_restored, status_restored = _role_status(target["id"])
    assert status_restored == "active", f"期望 status='active'，实得 {status_restored}"
    # 【C2 核心修复】恢复后角色仍为 admin，管理员权限未丢失
    assert role_restored == "admin", (
        f"C2 回归：重启后 role 被降级（实得 {role_restored}），应保留 'admin'"
    )
    # 旧 token 恢复可用，且仍具管理员权限
    assert client.get("/api/me", headers=target["headers"]).status_code == 200
    assert client.get("/api/admin/reviews", headers=target["headers"]).status_code == 200
