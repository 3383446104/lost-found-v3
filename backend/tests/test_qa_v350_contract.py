"""QA 独立回归（v3.5.0）——``POST /api/items/match`` 契约、鉴权、路由顺序。

关键差异（相对工程师用例）：对 ``match_source`` 的三种分支逐一用**真实可区分的入参**
驱动，并显式验证 legend **随 config 派生**、``matches`` 上限 = 20、公开接口路由顺序
未被参数化路由吞掉。

v3.5.0-R-T1 后续（本文件自修，测试基建升级后的连带修复）
--------------------------------------------------------
``conftest.py`` 的 ``stub_clip`` 已从「图/文特征都返回同一个常量向量（任意两向量余弦
恒为 1.0）」升级为「**由入参派生**的、近似正交的确定性向量，且图/文命名空间隔离」。
升级让下述用例原先把「命中」当默认结果、只断言 ``match_source`` 的写法**暴露为假绿**
（跨模态通道完全失效时，旧桩照样让它们全绿）。

现在每条 ``assert matches`` 都必须由**一条真实生效的相似度通道**支撑：

= 用例                                    = 依赖的真实通道
=======================================  ===============================================
``test_C_match_source_text``             文-文（``q_text·t_text``）
``test_C_match_source_image``            图-图（``q_img·t_img``，目标 text_vector 置空）
``test_C_match_source_mixed``            图-图 + 跨模态 t2i（``q_text·t_img``）
``test_C_match_source_follows_...``      文-文（图片缺失回退到文本后）
``test_C_matches_capped_at_20``          文-文 ×21（同文目标全部命中 → 截断 20）
``test_C_text_search_hits_image_only...`` 跨模态 t2i + 负对照（正交图向量不命中）
=======================================  ===============================================

作者：yan-qa（独立验证，不修改任何源码）。
"""
import json
import os

import numpy as np

from app import database as db_module
from app.clip_service import clip_service
from app.config import settings

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


# --------------------------------------------------------------------------- #
# 构造助手
# --------------------------------------------------------------------------- #
def _config_embed_dim() -> int:
    """当前后端声明的联合嵌入维度（**从 config 取，绝不硬编码**）。

    v3.5.0 默认后端 ``cn_clip`` → 1024；回滚 ``open_clip`` → 512。
    与 ``clip_backend.get_backend`` / ``conftest._active_embed_dim`` 同源，
    使本文件的显式构造向量与「桩实际产出的维度」一致（否则触发 ``/match`` 维度预检 → 500）。
    """
    if getattr(settings, "CLIP_BACKEND", "cn_clip") == "cn_clip":
        return int(settings.CLIP_CN_EMBED_DIM)
    return int(settings.CLIP_OPEN_EMBED_DIM)


def _unit_vector(dim: int, seed: int) -> np.ndarray:
    """由 ``seed`` 确定性派生 ``dim`` 维 L2 归一化向量（用于构造库中向量）。"""
    rng = np.random.default_rng(seed)
    vec = rng.standard_normal(dim).astype(np.float32)
    return vec / np.linalg.norm(vec)


