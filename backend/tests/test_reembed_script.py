"""重嵌入脚本单测（T05）——依赖注入 FakeEncoder，**不加载真实模型**。

覆盖设计 §5.4：
- ``--dry-run`` 不写库、不落断点，且输出 ETA；
- ``--backup-only`` 生成 ``.bak-*``；
- 幂等：连跑两次向量逐元素相等；
- 断点续跑不重复处理；
- 指纹不匹配拒绝续跑。
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
    module_name = f"_script_{name}"
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(SCRIPTS_DIR, f"{name}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    # 必须在 exec 前注册进 sys.modules：脚本内的 @dataclass 会在装饰期调
    # sys.modules.get(cls.__module__).__dict__，未注册时拿到 None 直接
    # AttributeError（collection failure）。
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return mod


reembed = _load_script("reembed_all_vectors")


class FakeEncoder:
    """确定性假编码器：按输入返回 512 维 L2 归一化向量（同输入必同输出）。"""

    name = "fake"
    model_name = "fake-model"

    def encode_image(self, path):
        v = np.full(512, (abs(hash(path)) % 97) + 1, dtype=np.float32)
        return v / np.linalg.norm(v)

    def encode_text(self, text):
        v = np.full(512, (abs(hash(text)) % 97) + 1, dtype=np.float32)
        return v / np.linalg.norm(v)


def _make_db(tmp_path, n=3, with_initial_vectors=True):
    """建一个最小 items 表 + 若干图片文件，返回 (db_path, ids)。"""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, title TEXT, description TEXT, "
        "image_path TEXT, image_vector TEXT, text_vector TEXT)"
    )
    ids = []
    for i in range(1, n + 1):
        img = tmp_path / f"img{i}.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i]))
        init_vec = json.dumps([0.0] * 512) if with_initial_vectors else None
        conn.execute(
            "INSERT INTO items (id, title, description, image_path, image_vector, text_vector) "
            "VALUES (?,?,?,?,?,?)",
            (i, f"物品{i}", f"描述{i}", str(img), init_vec, init_vec),
        )
        ids.append(i)
    conn.commit()
    conn.close()
    return db_path, ids


def _read_vectors(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, image_vector, text_vector FROM items ORDER BY id").fetchall()
    conn.close()
    return {r[0]: (r[1], r[2]) for r in rows}


def _vec_equal(a, b):
    return np.allclose(np.array(json.loads(a)), np.array(json.loads(b)))


# --------------------------------------------------------------------------- #
# dry-run
# --------------------------------------------------------------------------- #
def test_dry_run_does_not_write_db_and_has_eta(tmp_path):
    db_path, _ = _make_db(tmp_path)
    before = _read_vectors(db_path)
    state = str(tmp_path / ".reembed_state.json")

    stats = reembed.run(db_path, FakeEncoder(), dry_run=True, state_path=state)

    after = _read_vectors(db_path)
    assert before == after, "dry-run 不得写库"
    assert not os.path.exists(state), "dry-run 不得落断点"
    assert stats.processed == 3
    assert stats.eta_s is not None and isinstance(stats.eta_s, float), "必须输出 ETA"
    assert stats.ok == 3
    # R-T5：dry-run 是只读预览，不应触发冷备；备份仅由 backup_only=True 显式触发


# --------------------------------------------------------------------------- #
# backup-only
# --------------------------------------------------------------------------- #
def test_backup_only_creates_bak(tmp_path):
    db_path, _ = _make_db(tmp_path)
    before = _read_vectors(db_path)

    stats = reembed.run(db_path, FakeEncoder(), backup_only=True)

    baks = [f for f in os.listdir(tmp_path) if ".bak-" in f]
    assert baks, "backup-only 应生成 .bak-*"
    assert stats.backup_path and os.path.exists(stats.backup_path)
    assert len(stats.backup_sha256) == 64, "应输出 sha256"
    assert _read_vectors(db_path) == before, "backup-only 不得改库"


# --------------------------------------------------------------------------- #
# 幂等
# --------------------------------------------------------------------------- #
def test_idempotent_two_runs(tmp_path):
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")

    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    first = _read_vectors(db_path)
    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    second = _read_vectors(db_path)

    for item_id in first:
        assert _vec_equal(first[item_id][0], second[item_id][0]), "image_vector 应幂等"
        assert _vec_equal(first[item_id][1], second[item_id][1]), "text_vector 应幂等"


# --------------------------------------------------------------------------- #
# 断点续跑
# --------------------------------------------------------------------------- #
def test_resume_skips_processed(tmp_path):
    db_path, ids = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")

    reembed.run(db_path, FakeEncoder(), resume=False, state_path=state)
    assert os.path.exists(state)

    stats2 = reembed.run(db_path, FakeEncoder(), resume=True, state_path=state)
    assert stats2.processed == 0, "续跑不应重复处理"
    assert stats2.skipped == len(ids)


def test_fingerprint_mismatch_refuses_resume(tmp_path):
    db_path, _ = _make_db(tmp_path)
    state = str(tmp_path / ".reembed_state.json")
    with open(state, "w", encoding="utf-8") as f:
        json.dump({"backend": "other_backend", "model_name": "other-model", "last_id": 1}, f)

    try:
        reembed.run(db_path, FakeEncoder(), resume=True, state_path=state)
        raise AssertionError("指纹不匹配应拒绝续跑")
    except RuntimeError:
        pass


def test_limit_processes_only_n(tmp_path):
    db_path, _ = _make_db(tmp_path, n=5)
    state = str(tmp_path / ".reembed_state.json")
    stats = reembed.run(db_path, FakeEncoder(), dry_run=True, limit=2, state_path=state)
    assert stats.processed == 2
    assert stats.total == 2
