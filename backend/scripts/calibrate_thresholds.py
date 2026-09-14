# backend/scripts/calibrate_thresholds.py
"""阈值标定 + PR 曲线 + Recall@K + 权重网格收敛（v3.5.0）。

用法（在 ``backend`` 目录下执行）::

    venv\\Scripts\\python.exe scripts\\calibrate_thresholds.py --with-penalty
    venv\\Scripts\\python.exe scripts\\calibrate_thresholds.py --grid
    venv\\Scripts\\python.exe scripts\\calibrate_thresholds.py \\
        --eval-set eval\\eval_set_v3.5.0.json --out ..\\docs\\review\\threshold-calibration-v3.5.0.md

设计要点
--------
- **同一口径**：复用线上同一个 ``clip_service.compute_weighted_similarity``，
  保证「标定口径 = 线上口径」。调用点与线上一致（``img1/text1/img2/text2`` +
  ``color1/color2``，见 :func:`score_pair`）；**颜色通道必须显式传入**，否则
  ``W_COLOR`` 会因 ``has_col=False`` 被动态归一化剔除而**完全惰性**（v3.5.0 已修）。
- **阈值口径（Q1）**：
    * ``AUTO``   = Precision ≥ 0.90 的**最低**分位；
    * ``EMAIL``  = Precision ≥ 0.98 的**最低**分位；
    * ``MANUAL`` = Recall ≥ 0.90 的**最高**分位。
- **Recall@K**：每个正样本查询对全部候选目标打分排序，目标命中 rank ≤ K 记为命中。
- **``--grid``**：对 ``{W_IMG_IMG, W_CROSS, W_TEXT_TEXT, W_COLOR}`` 做步长 0.05、和 = 1.0
  的粗网格搜索，目标「在 Precision ≥ 0.90 的最低阈值处最大化 Recall@3」，输出 Top-5。
- **可打桩**：:func:`evaluate` / :func:`run_calibration` 接受注入的 ``encoder``；
  测试传 ``FakeEncoder`` → **不加载真实模型**。
- **阻塞性标注**：若任一阈值下 ``Recall@3 < 0.90``，报告显著标注为**阻塞性发现**。
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.clip_service import clip_service  # noqa: E402
from app.config import settings  # noqa: E402
from app.logger import logger  # noqa: E402

DEFAULT_EVAL_SET = os.path.join(BACKEND_DIR, "eval", "eval_set_v3.5.0.json")
DEFAULT_OUT = os.path.join(
    os.path.dirname(BACKEND_DIR), "docs", "review", "threshold-calibration-v3.5.0.md"
)

# 权重网格的 4 个维度 ↔ config 键名
_WEIGHT_KEYS = ("img_img", "cross", "text_text", "color")


class _FakeEncoder:
    """确定性假编码器（**仅**用于 ``--fake-encoder`` 冒烟，不加载真实模型）。

    真实编码需 3.8GB 权重；CI/结构校验时用本类走通完整链路（PR 曲线/召回计算）。
    """

    name = "fake"
    model_name = "fake-model"

    def encode_image(self, path):
        import numpy as np

        v = np.full(512, (abs(hash(path)) % 97) + 1, dtype=np.float32)
        return v / np.linalg.norm(v)

    def encode_text(self, text):
        import numpy as np

        v = np.full(512, (abs(hash(text)) % 97) + 1, dtype=np.float32)
        return v / np.linalg.norm(v)

    def encode_color(self, path):
        """确定性 27 维颜色直方图（**仅**冒烟；形状对齐 ``get_color_histogram``）。"""
        import numpy as np

        h = np.zeros(27, dtype=np.float32)
        h[abs(hash(path)) % 27] = 1.0
        return h


class _ServiceEncoderAdapter:
    """把线上 ``clip_service`` 适配成本脚本的 ``encode_*`` 接口。

    为什么需要这一层（v3.5.0 真实权重实测才暴露的 bug）
    --------------------------------------------------
    本脚本原先在 :class:`_EncoderCache` 里直接调用 ``encoder.encode_text`` /
    ``encoder.encode_image`` —— 而这两个名字**只有** :class:`_FakeEncoder` 才有；
    真实 ``clip_service``（``CLIPService``）暴露的是 ``get_text_feature`` /
    ``get_image_feature``。

    也就是说**假编码器定义了接口，真实编码器从未被接上**：``--fake-encoder``
    一路绿灯，真机一跑就是 ``AttributeError: 'CLIPService' object has no attribute
    'encode_text'``。因为真实权重长期不可得，这条路径从未被执行过，
    连 ``--fake-encoder`` 冒烟也照不出问题。

    修法：**适配脚本去迁就服务的冻结接口**（``clip_service`` 的公开方法名与签名
    是冻结契约，见 ``app/clip_service.py``；改名会让 conftest 的打桩全面失效），
    而不是反过来改服务。
    """

    def __init__(self, service: Any):
        self.service = service

    @property
    def name(self) -> str:
        return str(settings.CLIP_BACKEND)

    @property
    def model_name(self) -> str:
        if settings.CLIP_BACKEND == "cn_clip":
            return str(settings.CLIP_CN_MODEL_NAME)
        return str(settings.CLIP_OPEN_MODEL_NAME)

    def encode_text(self, text: str):
        return self.service.get_text_feature(text)

    def encode_image(self, path: str):
        return self.service.get_image_feature(path)

    def encode_color(self, path: str):
        """颜色直方图（27 维）——与线上 ``color1``/``color2`` 同源。

        见 :func:`score_pair` 的『颜色通道缺失』注记：加上本方法后，标定脚本才
        真正复现线上「图+文+色」的完整打表面。
        """
        return self.service.get_color_histogram(path)


# --------------------------------------------------------------------------- #
# 评测集
# --------------------------------------------------------------------------- #
def load_eval_set(path: str) -> Dict[str, Any]:
    """加载评测集 JSON（结构：``{version, pairs:[{id,label,category,query,target}]}``）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "pairs" not in data or not isinstance(data["pairs"], list):
        raise ValueError(f"评测集格式非法（缺 pairs）: {path}")
    return data


