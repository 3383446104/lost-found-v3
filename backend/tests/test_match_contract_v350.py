"""``POST /api/items/match`` 契约回归（T05，v3.5.0）——不加载真实模型。

覆盖设计 §5.3：
- 结果项含 ``match_source ∈ {text,image,mixed}``（三分支）；
- 响应顶层含 ``legend{high,mid}``，且由阈值派生；
- 纯文搜（目标仅有图片、无 text_vector）仍返回非空 matches；
- **403/401 鉴权契约不变**。

v3.5.0-R-T1：本文件原先依赖 conftest 的「相似度恒为 1.0」假向量才能命中（假绿）。
现按真实语义重表达——用**真实可区分的桩向量**构造命中，使每个用例的 ``assert matches``
都对应一条真实生效的相似度通道（文-文 / 图-图 / 跨模态），而非「什么都恒为 1」。
"""
import json
import os

import numpy as np

from app import database as db_module
from app.clip_service import clip_service

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _create_item_with_image(client, headers, type="found", title="带图物品",
                            description="有图描述"):
    resp = client.post(
        "/api/items/",
        data={"type": type, "title": title, "description": description,
              "category": "其他", "contact": "", "location": "图书馆"},
        files={"image": ("pic.png", PNG_1X1, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 201, f"带图发布失败: {resp.status_code} {resp.text}"
    return resp.json()["id"]


def _get_image_name(item_id):
    """目标物品持久化的图片文件名（basename，供 /match 的 image_path 复用）。"""
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT image_path FROM items WHERE id=?", (item_id,)
        ).fetchone()
    return os.path.basename(row["image_path"])


def _get_image_vector(item_id):
    """目标物品库中已持久化的图向量（``list[float]``，与桩的确定性一致）。"""
    with db_module.get_db_connection() as conn:
        row = conn.execute(
            "SELECT image_vector FROM items WHERE id=?", (item_id,)
        ).fetchone()
    return json.loads(row["image_vector"])


def _set_text_vector_null(item_id):
    with db_module.get_db_connection() as conn:
        conn.execute("UPDATE items SET text_vector=NULL WHERE id=?", (item_id,))


# --------------------------------------------------------------------------- #
# 鉴权契约（冻结）
# --------------------------------------------------------------------------- #
def test_v350_match_without_token_403_not_authenticated(client):
    resp = client.post("/api/items/match", json={"text": "黑色钱包", "target_type": "found"})
    assert resp.status_code == 403, f"期望 403，实得 {resp.status_code}"
    assert resp.json().get("detail") == "Not authenticated"


def test_v350_match_with_invalid_token_401(client):
    resp = client.post(
        "/api/items/match",
        json={"text": "黑色钱包", "target_type": "found"},
        headers={"Authorization": "Bearer garbage"},
    )
    assert resp.status_code == 401, f"期望 401，实得 {resp.status_code}"
    assert "无效或过期" in resp.json().get("detail", "")


# --------------------------------------------------------------------------- #
# legend
# --------------------------------------------------------------------------- #
def test_v350_response_contains_legend(client, make_user):
    user = make_user(username="v350_legend")
    resp = client.post(
        "/api/items/match",
        json={"text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "legend" in body
    legend = body["legend"]
    assert isinstance(legend["high"], (int, float))
    assert isinstance(legend["mid"], (int, float))
    assert legend["high"] >= legend["mid"], "高置信阈值不应低于中等阈值"


# --------------------------------------------------------------------------- #
# match_source 三分支
# --------------------------------------------------------------------------- #
def test_v350_match_source_text(client, make_user, approve_item, create_item):
    """纯文搜 → ``match_source='text'``，命中来自真实的**文-文**通道。

    目标物品不含图片、其文本与查询文本一致（``title`` 即查询词）→ ``sim_text_text=1.0``；
    由于目标无图（无跨模态通道）且查询无图（无 img_img 通道），命中只可能由文-文通道产生。
    """
    user = make_user(username="v350_src_text")
    item_id = create_item(user["headers"], type="found", title="黑色钱包", description="")
    approve_item(item_id)  # /match 只检索 status=active 且 review_status=approved 的目标
    resp = client.post(
        "/api/items/match",
        json={"text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "与查询同文的纯文目标应命中"
    assert all(m["match_source"] == "text" for m in matches)


def test_v350_match_source_image(client, make_user, approve_item):
    """纯图搜 → ``match_source='image'``，命中来自真实的**图-图**通道。

    目标置为「仅图无文」，并以**目标自身的图片**作为查询 → ``sim_img_img=1.0``，
    命中只可能由图-图通道产生（无文本 → 无跨模态通道可用）。
    """
    user = make_user(username="v350_src_image")
    item_id = _create_item_with_image(client, user["headers"], type="found", title="图搜目标")
    approve_item(item_id)
    _set_text_vector_null(item_id)  # 锁死为图-图通道
    image_name = _get_image_name(item_id)
    resp = client.post(
        "/api/items/match",
        json={"image_path": image_name, "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "以目标自身图片查询应命中"
    assert all(m["match_source"] == "image" for m in matches)


def test_v350_match_source_mixed(client, make_user, approve_item, monkeypatch):
    """图文混合 → ``match_source='mixed'``，命中来自 **img_img + 跨模态 t2i** 两真实通道。

    目标置为「仅图无文」；查询用目标自身图片（``sim_img_img=1.0``），并令查询文本的
    嵌入等于目标图向量（``sim_cross_t2i=1.0``）。两通道一致（cc=1.0 ≥ CC_HIGH）→ 不触发
    跨模态一致性惩罚 → 命中。
    """
    user = make_user(username="v350_src_mixed")
    item_id = _create_item_with_image(client, user["headers"], type="found", title="混合目标")
    approve_item(item_id)
    _set_text_vector_null(item_id)
    image_name = _get_image_name(item_id)
    img_vec = np.asarray(_get_image_vector(item_id), dtype=np.float32)
    # 让「本次查询文本」的嵌入 == 目标图向量（模拟「文字正好描述了这张图」）：
    # 由于目标无 text_vector，跨模态方向只有 t2i 可用；两通道全对齐才不触发惩罚。
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: img_vec)

    resp = client.post(
        "/api/items/match",
        json={"image_path": image_name, "text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert any(m["id"] == item_id for m in matches), "图文混合应命中"
    assert all(m["match_source"] == "mixed" for m in matches)


# --------------------------------------------------------------------------- #
# 跨模态命中：目标仅有图片、无 text_vector
# --------------------------------------------------------------------------- #
def test_v350_text_search_hits_image_only_target(client, make_user, approve_item, monkeypatch):
    """核心修复：纯文搜仍能命中「仅有图片、无 text_vector」的目标。

    目标无 text_vector → 唯一可用通道是**跨模态 t2i**（``q_text · t_img``）。令查询文本
    的嵌入等于目标图向量（模拟「文字正好描述了这张图」）→ ``t2i=1.0``；若跨模态通道缺失，
    则查询与目标无任何可用通道 → 相似度 0 → 空集。故命中即证明跨模态通道真实生效。
    """
    user = make_user(username="v350_imgonly")
    item_id = _create_item_with_image(client, user["headers"], type="found", title="仅图目标")
    approve_item(item_id)           # 先审核（使 /match 可见），再置空 text_vector
    _set_text_vector_null(item_id)
    img_vec = np.asarray(_get_image_vector(item_id), dtype=np.float32)
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: img_vec)

    resp = client.post(
        "/api/items/match",
        json={"text": "黑色钱包", "target_type": "found"},
        headers=user["headers"],
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert matches, "目标无 text_vector 时仍应通过跨模态通道命中"
    assert any(m["id"] == item_id for m in matches)


def test_v350_missing_image_and_text_returns_zero_no_crash(client, make_user):
    """缺图缺文：compute_weighted_similarity 返回 0.0，不抛异常。"""
    from app.clip_service import clip_service
    assert clip_service.compute_weighted_similarity(None, None, None, None) == 0.0
