"""pytest 全局夹具（conftest）。

本项目为「从零补充自动化测试」，此文件解决架构评审 §7.2 列出的四处可测性障碍：

1. DB 路径是模块级全局量（``app.database.DB_PATH``），import 时绑定；
   因此必须 monkeypatch ``app.database.DB_PATH`` 指向每个测试独立的临时文件，
   再调用 ``init_db()`` 建表。改 ``settings.DATABASE`` 不会生效。
2. ``clip_service`` 是单例 + 懒加载，首次调用会下载/加载 ~600MB 的 ViT-B-32 模型；
   这里用 autouse 夹具把特征提取方法全部替换为确定性假向量，保证测试永不加载模型。
3. ``settings.SECRET_KEY`` 无默认值，须在 import 应用之前用环境变量兜底。
4. 上传目录重定向到临时目录，避免污染真实的 ``backend/uploads/``。

所有夹具均不修改 ``app/`` 下的产品代码。
"""
import hashlib
import os
import sys

import numpy as np
import pytest

# ---- 关键：必须在 import 应用（app.*）之前设置 SECRET_KEY（config.py:11 无默认值）----
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")

# 确保 backend 目录（app 包所在目录）在 sys.path 上
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import database as db_module  # noqa: E402
from app.config import settings  # noqa: E402
from app.clip_service import clip_service  # noqa: E402


DEFAULT_PASSWORD = "pass1234"


# --------------------------------------------------------------------------- #
# 确定性、可区分的假向量（v3.5.0 修正）
# --------------------------------------------------------------------------- #
# 背景：旧桩让「图像/文本特征」都返回同一个 ``np.ones(512)/norm`` 常量向量，
# 于是任意两向量的余弦相似度恒为 1.0 —— 所有依赖 ``POST /api/items/match`` 命中的
# 契约测试（match_source 三分支、纯文搜命中「仅图无文」目标……）在**跨模态通道完全
# 未生效**时也会通过，等于没有信号（假绿）。下面改为「由入参派生」的桩：
#   - 同一入参 → 恒同一向量（确定性，测试可重复）；
#   - 不同入参 → 近似正交（余弦 ≈ 0），跨模态通道一旦失效命中数会真实掉到 0；
#   - 图像/文本使用**不同命名空间前缀**，故「同一字符串经图桩与文桩得到的向量不等」，
#     从而能真实区分 sim_img_img / sim_text_text / sim_cross_t2i / sim_cross_i2t 四通道。
#   - 维度**从 config 读取**（cn_clip→CLIP_CN_EMBED_DIM，其余→CLIP_OPEN_EMBED_DIM），
#     不硬编码 512 —— v3.5.0 默认后端为 cn_clip（1024 维）。
# --------------------------------------------------------------------------- #
_IMAGE_NAMESPACE = b"image:"
_TEXT_NAMESPACE = b"text:"


def _active_embed_dim() -> int:
    """当前后端声明的联合嵌入维度（config 驱动，与 ``clip_backend.get_backend`` 同源）。

    - ``settings.CLIP_BACKEND == "cn_clip"`` → ``settings.CLIP_CN_EMBED_DIM``（v3.5.0 默认 1024）；
    - 否则（如 ``open_clip`` 回滚路径）→ ``settings.CLIP_OPEN_EMBED_DIM``（512）。

    每次调用时读取，保证用例内 monkeypatch ``settings.*`` 的维度也能被立即反映。
    """
    if getattr(settings, "CLIP_BACKEND", "cn_clip") == "cn_clip":
        return int(settings.CLIP_CN_EMBED_DIM)
    return int(settings.CLIP_OPEN_EMBED_DIM)


def _derive_vector(seed: bytes, dim: int) -> np.ndarray:
    """由 ``seed`` 确定性派生 ``dim`` 维 L2 归一化向量。

    ``hashlib.sha256(seed)`` 摘要 → 取前 8 字节作 ``np.random.default_rng`` 种子 →
    标准正态采样 → L2 归一化。**同一 seed 恒返回逐元素相同**的向量；不同 seed 近似正交。
    """
    digest = hashlib.sha256(seed).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "little"))
    vec = rng.standard_normal(dim).astype(np.float32)
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:  # pragma: no cover - 极端兜底，实际不会发生
        return np.ones(dim, dtype=np.float32) / float(np.sqrt(dim))
    return vec / norm


def _fake_image_feature(image_path):
    """由 ``image_path`` 派生的确定性图向量（图像命名空间）。"""
    return _derive_vector(_IMAGE_NAMESPACE + str(image_path).encode("utf-8"), _active_embed_dim())


def _fake_text_feature(text):
    """由 ``text`` 派生的确定性文向量（文本命名空间，与图命名空间隔离）。"""
    return _derive_vector(_TEXT_NAMESPACE + str(text).encode("utf-8"), _active_embed_dim())


# --------------------------------------------------------------------------- #
# 隔离夹具
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def stub_clip(monkeypatch):
    """把 CLIP 特征提取替换为确定性、可区分的桩（图像/文本 config 维度）。

    图像/文本桩**由入参派生**（见 :func:`_derive_vector`），故：
    - 同一入参恒同向量 → 测试可重复；
    - 不同入参近似正交 → 不再有「相似度恒为 1.0」的假绿；
    - 图/文命名空间隔离 → 四个相似度通道（ii / tt / t2i / i2t）真实可区分。
    """

    # 双保险：既 patch 实例方法，也阻断懒加载入口。
    # 方法名（_initialize / get_image_feature / get_text_feature）
    # 是**冻结契约**（app/clip_service.py 靠这些名字被桩掉），不得更名。
    monkeypatch.setattr(clip_service, "_initialize", lambda *a, **k: None)
    monkeypatch.setattr(clip_service, "get_image_feature", _fake_image_feature)
    monkeypatch.setattr(clip_service, "get_text_feature", _fake_text_feature)