# --------------------------------------------------------------------------- #
# 评测集结构统计 / 校验（不加载模型）
# --------------------------------------------------------------------------- #
# 模型文本塔可用窗口（汉字）：context_length 52 − [CLS] − [SEP] = 50
TEXT_TOWER_WINDOW = 50


def _char_len(text: Any) -> int:
    """按「字符」计数（中文一字一字符；与前端 maxlength / 模型窗口同口径）。"""
    if not isinstance(text, str):
        return 0
    return len(text)


# 『同图自比』退化对的标记键（JSON pair 级布尔字段）
DEGENERATE_KEY = "degenerate_self"


def is_degenerate(pair: Dict[str, Any]) -> bool:
    """是否为『同图自比』退化对（``query.image`` 与 ``target.item_ref`` 同一文件）。

    此类对 ``sim_ii = v·v ≡ 1.0``，会**虚高 Recall** 并**向下拖低 auto 阈值**
    （``lowest_with_precision`` 更早满足 0.90）→ 生产风险。故 **不计入标定计算**，
    仅保留作 ``sim_ii`` 通道接线自检。

    判定：显式标记 ``degenerate_self=True`` **或** 两图路径字面相同（兜底，防漏标）。
    """
    if pair.get(DEGENERATE_KEY):
        return True
    q = (pair.get("query") or {}).get("image")
    t = (pair.get("target") or {}).get("item_ref")
    return bool(q) and bool(t) and q == t


def summarize_eval_set(eval_set: Dict[str, Any], base_dir: Optional[str] = None) -> Dict[str, Any]:
    """统计并校验评测集结构（**纯结构分析，不加载模型、不联网**）。

    覆盖团队要求的扩展统计：
    - 总数 / 正样本 / 负样本；
    - ``query.image`` 非空总数，并拆分为 img→text（仅 target.text）、
      img→img（仅 target.item_ref）、img→mixed（目标图文兼备）；
    - 纯文查询数量；
    - ``target.text`` 缺失（``null``）数量——即「目标仅有图片」路径覆盖；
    - 查询文本长度 min / max，以及 > ``TEXT_TOWER_WINDOW`` 字（会被静默截断）的数量；
    - 正样本「标题原词泄漏」列表（查询文本包含目标 title 原词 → 违反 §3 硬约束）；
    - 所有 ``query.image`` / ``target.item_ref`` 引用的图片是否真实存在（相对 ``base_dir``）。

    Returns:
        上述统计组成的字典。
    """
    base_dir = base_dir or BACKEND_DIR
    pairs = eval_set.get("pairs", []) or []
    total = len(pairs)
    pos = sum(1 for p in pairs if int(p.get("label", 0)) == 1)
    neg = total - pos

    query_image = 0
    img_to_text = 0      # query.image + 仅 target.text
    img_to_img = 0       # query.image + 仅 target.item_ref
    img_to_mixed = 0     # query.image + target 图文兼备
    text_query = 0       # 纯文查询（无图片）
    target_text_null = 0

    lengths: List[int] = []
    over_window = 0
    title_violations: List[str] = []
    image_refs: List[str] = []
    degenerate_self = 0

    for p in pairs:
        if is_degenerate(p):
            degenerate_self += 1
        q = p.get("query", {}) or {}
        t = p.get("target", {}) or {}
        q_has_img = bool(q.get("image"))
        q_has_text = bool(q.get("text"))
        t_has_img = bool(t.get("item_ref"))
        t_has_text = bool(t.get("text"))

        if q_has_img:
            image_refs.append(str(q["image"]))
        if t_has_img:
            image_refs.append(str(t["item_ref"]))

        if not t_has_text:
            target_text_null += 1

        if q_has_img:
            query_image += 1
            if t_has_text and not t_has_img:
                img_to_text += 1
            elif t_has_img and not t_has_text:
                img_to_img += 1
            else:
                img_to_mixed += 1
        elif q_has_text:
            text_query += 1

        if q_has_text:
            n = _char_len(q["text"])
            lengths.append(n)
            if n > TEXT_TOWER_WINDOW:
                over_window += 1

        # 正样本标题原词泄漏（弱标注自检；负样本不适用）
        if int(p.get("label", 0)) == 1 and q_has_text and t_has_text:
            title = str(t["text"]).split(" ")[0].strip()
            if title and title in q["text"]:
                title_violations.append(str(p.get("id")))

    unique_refs = sorted(set(image_refs))
    missing_images = [
        ref for ref in unique_refs
        if not os.path.isfile(os.path.join(base_dir, ref))
    ]

    # 退化对按标签拆分（用于计算「有效标定集」规模）
    degenerate_pos = sum(
        1 for p in pairs if is_degenerate(p) and int(p.get("label", 0)) == 1
    )
    degenerate_neg = degenerate_self - degenerate_pos

    return {
        "total": total,
        "positive": pos,
        "negative": neg,
        "degenerate_self": degenerate_self,
        "effective_positive": pos - degenerate_pos,
        "effective_negative": neg - degenerate_neg,
        "query_image": query_image,
        "img_to_text": img_to_text,
        "img_to_img": img_to_img,
        "img_to_mixed": img_to_mixed,
        "text_query": text_query,
        "target_text_null": target_text_null,
        "query_text_min_len": min(lengths) if lengths else 0,
        "query_text_max_len": max(lengths) if lengths else 0,
        "query_text_over_window": over_window,
        "window": TEXT_TOWER_WINDOW,
        "title_violations": title_violations,
        "image_refs": unique_refs,
        "missing_images": missing_images,
    }


