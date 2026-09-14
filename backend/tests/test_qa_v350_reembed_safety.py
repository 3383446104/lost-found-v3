"""QA 独立回归（v3.5.0）——重嵌入脚本（``scripts/reembed_all_vectors.py``）破坏性操作安全。

全部在**临时目录的自建 sqlite 库**上运行，绝不触碰 ``backend/lost_found.db``。
通过依赖注入 ``FakeEncoder`` 走完整链路，不加载真实模型。

作者：yan-qa（独立验证，不修改任何源码）。
"""
import importlib.util
import json
import os
import sqlite3
import sys

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")


def _load_script(name):
    module_name = f"_qa_script_{name}"
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(SCRIPTS_DIR, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return mod


reembed = _load_script("reembed_all_vectors")


class FakeEncoder:
    name = "fake"
    model_name = "fake-model"

    def encode_image(self, path):
        v = np.full(512, (abs(hash(path)) % 97) + 1, dtype=np.float32)
        return v / np.linalg.norm(v)

    def encode_text(self, text):
        v = np.full(512, (abs(hash(text)) % 97) + 1, dtype=np.float32)
        return v / np.linalg.norm(v)


class BadImageEncoder(FakeEncoder):
    """图片编码总是失败；文本编码正常——用于验证失败隔离。"""

    def encode_image(self, path):
        raise RuntimeError("boom-image")


def _make_db(tmp_path, n=3, with_images=True):
    db_path = str(tmp_path / "qa.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT, description TEXT, "
        "image_path TEXT, image_vector TEXT, text_vector TEXT, color_vector TEXT)"
    )
    ids = []
    for i in range(1, n + 1):
        img_path = None
        if with_images:
            img = tmp_path / f"img{i}.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i]))
            img_path = str(img)
        init = json.dumps([0.1] * 512)
        conn.execute(
            "INSERT INTO items (id,title,description,image_path,image_vector,text_vector,color_vector) "
            "VALUES (?,?,?,?,?,?,?)",
            (i, f"物品{i}", f"描述{i}", img_path, init, init, json.dumps([0.0] * 27)),
        )
        ids.append(i)
    conn.commit()
    conn.close()
    return db_path, ids


def _read(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT id,image_vector,text_vector,color_vector FROM items ORDER BY id"
    ).fetchall()
    conn.close()
    return {r[0]: r[1:] for r in rows}


def _baks(tmp_path):
    return [f for f in os.listdir(tmp_path) if ".bak-" in f]


# --------------------------------------------------------------------------- #
# dry-run
# --------------------------------------------------------------------------- #
def test_E_dry_run_no_db_write_no_state(tmp_path):
    db_path, _ = _make_db(tmp_path)
    before = _read(db_path)
    state = str(tmp_path / ".reembed_state.json")
    stats = reembed.run(db_path, FakeEncoder(), dry_run=True, state_path=state)
    assert _read(db_path) == before, "dry-run 不得写库"
    assert not os.path.exists(state), "dry-run 不得落断点"
    assert stats.processed == 3 and stats.ok == 3


def test_E_dry_run_still_creates_backup_side_effect(tmp_path):
    """R-T5（v3.5.0）：dry-run 是只读预览，**不应**触发任何写盘副作用（含冷备）。

    历史契约：本用例先前锁定「dry-run 也会冷备」作为现状记录；T5 修复后语义
    调整为「dry-run 完全只读」，备份仅由 ``backup_only=True`` 显式触发。
    """
    db_path, _ = _make_db(tmp_path)
    reembed.run(db_path, FakeEncoder(), dry_run=True, state_path=str(tmp_path / "s.json"))
    assert not _baks(tmp_path), "dry-run 不应创建 .bak-*（R-T5：完全只读）"


def test_E_dry_run_does_not_overwrite_existing_state(tmp_path):
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    saved = json.load(open(state, encoding="utf-8"))
    reembed.run(db_path, FakeEncoder(), dry_run=True, resume=True, state_path=state)
    assert json.load(open(state, encoding="utf-8")) == saved, "dry-run 不得修改断点"


# --------------------------------------------------------------------------- #
# backup-only
# --------------------------------------------------------------------------- #
def test_E_backup_only_creates_bak_and_sha(tmp_path):
    db_path, _ = _make_db(tmp_path)
    before = _read(db_path)
    stats = reembed.run(db_path, FakeEncoder(), backup_only=True)
    assert _baks(tmp_path)
    assert os.path.exists(stats.backup_path)
    assert len(stats.backup_sha256) == 64
    assert _read(db_path) == before
    # backup-only 不落断点
    assert not os.path.exists(os.path.join(SCRIPTS_DIR, ".reembed_state.json"))


def test_E_backup_copy_is_valid_sqlite(tmp_path):
    db_path, _ = _make_db(tmp_path)
    stats = reembed.run(db_path, FakeEncoder(), backup_only=True)
    conn = sqlite3.connect(stats.backup_path)
    cnt = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    assert cnt == 3


# --------------------------------------------------------------------------- #
# limit / 幂等 / 续跑 / 指纹
# --------------------------------------------------------------------------- #
def test_E_limit_processes_only_n(tmp_path):
    db_path, _ = _make_db(tmp_path, n=5)
    stats = reembed.run(
        db_path, FakeEncoder(), dry_run=True, limit=2, state_path=str(tmp_path / "s.json")
    )
    assert stats.processed == 2 and stats.total == 2


def test_E_idempotent(tmp_path):
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    first = _read(db_path)
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    second = _read(db_path)
    for iid in first:
        for a, b in zip(first[iid], second[iid]):
            assert np.allclose(np.array(json.loads(a)), np.array(json.loads(b)))


def test_E_resume_skips_processed(tmp_path):
    db_path, ids = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    s2 = reembed.run(db_path, FakeEncoder(), resume=True, state_path=state)
    assert s2.processed == 0 and s2.skipped == len(ids)


def test_E_fingerprint_mismatch_refuses_resume(tmp_path):
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    json.dump(
        {"backend": "open_clip", "model_name": "ViT-B-32", "last_id": 1},
        open(state, "w", encoding="utf-8"),
    )
    try:
        reembed.run(db_path, FakeEncoder(), resume=True, state_path=state)
    except RuntimeError:
        return
    raise AssertionError("跨模型续跑必须被拒绝")


def test_E_no_resume_ignores_mismatched_state(tmp_path):
    """--no-resume 应忽略不匹配断点并从头重跑（不抛异常）。"""
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    json.dump(
        {"backend": "open_clip", "model_name": "ViT-B-32", "last_id": 2},
        open(state, "w", encoding="utf-8"),
    )
    stats = reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    assert stats.processed == 3
    assert json.load(open(state, encoding="utf-8"))["backend"] == "fake"


def test_E_state_records_fingerprint(tmp_path):
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    saved = json.load(open(state, encoding="utf-8"))
    assert saved["backend"] == "fake" and saved["model_name"] == "fake-model"
    assert saved["last_id"] >= 1


# --------------------------------------------------------------------------- #
# 失败隔离
# --------------------------------------------------------------------------- #
def test_E_image_encode_failure_isolated(tmp_path):
    """图片编码失败：计入 failed_encode，文本向量仍更新，脚本不崩。"""
    db_path, _ = _make_db(tmp_path)
    before = _read(db_path)
    state = str(tmp_path / ".reembed_state.json")
    stats = reembed.run(db_path, BadImageEncoder(), resume=False, state_path=state)
    assert stats.failed_encode >= 3
    after = _read(db_path)
    # 文本向量应已变更，图片向量保持旧值
    for iid in before:
        assert after[iid][1] != before[iid][1], "文本向量应被更新"
        assert after[iid][0] == before[iid][0], "图片编码失败时不得污染原图片向量"


def test_E_color_vector_untouched(tmp_path):
    """color_vector 与模型无关，重嵌入不得改写（铁律5）。"""
    db_path, _ = _make_db(tmp_path)
    before = _read(db_path)
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=str(tmp_path / "s.json"))
    after = _read(db_path)
    for iid in before:
        assert after[iid][2] == before[iid][2]