@pytest.fixture(autouse=True)
def stub_email(monkeypatch):
    """阻断真实 SMTP 发送，避免测试触碰网络。

    match_service 在模块级 import 了 send_match_notification（持自有引用），
    只桩 email_utils 对 match_service 无效，必须直接桩 match_service 的引用。
    """
    import app.utils.email_utils as email_utils
    import app.services.match_service as match_service

    monkeypatch.setattr(email_utils, "send_email", lambda *a, **k: True)
    monkeypatch.setattr(match_service, "send_match_notification", lambda *a, **k: True)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """每个测试使用独立的临时 SQLite 文件与上传目录。"""
    db_file = tmp_path / "test_lost_found.db"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(db_module, "DB_PATH", str(db_file))
    monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(upload_dir))

    db_module.init_db()
    yield db_file


# --------------------------------------------------------------------------- #
# 客户端
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(isolated_db):
    """FastAPI 测试客户端。

    刻意不作为上下文管理器使用：避免触发 lifespan（否则会用真实 DB_PATH 再初始化一次）。
    DB 初始化已由 ``isolated_db`` 完成。
    """
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


# --------------------------------------------------------------------------- #
# 数据工厂
# --------------------------------------------------------------------------- #
@pytest.fixture
def make_user(client):
    """注册用户工厂，role/status 通过直接改库设置（等价于管理员操作），返回含 token 的字典。

    - ``role``   ∈ ``{'user', 'admin'}``               —— 授权角色
    - ``status`` ∈ ``{'active', 'disabled', 'deleted'}`` —— 账号状态（C2 拆分后的独立列）

    兼容历史写法：早期用例用 ``role='disabled'`` / ``role='deleted'`` 表达账号状态，
    此处自动映射为 ``status=<role>`` 且 ``role='user'``（与 §2.3 迁移语义一致），
    使旧调用不会静默失效。
    """
    state = {"n": 0}

    def _make(username=None, password=DEFAULT_PASSWORD, phone=None, role=None,
              status=None, email=None):
        state["n"] += 1
        n = state["n"]
        username = username or f"user{n}"
        phone = phone or f"138{n:08d}"

        payload = {"username": username, "password": password, "phone": phone}
        if email:
            payload["email"] = email

        resp = client.post("/api/register", json=payload)
        assert resp.status_code == 201, f"注册失败: {resp.status_code} {resp.text}"
        data = resp.json()

        user_id = data["user"]["id"]
        token = data["token"]

        # 兼容：role 里塞状态值（'disabled'/'deleted'）→ 迁到 status 列，role 复位为 'user'
        if role in ("disabled", "deleted"):
            status = status or role
            role = "user"

        sets, params = [], []
        if role is not None:
            sets.append("role=?")
            params.append(role)
        if status is not None:
            sets.append("status=?")
            params.append(status)
        if sets:
            params.append(user_id)
            with db_module.get_db_connection() as conn:
                conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", params)

        return {
            "id": user_id,
            "username": username,
            "password": password,
            "phone": phone,
            "role": role or "user",
            "status": status or "active",
            "token": token,
            "headers": {"Authorization": f"Bearer {token}"},
        }

    return _make


@pytest.fixture
def make_admin(make_user):
    """管理员工厂。"""

    def _make(username=None, **kwargs):
        return make_user(username=username, role="admin", **kwargs)

    return _make


@pytest.fixture
def create_item(client):
    """通过 HTTP 发布物品（不带图片，避免触发真实 CLIP），返回物品 id。"""

    def _create(headers, type="lost", title="丢失的钱包", description="黑色钱包",
                category="其他", contact="", location="图书馆"):
        resp = client.post(
            "/api/items/",
            data={
                "type": type,
                "title": title,
                "description": description,
                "category": category,
                "contact": contact,
                "location": location,
            },
            headers=headers,
        )
        assert resp.status_code == 201, f"发布失败: {resp.status_code} {resp.text}"
        return resp.json()["id"]

    return _create


@pytest.fixture
def approve_item():
    """直接把物品置为已审核+活跃（等价于管理员审核通过，供数据构造使用）。"""

    def _approve(item_id, status="active", review_status="approved"):
        with db_module.get_db_connection() as conn:
            conn.execute(
                "UPDATE items SET review_status=?, status=? WHERE id=?",
                (review_status, status, item_id),
            )
        return item_id

    return _approve


@pytest.fixture
def create_item_row():
    """绕过 HTTP 直接用 SQL 造物品（用于构造特定 created_at / 审核状态等场景）。"""

    def _create(user_id, type="lost", title="测试物品", description="",
                category="其他", location="", status="pending",
                review_status="pending", created_at=None, image_path=None):
        with db_module.get_db_connection() as conn:
            cur = conn.cursor()
            if created_at is None:
                cur.execute(
                    "INSERT INTO items (type, title, description, category, location, "
                    "status, user_id, review_status, image_path) VALUES (?,?,?,?,?,?,?,?,?)",
                    (type, title, description, category, location, status, user_id,
                     review_status, image_path),
                )
            else:
                cur.execute(
                    "INSERT INTO items (type, title, description, category, location, "
                    "status, user_id, review_status, image_path, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (type, title, description, category, location, status, user_id,
                     review_status, image_path, created_at, created_at),
                )
            return cur.lastrowid

    return _create
