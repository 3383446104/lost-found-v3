"""QA 独立回归（v3.5.0）——R2「向量维度预检」行为验证。

目标：独立证明预检在**逐条打分之前**把「库中向量维度 ≠ 当前模型维度」变成**响亮错误**
（HTTP 500），而不是被逐条 ``except → continue`` 吞成「未找到」。逐个核验边界：
维度一致放行、库中维度混杂拦截、``query_dim=None`` 跳过、全目标异常 vs 真无命中的区分、
自动匹配路径不掉队。

作者：yan-qa（本文件归 yan-qa 维护）。
"""
import json
import logging

import numpy as np
import pytest
from fastapi import HTTPException

from app import database as db_module
from app.clip_service import clip_service
from app.config import settings
from app.services.match_service import auto_match_and_notify
from app.api.items import _assert_vector_dims_match


def _j(dim):
    return json.dumps([0.01] * dim) if dim else None


def _insert_item(user_id, type_="found", iv_dim=None, tv_dim=None,
                 status="active", review_status="approved"):
    with db_module.get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO items (type,title,description,category,location,status,user_id,"
            "review_status,image_path,image_vector,text_vector) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (type_, "QA预检", "d", "其他", "图书馆", status, user_id, review_status,
             None, _j(iv_dim), _j(tv_dim)),
        )
        return cur.lastrowid


def _count(table):
    with db_module.get_db_connection() as conn:
        return conn.cursor().execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]


def _errors(caplog):
    return "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


def _unit(v):
    return np.ones(v, np.float32) / np.sqrt(v)

def _detail(content_score, reference_score=None, level="high_suspect", basis=None):
    """构造 ``compute_match_detail`` 的返回契约（2026-09-21 新增接口）。

    自动匹配与 /match 现在统一调用它，mock 必须对齐新接口名与结构，
    否则 mock 静默失效（本文件原先 4 处即因此失效）。
    """
    return {
        "score": content_score,
        "content_score": content_score,
        "reference_score": reference_score if reference_score is not None else content_score,
        "level": level,
        "basis": basis or ["text_match"],
        "channels": {
            "sim_img_img": None, "sim_text_text": None, "sim_t2i": None,
            "sim_i2t": None, "sim_cross": None, "sim_cross_mapped": None,
        },
    }



# --------------------------------------------------------------------------- #
# 1) 核心：预检在逐条打分之前拦截（HTTP 500），不进入打分循环
# --------------------------------------------------------------------------- #
def test_precheck_blocks_before_scoring_with_500(client, make_user, monkeypatch):
    user = make_user(username="qa_precheck_block")
    _insert_item(user["id"], tv_dim=512)  # 库中 512 维

    calls = {"n": 0}

    def _sentinel(*a, **k):
        calls["n"] += 1
        return _detail(1.0)

    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(1024))  # 当前模型 1024 维
    monkeypatch.setattr(clip_service, "compute_match_detail", _sentinel)

    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 500, "维度不匹配应响亮报错（HTTP 500），而非静默空集"
    detail = resp.json()["detail"]
    assert "向量维度不匹配" in detail
    assert "512" in detail and "1024" in detail
    assert "reembed_all_vectors.py" in detail
    assert calls["n"] == 0, "预检必须在逐条打分**之前**触发"


def test_precheck_passes_when_dims_match(client, make_user, monkeypatch):
    user = make_user(username="qa_precheck_pass")
    _insert_item(user["id"], tv_dim=512)

    calls = {"n": 0}

    def _sentinel(*a, **k):
        calls["n"] += 1
        return _detail(1.0)

    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(512))
    monkeypatch.setattr(clip_service, "compute_match_detail", _sentinel)

    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    assert calls["n"] >= 1, "维度一致时应正常进入打分"


def test_precheck_any_mismatch_in_mixed_db_raises(client, make_user, monkeypatch):
    """库中维度混杂（部分已重嵌入 1024 / 部分未 512）→ 任一不符即 500。"""
    user = make_user(username="qa_precheck_mixed")
    _insert_item(user["id"], tv_dim=512)
    _insert_item(user["id"], tv_dim=1024)  # 末条不符 → 仍须被查到

    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(512))
    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 500
    assert "向量维度不匹配" in resp.json()["detail"]


