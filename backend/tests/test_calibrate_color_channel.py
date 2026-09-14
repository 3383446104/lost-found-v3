"""标定脚本「颜色通道」契约回归测试。

背景（v3.5.0 真实权重下暴露的第二处缺陷）
------------------------------------------
``calibrate_thresholds.score_pair`` / ``score_pair_vs_target`` 原先只传
``(q_img, q_text, t_img, t_text)``，**不传** ``color1``/``color2``；而线上两个真实
调用点（``services/match_service.py:104``、``api/items.py:614``）都传。

后果链：
  1. ``compute_weighted_similarity`` 内 ``has_col = color1 is not None and color2 is not None``
     **恒为 False**；
  2. 颜色通道 ``sim_col=None`` → 被外层「缺维度动态归一化」从分母剔除；
  3. ``W_COLOR`` 因此**数学上完全惰性**（改它以任何值，得分都不变）；
  4. 权重网格里那列 ``W_COLOR 0.7~0.9`` 是**假象**（网格实际选中的是 ``W_CROSS=0``）。

本文件锁死两点：
  A. **服务层语义**：不传颜色向量时颜色通道被剔除（惰性）；传入后才生效（活性）。
  B. **标定层契约**：``score_pair`` 必须把颜色直方图传下去 —— 否则 ``W_COLOR`` 惰性。

又一个「桩路径掩盖真实路径」的实例：``--fake-encoder`` 冒烟从不断言颜色是否生效，
所以这个缺陷在假编码器下一路绿灯。

作者：team-lead（齐活林）—— 修复者自留守卫。
"""
import os
import sys

import numpy as np

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from calibrate_thresholds import (  # noqa: E402
    _EncoderCache,
    score_pair,
    score_pair_vs_target,
)


# --------------------------------------------------------------------------- #
# 测试用编码器：图像通道恒同（sim_ii=1.0），颜色通道按路径正交（sim_col=0）
# --------------------------------------------------------------------------- #
class _ColorEncoder:
    name = "color-fake"
    model_name = "color-fake"

    def encode_image(self, path):
        return np.array([1.0, 0.0], dtype=np.float32)

    def encode_text(self, text):
        return np.array([1.0, 0.0], dtype=np.float32)

    def encode_color(self, path):
        # 查询图（含 "q_"）→ [1,0]；目标图 → [0,1] → 余弦 = 0
        if "q_" in path:
            return np.array([1.0, 0.0], dtype=np.float32)
        return np.array([0.0, 1.0], dtype=np.float32)


def _pair():
    return {
        "id": "T1",
        "label": 1,
        "query": {"image": "uploads/q_img.jpg", "text": None},
        "target": {"item_id": 1, "item_ref": "uploads/t_img.jpg", "text": None},
    }


# 仅 img-img 与 color 两个通道可用：前者 sim=1.0，后者 sim=0.0
_W_ONLY_IMG = {"img_img": 1.0, "cross": 0.0, "text_text": 0.0, "color": 0.0}
_W_IMG_AND_COLOR = {"img_img": 0.5, "cross": 0.0, "text_text": 0.0, "color": 0.5}


# --------------------------------------------------------------------------- #
# A. 服务层语义（机制注记）
# --------------------------------------------------------------------------- #
def test_service_excludes_color_channel_without_vectors():
    """机制：不传 color 向量时，``color_weight`` 改任何值都不影响得分（=缺陷根因）。

    取 ``sim_ii=1.0``（非 0），使断言非平凡 —— 若颜色通道误被计入，得分会随
    ``color_weight`` 变化。
    """
    from app.clip_service import clip_service

    q = np.array([1.0, 0.0], dtype=np.float32)
    t = np.array([1.0, 0.0], dtype=np.float32)  # sim_ii = 1.0
    base = dict(img_weight=0.5, cross_weight=0.0, text_weight=0.0)
    s_zero = clip_service.compute_weighted_similarity(q, None, t, None, color_weight=0.0, **base)
    s_max = clip_service.compute_weighted_similarity(q, None, t, None, color_weight=0.9, **base)
    assert s_zero == s_max == 1.0, (
        "未传颜色向量时 color_weight 影响了得分 —— 与 clip_service 的"
        f"『缺维度动态归一化』语义不符（zero={s_zero}, max={s_max}）"
    )