def print_eval_stats(stats: Dict[str, Any]) -> None:
    """把 :func:`summarize_eval_set` 的结果打印为可读清单。"""
    print("=" * 60)
    print("评测集结构统计（不加载模型）")
    print(f"  总对数          : {stats['total']}")
    print(f"  正样本 / 负样本 : {stats['positive']} / {stats['negative']}")
    print(
        f"  query.image 非空: {stats['query_image']}"
        f"（img→text {stats['img_to_text']} ｜ img→img {stats['img_to_img']}"
        f" ｜ img→mixed {stats['img_to_mixed']}）"
    )
    print(f"  纯文查询        : {stats['text_query']}")
    print(f"  target.text=null: {stats['target_text_null']}")
    print(
        f"  退化正例(同图自比): {stats['degenerate_self']}"
        f"  → 已从标定计算【剔除】（仅作 sim_ii 接线自检）"
    )
    print(
        f"  有效标定集规模  : {stats['effective_positive']} 正 / "
        f"{stats['effective_negative']} 负（正负不平衡为有意保守）"
    )
    print(
        f"  查询文本长度    : min {stats['query_text_min_len']} ｜ "
        f"max {stats['query_text_max_len']} ｜ "
        f">{stats['window']} 字 {stats['query_text_over_window']}"
    )
    tv = stats["title_violations"]
    print(f"  正样本标题词泄漏: {len(tv)}" + (f"  → {', '.join(tv)}" if tv else ""))
    miss = stats.get("missing_images", [])
    print(
        f"  引用图片存在性  : {len(stats.get('image_refs', []))} 个引用，"
        f"缺失 {len(miss)}" + (f"  → {', '.join(miss)}" if miss else "")
    )
    print("=" * 60)


def verify_degenerate_self(eval_set: Dict[str, Any], encoder: Any) -> List[Dict[str, Any]]:
    """对每对『同图自比』退化样本，实测 ``sim_ii = q_img · t_img``（通道接线自检）。

    期望恒为 1.0：同一文件 → 同一向量 ``v``，且 ``v`` 已 L2 归一化 → ``v·v = 1.0``。
    本函数**只验证 ``sim_ii`` 通道被正确接通**，其数值**不参与**阈值标定。
    """
    cache = _EncoderCache(encoder)
    rows: List[Dict[str, Any]] = []
    for p in eval_set["pairs"]:
        if not is_degenerate(p):
            continue
        q_ref = (p.get("query") or {}).get("image")
        t_ref = (p.get("target") or {}).get("item_ref")
        q_img = cache.image(q_ref)
        t_img = cache.image(t_ref)
        sim_ii = float(np.dot(q_img, t_img))
        score = clip_service.compute_weighted_similarity(q_img, None, t_img, None)
        rows.append({
            "id": p.get("id"),
            "query.image": q_ref,
            "target.item_ref": t_ref,
            "same_file": q_ref == t_ref,
            "sim_ii": round(sim_ii, 6),
            "score": score,
        })
    return rows


def print_degenerate_check(rows: List[Dict[str, Any]]) -> None:
    """打印 ``sim_ii`` 通道接线自检结果（同图自比恒为 1.0）。"""
    print("=" * 60)
    print("退化对 sim_ii 通道接线自检（同图自比；不计入标定）")
    if not rows:
        print("  （无退化对）")
        print("=" * 60)
        return
    for r in rows:
        print(
            f"  {r['id']}: q={r['query.image']}  t.ref={r['target.item_ref']}  "
            f"same_file={r['same_file']}  sim_ii={r['sim_ii']}  score={r['score']}"
        )
    all_one = all(abs(r["sim_ii"] - 1.0) < 1e-6 for r in rows)
    verdict = "是 ✅ sim_ii 通道已接通" if all_one else "⚠️ 否（异常，请排查）"
    print(f"  → 共 {len(rows)} 对，全部 sim_ii == 1.0：{verdict}")
    print("=" * 60)


# --------------------------------------------------------------------------- #
# 编码缓存 + 打分
# --------------------------------------------------------------------------- #
class _EncoderCache:
    """按 (kind, key) 缓存编码结果，避免重复调用编码器。"""

    def __init__(self, encoder: Any):
        self.encoder = encoder
        self._cache: Dict[Tuple[str, str], Any] = {}

    def text(self, text: str):
        key = ("text", text)
        if key not in self._cache:
            self._cache[key] = self.encoder.encode_text(text)
        return self._cache[key]

    def image(self, path: str):
        key = ("image", path)
        if key not in self._cache:
            self._cache[key] = self.encoder.encode_image(path)
        return self._cache[key]

    def color(self, path: str):
        """颜色直方图缓存（27 维）。与 :meth:`image` 分开缓存：同一路径下两者不同物。"""
        key = ("color", path)
        if key not in self._cache:
            self._cache[key] = self.encoder.encode_color(path)
        return self._cache[key]