def test_precheck_query_dim_none_skips_silently():
    """query_dim=None（无图无文查询向量）→ 预检直接放行，不抛异常。"""
    _assert_vector_dims_match(None, [{"image_vector": _j(512), "text_vector": None}])


def test_precheck_unit_mismatch_raises_http_500():
    """单元级：任一列（text_vector）维度不符即抛 HTTP 500，且消息带重嵌入指引。"""
    with pytest.raises(HTTPException) as ei:
        _assert_vector_dims_match(1024, [{"image_vector": None, "text_vector": _j(512)}])
    assert ei.value.status_code == 500
    assert "向量维度不匹配" in ei.value.detail


def test_precheck_no_false_500_when_target_vectors_null(client, make_user, monkeypatch):
    """目标向量为 NULL（无图无文物品）不得误报 500——只有真实维度冲突才拦。"""
    user = make_user(username="qa_null_vec")
    _insert_item(user["id"], iv_dim=None, tv_dim=None)
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(1024))
    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200, "NULL 向量不是维度冲突，不应 500"


def test_precheck_no_false_500_when_no_targets(client, make_user, monkeypatch):
    """无目标候选 → 预检无可比较对象 → 200（不得据 config 维度臆造 500）。"""
    user = make_user(username="qa_no_targets")
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(1024))
    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["matches"] == []


# --------------------------------------------------------------------------- #
# 2) 「全部目标异常」必须与「真的没找到」在日志上区分
# --------------------------------------------------------------------------- #
def test_all_targets_throw_logs_error_not_plain_no_hit(client, make_user, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    user = make_user(username="qa_all_throw")
    _insert_item(user["id"], tv_dim=512)

    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(512))

    def _boom(*a, **k):
        raise RuntimeError("synthetic score error")

    monkeypatch.setattr(clip_service, "compute_match_detail", _boom)

    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200 and resp.json()["matches"] == []
    text = _errors(caplog)
    assert "并非「未找到」" in text, "全目标异常必须记 ERROR，与真实无命中区分"
    assert "全部失败" in text


def test_genuine_no_hit_has_no_such_error(client, make_user, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    user = make_user(username="qa_no_hit")
    _insert_item(user["id"], tv_dim=512)
    monkeypatch.setattr(clip_service, "get_text_feature", lambda _t: _unit(512))
    monkeypatch.setattr(clip_service, "compute_match_detail", lambda *a, **k: _detail(0.0))

    resp = client.post(
        "/api/items/match", json={"text": "任意", "target_type": "found"}, headers=user["headers"]
    )
    assert resp.status_code == 200 and resp.json()["matches"] == []
    assert "并非「未找到」" not in _errors(caplog), "真实无命中不应触发该 ERROR"


# --------------------------------------------------------------------------- #
# 3) 自动匹配路径也有同一道预检，且不静默
# --------------------------------------------------------------------------- #
def test_auto_match_dim_mismatch_logs_error_and_stops(client, make_user, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    user = make_user(username="qa_auto_mismatch")
    new_id = _insert_item(user["id"], type_="lost", iv_dim=1024, tv_dim=1024)
    _insert_item(user["id"], type_="found", iv_dim=512, tv_dim=512)
    monkeypatch.setattr(settings, "AUTO_MATCH_ENABLED", True)

    auto_match_and_notify(new_id, "lost")  # 不得抛异常

    text = _errors(caplog)
    assert "向量维度不匹配" in text, "自动匹配维度不符必须记 ERROR（不得静默）"
    assert _count("matches") == 0
    assert _count("notifications") == 0


def test_auto_match_happy_path_inserts_when_dims_match(client, make_user, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    user = make_user(username="qa_auto_ok")
    new_id = _insert_item(user["id"], type_="lost", iv_dim=512, tv_dim=512)
    _insert_item(user["id"], type_="found", iv_dim=512, tv_dim=512)
    monkeypatch.setattr(settings, "AUTO_MATCH_ENABLED", True)
    monkeypatch.setattr(clip_service, "compute_match_detail", lambda *a, **k: _detail(0.90))

    auto_match_and_notify(new_id, "lost")

    assert "向量维度不匹配" not in _errors(caplog)
    assert _count("matches") == 1, "维度一致且高分时应正常落库"