def _temp_upload(client, headers):
    resp = client.post(
        "/api/items/temp-upload",
        files={"image": ("temp.png", PNG_1X1, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["path"]


def _create_found(client, headers, title, description=""):
    """发布 ``found`` 物品。

    ``description`` 默认置空 —— 因为创建时目标文本向量 = ``f"{title} {description}".strip()``
    （见 ``app/api/items.py`` 创建/编辑处）。若沿用旧硬编码 ``"描述"``，目标文本会变成
    ``"{title} 描述"``，与查询词 ``title`` 不同 → 文-文相似度≈0 → 无论如何都命中不了
    （旧桩靠「全都相似度 1.0」掩盖，新桩下必须让「目标文本 == 查询文本」）。
    """
    resp = client.post(
        "/api/items/",
        data={"type": "found", "title": title, "description": description,
              "category": "其他", "contact": "", "location": "图书馆"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _create_found_with_image(client, headers, title, description=""):
    resp = client.post(
        "/api/items/",
        data={"type": "found", "title": title, "description": description,
              "category": "其他", "contact": "", "location": "图书馆"},
        files={"image": ("pic.png", PNG_1X1, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _get_image_name(item_id: str) -> str:
    """目标物品持久化的图片文件名（basename，供 ``/match`` 的 ``image_path`` 复用）。"""
    with db_module.get_db_connection() as conn:
        row = conn.execute("SELECT image_path FROM items WHERE id=?", (item_id,)).fetchone()
    return os.path.basename(row["image_path"])


def _get_image_vector(item_id: str) -> np.ndarray:
    """目标物品库中已持久化的图向量（与桩的确定性派生一致）。"""
    with db_module.get_db_connection() as conn:
        row = conn.execute("SELECT image_vector FROM items WHERE id=?", (item_id,)).fetchone()
    return np.asarray(json.loads(row["image_vector"]), dtype=np.float32)


def _set_text_vector_null(item_id: str) -> None:
    """置空目标 text_vector —— 锁死为「仅图无文」，消除 i2t 通道。"""
    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE items SET text_vector=NULL WHERE id=?", (item_id,))


def _set_image_vector(item_id: str, vec: np.ndarray) -> None:
    """把库中图向量显式写成 ``vec``（维度须与 config 一致，否则 /match 维度预检报 500）。"""
    with db_module.get_db_connection() as conn:
        conn.execute(
            "UPDATE items SET image_vector=? WHERE id=?",
            (db_module.vector_to_json(vec), item_id),
        )


# --------------------------------------------------------------------------- #
# 鉴权契约（冻结）
# --------------------------------------------------------------------------- #
def test_C_match_without_token_is_403(client):
    resp = client.post("/api/items/match", json={"text": "x", "target_type": "found"})
    assert resp.status_code == 403
    assert resp.json().get("detail") == "Not authenticated"


def test_C_match_with_bad_token_is_401(client):
    resp = client.post(
        "/api/items/match",
        json={"text": "x", "target_type": "found"},
        headers={"Authorization": "Bearer not-a-jwt"},
    )
    assert resp.status_code == 401
    assert "无效或过期" in resp.json().get("detail", "")


# --------------------------------------------------------------------------- #
# legend 派生
# --------------------------------------------------------------------------- #
def test_C_legend_derived_from_thresholds_via_http(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "MATCH_LEGEND_HIGH", None)
    monkeypatch.setattr(settings, "MATCH_LEGEND_MID", None)
    monkeypatch.setattr(settings, "MATCH_THRESHOLD_AUTO", 0.77)
    monkeypatch.setattr(settings, "MATCH_THRESHOLD_MANUAL", 0.42)
    user = make_user(username="qa_legend_http")
    resp = client.post(
        "/api/items/match", json={"text": "x", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["legend"] == {"high": 0.77, "mid": 0.42}


def test_C_legend_override_via_http(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "MATCH_LEGEND_HIGH", 0.95)
    monkeypatch.setattr(settings, "MATCH_LEGEND_MID", 0.55)
    user = make_user(username="qa_legend_ovr")
    resp = client.post(
        "/api/items/match", json={"text": "x", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["legend"] == {"high": 0.95, "mid": 0.55}


def test_C_legend_present_even_without_matches(client, make_user):
    """空结果也必须带 legend（前端据此渲染图例）。"""
    user = make_user(username="qa_legend_empty")
    resp = client.post(
        "/api/items/match", json={"text": "x", "target_type": "lost"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["matches"] == []
    assert set(body["legend"].keys()) == {"high", "mid"}


# --------------------------------------------------------------------------- #
# match_source 三分支（每条断言由一条真实相似度通道支撑）
# --------------------------------------------------------------------------- #
def test_C_match_source_text(client, make_user, approve_item):
    """纯文搜 ``match_source='text'``：命中来自**文-文**通道。

    目标无图（``img2=None``）、查询无图（``img1=None``）→ 图-图 / 两个跨模态方向全不可用；
    唯一可用通道是 ``q_text·t_text``。令目标文本 == 查询文本 → ``sim_text_text=1.0``。
    文-文通道一旦失效，相似度掉到 ≈0 → 无命中 → 本断言变红。
    """
    user = make_user(username="qa_src_text")
    item_id = _create_found(client, user["headers"], "黑色钱包")
    approve_item(item_id)
    resp = client.post(
        "/api/items/match", json={"text": "黑色钱包", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "与查询同文的纯文目标应命中（文-文通道）"
    assert all(m["match_source"] == "text" for m in matches)


def test_C_match_source_image(client, make_user, approve_item):
    """纯图搜 ``match_source='image'``：命中来自**图-图**通道。

    目标置为「仅图无文」（``text_vector=NULL`` → 两个跨模态方向均不可用）；
    并**以目标自身的图片**发起查询 → ``sim_img_img=1.0``。图-图通道一旦失效 → 无命中。
    """
    user = make_user(username="qa_src_image")
    item_id = _create_found_with_image(client, user["headers"], "QA图搜目标")
    approve_item(item_id)
    _set_text_vector_null(item_id)
    image_name = _get_image_name(item_id)
    resp = client.post(
        "/api/items/match", json={"image_path": image_name, "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "以目标自身图片查询应命中（图-图通道）"
    assert all(m["match_source"] == "image" for m in matches)


def test_C_match_source_mixed(client, make_user, approve_item, monkeypatch):
    """图文混合 ``match_source='mixed'``：命中来自**图-图 + 跨模态 t2i** 两条真实通道。

    目标「仅图无文」；查询用目标自身图片（``sim_img_img=1.0``），并令本次查询文本的嵌入
    等于目标图向量（``sim_cross_t2i=1.0``）。两通道一致（``cc=1.0 ≥ CC_HIGH``）→ 不触发
    跨模态一致性惩罚 → 命中。若任一通道失效，命中即消失。
    """
    user = make_user(username="qa_src_mixed")
    item_id = _create_found_with_image(client, user["headers"], "QA混合目标")
    approve_item(item_id)
    _set_text_vector_null(item_id)
    image_name = _get_image_name(item_id)
    img_vec = _get_image_vector(item_id)
    # 让「本次查询文本」的嵌入 == 目标图向量（模拟「文字正好描述了这张图」）。
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: img_vec)
    resp = client.post(
        "/api/items/match",
        json={"image_path": image_name, "text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "图文混合应命中（图-图 + t2i）"
    assert all(m["match_source"] == "mixed" for m in matches)


def test_C_match_source_follows_actually_used_input(client, make_user, approve_item):
    """``image_path`` 指向不存在文件但提供了 ``text`` → 实际走文本 → ``match_source=='text'``。

    同时证明「回退后确实走文本通道」：目标文本 == 查询文本 → ``sim_text_text=1.0`` 命中。
    若回退逻辑把不存在的图片当有效输入（或未回退），本用例将因无命中而变红。
    """
    user = make_user(username="qa_src_fallback")
    item_id = _create_found(client, user["headers"], "黑色钱包")
    approve_item(item_id)
    resp = client.post(
        "/api/items/match",
        json={"image_path": "temp_missing_qa.png", "text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "回退到文本通道后应与同文目标命中"
    assert all(m["match_source"] == "text" for m in matches)


def test_C_image_only_missing_file_is_404(client, make_user):
    """仅给不存在的 image_path（无 text）→ 404，不误判为 text。"""
    user = make_user(username="qa_imgmissing")
    resp = client.post(
        "/api/items/match", json={"image_path": "temp_missing_qa.png", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- #
# matches[:20] 上限
# --------------------------------------------------------------------------- #
def test_C_matches_capped_at_20(client, make_user, approve_item):
    """21 个与查询**同文**的目标全部真实命中（``sim_text_text=1.0``）→ 结果截断为 20。

    旧桩下「21 个目标相似度都是 1.0」也成立，但那是「向量全都相同」的假象；新桩下必须让
    每个目标文本恰等于查询文本才会命中。文-文通道失效 → 命中数 0 → ``len`` 断言变红。
    """
    user = make_user(username="qa_cap")
    query = "上限命中目标"
    for _ in range(21):
        approve_item(_create_found(client, user["headers"], query))
    resp = client.post(
        "/api/items/match", json={"text": query, "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 20, f"应截断为 20，实得 {len(matches)}"
    # 截断前必须已按相似度降序
    sims = [m["similarity"] for m in matches]
    assert sims == sorted(sims, reverse=True)


# --------------------------------------------------------------------------- #
# 路由顺序（隐性契约）
# --------------------------------------------------------------------------- #
def test_F_route_order_static_paths_not_swallowed(client, make_user, approve_item, create_item):
    # 1) /categories 必须命中静态路由
    r = client.get("/api/items/categories")
    assert r.status_code == 200
    assert "categories" in r.json()

    # 2) /uploads/{filename:path} 必须命中文件路由（而非 422/其它）
    r = client.get("/api/items/uploads/does_not_exist_qa.png")
    assert r.status_code == 404
    assert r.json().get("detail") == "图片不存在"

    # 3) /{item_id} 详情命中
    user = make_user(username="qa_route")
    item_id = create_item(user["headers"])
    approve_item(item_id)
    r = client.get(f"/api/items/{item_id}")
    assert r.status_code == 200
    assert r.json()["item"]["id"] == item_id

    # 4) /{item_id}/mark-claimed 必须自成一路由
    r = client.put(f"/api/items/{item_id}/mark-claimed", headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["new_status"] == "claimed"


# --------------------------------------------------------------------------- #
# 遗留缺陷回归：公开接口身份（disabled 不得以属主身份越权）
# --------------------------------------------------------------------------- #
def _insert_pending(user_id):
    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items (type,title,description,category,location,status,user_id,review_status) "
            "VALUES ('lost','QA私有物品','','其他','','pending',?, 'pending')",
            (user_id,),
        )
        return cur.lastrowid


def test_F_disabled_user_cannot_see_pending_item_as_owner(client, make_user):
    owner = make_user(username="qa_own_pending")
    item_id = _insert_pending(owner["id"])

    # 属主本人可见
    assert client.get(f"/api/items/{item_id}", headers=owner["headers"]).status_code == 200

    # 禁用用户（合法 token 但 status=disabled）→ 降级匿名 → 看不到未审核物品
    disabled = make_user(username="qa_disabled_view", status="disabled")
    r = client.get(f"/api/items/{item_id}", headers=disabled["headers"])
    assert r.status_code == 404, f"disabled 用户不应以属主身份看到未审核物品，实得 {r.status_code}"

    # 匿名同样看不到
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_F_disabled_user_list_excludes_own_pending(client, make_user):
    """GET /api/items/ 用 disabled token 也不得因为 user_id 过滤而泄露未审核数据。"""
    disabled = make_user(username="qa_disabled_list", status="disabled")
    item_id = _insert_pending(disabled["id"])
    r = client.get("/api/items/", params={"user_id": disabled["id"]}, headers=disabled["headers"])
    assert r.status_code == 200
    assert all(it["id"] != item_id for it in r.json()["items"])


# --------------------------------------------------------------------------- #
# 跨模态核心路径（用可区分桩，避免「所有向量相同」造成的假绿）
# --------------------------------------------------------------------------- #
def test_C_text_search_hits_image_only_target_with_distinct_vectors(
    client, make_user, approve_item, monkeypatch
):
    """目标**仅有图片**（``text_vector=NULL``）时，纯文搜应通过 ``q_text·t_img`` 命中。

    - 库中图向量与「查询文本向量」**显式对应**（都写入/返回同一个 config 维度向量）
      → ``sim_cross_t2i=1.0``；维度**从 config 取**（勿硬编码，v3.5.0 默认 1024 而非 512），
      避免命中 ``/match`` 的维度预检 → 500。
    - **负对照**：另一「仅图」目标的图向量与查询文本近似正交 → 相似度 ≈0 → **不应命中**。
      命中集「恰含目标、恰不含诱饵」证明跨模态通道真实且具区分度——若该通道失效，
      目标命中消失 → 本断言变红。
    """
    user = make_user(username="qa_imgonly_strict")
    dim = _config_embed_dim()

    item_id = _create_found_with_image(client, user["headers"], "仅图目标QA")
    approve_item(item_id)
    _set_text_vector_null(item_id)
    target_vec = _unit_vector(dim, seed=20260912)
    _set_image_vector(item_id, target_vec)

    decoy_id = _create_found_with_image(client, user["headers"], "仅图诱饵QA")
    approve_item(decoy_id)
    _set_text_vector_null(decoy_id)
    _set_image_vector(decoy_id, _unit_vector(dim, seed=777))

    # 让查询文本向量 == 目标图向量（等价「这段文字正好描述这张图」）。
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: target_vec)

    resp = client.post(
        "/api/items/match", json={"text": "任意文本", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200, resp.text
    ids = {m["id"] for m in resp.json()["matches"]}
    assert item_id in ids, "目标无 text_vector 时应通过跨模态 q_text·t_img 命中"
    assert decoy_id not in ids, "与查询文本正交的仅图目标不应命中（跨模态通道须具区分度）"