def test_service_color_channel_live_when_vectors_passed():
    """对照：传入颜色向量后，``color_weight`` 必须真正生效（通道被接通）。"""
    from app.clip_service import clip_service

    q = np.array([1.0, 0.0], dtype=np.float32)
    t = np.array([1.0, 0.0], dtype=np.float32)     # sim_ii = 1.0
    cq = np.array([1.0, 0.0], dtype=np.float32)
    ct = np.array([0.0, 1.0], dtype=np.float32)    # sim_col = 0
    base = dict(img_weight=0.5, cross_weight=0.0, text_weight=0.0)
    s_zero = clip_service.compute_weighted_similarity(
        q, None, t, None, color1=cq, color2=ct, color_weight=0.0, **base
    )
    s_max = clip_service.compute_weighted_similarity(
        q, None, t, None, color1=cq, color2=ct, color_weight=0.9, **base
    )
    assert s_zero == 1.0
    assert abs(s_max - (0.5 / 1.4)) < 1e-6, f"颜色加权得分异常: {s_max}"
    assert s_zero != s_max, "传入颜色向量后 color_weight 仍无效 —— 颜色通道未接通"


# --------------------------------------------------------------------------- #
# B. 标定层契约（本次修复的直接守卫）
# --------------------------------------------------------------------------- #
def test_score_pair_passes_color_channel():
    """``score_pair`` 必须把颜色直方图传给打分函数；否则 W_COLOR 惰性（原缺陷回归）。"""
    cache = _EncoderCache(_ColorEncoder())
    s_only_img = score_pair(cache, _pair(), _W_ONLY_IMG)
    s_img_color = score_pair(cache, _pair(), _W_IMG_AND_COLOR)
    assert s_only_img != s_img_color, (
        "score_pair 的得分对 W_COLOR 不敏感 → 颜色直方图未传入 "
        "compute_weighted_similarity（W_COLOR 惰性，网格搜索失真）"
    )
    # 与手工口径一致：(0.5*1.0 + 0.5*0.0)/1.0 = 0.5
    assert abs(s_img_color - 0.5) < 1e-6, f"颜色加权得分异常: {s_img_color}"


def test_score_pair_vs_target_passes_color_channel():
    """``score_pair_vs_target``（Recall@K 排序用）同样必须传颜色。"""
    cache = _EncoderCache(_ColorEncoder())
    q = {"image": "uploads/q_img.jpg", "text": None}
    t = {"item_id": 1, "item_ref": "uploads/t_img.jpg", "text": None}
    s_only_img = score_pair_vs_target(cache, q, t, _W_ONLY_IMG)
    s_img_color = score_pair_vs_target(cache, q, t, _W_IMG_AND_COLOR)
    assert s_only_img != s_img_color, (
        "score_pair_vs_target 对 W_COLOR 不敏感 → 候选排序未使用颜色（Recall@K 失真）"
    )
    assert abs(s_img_color - 0.5) < 1e-6, f"颜色加权得分异常: {s_img_color}"


def test_score_pair_color_none_for_text_only_query():
    """纯文查询（无图）→ 查询无颜色 → ``has_col=False``，与线上行为一致（不炸）。"""
    cache = _EncoderCache(_ColorEncoder())
    pair = {
        "id": "T2",
        "label": 1,
        "query": {"image": None, "text": "白色耳机"},
        "target": {"item_id": 1, "item_ref": None, "text": "蓝牙耳机"},
    }
    # 仅 text_text 可用；color 权重再大也只走 sim_tt
    w = {"img_img": 0.0, "cross": 0.0, "text_text": 0.5, "color": 0.5}
    assert score_pair(cache, pair, w) == 1.0  # sim_tt = 1.0（两文本同向量）