@contextlib.contextmanager
def penalty_enabled(enabled: bool):
    """临时切换 ``CROSS_PENALTY_ENABLED``（用于 with/without-penalty 对照）。"""
    old = settings.CROSS_PENALTY_ENABLED
    settings.CROSS_PENALTY_ENABLED = bool(enabled)
    try:
        yield
    finally:
        settings.CROSS_PENALTY_ENABLED = old


def _weights_kwargs(weights: Optional[Dict[str, float]]) -> Dict[str, float]:
    """把 4 维权重 dict 转成 ``compute_weighted_similarity`` 关键字参数。"""
    if not weights:
        return {}
    return {
        "img_weight": weights["img_img"],
        "text_weight": weights["text_text"],
        "color_weight": weights["color"],
        "cross_weight": weights["cross"],
    }


def score_pair(
    cache: _EncoderCache,
    pair: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """对单个「查询-目标」对打分（复用线上 ``compute_weighted_similarity``）。

    说明：默认**不传类别/位置/时间**（标定纯内容相似度，避免统一加分造成阈值漂移）。

    颜色通道缺失缺陷（v3.5.0 真实权重实测第二处才暴露）
    -----------------------------------------------------
    本函数原先只传 ``(q_img, q_text, t_img, t_text)``，**不传** ``color1``/``color2``。
    而线上两个真实调用点都传：

      - ``services/match_service.py:104`` → ``color1=new_color_vec, color2=target_color_vec``
      - ``api/items.py:614``              → ``color1=query_color_vec, color2=target_color_vec``

    后果：``clip_service.compute_weighted_similarity`` 里 ``has_col = color1 is not None
    and color2 is not None`` **恒为 False** → 颜色通道被动态归一化剔除 → ``W_COLOR``
    在标定里**数学上完全惰性**（实测 color_weight 取 0.0 / 0.15 / 0.5 / 0.9 得分**完全
    相同**）。于是权重网格里那列 ``W_COLOR 0.7~0.9`` 是**假象**：网格实际选中的是
    ``W_CROSS=0``（等价于纯 ``sim_tt``），只是把剩余权重随便塞进了惰性的 color 列。

    这违反了本模块「标定口径 = 线上口径」的设计前提（见模块 docstring）。修法：与线上
    一致，查询色取自 ``query.image``、目标色取自 ``target.item_ref``；无图则对应色为
    ``None`` → ``has_col=False``（与线上「无查询图则无查询色」的行为一致）。
    """
    query = pair.get("query", {})
    target = pair.get("target", {})

    q_img = cache.image(query["image"]) if query.get("image") else None
    q_text = cache.text(query["text"]) if query.get("text") else None
    q_color = cache.color(query["image"]) if query.get("image") else None
    t_img = cache.image(target["item_ref"]) if target.get("item_ref") else None
    t_text = cache.text(target["text"]) if target.get("text") else None
    t_color = cache.color(target["item_ref"]) if target.get("item_ref") else None

    return clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
        color1=q_color, color2=t_color,
        **_weights_kwargs(weights),
    )


def score_pair_vs_target(
    cache: _EncoderCache,
    query: Dict[str, Any],
    target: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """对一个查询与任意候选目标打分（Recall@K 排序用）。

    颜色通道同 :func:`score_pair`：必须传入，否则 ``W_COLOR`` 惰性、候选排序与线上不符。
    """
    q_img = cache.image(query["image"]) if query.get("image") else None
    q_text = cache.text(query["text"]) if query.get("text") else None
    q_color = cache.color(query["image"]) if query.get("image") else None
    t_img = cache.image(target["item_ref"]) if target.get("item_ref") else None
    t_text = cache.text(target["text"]) if target.get("text") else None
    t_color = cache.color(target["item_ref"]) if target.get("item_ref") else None
    return clip_service.compute_weighted_similarity(
        q_img, q_text, t_img, t_text,
        color1=q_color, color2=t_color,
        **_weights_kwargs(weights),
    )


def _target_key(target: Dict[str, Any]) -> str:
    return target.get("item_ref") or target.get("text") or "?"


def _candidate_key(target: Dict[str, Any]) -> Any:
    """候选集的**身份**键：优先 ``item_id``。

    为什么不能直接用 :func:`_target_key` 去重（原实现即如此，**是 bug**）
    -----------------------------------------------------------------
    评测集里**同一条物品**在不同 pair 中的表达方式不同：
      - P01~P04 给的是 ``target.item_ref``（图片）；
      - P21~P24 给的是 ``target.text``（且 ``item_ref=null``）。
    按 ``item_ref or text`` 去重会把**同一条物品拆成两个候选**
    （实测 10 个候选 = 6 条物品 + 4 条幻影重复），而且两者可用通道不同
    （一个有图、一个只有文字）→ 打分不同 → 「正确目标」被自己的幻影副本挤出
    Top-3 → Recall@1/@3 被严重低估（实测 0.0 vs 真实 1.0）。
    """
    key = target.get("item_id")
    return key if key is not None else _target_key(target)


# --------------------------------------------------------------------------- #
# 评估
# --------------------------------------------------------------------------- #
def _candidates(eval_set: Dict[str, Any]) -> List[Dict[str, Any]]:
    """候选目标集合：按**物品身份**（``item_id``）去重，并把同一条物品在不同
    pair 中出现的字段**合并**（只有图的补文字、只有文字的补图），以还原生产里
    「一条真实物品同时带有图片与文字」的形态 —— 这也是 ``/match`` 的真实打分对象。
    """
    merged: Dict[Any, Dict[str, Any]] = {}
    order: List[Any] = []
    for p in eval_set["pairs"]:
        t = p.get("target", {})
        key = _candidate_key(t)
        cur = merged.get(key)
        if cur is None:
            merged[key] = dict(t)
            order.append(key)
            continue
        for field in ("item_ref", "text", "item_id"):
            if not cur.get(field) and t.get(field):
                cur[field] = t[field]
    return [merged[k] for k in order]


def _recall_ranks(
    eval_set: Dict[str, Any],
    cache: _EncoderCache,
    candidates: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]],
) -> List[int]:
    """每个正样本查询，其目标在候选中的排名（1-based）。"""
    ranks: List[int] = []
    for p in eval_set["pairs"]:
        if int(p.get("label", 0)) != 1:
            continue
        if is_degenerate(p):
            continue  # 同图自比退化正样本不计入 Recall（否则必 rank=1，虚高）
        query = p.get("query", {})
        own = _candidate_key(p.get("target", {}))
        scored = sorted(
            (
                (score_pair_vs_target(cache, query, c, weights), _candidate_key(c))
                for c in candidates
            ),
            key=lambda x: x[0],
            reverse=True,
        )
        rank = len(scored) + 1
        for i, (_, key) in enumerate(scored, start=1):
            if key == own:
                rank = i
                break
        ranks.append(rank)
    return ranks


