# app/clip_service.py
"""CLIP 服务外观（Facade）。

v3.5.0 起 ``CLIPService`` 不再直接持有具体模型，而是作为**兼容壳**委托给
:class:`~app.clip_backend.ClipBackend`（``open_clip`` / ``cn_clip`` 二选一）。

**公开方法名与签名冻结**（工程铁律 3）：``_initialize`` / ``get_image_feature`` /
``get_text_feature`` / ``compute_weighted_similarity``——``tests/conftest.py`` 依赖
monkeypatch 这些方法名来阻断真实模型加载，**改名即测试全红**。
``clip_service`` 仍是模块级单例名。
"""
from typing import Optional

import numpy as np

from .clip_backend import ClipBackend, get_backend
from .config import settings
from .logger import logger


class CLIPService:
    """CLIP 模型服务（单例模式 + 后端委托）。"""

    _instance = None
    _backend: Optional[ClipBackend] = None
    _device = "cpu"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ------------------------------------------------------------------ #
    # 初始化 / 后端
    # ------------------------------------------------------------------ #
    def _initialize(self):
        """延迟加载：首次调用时按 config 选择并持有后端。

        ``conftest`` 会把本方法替换为 no-op，从而阻断真实模型加载；保留方法名不变。
        """
        if self._backend is None:
            self._backend = get_backend(settings)
            self._device = getattr(self._backend, "_device", "cpu")
            logger.info("CLIP 后端已选择: %s（模型 %s）",
                        getattr(self._backend, "name", "?"),
                        getattr(self._backend, "model_name", "?"))

    def get_backend(self) -> ClipBackend:
        """返回当前所选后端实例（懒加载）。"""
        self._initialize()
        return self._backend

    # ------------------------------------------------------------------ #
    # 特征提取（委托后端）
    # ------------------------------------------------------------------ #
    def get_image_feature(self, image_path: str) -> np.ndarray:
        """提取图像特征向量（L2 归一化，维度为当前后端的各自 ``embed_dim``）。"""
        self._initialize()
        return self._backend.encode_image(image_path)

    def get_text_feature(self, text: str) -> np.ndarray:
        """提取文本特征向量（L2 归一化，维度为当前后端的各自 ``embed_dim``）。"""
        self._initialize()
        return self._backend.encode_text(text)

    # ------------------------------------------------------------------ #
    # 打分（跨模态 + 五阶段）
    # ------------------------------------------------------------------ #
    def compute_weighted_similarity(
        self,
        img1: np.ndarray = None,
        text1: np.ndarray = None,
        img2: np.ndarray = None,
        text2: np.ndarray = None,
        cat1: str = "",
        cat2: str = "",
        loc1: str = "",
        loc2: str = "",
        days_old: int = 0,
        img_weight: Optional[float] = None,
        text_weight: Optional[float] = None,
        *,
        cross_weight: Optional[float] = None,
        w_cross_t2i: Optional[float] = None,
        w_cross_i2t: Optional[float] = None,
    ) -> float:
        """五阶段 + **三通道等权** 加权相似度算法（2026-09-16 修订）。

        三通道定义（``q`` = 查询，``t`` = 目标；``·`` = 余弦，向量均已 L2 归一化）：

        ==================  ================================================  =========================
        通道                 表达式                                            可用条件
        ==================  ================================================  =========================
        ``sim_text_text``   ``q_text · t_text``                              ``text1, text2`` 均非空
        ``sim_cross``       ``q_text·t_img`` 与 ``q_img·t_text`` 的加权平均    双向任一可用
        ``sim_img_img``     ``q_img · t_img``                                ``img1, img2`` 均非空
        ==================  ================================================  =========================

        - **三通道各自独立、等权**（``MATCH_W_* = 1.0``）⇒ 打分等价于「可用通道的算术平均」；
          缺通道**动态归一化**（不可用通道从分母剔除，权重和恒为 1）；全缺 → ``0.0``；
        - 阶段1 类别/位置；阶段2 时间衰减；阶段5 **跨模态一致性惩罚（只降权，≤×0.5）**。

        权重参数默认 ``None`` → 回落 ``settings.*``（config 驱动，代码内不硬编码）。
        ``cross_weight`` / ``w_cross_t2i`` / ``w_cross_i2t`` 位于 ``*`` 之后，为关键字专用。
        """
        # ---- 权重：None → 回落 config（三通道等权，默认均为 1.0）----
        w_ii = settings.MATCH_W_IMG_IMG if img_weight is None else img_weight
        w_tt = settings.MATCH_W_TEXT_TEXT if text_weight is None else text_weight
        w_cross = settings.MATCH_W_CROSS if cross_weight is None else cross_weight
        w_t2i = settings.MATCH_W_CROSS_T2I if w_cross_t2i is None else w_cross_t2i
        w_i2t = settings.MATCH_W_CROSS_I2T if w_cross_i2t is None else w_cross_i2t

        # ---- 通道可用性 ----
        has_ii = img1 is not None and img2 is not None
        has_tt = text1 is not None and text2 is not None
        has_t2i = text1 is not None and img2 is not None      # 查询文字 × 目标图片
        has_i2t = img1 is not None and text2 is not None      # 查询图片 × 目标文字
        has_cc = has_t2i or has_i2t

        # ---- 逐通道取值（None 表示不可用）----
        sim_ii = float(np.dot(img1, img2)) if has_ii else None
        sim_tt = float(np.dot(text1, text2)) if has_tt else None
        sim_t2i = float(np.dot(text1, img2)) if has_t2i else None
        sim_i2t = float(np.dot(img1, text2)) if has_i2t else None

        # ---- 跨模态通道 = 可用方向的加权平均 ----
        if has_cc:
            num = (w_t2i * sim_t2i if has_t2i else 0.0) + (w_i2t * sim_i2t if has_i2t else 0.0)
            den = (w_t2i if has_t2i else 0.0) + (w_i2t if has_i2t else 0.0)
            sim_cross = (num / den) if den > 0 else None
        else:
            sim_cross = None

        # ---- 跨模态「尺度映射」：原生余弦(0.15~0.35) → 可读尺度 [0,1] ----
        # 仅作用于**外层加权**；阶段5 惩罚仍用原始 sim_t2i / sim_i2t（其阈值按原始尺度设计）
        sim_cross_mapped = self._map_cross(sim_cross)

        # ---- 外层缺维度动态归一化（权重和恒为 1；全缺 → 0.0）----
        # 按查询形态自动成形：文字检索只剩(文-文 + 跨模态)→0.75/0.25；
        # 图片检索只剩(图-图 + 跨模态)→0.75/0.25；图文混合三通道全参与。
        channels = [
            (w_tt, sim_tt),                    # 主证据：文-文
            (w_cross, sim_cross_mapped),       # 辅助：跨模态（映射后）
            (w_ii, sim_ii),                    # 主证据：图-图
        ]
        avail = [(w, s) for (w, s) in channels if s is not None and w > 0]
        base = (sum(w * s for w, s in avail) / sum(w for w, _ in avail)) if avail else 0.0

        # ---- 阶段1: 类别/位置双向调节 ----
        if cat1 and cat2:
            if cat1 == cat2:
                base = min(base + settings.MATCH_CAT_SAME_BONUS, 1.0)
            else:
                base = max(base - settings.MATCH_CAT_DIFF_PENALTY, 0.0)
        if loc1 and loc2:
            if loc1 == loc2:
                base = min(base + settings.MATCH_LOC_SAME_BONUS, 1.0)
            else:
                base = max(base - settings.MATCH_LOC_DIFF_PENALTY, 0.0)

        # ---- 阶段2: 时间衰减 ----
        decay = (
            max(settings.MATCH_DECAY_FLOOR, 1.0 - days_old / float(settings.MATCH_DECAY_DAYS))
            if days_old > 0
            else 1.0
        )
        base = base * decay

        # ---- 阶段5: 跨模态一致性惩罚（只降权，≤×0.5）----
        base = base * self._cross_penalty(sim_ii, sim_tt, sim_t2i, sim_i2t)

        return round(base, 6)

    def _map_cross(self, value: Optional[float]) -> Optional[float]:
        """跨模态通道「尺度映射」：原生余弦 → 可读尺度 [0, 1]。

        为什么需要（2026-09-21 实测）
        ----------------------------
        CLIP 的图文跨模态余弦天生只落在 **0.15~0.35**（即使图文完美对应也仅 ~0.27），
        因为图像与文本在联合嵌入空间里的对齐程度本就低于同模态。若直接参与加权，
        它在任何权重下都被系统性低估 —— 表现为「以文搜图命中却只显示 27%」。

        映射（线性拉伸，夹到 [0,1]）::

            ref = clip((x - LO) / (HI - LO), 0, 1)

        ``LO`` / ``HI`` 取自评测集实测分布：负样本均值 → 0、正样本均值 → 1。

        ⚠️ 只用于**外层加权与对外展示**；阶段5 惩罚使用原始余弦（阈值按原始尺度设计）。
        """
        if value is None:
            return None
        lo = settings.MATCH_CROSS_REF_LO
        hi = settings.MATCH_CROSS_REF_HI
        if hi <= lo:
            return value
        return max(0.0, min(1.0, (value - lo) / (hi - lo)))

    def _content_score(
        self,
        sim_tt: Optional[float],
        sim_cross_mapped: Optional[float],
        sim_ii: Optional[float],
    ) -> float:
        """**内容分**：主辅加权 + 缺通道动态归一化，**不含**阶段1（类别/位置）与阶段2（时间衰减）。

        为什么单独抽出来（2026-09-21）
        -----------------------------
        标定脚本刻意不传类别/位置/时间（「标定纯内容相似度，避免统一加分造成阈值漂移」），
        因此标定出的 ``MANUAL/AUTO/EMAIL`` 阈值是**内容分尺度**。而线上完整分会被
        时间衰减压低（81 天前物品 ×0.66）——若用完整分与阈值比较，老物品会被系统性
        过滤掉（实测：内容分 0.905 的文字强命中，衰减后 0.565 ＜ 阈值 0.625 → 结果消失）。

        所以：**阈值判定用内容分**（与标定同尺度），**排序用完整分**（含衰减，实现
        「新物品优先」的时效性），**展示用最强证据**（见 :meth:`build_evidence`）。
        """
        w_tt = settings.MATCH_W_TEXT_TEXT
        w_cross = settings.MATCH_W_CROSS
        w_ii = settings.MATCH_W_IMG_IMG
        avail = [
            (w_tt, sim_tt),
            (w_cross, sim_cross_mapped),
            (w_ii, sim_ii),
        ]
        usable = [(w, s) for w, s in avail if s is not None and w > 0]
        if not usable:
            return 0.0
        return sum(w * s for w, s in usable) / sum(w for w, _ in usable)

    def compute_match_detail(
        self,
        img1: np.ndarray = None,
        text1: np.ndarray = None,
        img2: np.ndarray = None,
        text2: np.ndarray = None,
        *,
        cat1: str = "",
        cat2: str = "",
        loc1: str = "",
        loc2: str = "",
        days_old: int = 0,
    ) -> dict:
        """一次调用返回**完整匹配结果**：排序分 + 各通道值 + 证据链。

        与 :meth:`compute_weighted_similarity` 的关系：后者只返回标量（保持既有契约不变），
        本方法在其基础上额外暴露各通道原始值与证据链，供接口层与邮件使用。

        Returns:
            ``{score, channels, level, basis, reference_score, cross_mapped}``
            - ``score``：排序/过滤用（按查询形态自动加权的综合分）
            - ``channels``：各通道原始余弦（透明可解释，便于调试与答辩展示）
            - ``level`` / ``basis`` / ``reference_score``：见 :meth:`build_evidence`
        """
        sim_ii = float(np.dot(img1, img2)) if (img1 is not None and img2 is not None) else None
        sim_tt = float(np.dot(text1, text2)) if (text1 is not None and text2 is not None) else None
        sim_t2i = float(np.dot(text1, img2)) if (text1 is not None and img2 is not None) else None
        sim_i2t = float(np.dot(img1, text2)) if (img1 is not None and text2 is not None) else None
        cross_vals = [v for v in (sim_t2i, sim_i2t) if v is not None]
        sim_cross = float(np.mean(cross_vals)) if cross_vals else None

        score = self.compute_weighted_similarity(
            img1, text1, img2, text2,
            cat1=cat1, cat2=cat2, loc1=loc1, loc2=loc2, days_old=days_old,
        )
        evidence = self.build_evidence(sim_ii, sim_tt, sim_cross)
        content = self._content_score(sim_tt, self._map_cross(sim_cross), sim_ii)
        return {
            "score": score,
            "content_score": round(content, 6),
            "channels": {
                "sim_img_img": sim_ii,
                "sim_text_text": sim_tt,
                "sim_t2i": sim_t2i,
                "sim_i2t": sim_i2t,
                "sim_cross": sim_cross,
                "sim_cross_mapped": self._map_cross(sim_cross),
            },
            **evidence,
        }

    def build_evidence(
        self,
        sim_ii: Optional[float],
        sim_tt: Optional[float],
        sim_cross_raw: Optional[float],
    ) -> dict:
        """把各通道分数翻译成「证据链」：等级 + 命中依据 + 展示分。

        设计意图（2026-09-21）：**相似度只用于排序与参考，判定靠证据分级**。
        混合成一个分数再切阈值，会让正负样本分布重叠恶化 2.5~6 倍
        （实测：单通道 0.067~0.158 → 混合后 0.397），这就是分层阈值长期标不出来的根因。

        - ``level``：confirmed（确定为同一物品）/ high_suspect（高度疑似）/
          related（相关）/ reference（参考）
        - ``basis``：命中依据列表（image_match / text_match / cross_modal），
          每条依据须通过各自阈值（IMG_MIN / TEXT_MIN / CROSS_MIN），
          通道「存在但数值低」不得进依据（2026-10-15 起）。
        - ``reference_score``：展示分 —— 取**最强证据通道**（映射到可读尺度后），
          用于界面与邮件给用户参考（不再被弱通道稀释）
        """
        cross_mapped = self._map_cross(sim_cross_raw)
        candidates = [
            ("image_match", sim_ii),
            ("text_match", sim_tt),
            ("cross_modal", cross_mapped),
        ]
        usable = [(name, v) for name, v in candidates if v is not None]
        if not usable:
            return {"level": "reference", "basis": [], "reference_score": 0.0}

        # 展示分 = 最强证据通道的值（各通道均已在可读尺度上）
        basis_all = [name for name, _ in usable]
        top_name, top_val = max(usable, key=lambda kv: kv[1])
        reference_score = round(float(top_val), 6)

        # 等级判定（优先级：确定 > 高度疑似 > 相关 > 参考）
        self_high = max([v for n, v in usable if n in ("image_match", "text_match")] or [0.0])
        if self_high >= settings.MATCH_EVIDENCE_CONFIRM_SELF:
            level = "confirmed"
            basis = ["image_match"] if sim_ii is not None and sim_ii >= settings.MATCH_EVIDENCE_CONFIRM_SELF \
                else ["text_match"]
        elif (sim_tt is not None and sim_tt >= settings.MATCH_EVIDENCE_TEXT_MIN) or \
             (cross_mapped is not None and cross_mapped >= settings.MATCH_EVIDENCE_CROSS_MIN):
            level = "high_suspect"
            # 2026-10-15 修复：image_match 原为「通道存在即进依据」，不看数值 ——
            # 文-文 高而图-图 低（如 0.2）时，用户会看到「文字描述高度吻合、图像高度一致」，
            # 后半句与事实相反。现改为图-图 ≥ MATCH_EVIDENCE_IMG_MIN 才计入依据。
            basis = [n for n, v in usable if (
                (n == "text_match" and v >= settings.MATCH_EVIDENCE_TEXT_MIN)
                or (n == "cross_modal" and v >= settings.MATCH_EVIDENCE_CROSS_MIN)
                or (n == "image_match" and v >= settings.MATCH_EVIDENCE_IMG_MIN)
            )]
        elif cross_mapped is not None and cross_mapped >= settings.MATCH_EVIDENCE_CROSS_WEAK:
            level = "related"
            basis = ["cross_modal"]
        else:
            level = "reference"
            basis = [top_name]

        return {
            "level": level,
            "basis": basis or basis_all,
            "reference_score": reference_score,
        }

    def _cross_penalty(
        self,
        sim_ii: Optional[float],
        sim_tt: Optional[float],
        sim_t2i: Optional[float],
        sim_i2t: Optional[float],
    ) -> float:
        """跨模态一致性惩罚因子（**只降权**；分段线性、对 ``cc`` 单调）。

        - ``cc = min(可用跨模态方向)``（取「最不一致」方向）；
        - **仅当「文-文」自相似 ``>= CROSS_PENALTY_SELF_HIGH`` 时才可能触发**
          （2026-09-21 修正：原本用 ``max(图-图, 文-文)`` 触发，会误伤「图-图 高」的
          可靠匹配 —— 那种情况下跨模态低是 CLIP 固有基线而非矛盾）；
        - ``cc >= CROSS_PENALTY_CC_HIGH`` → 不惩罚；``cc <= CROSS_PENALTY_CC_LOW`` → 触底；
        - 返回值恒在 ``[CROSS_PENALTY_FLOOR, 1.0]``，默认下限 0.5（腰斩上限）；
        - ``CROSS_PENALTY_ENABLED=False`` 或跨模态方向缺失 → 恒返回 ``1.0``。

        Returns:
            惩罚因子（乘到 base 上），∈ ``[CROSS_PENALTY_FLOOR, 1.0]``。
        """
        if not settings.CROSS_PENALTY_ENABLED:
            return 1.0

        cross_values = [v for v in (sim_t2i, sim_i2t) if v is not None]
        if not cross_values:
            return 1.0

        # 触发前提收窄为「**文-文**自相似高」（2026-09-21 修正）
        # ----------------------------------------------------------
        # 本惩罚针对的是「文本描述撞车、实物却不同」——该场景的特征是
        # 文-文 高 而 跨模态 低。而「图-图 高」时跨模态低是 CLIP 的**固有基线**
        # （同一物品的图片与其自身文字也只有 ~0.24），拿它触发会**误伤最可靠的匹配**：
        # 实测原图自比被无谓压低 15.6%（0.619 → 0.522）。
        if sim_tt is None or sim_tt < settings.CROSS_PENALTY_SELF_HIGH:
            return 1.0

        # 但若「图-图」同样很高，说明**图像证据独立支持**该匹配 —— 此时跨模态低
        # 只是 CLIP 基线，不是「文本撞车」（典型：用户上传同物品的图+文，文-文≈1.0）。
        # 真正的文本撞车场景是「文-文高 而 图-图低/缺失」（文字像、图像不像）。
        if sim_ii is not None and sim_ii >= settings.CROSS_PENALTY_SELF_HIGH:
            return 1.0

        cc = min(cross_values)  # 取最不一致方向
        lo = settings.CROSS_PENALTY_CC_LOW
        hi = settings.CROSS_PENALTY_CC_HIGH
        floor = settings.CROSS_PENALTY_FLOOR

        if cc >= hi:
            return 1.0
        if cc <= lo or hi <= lo:
            return floor
        t = (cc - lo) / (hi - lo)
        return floor + (1.0 - floor) * t


# 创建全局单例实例
clip_service = CLIPService()
