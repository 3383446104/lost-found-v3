# app/services/fusion.py
"""加权融合相似度算法（Weighted-Fusion Similarity, WFS）——**唯一实现点**。

本模块把打分拆成两个**纯函数**，与模型、数据库、配置完全解耦，便于在论文中
直接给出算法定义、复杂度与可复现实验：

============  ==========================================================
``channels_from_sims``  一级：**通道级加权**（向量空间）—— 把多路余弦
                        归并成三个可比通道 ``text / img / cross``
``fuse``                二级：**证据级加权**（证据空间）—— 通道加权 +
                        类别/地点先验 + 字面命中加分，输出判定分
============  ==========================================================

符号（与论文第 4 章一致）
------------------------
=================  ====================================================
:math:`q, x`       查询与候选物品
:math:`s^{tt}`     ``q_text · x_text``（全文向量余弦）
:math:`s^{t\\tau}` ``q_text · x_title``（标题向量余弦）
:math:`s^{ii}`     ``q_img · x_img``
:math:`s^{t2i}`    ``q_text · x_img``
:math:`s^{i2t}`    ``q_img · x_text``
:math:`\\ell`      字面命中强度 ∈ {0, .4, .8, 1}（见 ``literal_features``）
:math:`\\kappa`    字面加分折扣（同义命中 0.3，确定性字面 1.0）
=================  ====================================================

一级（式 4-1 ~ 4-3）::

    s^{text}  = max(s^{tτ}, s^{tt})           若 κ 允许标题通道
              = s^{tt}                        否则（未字面命中，标题不可信）
    s^{img}   = s^{ii}
    s^{cross} = ½·[φ(s^{t2i}) + φ(s^{i2t})],  φ(v) = (v − LO)/(HI − LO)   ← 不截断

二级（式 4-4）::

    Score = clamp( Σ_{c∈C} w_c·s^c / Σ_{c∈C} w_c
                   + δ_cat·[同类] + δ_loc·[同地点]
                   + γ·ℓ·κ , 0, 1 )

    其中 C = {c | s^c 可计算}，w_text = w_img = 0.80、w_cross = 0.20，
    δ_cat = +0.03/−0.05、δ_loc = +0.02/−0.03、γ = 0.15。

设计要点（论文需展开论证的三点）
--------------------------------
1. **缺通道动态归一化**：分母只累加可用通道，因此纯文本 / 纯图片 / 图文混合
   三种检索模式**零分支自动成形**（0.80/0.20、0.80/0.20、0.44/0.44/0.11）。
2. **跨模态仿射不截断**：φ 保留 LO 以下的序关系。若截断到 [0,1]，短查询的
   跨模态余弦（实测 0.107~0.191 < LO=0.194）会一律归零，通道形同不存在。
3. **标题通道的信任门控**：标题余弦在短标题上各向异性严重（「一个手机」对
   查询「房卡」达 0.7783），故仅在字面命中时启用；否则退回全文向量。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

#: 通道名（顺序即论文表格中的顺序）
CHANNELS = ("text", "img", "cross")


@dataclass(frozen=True)
class FusionWeights:
    """融合参数。全部有明确来源（设计取值 / 标定值），见论文参数表。"""

    w_text: float = 0.80
    w_img: float = 0.80
    w_cross: float = 0.20
    literal_bonus: float = 0.15
    cat_same: float = 0.03
    cat_diff: float = -0.05
    loc_same: float = 0.02
    loc_diff: float = -0.03
    #: 标题通道信任门槛："literal" 仅字面命中时启用；"always" 常开（消融用）
    title_gate: str = "literal"
    #: 字面命中放行门控所需的最低强度
    gate_level: float = 0.8

    def as_dict(self) -> dict:
        return {
            "w_text": self.w_text, "w_img": self.w_img, "w_cross": self.w_cross,
            "literal_bonus": self.literal_bonus,
            "cat_same": self.cat_same, "cat_diff": self.cat_diff,
            "loc_same": self.loc_same, "loc_diff": self.loc_diff,
            "title_gate": self.title_gate,
        }


DEFAULT_WEIGHTS = FusionWeights()


@dataclass(frozen=True)
class Channels:
    """一级输出：三个**可比**通道 + 字面证据 + 先验标记。``None`` 表示不可用。"""

    text: Optional[float]
    img: Optional[float]
    cross: Optional[float]
    literal: float = 0.0
    literal_scale: float = 1.0
    cat_same: Optional[bool] = None
    loc_same: Optional[bool] = None

    def available(self) -> tuple:
        return tuple(n for n in CHANNELS if getattr(self, n) is not None)


def affine_cross(value: Optional[float], lo: float, hi: float) -> Optional[float]:
    """跨模态尺度对齐 φ(v) = (v − lo)/(hi − lo)，**不截断**。

    截断会把 LO 以下的取值压成 0，让「两字查询」的跨模态通道整体失效；
    不截断则保留序关系（0.1908 → −0.031，0.142 → −0.50），差异仍可被利用。
    """
    if value is None:
        return None
    if hi <= lo:
        return value
    return (value - lo) / (hi - lo)


def channels_from_sims(
    *,
    sim_tt: Optional[float],
    sim_title: Optional[float],
    sim_ii: Optional[float] = None,
    sim_t2i: Optional[float] = None,
    sim_i2t: Optional[float] = None,
    literal: float = 0.0,
    literal_scale: float = 1.0,
    cat1: str = "",
    cat2: str = "",
    loc1: str = "",
    loc2: str = "",
    lo: float = 0.194,
    hi: float = 0.298,
    weights: FusionWeights = DEFAULT_WEIGHTS,
) -> Channels:
    """一级：把多路余弦归并成 ``text / img / cross`` 三个可比通道（式 4-1 ~ 4-3）。"""
    # --- text：标题 ∨ 全文取更优者，并受字面门控约束 ---
    text: Optional[float] = None
    if sim_title is not None or sim_tt is not None:
        gate_open = (
            weights.title_gate != "literal"
            or sim_title is None
            or float(literal or 0.0) >= weights.gate_level
        )
        if gate_open:
            vals = [v for v in (sim_title, sim_tt) if v is not None]
            text = max(vals) if vals else None
        else:
            # 未字面命中：标题余弦视为噪声，退回全文；连全文都没有才兜底用标题
            text = sim_tt if sim_tt is not None else sim_title

    # --- cross：双向平均，逐项仿射（不截断）---
    cross_vals = [affine_cross(v, lo, hi) for v in (sim_t2i, sim_i2t)]
    cross_vals = [v for v in cross_vals if v is not None]
    cross = sum(cross_vals) / len(cross_vals) if cross_vals else None

    return Channels(
        text=text,
        img=sim_ii,
        cross=cross,
        literal=float(literal or 0.0),
        literal_scale=float(literal_scale),
        cat_same=(cat1 == cat2) if (cat1 and cat2) else None,
        loc_same=(loc1 == loc2) if (loc1 and loc2) else None,
    )


def base_score(ch: Channels, weights: FusionWeights = DEFAULT_WEIGHTS) -> float:
    """一级加权平均（式 4-4 第一项）：分母只累加**可用**通道。"""
    pairs = (
        (weights.w_text, ch.text),
        (weights.w_img, ch.img),
        (weights.w_cross, ch.cross),
    )
    usable = [(w, s) for w, s in pairs if s is not None and w > 0]
    if not usable:
        return 0.0
    return sum(w * s for w, s in usable) / sum(w for w, _ in usable)


def fuse(ch: Channels, weights: FusionWeights = DEFAULT_WEIGHTS) -> float:
    """二级：证据级加权，输出判定分 ∈ [0, 1]（式 4-4）。"""
    score = base_score(ch, weights)

    if ch.cat_same is not None:
        score += weights.cat_same if ch.cat_same else weights.cat_diff
    if ch.loc_same is not None:
        score += weights.loc_same if ch.loc_same else weights.loc_diff

    lit = max(0.0, min(1.0, ch.literal))
    score += weights.literal_bonus * lit * max(0.0, min(1.0, ch.literal_scale))

    return round(max(0.0, min(1.0, score)), 6)


def fuse_sims(weights: FusionWeights = DEFAULT_WEIGHTS, **sims) -> float:
    """便利函数：``fuse(channels_from_sims(**sims), weights)``。"""
    return fuse(channels_from_sims(weights=weights, **sims), weights)


def with_overrides(weights: FusionWeights, **kw) -> FusionWeights:
    """返回替换了若干参数的新权重对象（不可变，避免全局状态被就地改写）。"""
    return replace(weights, **{k: v for k, v in kw.items() if k in weights.as_dict()})
