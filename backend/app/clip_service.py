# app/clip_service.py
"""CLIP 服务外观（Facade）。

v3.5.0 起 ``CLIPService`` 不再直接持有具体模型，而是作为**兼容壳**委托给
:class:`~app.clip_backend.ClipBackend`（``open_clip`` / ``cn_clip`` 二选一）。

**公开方法名与签名冻结**（工程铁律 3）：``_initialize`` / ``get_image_feature`` /
``get_text_feature`` / ``get_color_histogram`` / ``compute_color_similarity`` /
``compute_weighted_similarity``——``tests/conftest.py`` 依赖 monkeypatch 这些方法名来
阻断真实模型加载，**改名即测试全红**。``clip_service`` 仍是模块级单例名。
"""
from typing import Optional

import numpy as np
from PIL import Image

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
    # 颜色直方图（与模型无关，逻辑自 v3.4.1 保持不变）
    # ------------------------------------------------------------------ #
    def get_color_histogram(self, image_path: str) -> np.ndarray:
        """提取 27 维归一化颜色直方图（RGB 各 3 级量化）。"""
        try:
            img = Image.open(image_path).convert('RGB').resize((64, 64))
            pixels = np.array(img).reshape(-1, 3) // 86    # 0-85→0, 86-171→1, 172-255→2
            hist = np.zeros((3, 3, 3), dtype=np.float32)
            for p in pixels:
                hist[min(p[0], 2)][min(p[1], 2)][min(p[2], 2)] += 1.0
            hist = hist.flatten()
            hist = hist / (hist.sum() + 1e-8)
            return hist
        except FileNotFoundError:
            logger.warning(f"颜色直方图提取失败: 文件不存在 {image_path}")
            return None
        except OSError as e:
            logger.warning(f"颜色直方图提取失败: 图片无法打开 {image_path}: {e}")
            return None
        except Exception as e:
            logger.warning(f"颜色直方图提取失败: 未知错误 {image_path}: {e}")
            return None

    def compute_color_similarity(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        """颜色直方图余弦相似度。"""
        if hist1 is None or hist2 is None:
            return 0.0
        return float(np.dot(hist1, hist2) / (np.linalg.norm(hist1) * np.linalg.norm(hist2) + 1e-8))

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
        color_weight: Optional[float] = None,
        color1: np.ndarray = None,
        color2: np.ndarray = None,
        *,
        cross_weight: Optional[float] = None,
        w_cross_t2i: Optional[float] = None,
        w_cross_i2t: Optional[float] = None,
    ) -> float:
        """五阶段 + 颜色增强 + **跨模态** 加权相似度算法。

        通道定义（``q`` = 查询，``t`` = 目标；``·`` = 余弦，向量均已 L2 归一化）：

        ==================  ========================  =========================
        通道                 表达式                     可用条件
        ==================  ========================  =========================
        ``sim_img_img``     ``q_img · t_img``         ``img1, img2`` 均非空
        ``sim_text_text``   ``q_text · t_text``       ``text1, text2`` 均非空
        ``sim_cross_t2i``   ``q_text · t_img``        ``text1, img2`` 均非空
        ``sim_cross_i2t``   ``q_img · t_text``        ``img1, text2`` 均非空
        ``sim_color``       ``cos(q_color, t_color)`` ``color1, color2`` 均非空
        ==================  ========================  =========================

        - ``sim_cross`` = 可用跨模态方向的加权平均（``MATCH_W_CROSS_T2I`` / ``MATCH_W_CROSS_I2T``）；
        - 外层**缺维度动态归一化**：不可用通道从分母剔除，权重和恒为 1；全缺 → ``0.0``；
        - 阶段1 类别/位置；阶段2 时间衰减；阶段5 **跨模态一致性惩罚（只降权，≤×0.5）**。

        权重参数默认 ``None`` → 回落 ``settings.*``（config 驱动，代码内不硬编码）。
        新增的 ``cross_weight`` / ``w_cross_t2i`` / ``w_cross_i2t`` 位于 ``*`` 之后，
        为**关键字专用**，杜绝位置参数错位。

        Note:
            四个外层权重与两个跨模态内权重均为**初值，需评测收敛**（见标定脚本）。
        """
        # ---- 权重：None → 回落 config ----
        w_ii = settings.MATCH_W_IMG_IMG if img_weight is None else img_weight
        w_tt = settings.MATCH_W_TEXT_TEXT if text_weight is None else text_weight
        w_col = settings.MATCH_W_COLOR if color_weight is None else color_weight
        w_cross = settings.MATCH_W_CROSS if cross_weight is None else cross_weight
        w_t2i = settings.MATCH_W_CROSS_T2I if w_cross_t2i is None else w_cross_t2i
        w_i2t = settings.MATCH_W_CROSS_I2T if w_cross_i2t is None else w_cross_i2t

        # ---- 通道可用性 ----
        has_ii = img1 is not None and img2 is not None
        has_tt = text1 is not None and text2 is not None
        has_t2i = text1 is not None and img2 is not None      # 查询文字 × 目标图片
        has_i2t = img1 is not None and text2 is not None      # 查询图片 × 目标文字
        has_cc = has_t2i or has_i2t
        has_col = color1 is not None and color2 is not None

        # ---- 逐通道取值（None 表示不可用）----
        sim_ii = float(np.dot(img1, img2)) if has_ii else None
        sim_tt = float(np.dot(text1, text2)) if has_tt else None
        sim_t2i = float(np.dot(text1, img2)) if has_t2i else None
        sim_i2t = float(np.dot(img1, text2)) if has_i2t else None
        sim_col = self.compute_color_similarity(color1, color2) if has_col else None

        # ---- 跨模态通道 = 可用方向的加权平均 ----
        if has_cc:
            num = (w_t2i * sim_t2i if has_t2i else 0.0) + (w_i2t * sim_i2t if has_i2t else 0.0)
            den = (w_t2i if has_t2i else 0.0) + (w_i2t if has_i2t else 0.0)
            sim_cross = (num / den) if den > 0 else None
        else:
            sim_cross = None

        # ---- 外层缺维度动态归一化（权重和恒为 1；全缺 → 0.0）----
        channels = [
            (w_ii, sim_ii),        # MATCH_W_IMG_IMG
            (w_cross, sim_cross),  # MATCH_W_CROSS
            (w_tt, sim_tt),        # MATCH_W_TEXT_TEXT
            (w_col, sim_col),      # MATCH_W_COLOR
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

    def _cross_penalty(
        self,
        sim_ii: Optional[float],
        sim_tt: Optional[float],
        sim_t2i: Optional[float],
        sim_i2t: Optional[float],
    ) -> float:
        """跨模态一致性惩罚因子（**只降权**；分段线性、对 ``cc`` 单调）。

        - ``cc = min(可用跨模态方向)``（取「最不一致」方向）；
        - 仅当同模态自相似 ``max(sim_img_img, sim_text_text) >= CROSS_PENALTY_SELF_HIGH``
          时才可能触发（避免对低置信组合误伤）；
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

        self_values = [v for v in (sim_ii, sim_tt) if v is not None]
        if not self_values:
            return 1.0

        if max(self_values) < settings.CROSS_PENALTY_SELF_HIGH:
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