def recall_at_k(ranks: Iterable[int], k: int) -> float:
    """Recall@K = 命中 rank ≤ K 的正样本比例。"""
    ranks = list(ranks)
    if not ranks:
        return 0.0
    return sum(1 for r in ranks if r <= k) / len(ranks)


def _precision_recall_at(threshold: float, scored: List[Tuple[float, int]]) -> Tuple[float, float]:
    tp = sum(1 for s, l in scored if l == 1 and s >= threshold)
    fp = sum(1 for s, l in scored if l == 0 and s >= threshold)
    pos = sum(1 for _, l in scored if l == 1)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / pos if pos > 0 else 0.0
    return precision, recall


def precision_recall_curve(scored: List[Tuple[float, int]]) -> List[Dict[str, float]]:
    """在候选阈值上计算 PR 曲线（去重、升序）。"""
    thresholds = sorted({round(s, 6) for s, _ in scored})
    if not thresholds:
        return []
    lo = min(thresholds) - 1e-6
    hi = max(thresholds) + 1e-6
    grid = [lo] + thresholds + [hi]
    curve = []
    for t in grid:
        precision, recall = _precision_recall_at(t, scored)
        curve.append({"threshold": round(t, 6), "precision": round(precision, 4), "recall": round(recall, 4)})
    return curve


def suggest_thresholds(
    scored: List[Tuple[float, int]],
    auto_p: float = 0.90,
    email_p: float = 0.98,
    manual_r: float = 0.90,
) -> Dict[str, Optional[float]]:
    """按 Q1 口径给出三个建议阈值（无法满足的返回 ``None``）。"""
    thresholds = sorted({round(s, 6) for s, _ in scored})
    if not thresholds:
        return {"auto": None, "email": None, "manual": None}
    lo = min(thresholds) - 1e-6
    hi = max(thresholds) + 1e-6
    grid = [lo] + thresholds + [hi]

    def lowest_with_precision(p_min: float) -> Optional[float]:
        for t in grid:  # 升序，取「最低分位」
            precision, _ = _precision_recall_at(t, scored)
            if precision >= p_min:
                return round(t, 6)
        return None

    def highest_with_recall(r_min: float) -> Optional[float]:
        for t in reversed(grid):  # 降序，取「最高分位」
            _, recall = _precision_recall_at(t, scored)
            if recall >= r_min:
                return round(t, 6)
        return None

    return {
        "auto": lowest_with_precision(auto_p),
        "email": lowest_with_precision(email_p),
        "manual": highest_with_recall(manual_r),
    }


