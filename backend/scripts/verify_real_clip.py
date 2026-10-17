"""真实 Chinese-CLIP 权重端到端验证（v3.5.0）。

用途
----
权重落盘后，用**真实模型**（而非打桩）验证整条链路，把 v3.5.0 的结论
从「已打桩验证」升级为「已用真实模型验证」。这是可复现的凭据，不是断言。

前置
----
::

    set CLIP_BACKEND=cn_clip
    set CLIP_CN_CKPT_PATH=<abs>\\backend\\models\\clip_cn_vit-h-14.pt
    venv\\Scripts\\python.exe scripts\\verify_real_clip.py

检查项
------
1. **环境与后端契约** —— 后端声明维度与 config 一致；ckpt 路径存在；
   且 ``CLIP_CN_MODEL_NAME`` 与 ``_CN_TEXT_MODEL_NAME`` 拼出的 struct
   确实存在于 cn_clip 的 ``_MODEL_INFO`` 中（配错必须响亮失败，不得静默降级）。
2. **真实加载** —— 真正从本地 ``.pt`` 载入（记录耗时）。
3. **编码维度与归一化** —— 图/文向量均为 1024 维且 L2 范数 ≈ 1。
4. **语义合理性** —— 取评测集中一条真实「文本描述 × 物品图」正样本，
   与一个**跨类别**物品图比较：正样本余弦应**显著高于**跨类别负样本。
   这一条能证明模型真的在做图文语义对齐，而不是「能跑出一个归一化向量」。

退出码 0 = 全部通过；非 0 = 有检查失败（并打印原因）。
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

EVAL_SET = os.path.join(BACKEND_DIR, "eval", "eval_set_v3.5.0.json")

_FAILURES: list[str] = []


def _ok(label: str, detail: str = "") -> None:
    print("  [PASS] %s%s" % (label, ("  " + detail) if detail else ""))


def _fail(label: str, detail: str = "") -> None:
    print("  [FAIL] %s%s" % (label, ("  " + detail) if detail else ""))
    _FAILURES.append(label + ("  " + detail if detail else ""))


def _check(cond: bool, label: str, detail: str = "") -> bool:
    if cond:
        _ok(label, detail)
    else:
        _fail(label, detail)
    return cond


# --------------------------------------------------------------------------- #
# 1. 环境与后端契约
# --------------------------------------------------------------------------- #
def check_env_contract() -> int:
    from app.clip_backend import _CN_TEXT_MODEL_NAME, get_backend
    from app.config import settings

    print("=" * 70)
    print("【1】环境与后端契约")
    print("  CLIP_BACKEND       : %s" % settings.CLIP_BACKEND)
    print("  CLIP_CN_MODEL_NAME : %s" % settings.CLIP_CN_MODEL_NAME)
    print("  CLIP_CN_CKPT_PATH  : %s" % (settings.CLIP_CN_CKPT_PATH or "(空)"))
    print("  CLIP_CN_EMBED_DIM  : %s" % settings.CLIP_CN_EMBED_DIM)

    backend = get_backend(settings)
    print("  backend class      : %s" % type(backend).__name__)
    print("  backend.embed_dim  : %s" % backend.embed_dim)

    _check(
        int(backend.embed_dim) == int(settings.CLIP_CN_EMBED_DIM),
        "后端声明维度 == config 声明维度",
        "%s == %s" % (backend.embed_dim, settings.CLIP_CN_EMBED_DIM),
    )

    if settings.CLIP_BACKEND != "cn_clip":
        _fail("CLIP_BACKEND 非 cn_clip（本次验证的是中文模型）",
              "实际为 %s" % settings.CLIP_BACKEND)
        return int(settings.CLIP_CN_EMBED_DIM)

    _check(bool(settings.CLIP_CN_CKPT_PATH),
           "CLIP_CN_CKPT_PATH 已设置（零网络加载）",
           "空值会退化为联网下载")
    if settings.CLIP_CN_CKPT_PATH:
        _check(os.path.isfile(settings.CLIP_CN_CKPT_PATH),
               "CLIP_CN_CKPT_PATH 指向真实文件",
               settings.CLIP_CN_CKPT_PATH)

    # 核实与 cn_clip 内部 struct 精确一致 —— 这是 3.8GB 能否加载的关键
    try:
        import cn_clip.clip.utils as cu

        constructed = "%s@%s" % (settings.CLIP_CN_MODEL_NAME, _CN_TEXT_MODEL_NAME)
        known = {v["struct"] for v in cu._MODEL_INFO.values()}
        _check(constructed in known,
               "clip_backend 构造的 struct 存在于 cn_clip _MODEL_INFO",
               constructed)
        declared = cu._MODEL_INFO.get(settings.CLIP_CN_MODEL_NAME, {}).get("struct")
        _check(declared == constructed,
               "与 cn_clip 官方声明的 struct 精确匹配",
               "官方=%s" % declared)
        for name in (settings.CLIP_CN_MODEL_NAME, _CN_TEXT_MODEL_NAME):
            cfg = os.path.join(os.path.dirname(cu.__file__), "model_configs", name + ".json")
            _check(os.path.isfile(cfg), "model_configs/%s.json 存在" % name)
    except ImportError as exc:  # pragma: no cover
        _fail("导入 cn_clip 失败", str(exc))

    return int(settings.CLIP_CN_EMBED_DIM)


# --------------------------------------------------------------------------- #
# 3. 编码维度与归一化
# --------------------------------------------------------------------------- #
def check_encoding(dim: int) -> None:
    from app.clip_service import clip_service

    print()
    print("【3】编码维度与 L2 归一化（期望 %d 维 / 范数 1.0）" % dim)

    text = "一个白色的真无线蓝牙耳机，配一个方形充电仓，在图书馆三楼捡到的"
    tvec = clip_service.get_text_feature(text)
    tvec = np.asarray(tvec, dtype=np.float32)
    _check(tuple(tvec.shape) == (dim,), "文本向量维度", "shape=%s" % (tvec.shape,))
    _check(abs(float(np.linalg.norm(tvec)) - 1.0) < 1e-3,
           "文本向量 L2 归一化", "norm=%.6f" % float(np.linalg.norm(tvec)))

    img = os.path.join(BACKEND_DIR, "uploads", "079e84f2be8e4ace8df4f663300d0200.jpg")
    _check(os.path.isfile(img), "示例图片存在", "uploads/079e...jpg")
    if os.path.isfile(img):
        ivec = np.asarray(clip_service.get_image_feature(img), dtype=np.float32)
        _check(tuple(ivec.shape) == (dim,), "图片向量维度", "shape=%s" % (ivec.shape,))
        _check(abs(float(np.linalg.norm(ivec)) - 1.0) < 1e-3,
               "图片向量 L2 归一化", "norm=%.6f" % float(np.linalg.norm(ivec)))


# --------------------------------------------------------------------------- #
# 4. 语义合理性（真实正样本 vs 跨类别负样本）
# --------------------------------------------------------------------------- #
def check_semantics() -> None:
    from app.clip_service import clip_service

    print()
    print("【4】语义合理性：真实「文本描述 × 物品图」正样本 vs 跨类别物品图")

    with open(EVAL_SET, encoding="utf-8") as fh:
        data = json.load(fh)
    pairs = data["pairs"]

    pos = next((p for p in pairs
                if p["label"] == 1 and p["query"].get("text") and p["target"].get("item_ref")), None)
    if pos is None:
        _fail("评测集中找不到「文本→物品图」正样本")
        return

    neg = next((p for p in pairs
                if p["label"] == 0
                and p["target"].get("item_ref")
                and p["target"]["item_ref"] != pos["target"]["item_ref"]
                and p["category"] != pos["category"]), None)
    if neg is None:
        _fail("评测集中找不到跨类别负样本")
        return

    print("  正样本 %s [%s]  query: %s" % (pos["id"], pos["category"], pos["query"]["text"][:34] + "…"))
    print("        目标图: %s" % pos["target"]["item_ref"])
    print("  负样本 %s [%s]  跨类别图: %s" % (neg["id"], neg["category"], neg["target"]["item_ref"]))

    qv = np.asarray(clip_service.get_text_feature(pos["query"]["text"]), dtype=np.float32)
    pv = np.asarray(clip_service.get_image_feature(
        os.path.join(BACKEND_DIR, pos["target"]["item_ref"])), dtype=np.float32)
    nv = np.asarray(clip_service.get_image_feature(
        os.path.join(BACKEND_DIR, neg["target"]["item_ref"])), dtype=np.float32)

    c_pos = float(np.dot(qv, pv))
    c_neg = float(np.dot(qv, nv))

    print("  cos(查询文本, 正样本图) = %+.4f" % c_pos)
    print("  cos(查询文本, 跨类别图) = %+.4f" % c_neg)
    print("  差值 (正 - 负)          = %+.4f" % (c_pos - c_neg))

    _check(c_pos > c_neg, "正样本余弦 > 跨类别负样本余弦",
           "%.4f > %.4f" % (c_pos, c_neg))
    _check((c_pos - c_neg) > 0.02, "留有余量（差值 > 0.02）",
           "差值 %.4f" % (c_pos - c_neg))


def main() -> int:
    t_start = time.time()
    print("真实 Chinese-CLIP 端到端验证 — v3.5.0")
    print()

    dim = check_env_contract()

    print()
    print("【2】真实加载权重（约 3.8GB，首次较慢）")
    from app.clip_service import clip_service  # noqa: F401  触发模块导入

    t_load = time.time()
    clip_service.get_text_feature("预热")  # 强制真正加载模型
    print("  [PASS] 权重加载 + 首次编码完成  用时 %.1f s" % (time.time() - t_load))

    check_encoding(dim)
    check_semantics()

    print()
    print("=" * 70)
    if _FAILURES:
        print("结论：**未能验证** — %d 项检查失败：" % len(_FAILURES))
        for f in _FAILURES:
            print("   - %s" % f)
        print("总耗时 %.1f s" % (time.time() - t_start))
        return 1
    print("结论：**已用真实模型验证** — 全部检查通过")
    print("总耗时 %.1f s" % (time.time() - t_start))
    return 0


if __name__ == "__main__":
    sys.exit(main())
