# backend/scripts/reembed_all_vectors.py
"""全量重嵌入 ``items.image_vector`` / ``items.text_vector``（v3.5.0 模型迁移）。

背景
----
v3.5.0 把图像/文本编码器从 ``open_clip ViT-B-32`` 换成 ``Chinese-CLIP ViT-H/14``。
**新旧向量处于不同嵌入空间、不可混用**，故上线前必须用新模型把历史 ``image_vector`` /
``text_vector`` 全量重算一遍。``color_vector``（27 维）与模型无关，**不重算**（铁律 5）。

用法（在 ``backend`` 目录下执行）::

    venv\\Scripts\\python.exe scripts\\reembed_all_vectors.py --backup-only      # 仅冷备
    venv\\Scripts\\python.exe scripts\\reembed_all_vectors.py --dry-run          # 干跑预检（不写库）
    venv\\Scripts\\python.exe scripts\\reembed_all_vectors.py --resume           # 分批正式执行
    venv\\Scripts\\python.exe scripts\\reembed_all_vectors.py --no-resume        # 忽略断点重跑

设计要点
--------
- **编码器解耦**：核心 :func:`run` 通过参数注入 ``encoder``（需提供 ``encode_image(path)`` /
  ``encode_text(text)``）。生产**必须**传 :class:`_ServiceEncoderAdapter`（真实
  ``clip_service`` 只有 ``get_*_feature``，没有 ``encode_*`` —— 见该类 docstring）；
  测试传 ``FakeEncoder`` → **不加载真实模型**。
- **冷备**：``sqlite3`` online backup → ``<DB_PATH>.bak-YYYYmmddHHMMSS``（一致性快照，避免
  半写），输出备份路径 + ``sha256``。
- **``--dry-run``**：只读遍历 + 编码 + 统计；**不写库、不落断点**；输出 **ETA**。
- **断点续跑**：sidecar ``.reembed_state.json`` 带**模型指纹**（``backend`` + ``model_name``），
  指纹不匹配**拒绝续跑并提示**（防跨模型续跑污染）。
- **幂等**：每条记录**始终从源重算**（图片文件 / ``title + ' ' + description``），
  不依赖旧向量 → 连跑两次向量逐元素相等。
- **不改 schema**：只 ``UPDATE`` 既有两列，不新增列/索引（Q6）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

# 允许脚本独立运行：把 backend 目录加入 sys.path（app 包所在目录）
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database import vector_to_json  # noqa: E402
from app.logger import logger  # noqa: E402

STATE_FILENAME = ".reembed_state.json"
DEFAULT_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), STATE_FILENAME)


# --------------------------------------------------------------------------- #
# 编码器适配（生产路径接线）
# --------------------------------------------------------------------------- #
class _ServiceEncoderAdapter:
    """把线上 ``clip_service`` 适配成本脚本的 ``encode_image`` / ``encode_text`` 接口。

    为什么需要这一层（v3.5.0 真实权重实测暴露的**同型缺陷第 4 例**）
    ---------------------------------------------------------------
    :func:`run` 按 ``encoder.encode_image(path)`` / ``encoder.encode_text(text)`` 调用，
    而真实 ``clip_service``（``CLIPService``）暴露的是 ``get_image_feature`` /
    ``get_text_feature`` —— 这两个 ``encode_*`` 名字**只有测试里的 ``FakeEncoder`` 才有**。

    ⇒ **假编码器定义了接口，真实编码器从未被接上**：注入 ``FakeEncoder`` 的单测全绿，
    真机一跑就是 ``AttributeError: 'CLIPService' object has no attribute 'encode_image'``。
    实测 6 条物品 × 2 = 12 次编码全部失败（``ok=0`` / ``failed_encode=12``）。
    这是本项目第 4 次踩同一个坑（前 3 次在 ``calibrate_thresholds.py``）。

    修法：**适配脚本去迁就服务的冻结接口**（``clip_service`` 的公开方法名是 conftest
    打桩依赖的契约，**改名即测试全红**），并配合 :func:`_exit_code` 让失败不再静默成功。

    Note:
        ``name`` / ``model_name`` 故意**委托给真实后端**（而非写死 "clip_service"），
        因为 :func:`model_fingerprint` 依赖它们做断点指纹；写死会让「换模型后续跑」
        的防护失效。
    """

    def __init__(self, service: Any):
        self.service = service

    def get_backend(self):
        return self.service.get_backend()

    @property
    def name(self) -> str:
        return str(getattr(self.service.get_backend(), "name", "unknown"))

    @property
    def model_name(self) -> str:
        return str(getattr(self.service.get_backend(), "model_name", "unknown"))

    def encode_image(self, path: str):
        return self.service.get_image_feature(path)

    def encode_text(self, text: str):
        return self.service.get_text_feature(text)


def _exit_code(stats: "ReembedStats", dry_run: bool) -> int:
    """真跑时的退出码：**失败不得静默成功**（原实现恒返回 0 ⇒ 假绿迁移）。

    为什么这是必须的
    ----------------
    原 ``main()`` 无论 ``ok`` 是几都 ``return 0``。实测在真实权重下 12 次编码全部
    ``AttributeError`` ⇒ ``ok=0`` 却「成功退出」—— 运维会误以为已迁移，而库中向量
    其实**分毫未动**（仍是旧模型维度），匹配继续不可用。

    规则（仅约束**真跑**；``--dry-run`` 是只读预览，失败只提示不判失败）：
      - ``failed_encode > 0``：任何编码失败都视为致命 —— 部分迁移会造成
        **新旧维度混杂**的库，比统一旧维度更危险（打分时部分 500、部分正常）。
      - ``ok == 0 and total > 0``：一条都没成功，等于没迁移。
    """
    if dry_run:
        return 0
    if stats.failed_encode > 0:
        return 2
    if stats.total > 0 and stats.ok == 0:
        return 3
    return 0


# --------------------------------------------------------------------------- #
# 统计
# --------------------------------------------------------------------------- #
@dataclass
class ReembedStats:
    """重嵌入运行统计。"""

    total: int = 0
    processed: int = 0
    ok: int = 0
    failed_encode: int = 0
    no_image_path: int = 0
    no_text: int = 0
    skipped: int = 0
    elapsed_s: float = 0.0
    throughput: float = 0.0
    eta_s: float = 0.0
    backup_path: str = ""
    backup_sha256: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _sha256_file(path: str, chunk_size: int = 1 << 20) -> str:
    """计算文件 sha256。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def _to_ndarray(vec: Any) -> np.ndarray:
    """把编码器输出规整为 ``numpy.ndarray``（``vector_to_json`` 要求 ndarray）。"""
    if isinstance(vec, np.ndarray):
        return vec
    return np.asarray(vec, dtype=np.float32)