def evaluate(
    eval_set: Dict[str, Any],
    encoder: Any,
    *,
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """在评测集上评估：全对打分 → PR 曲线 → 建议阈值 + Recall@1/3/5/10。

    Args:
        eval_set: :func:`load_eval_set` 的返回值。
        encoder: 编码器（生产传 ``clip_service``；测试传 ``FakeEncoder``）。
        weights: 可选权重覆盖（None → 用 config 现值）。

    Returns:
        含 ``scored`` / ``curve`` / ``thresholds`` / ``recall`` / ``recall_ranks`` 的字典。
    """
    cache = _EncoderCache(encoder)
    scored: List[Tuple[float, int]] = []
    degenerate: List[Tuple[str, float]] = []
    skipped = 0
    for p in eval_set["pairs"]:
        try:
            s = score_pair(cache, p, weights)
        except Exception as e:
            skipped += 1
            logger.warning(f"跳过评测对 {p.get('id')}: {e}")
            continue
        if is_degenerate(p):
            degenerate.append((str(p.get("id")), s))  # 仅记录，不计入标定
            continue
        scored.append((s, int(p.get("label", 0))))

    candidates = _candidates(eval_set)
    ranks = _recall_ranks(eval_set, cache, candidates, weights)

    effective_positive = sum(1 for _, label in scored if label == 1)
    effective_negative = sum(1 for _, label in scored if label == 0)

    return {
        "scored": scored,
        "skipped": skipped,
        "degenerate": degenerate,
        "effective_positive": effective_positive,
        "effective_negative": effective_negative,
        "curve": precision_recall_curve(scored),
        "thresholds": suggest_thresholds(scored),
        "recall": {f"recall@{k}": round(recall_at_k(ranks, k), 4) for k in (1, 3, 5, 10)},
        "recall_ranks": ranks,
    }


# --------------------------------------------------------------------------- #
# 权重网格
# --------------------------------------------------------------------------- #
def iter_weight_grid(step: float = 0.05) -> Iterable[Dict[str, float]]:
    """枚举 ``{img_img, cross, text_text, color}`` 和为 1.0、步长 ``step`` 的粗网格。"""
    n = round(1.0 / step)
    for a in range(n + 1):
        for b in range(n + 1 - a):
            for c in range(n + 1 - a - b):
                d = n - a - b - c
                yield {
                    "img_img": round(a * step, 4),
                    "cross": round(b * step, 4),
                    "text_text": round(c * step, 4),
                    "color": round(d * step, 4),
                }


def summarize_grid(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对**全部合格组合**（``auto`` 可达，即 Precision≥0.90 有解）做分布摘要。

    为什么需要它（v3.5.0 真实权重实测第三处暴露的方法论缺陷）
    -----------------------------------------------------------
    ``grid_search`` 的目标是「在 Precision≥0.90 的最低阈值处最大化 Recall@3」。
    但真实评测集上，**大量权重组合并列 Recall@3 = 1.0**（实测 103 个合格组合里 102 个
    并列）。此时 Top-N 的**顺序纯属并列类的任意代表**（Python 稳定排序 → 实际等于
    网格枚举顺序），把它当成「最优权重」会得出**不可复现的伪结论** —— 我们此前正是
    被它误导，把惰性的 ``W_COLOR`` 读成了「0.7~0.9 最优」。

    有信息量的不是单个 Top-1，而是**合格集合的结构**：各权重维度允许取值、以及
    ``W_COLOR`` 在「满分召回」子集中的取值直方图（单调递减即说明该维度越小越好）。

    Args:
        results: ``grid_search`` 收集的**全部**合格组合（每个含 ``weights`` / ``recall@K``）。

    Returns:
        含 ``n_qualified`` / ``n_full_recall`` / 各维度取值集合 / 颜色直方图的摘要字典。
    """
    full = [r for r in results if r.get("recall@3") == 1.0]
    color_hist: Dict[float, int] = {}
    for r in full:
        c = float(r["weights"]["color"])
        color_hist[c] = color_hist.get(c, 0) + 1
    per_dim = {
        name: sorted({float(r["weights"][name]) for r in results}) for name in _WEIGHT_KEYS
    }
    return {
        "n_qualified": len(results),
        "n_full_recall": len(full),
        "per_dim_values": per_dim,
        "color_hist_full_recall": dict(sorted(color_hist.items())),
        "recall1_values": sorted({float(r["recall@1"]) for r in results}),
        "max_color_full_recall": (max(color_hist) if color_hist else None),
    }


def grid_search(
    eval_set: Dict[str, Any],
    encoder: Any,
    *,
    step: float = 0.05,
    top_n: int = 5,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """权重网格搜索：在 Precision ≥ 0.90 的最低阈值处最大化 Recall@3。

    Returns:
        ``(top_n 列表, 合格集合摘要)``。``top_n`` 内的**顺序在并列时无意义**，
        请连同 :func:`summarize_grid` 的摘要一起解读（见其 docstring）。
    """
    results: List[Dict[str, Any]] = []
    cache = _EncoderCache(encoder)
    candidates = _candidates(eval_set)
    for weights in iter_weight_grid(step):
        scored: List[Tuple[float, int]] = []
        for p in eval_set["pairs"]:
            if is_degenerate(p):
                continue  # 同图自比退化正例不计入标定
            try:
                scored.append((score_pair(cache, p, weights), int(p.get("label", 0))))
            except Exception:
                continue
        thresholds = suggest_thresholds(scored)
        if thresholds["auto"] is None:
            continue  # 该权重组合无法达到 Precision ≥ 0.90，跳过
        ranks = _recall_ranks(eval_set, cache, candidates, weights)
        results.append(
            {
                "weights": weights,
                "auto_threshold": thresholds["auto"],
                "recall@3": round(recall_at_k(ranks, 3), 4),
                "recall@1": round(recall_at_k(ranks, 1), 4),
                "recall@5": round(recall_at_k(ranks, 5), 4),
                "recall@10": round(recall_at_k(ranks, 10), 4),
            }
        )
    summary = summarize_grid(results)
    results.sort(key=lambda r: (r["recall@3"], r["recall@1"]), reverse=True)
    return results[:top_n], summary


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def _recall3_blocking(result: Dict[str, Any]) -> bool:
    """是否触发阻塞性发现：任一阈值下 Recall@3 < 0.90。"""
    return result["recall"]["recall@3"] < 0.90


def write_markdown_report(
    out_path: str,
    result: Dict[str, Any],
    *,
    compare: Optional[Dict[str, Any]] = None,
    grid_top: Optional[List[Dict[str, Any]]] = None,
    grid_summary: Optional[Dict[str, Any]] = None,
    fake_encoder: bool = False,
) -> None:
    """把标定结果写为 Markdown 报告。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    lines: List[str] = []
    lines.append("# 阈值标定报告（v3.5.0）\n")
    if fake_encoder:
        lines.append(
            "\n> # ⚠️⚠️ 本报告由 `--fake-encoder` 生成，数字不可用于任何决策 ⚠️⚠️\n"
            "> **`--fake-encoder` 使用确定性假向量，输出的阈值/Recall 全是噪声，"
            "严禁回填 `.env`、严禁作为标定结论引用。**"
            "真实标定必须在**真实 cn_clip 权重 + 真实评测图片**上重跑。\n"
        )
    lines.append(f"> 模型后端：`{settings.CLIP_BACKEND}` ｜ 生成脚本：`scripts/calibrate_thresholds.py`\n")
    lines.append(
        f"> 编码器：`{'--fake-encoder（噪声，仅供结构校验）' if fake_encoder else 'clip_service（真实模型）'}`\n"
    )
    eff_pos = result.get("effective_positive")
    eff_neg = result.get("effective_negative")
    if eff_pos is not None:
        deg = result.get("degenerate", []) or []
        lines.append(
            f"> 有效标定集：**{eff_pos} 正 / {eff_neg} 负**"
            f"（已剔除 {len(deg)} 对『同图自比』退化正例 → `sim_ii ≡ 1.0`，"
            "仅作通道接线自检；正负不平衡为**有意保守**）。\n"
        )
    lines.append("> ⚠️ 本报告由脚本生成；正式上线前须在**真实评测集 + 真实模型**上重跑并回填 config。\n")

    if _recall3_blocking(result):
        lines.append(
            "\n> 🚨 **阻塞性发现**：当前配置下 `Recall@3 = "
            f"{result['recall']['recall@3']:.4f} < 0.90`。"
            "**不得以牺牲 Recall 换取「看起来更严谨」**；须调整权重/阈值或关闭阶段5 惩罚后重跑。\n"
        )

    lines.append("\n## 1. 建议阈值\n")
    th = result["thresholds"]
    lines.append("| 阈值 | 口径 | 建议值 |")
    lines.append("|------|------|:--:|")
    lines.append(f"| `MATCH_THRESHOLD_AUTO` | Precision ≥ 0.90 最低分位 | {th['auto']} |")
    lines.append(f"| `MATCH_THRESHOLD_EMAIL` | Precision ≥ 0.98 最低分位 | {th['email']} |")
    lines.append(f"| `MATCH_THRESHOLD_MANUAL` | Recall ≥ 0.90 最高分位 | {th['manual']} |")

    lines.append("\n## 2. Recall@K\n")
    lines.append("| 指标 | 值 |")
    lines.append("|------|:--:|")
    for k in (1, 3, 5, 10):
        lines.append(f"| Recall@{k} | {result['recall'][f'recall@{k}']} |")

    lines.append("\n## 3. Precision-Recall 曲线\n")
    lines.append("| threshold | precision | recall |")
    lines.append("|:--:|:--:|:--:|")
    for row in result["curve"]:
        lines.append(f"| {row['threshold']} | {row['precision']} | {row['recall']} |")

    if compare is not None:
        lines.append("\n## 4. 阶段5 惩罚对照（with-penalty vs without-penalty）\n")
        lines.append("| 配置 | Recall@1 | Recall@3 | Recall@5 | Recall@10 |")
        lines.append("|------|:--:|:--:|:--:|:--:|")
        for name, res in compare.items():
            r = res["recall"]
            lines.append(
                f"| {name} | {r['recall@1']} | {r['recall@3']} | {r['recall@5']} | {r['recall@10']} |"
            )
        lines.append(
            "\n> 断言：`Recall@3(with_penalty=True) >= Recall@3(with_penalty=False)`；"
            "若下降则置 `CROSS_PENALTY_ENABLED=false`。\n"
        )

    if grid_top:
        lines.append("\n## 5. 权重网格（目标：Precision≥0.90 处最大化 Recall@3）\n")
        if grid_summary:
            n_q = grid_summary.get("n_qualified", 0)
            n_f = grid_summary.get("n_full_recall", 0)
            lines.append(
                f"> **并列退化提示**：合格组合（`Precision≥0.90` 有解）共 **{n_q}** 个，"
                f"其中 **{n_f}** 个并列 `Recall@3 = 1.0`。"
                "**下表顺序只是并列类的任意代表（= 网格枚举顺序），不是「最优权重排名」**；"
                "请以下方的**合格集合分布**为准。\n"
            )
        lines.append("### 5.1 Top-N（并列代表，顺序无意义）\n")
        lines.append("| # | W_IMG_IMG | W_CROSS | W_TEXT_TEXT | W_COLOR | auto 阈值 | Recall@1 | Recall@3 | Recall@5 | Recall@10 |")
        lines.append("|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|")
        for i, g in enumerate(grid_top, start=1):
            w = g["weights"]
            lines.append(
                f"| {i} | {w['img_img']} | {w['cross']} | {w['text_text']} | {w['color']} | "
                f"{g['auto_threshold']} | {g['recall@1']} | {g['recall@3']} | {g['recall@5']} | {g['recall@10']} |"
            )
        if grid_summary:
            lines.append("\n### 5.2 合格集合分布（**有信息量**）\n")
            hist = grid_summary.get("color_hist_full_recall", {})
            lines.append(
                "- `W_COLOR` 在「满分召回」子集中的取值分布（单调递减 ⇒ 该维度越小越好）："
                f"`{hist}`"
            )
            lines.append(
                f"- 合格集合内 `W_COLOR` 最大取值：`{grid_summary.get('max_color_full_recall')}`"
            )
            per_dim = grid_summary.get("per_dim_values", {})
            for name, vals in per_dim.items():
                lines.append(f"- 合格集合内 `{name}` 允许取值：`{vals}`")
            lines.append(
                f"- 合格集合内 `Recall@1` 取值：`{grid_summary.get('recall1_values')}`\n"
            )

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def write_csv(out_path: str, curve: List[Dict[str, float]]) -> None:
    """写出 PR 曲线 CSV。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["threshold", "precision", "recall"])
        writer.writeheader()
        for row in curve:
            writer.writerow(row)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="阈值标定 + PR 曲线 + Recall@K + 权重网格（v3.5.0）")
    parser.add_argument("--eval-set", default=DEFAULT_EVAL_SET, help="评测集 JSON 路径")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Markdown 报告输出路径")
    parser.add_argument("--csv", default=None, help="PR 曲线 CSV 输出路径（默认与 --out 同名 .csv）")
    parser.add_argument("--grid", action="store_true", help="执行权重粗网格搜索（步长 0.05）")
    parser.add_argument("--grid-step", type=float, default=0.05, help="网格步长（默认 0.05）")
    parser.add_argument("--limit", type=int, default=None, help="只评估前 N 对（冒烟用）")
    parser.add_argument("--stats", action="store_true",
                        help="仅打印评测集结构统计（不加载模型、不评估），供 CI/人工校验")
    parser.add_argument("--degenerate-check", action="store_true",
                        help="仅做『同图自比』退化对的 sim_ii 通道接线自检（默认假编码器），不评估")
    parser.add_argument("--fake-encoder", action="store_true",
                        help="用确定性假编码器冒烟（不加载真实模型，供 CI/结构校验）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--with-penalty", dest="with_penalty", action="store_true", default=True,
                       help="启用阶段5 惩罚（默认）")
    group.add_argument("--without-penalty", dest="with_penalty", action="store_false",
                       help="关闭阶段5 惩罚（对照）")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    eval_set = load_eval_set(args.eval_set)

    # 结构统计（始终打印；--stats 时打印后即退出，不加载模型）
    stats = summarize_eval_set(eval_set)
    print_eval_stats(stats)
    if args.stats:
        return 0

    if args.degenerate_check:
        # 仅做 sim_ii 通道接线自检（默认假编码器；真实权重不可得时不阻塞）
        print_degenerate_check(verify_degenerate_self(eval_set, _FakeEncoder()))
        return 0

    full_eval_set = eval_set  # 退化自检始终覆盖全量（不受 --limit 影响）

    if args.limit:
        eval_set = dict(eval_set)
        eval_set["pairs"] = eval_set["pairs"][: args.limit]

    csv_path = args.csv or (os.path.splitext(args.out)[0] + ".csv")

    # 真实路径必须经适配器：clip_service 暴露 get_*_feature，而本脚本内部用 encode_*
    encoder = _FakeEncoder() if args.fake_encoder else _ServiceEncoderAdapter(clip_service)

    # 主评估 + with/without-penalty 对照
    with penalty_enabled(args.with_penalty):
        result = evaluate(eval_set, encoder)

    # sim_ii 通道接线自检（同图自比退化对；仅打印，不计入标定）
    print_degenerate_check(verify_degenerate_self(full_eval_set, encoder))

    compare = None
    if args.with_penalty:
        with penalty_enabled(True):
            r_on = evaluate(eval_set, encoder)
        with penalty_enabled(False):
            r_off = evaluate(eval_set, encoder)
        compare = {"with_penalty=True": r_on, "with_penalty=False": r_off}
        if r_on["recall"]["recall@3"] < r_off["recall"]["recall@3"]:
            logger.warning(
                "阶段5 惩罚导致 Recall@3 下降（%.4f → %.4f），建议 CROSS_PENALTY_ENABLED=false",
                r_off["recall"]["recall@3"],
                r_on["recall"]["recall@3"],
            )

    grid_top = None
    grid_summary = None
    if args.grid:
        print("正在执行权重网格搜索（步长 %.2f）..." % args.grid_step)
        grid_top, grid_summary = grid_search(eval_set, encoder, step=args.grid_step)
        print(f"网格搜索完成，Top-{len(grid_top)} 组合（顺序在并列时无意义）：")
        for i, g in enumerate(grid_top, start=1):
            print(f"  #{i} weights={g['weights']} auto={g['auto_threshold']} Recall@3={g['recall@3']}")
        if grid_summary:
            print(
                f"  合格组合 {grid_summary['n_qualified']} 个，"
                f"其中 {grid_summary['n_full_recall']} 个并列 Recall@3=1.0"
            )
            print(f"  W_COLOR 在满分召回子集的分布: {grid_summary['color_hist_full_recall']}")

    write_markdown_report(args.out, result, compare=compare, grid_top=grid_top,
                          grid_summary=grid_summary, fake_encoder=args.fake_encoder)
    write_csv(csv_path, result["curve"])

    if args.fake_encoder:
        print("#" * 56)
        print("# ⚠️  --fake-encoder：数字为噪声，不可用于任何决策/回填 .env  #")
        print("#" * 56)

    print("=" * 56)
    print("标定完成")
    print(
        f"  有效标定对: {len(result['scored'])}"
        f"（正 {result.get('effective_positive')} / 负 {result.get('effective_negative')}；"
        f"剔除退化 {len(result.get('degenerate', []))}；跳过 {result['skipped']}）"
    )
    print(f"  建议阈值: {result['thresholds']}")
    print(f"  Recall: {result['recall']}")
    if _recall3_blocking(result):
        print("  🚨 阻塞性发现：Recall@3 < 0.90")
    print(f"  报告: {args.out}")
    print(f"  CSV : {csv_path}")
    print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
