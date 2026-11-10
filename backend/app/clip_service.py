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

import re
import threading

import numpy as np

from .clip_backend import ClipBackend, get_backend
from .config import settings, match_threshold
from .logger import logger
from .services import fusion
from .utils import synonyms


#: 字面比对前的噪声清理：空白 + 中英文标点。只保留文字与数字，
#: 使「房卡」「房卡 」「房卡（宿舍）」在字面层面可比。
_TEXT_NOISE = re.compile(r"[\s\u3000,.!?;:'\"()\[\]{}<>/\\|_\-—–·、，。！？；：（）【】《》“”‘’…]+")

#: 同义命中的加分折扣：词典只能证明「同一类」，不能证明「同一件」，
#: 全额加分会把同类负样本一起抬过阈值（实测 0.7774 → 0.8554，越过邮件阈值）。
ALIAS_BONUS_SCALE = 0.3


def _normalize_text(text: object) -> str:
    """归一化文本用于字面比对（小写 + 去空白与标点）。"""
    return _TEXT_NOISE.sub("", str(text or "")).lower()


class CLIPService:
    """CLIP 模型服务（单例模式 + 后端委托）。"""

    _instance = None
    _backend: Optional[ClipBackend] = None
    _device = "cpu"
    # 后端选择锁（v3.6.3）：预热线程与首个请求可能同时进入 _initialize，
    # 无锁时理论上会各自 get_backend() 一次（虽然后者会被覆盖，但会多一个实例）。
    _init_lock = threading.Lock()

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
        v3.6.3 起加锁双检 —— 启动预热线程与首个用户请求可能并发进入此方法。
        """
        if self._backend is not None:      # 快路径
            return
        with self._init_lock:
            if self._backend is None:      # 双检
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
        title_vec2: np.ndarray = None,
        query_text: str = "",
        target_title: str = "",
        target_desc: str = "",
        scoring_mode: Optional[str] = None,
    ) -> dict:
        """一次调用返回**完整匹配结果**：单一分数 + 各通道原始值 + 证据链。

        v3.7.0 起支持两套口径，由 ``scoring_mode``（默认取
        ``settings.MATCH_SCORING_MODE``）分派：

        ==========  =====================================================
        legacy      旧五阶段口径：``base`` 加权 → 类别/地点 → 时间衰减
                    → 跨模态惩罚；三个分数（score / content_score /
                    reference_score）语义不同
        v2          单一分数：文本(标题∨全文) + 图像 + 跨模态(原始余弦)
                    加权 + **字面命中加分**；时间只进 ``ranking_score``
        ==========  =====================================================

        Args:
            title_vec2: 目标物品的**标题独立向量**。缺省（旧库未回填）时 v2 自动
                退化为「仅全文向量」，不会抛错。
            query_text / target_title / target_desc: 原始字符串，仅供 v2 的字面命中
                特征使用；不传则字面分为 0（不影响向量通道）。
            scoring_mode: 显式覆盖口径，用于消融对比与单测。

        Returns:
            ``{score, content_score, ranking_score, channels, level, basis,
            reference_score, scoring_mode}``
            - ``score``：**唯一判定分**（v2 下与本字典的 content_score 相同）
            - ``ranking_score``：仅用于排序（v2 = score × 时间衰减）
            - ``channels``：各通道原始余弦（透明可解释）
        """
        mode = str(scoring_mode or settings.MATCH_SCORING_MODE or "legacy").strip().lower()

        sim_ii = float(np.dot(img1, img2)) if (img1 is not None and img2 is not None) else None
        sim_tt = float(np.dot(text1, text2)) if (text1 is not None and text2 is not None) else None
        sim_t2i = float(np.dot(text1, img2)) if (text1 is not None and img2 is not None) else None
        sim_i2t = float(np.dot(img1, text2)) if (img1 is not None and text2 is not None) else None
        # 标题向量是**全文向量的细化**，不是独立通道：目标若没有 text_vector
        # （历史「仅有图片」条目 / 未重嵌入），整条文本通道都应视为不可用。
        # 否则残留的 title_vector 会以 0 分参与加权，把跨模态命中稀释掉
        # （实测：text2=NULL 的目标 t2i=1.0 时，被 0.8×0 拖到 0.2）。
        sim_title = (
            float(np.dot(text1, title_vec2))
            if (text1 is not None and title_vec2 is not None and text2 is not None)
            else None
        )
        cross_vals = [v for v in (sim_t2i, sim_i2t) if v is not None]
        sim_cross = float(np.mean(cross_vals)) if cross_vals else None

        channels = {
            "sim_img_img": sim_ii,
            "sim_text_text": sim_tt,
            "sim_text_title": sim_title,
            "sim_t2i": sim_t2i,
            "sim_i2t": sim_i2t,
            "sim_cross": sim_cross,
            "sim_cross_mapped": self._map_cross(sim_cross),
        }

        if mode != "v2":
            score = self.compute_weighted_similarity(
                img1, text1, img2, text2,
                cat1=cat1, cat2=cat2, loc1=loc1, loc2=loc2, days_old=days_old,
            )
            evidence = self.build_evidence(sim_ii, sim_tt, sim_cross)
            content = self._content_score(sim_tt, self._map_cross(sim_cross), sim_ii)
            return {
                "score": score,
                "content_score": round(content, 6),
                "ranking_score": score,
                "channels": channels,
                "scoring_mode": "legacy",
                **evidence,
            }

        literal, literal_scale = self.literal_features(query_text, target_title, target_desc)
        score = self.compute_score_v2(
            sim_tt=sim_tt, sim_title=sim_title, sim_ii=sim_ii,
            sim_t2i=sim_t2i, sim_i2t=sim_i2t,
            cat1=cat1, cat2=cat2, loc1=loc1, loc2=loc2,
            literal=literal, literal_scale=literal_scale,
        )
        evidence = self.build_evidence(sim_ii, sim_tt, sim_cross)
        # v2 是**单一分数**体系，等级必须由该分数决定，否则会出现
        # 「69.7% + 高度疑似」这种自相矛盾的组合：build_evidence 的等级来自
        # 单通道阈值（text ≥ 0.606），而短标题的两字词余弦普遍 0.75~0.85，
        # 一条 69% 的弱相关会因为「标题余弦 0.84」被判成高度疑似。
        level = self._level_from_score(score)
        return {
            "score": score,
            "content_score": score,
            "ranking_score": round(score * self._time_decay(days_old), 6),
            "channels": channels,
            "literal_hit": literal,
            "scoring_mode": "v2",
            "level": level,
            "basis": evidence["basis"],
            # v2 只有**一个**分数：展示分不再另取「最强通道」，否则又回到
            # 「用户看到的分 ≠ 判定用的分」的老问题（房卡：展示 0.7569 / 判定 0.5677）。
            "reference_score": score,
        }

    # ------------------------------------------------------------------ #
    # v3.7.0 打分口径 v2
    # ------------------------------------------------------------------ #
    def _level_from_score(self, score: float) -> str:
        """v2：等级由**判定分**决定，与三档业务阈值一一对应。

        WHY（2026-11-10 实测）：``build_evidence`` 的等级来自**单通道阈值**
        （文-文/图-图 ≥ 0.606），而 Chinese-CLIP 的短标题余弦普遍 0.75~0.85，
        于是一条判定分仅 0.697 的弱相关（笔记本 × 学生证）会因为「标题余弦 0.84」
        被评为 high_suspect，界面上出现「69.7% + 高度疑似」的自相矛盾。

        v2 是单一分数体系，等级必须与分数同源：
            ≥ email  → confirmed     （高度确定）
            ≥ auto   → high_suspect  （高度疑似）
            ≥ manual → related       （可能相关）
            其余     → reference     （仅供参考）
        """
        if score >= match_threshold("email"):
            return "confirmed"
        if score >= match_threshold("auto"):
            return "high_suspect"
        if score >= match_threshold("manual"):
            return "related"
        return "reference"

    def _time_decay(self, days_old: int) -> float:
        """时间衰减因子 ∈ [FLOOR, 1.0]，**只作用于排序分**。

        为什么不进判定分：阈值是在「不含时间」的内容尺度上标定的；若把衰减乘进
        判定分，81 天前的强命中（0.905 → 0.565）会被阈值系统性过滤掉
        —— 这正是旧口径 content_score / score 两套尺度的由来。
        """
        if not days_old or days_old <= 0:
            return 1.0
        days = float(getattr(settings, "V2_TIME_DECAY_DAYS", 240) or 240)
        floor = float(getattr(settings, "V2_TIME_DECAY_FLOOR", 0.6) or 0.0)
        if days <= 0:
            return 1.0
        return max(floor, 1.0 - days_old / days)

    def literal_features(self, query_text: str, target_title: str, target_desc: str):
        """一次返回 ``(命中强度, 加分系数)`` —— 门控看强度，加分看系数。

        WHY 要拆成两个数（2026-11-10 实测）
        -----------------------------------
        同义命中（校园卡≡一卡通）代表「用户点明了这是**哪一类**东西」，
        它足以让人信任标题向量（放行门控），但**不能证明是同一件**：
        词典对「充电宝」和「移动电源」这两个**不同实物**同样命中。

        实测（v3.7.0 评测集，7 对受词典影响）：
            5 条正样本  +0.12（课本≡教材、折叠伞≡雨伞、水杯≡保温杯 …）
            2 条同类负样本 **也 +0.12**（课本 × 办公软件教材、折叠伞 × 格纹雨伞）
        正负同幅上移 → 判别力不增，但「同类负样本最高分」从 0.7774 抬到
        **0.8554**，越过邮件阈值 0.85 —— 等于用词典换来了几封发错人的邮件。

        故：强度仍记 0.8（`literal >= 0.8` 才会放行标题通道），
        但加分打折到 ``ALIAS_BONUS_SCALE``；确定性字面（完全相同/包含）不打折。
        """
        q = _normalize_text(query_text)
        if not q:
            return 0.0, 1.0
        use_alias = bool(getattr(settings, "V2_SYNONYM_ENABLED", True))
        t = _normalize_text(target_title)
        if t:
            if q == t:
                return 1.0, 1.0
            if len(q) >= 2 and (q in t or t in q):
                return 0.8, 1.0
            if use_alias and len(q) >= 2 and synonyms.alias_hit(q, t):
                return 0.8, ALIAS_BONUS_SCALE
        d = _normalize_text(target_desc)
        if d and len(q) >= 2:
            if q in d:
                return 0.4, 1.0
            if use_alias and synonyms.alias_hit(q, d):
                return 0.4, ALIAS_BONUS_SCALE
        return 0.0, 1.0

    def _literal_hit(self, query_text: str, target_title: str, target_desc: str) -> float:
        """字面命中强度 ∈ {0, 0.4, 0.8, 1.0}（分级规则见 :meth:`literal_features`）。

        WHY（2026-11-09 实测）：Chinese-CLIP 的短文本余弦存在严重各向异性 ——
        两字词之间普遍 0.75~0.85（「学生证」对查询「笔记本」竟有 0.8436，
        高于真解「一本蓝色的笔记本」的 0.7877）。此时**字面是唯一确定性证据**，
        必须显式进入打分，而不是指望向量把它推上来。

        - 1.0：查询与标题归一化后完全相同
        - 0.8：标题包含查询（或反之），查询 ≥ 2 字（避免单字误命中）
        - 0.8：**同义命中** —— 各含同一同义词组的不同组员（校园卡 × 一卡通），
               见 ``app/utils/synonyms.py``；加分系数另行打折
        - 0.4：仅描述命中（描述常是「怎么丢的」，噪声大）
        - 0.0：无字面重合
        """
        return self.literal_features(query_text, target_title, target_desc)[0]

    def compute_score_v2(
        self,
        *,
        sim_tt: Optional[float],
        sim_title: Optional[float],
        sim_ii: Optional[float],
        sim_t2i: Optional[float] = None,
        sim_i2t: Optional[float] = None,
        cat1: str = "",
        cat2: str = "",
        loc1: str = "",
        loc2: str = "",
        literal: float = 0.0,
        literal_scale: float = 1.0,
        title_gate: Optional[str] = None,
    ) -> float:
        """v2 单分数：可用通道加权平均 + 字面加分（封顶 1.0）。

        从 v3.7.0 起**只做参数装配**，算法本体在
        :func:`app.services.fusion.channels_from_sims` 与
        :func:`app.services.fusion.fuse`（论文第 4 章的式 4-1 ~ 4-4）。

        与旧口径的三点差异：

        1. **文本通道取「标题 ∨ 全文」的更优者**（不是加权平均）。全文向量是
           ``encode(title + description)``，描述会把标题稀释成嵌合体
           （实测：房卡标题 1.0000 / 全文 0.7569）；取 max 才能让「描述写歪了」
           不拖累正解。
        2. **跨模态用「仿射缩放但不截断」**（见 :func:`app.services.fusion.affine_cross`）。
           保留缩放是为了放大正负差距（原始余弦正负只差 0.10，直接加权会被文本
           通道淹没，实测 Precision 掉到 0.46）；去掉截断是为了不让「短查询的
           跨模态分一律 < LO」被压成 0 —— 那会让通道对两字查询彻底失效。
        3. **缺通道动态归一化保留**（分母只累加可用通道），因此三种检索模式
           仍然零分支自动成形。
        """
        weights = fusion.FusionWeights(
            w_text=float(getattr(settings, "V2_W_TEXT", 0.8)),
            w_img=float(getattr(settings, "V2_W_IMG", 0.8)),
            w_cross=float(getattr(settings, "V2_W_CROSS", 0.2)),
            literal_bonus=float(getattr(settings, "V2_LITERAL_BONUS", 0.0)),
            title_gate=str(title_gate or getattr(settings, "V2_TITLE_GATE", "always")).strip().lower(),
        )
        ch = fusion.channels_from_sims(
            sim_tt=sim_tt, sim_title=sim_title, sim_ii=sim_ii,
            sim_t2i=sim_t2i, sim_i2t=sim_i2t,
            literal=literal, literal_scale=literal_scale,
            cat1=cat1, cat2=cat2, loc1=loc1, loc2=loc2,
            lo=float(settings.MATCH_CROSS_REF_LO),
            hi=float(settings.MATCH_CROSS_REF_HI),
            weights=weights,
        )
        return fusion.fuse(ch, weights)

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