def _text_source(title: Optional[str], description: Optional[str]) -> str:
    """文本向量源：``title + ' ' + description``（幂等、与线上一致）。"""
    parts = [(title or "").strip(), (description or "").strip()]
    return " ".join(p for p in parts if p)


def backup_db(db_path: str) -> tuple[str, str]:
    """冷备数据库（``sqlite3`` online backup，一致性快照）。

    Returns:
        ``(backup_path, sha256)``。
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    dst_path = f"{db_path}.bak-{ts}"
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(dst_path)
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return dst_path, _sha256_file(dst_path)


def model_fingerprint(encoder: Any) -> Dict[str, str]:
    """从编码器提取模型指纹（``backend`` + ``model_name``）。

    - 若 encoder 直接带 ``name`` / ``model_name``（如假编码器），直接用；
    - 若 encoder 是 ``clip_service``（单例外观），经 ``get_backend()`` 取得。
    """
    backend = getattr(encoder, "name", None)
    model_name = getattr(encoder, "model_name", None)
    if backend is None and hasattr(encoder, "get_backend"):
        try:
            b = encoder.get_backend()
            backend = getattr(b, "name", None)
            model_name = getattr(b, "model_name", None)
        except Exception:  # pragma: no cover - 后端不可用时退化为 unknown
            pass
    return {"backend": backend or "unknown", "model_name": model_name or "unknown"}


def _load_state(state_path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # pragma: no cover - 损坏断点视为无断点
        logger.warning(f"断点文件读取失败，忽略: {state_path}: {e}")
        return None


def _save_state(state_path: str, state: Dict[str, Any]) -> None:
    """原子写入断点文件。"""
    tmp = state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, state_path)


# --------------------------------------------------------------------------- #
# 核心
# --------------------------------------------------------------------------- #
def run(
    db_path: str,
    encoder: Any,
    *,
    dry_run: bool = False,
    backup_only: bool = False,
    resume: bool = True,
    batch_size: int = 100,
    limit: Optional[int] = None,
    state_path: Optional[str] = None,
) -> ReembedStats:
    """执行全量重嵌入。

    Args:
        db_path: SQLite 库文件路径。
        encoder: 编码器（需 ``encode_image(path)`` / ``encode_text(text)``）。
            生产传 ``clip_service``；测试传 ``FakeEncoder``。
        dry_run: 只读干跑，**不写库、不落断点**；仍输出统计与 ETA。
        backup_only: 只做冷备后返回。
        resume: 是否读取断点续跑（默认 True）。
        batch_size: 每 N 行提交一次事务（避免长写锁）。
        limit: 只处理前 N 行（冒烟用）。
        state_path: 断点文件路径（默认 ``scripts/.reembed_state.json``）。

    Returns:
        :class:`ReembedStats`。
    """
    state_path = state_path or DEFAULT_STATE_PATH
    stats = ReembedStats()
    started = time.time()

    # ---- 1) 冷备（先做，回滚源）----
    # R-T5：dry_run 是只读预览，不应触发任何**写盘**操作（含冷备）；
    #       backup_only 仍照做（它本身的任务就是冷备）。
    if not dry_run:
        try:
            backup_path, sha = backup_db(db_path)
            stats.backup_path = backup_path
            stats.backup_sha256 = sha
            print(f"[备份] {backup_path}  sha256={sha}")
        except Exception as e:
            logger.error(f"冷备失败: {e}")
            raise

    if backup_only:
        stats.elapsed_s = round(time.time() - started, 3)
        print("[备份] --backup-only 完成，未执行重嵌入")
        return stats

    # ---- 2) 断点校验（指纹）----
    fingerprint = model_fingerprint(encoder)
    last_id = 0
    if resume:
        state = _load_state(state_path)
        if state:
            if (
                state.get("backend") != fingerprint["backend"]
                or state.get("model_name") != fingerprint["model_name"]
            ):
                raise RuntimeError(
                    "断点指纹不匹配，拒绝续跑（防止跨模型污染）："
                    f"断点=({state.get('backend')}/{state.get('model_name')})，"
                    f"当前=({fingerprint['backend']}/{fingerprint['model_name']})。"
                    "如确需重跑请加 --no-resume。"
                )
            last_id = int(state.get("last_id", 0) or 0)

    run_id = str(uuid.uuid4())
    now_iso = datetime.now().isoformat(timespec="seconds")

    # ---- 3) 遍历 ----
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    processed_rows: List[int] = []
    try:
        sql = "SELECT id, title, description, image_path FROM items ORDER BY id ASC"
        params: List[Any] = []
        if limit:
            sql += " LIMIT ?"
            params.append(int(limit))
        rows = conn.execute(sql, params).fetchall()
        stats.total = len(rows)
        pending = [r for r in rows if int(r["id"]) > last_id]
        stats.skipped = stats.total - len(pending)

        for row in pending:
            item_id = int(row["id"])
            stats.processed += 1
            updates: Dict[str, Any] = {}

            # 图片向量：始终从源（图片文件）重算
            image_path = row["image_path"]
            if image_path and os.path.exists(image_path):
                try:
                    updates["image_vector"] = vector_to_json(
                        _to_ndarray(encoder.encode_image(image_path))
                    )
                except Exception as e:
                    stats.failed_encode += 1
                    logger.warning(f"物品 {item_id} 图片编码失败: {e}")
            else:
                stats.no_image_path += 1

            # 文本向量：始终从源（title + description）重算
            text_src = _text_source(row["title"], row["description"])
            if text_src:
                try:
                    updates["text_vector"] = vector_to_json(
                        _to_ndarray(encoder.encode_text(text_src))
                    )
                except Exception as e:
                    stats.failed_encode += 1
                    logger.warning(f"物品 {item_id} 文本编码失败: {e}")
            else:
                stats.no_text += 1

            # 写库（dry-run 时跳过）
            if updates:
                stats.ok += 1
                if not dry_run:
                    sets = ", ".join(f"{k}=?" for k in updates)
                    conn.execute(
                        f"UPDATE items SET {sets} WHERE id=?",
                        list(updates.values()) + [item_id],
                    )
                    if stats.processed % max(1, batch_size) == 0:
                        conn.commit()
                processed_rows.append(item_id)

            # 进度 + ETA（保证 dry-run 也输出 ETA）
            elapsed = time.time() - started
            rate = stats.processed / elapsed if elapsed > 0 else 0.0
            remaining = stats.total - stats.skipped - stats.processed
            stats.throughput = round(rate, 3)
            stats.eta_s = round(remaining / rate, 1) if rate > 0 and remaining > 0 else 0.0
            if stats.processed % max(1, batch_size) == 0:
                print(
                    f"[进度] {stats.processed}/{len(pending)} "
                    f"throughput={stats.throughput}/s ETA={stats.eta_s}s"
                )

        if not dry_run:
            conn.commit()
    finally:
        conn.close()

    # ---- 4) 收尾统计 ----
    stats.elapsed_s = round(time.time() - started, 3)
    if stats.elapsed_s > 0 and stats.processed > 0:
        stats.throughput = round(stats.processed / stats.elapsed_s, 3)
    if stats.throughput > 0:
        remaining = stats.total - stats.skipped - stats.processed
        stats.eta_s = round(remaining / stats.throughput, 1) if remaining > 0 else 0.0

    # ---- 5) 落断点（dry-run / 无处理时不落）----
    if not dry_run and processed_rows:
        _save_state(
            state_path,
            {
                "run_id": run_id,
                "backend": fingerprint["backend"],
                "model_name": fingerprint["model_name"],
                "last_id": max(processed_rows),
                "started_at": now_iso,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )

    return stats


def _print_stats(stats: ReembedStats) -> None:
    """打印统计摘要（含 ETA）。"""
    d = stats.to_dict()
    print("=" * 56)
    print("重嵌入统计")
    print("=" * 56)
    for key in (
        "total",
        "processed",
        "ok",
        "failed_encode",
        "no_image_path",
        "no_text",
        "skipped",
        "elapsed_s",
        "throughput",
        "eta_s",
        "backup_path",
        "backup_sha256",
    ):
        print(f"  {key:<16}: {d[key]}")
    print("=" * 56)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="全量重嵌入 items.image_vector / text_vector（v3.5.0）"
    )
    parser.add_argument("--db", default=None, help="SQLite 库文件路径（默认取 app.database.DB_PATH）")
    parser.add_argument("--dry-run", action="store_true", help="只读干跑，不写库、不落断点（输出 ETA）")
    parser.add_argument("--backup-only", action="store_true", help="仅冷备，不重算")
    parser.add_argument("--resume", dest="resume", action="store_true", default=True, help="从断点续跑（默认）")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="忽略断点，从头重跑")
    parser.add_argument("--batch-size", type=int, default=100, help="每 N 行提交一次事务（默认 100）")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 行（冒烟用）")
    parser.add_argument("--state-path", default=None, help="断点文件路径（默认 scripts/.reembed_state.json）")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    from app.database import DB_PATH
    from app.clip_service import clip_service

    db_path = args.db or DB_PATH
    # 生产路径必须经适配器：真实 clip_service 暴露 get_*_feature，本脚本内部用 encode_*
    stats = run(
        db_path,
        _ServiceEncoderAdapter(clip_service),
        dry_run=args.dry_run,
        backup_only=args.backup_only,
        resume=args.resume,
        batch_size=args.batch_size,
        limit=args.limit,
        state_path=args.state_path,
    )
    _print_stats(stats)
    code = _exit_code(stats, args.dry_run)
    if code != 0:
        print("!" * 56)
        print(
            f"[FAIL] 重嵌入未成功：ok={stats.ok} / failed_encode={stats.failed_encode}"
            f" / total={stats.total}（退出码 {code}）"
        )
        print("       库中向量很可能未变化（或部分变化）→ 请勿视为已迁移。")
        print("!" * 56)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
