# app/clip_service.py
import open_clip
import torch
from PIL import Image
import numpy as np
from .logger import logger


class CLIPService:
    """CLIP 模型服务（单例模式）"""
    _instance = None
    _model = None
    _preprocess = None
    _tokenizer = None
    _device = "cpu"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _initialize(self):
        """延迟加载模型（首次调用时初始化）"""
        if self._model is not None:
            return
        logger.info("正在加载 CLIP 模型（首次加载约 600MB，请耐心等待）...")
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            'ViT-B-32',
            pretrained='laion2b_s34b_b79k'
        )
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer('ViT-B-32')
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = self._model.to(self._device)
        logger.info(f"CLIP 模型加载完成，运行设备: {self._device}")

    def get_image_feature(self, image_path: str) -> np.ndarray:
        """
        提取图像 512 维特征向量（L2 归一化）
        """
        self._initialize()
        image = Image.open(image_path).convert('RGB')
        tensor = self._preprocess(image).unsqueeze(0).to(self._device)
        with torch.no_grad():
            features = self._model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().numpy().flatten()

    def get_text_feature(self, text: str) -> np.ndarray:
        """
        提取文本 512 维特征向量（L2 归一化）
        """
        self._initialize()
        tokens = self._tokenizer([text]).to(self._device)
        with torch.no_grad():
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        return features.cpu().numpy().flatten()

    def get_color_histogram(self, image_path: str) -> np.ndarray:
        """提取 27 维归一化颜色直方图（RGB 各 3 级量化）"""
        try:
            img = Image.open(image_path).convert('RGB').resize((64, 64))
            pixels = np.array(img).reshape(-1, 3) // 86    # 0-85→0, 86-171→1, 172-255→2
            hist = np.zeros((3, 3, 3), dtype=np.float32)
            for p in pixels:
                hist[min(p[0], 2)][min(p[1], 2)][min(p[2], 2)] += 1.0
            hist = hist.flatten()
            hist = hist / (hist.sum() + 1e-8)
            return hist
        except Exception:
            return None

    def compute_color_similarity(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        """颜色直方图余弦相似度"""
        if hist1 is None or hist2 is None:
            return 0.0
        return float(np.dot(hist1, hist2) / (np.linalg.norm(hist1) * np.linalg.norm(hist2) + 1e-8))

    def compute_weighted_similarity(
        self,
        img1: np.ndarray,
        text1: np.ndarray,
        img2: np.ndarray,
        text2: np.ndarray,
        cat1: str = "",
        cat2: str = "",
        loc1: str = "",
        loc2: str = "",
        days_old: int = 0,
        img_weight: float = 0.50,
        text_weight: float = 0.30,
        color_weight: float = 0.20,
        color1: np.ndarray = None,
        color2: np.ndarray = None,
    ) -> float:
        """
        五阶段 + 颜色增强的加权相似度算法

        权重分配: 图像50% + 文本30% + 颜色20%
        阶段1 - 类别/位置增强: 同类+同位置给加分，不同类/位置降权
        阶段2 - 时间衰减:      越旧的物品得分越低
        阶段3 - 分层阈值:      通过返回修正后的值，调用方用不同阈值
        阶段4 - 动态权重:      无图像时文本=1.0；无颜色时权重回归图像
        阶段5 - 交叉验证:      图文高度矛盾时施加惩罚
        """
        has_both_images = img1 is not None and img2 is not None
        has_both_texts = text1 is not None and text2 is not None
        has_both_colors = color1 is not None and color2 is not None

        # ---- 基础相似度 ----
        img_sim = float(np.dot(img1, img2)) if has_both_images else 0.0
        text_sim = float(np.dot(text1, text2)) if has_both_texts else 0.0
        color_sim = self.compute_color_similarity(color1, color2) if has_both_colors else 0.0

        # 纯文本匹配
        if has_both_texts and not has_both_images:
            base = text_sim
        # 有图像：图像+文本+颜色三合一
        elif has_both_images and has_both_colors:
            base = img_weight * img_sim + text_weight * text_sim + color_weight * color_sim
        # 有图像无颜色：图像+文本（权重重新分配）
        elif has_both_images:
            base = 0.65 * img_sim + 0.35 * text_sim
        # 纯图像无文本无颜色
        else:
            base = img_sim

        # ---- 阶段1: 类别/位置双向调节 ----
        # 同类别/同位置加分，不同则降权
        if cat1 and cat2:
            if cat1 == cat2:
                base = min(base + 0.05, 1.0)    # 同类别 +5%
            else:
                base = max(base - 0.08, 0.0)    # 不同类别 -8%
        if loc1 and loc2:
            if loc1 == loc2:
                base = min(base + 0.03, 1.0)    # 同位置 +3%
            else:
                base = max(base - 0.04, 0.0)    # 不同位置 -4%

        # ---- 阶段2: 时间衰减 ----
        decay = max(0.5, 1.0 - days_old / 90.0) if days_old > 0 else 1.0
        base = base * decay

        # ---- 阶段5: 交叉验证惩罚 ----
        if has_both_images and has_both_texts:
            if img_sim > 0.7 and text_sim < 0.15:
                base = base * 0.50    # 图文高度矛盾，腰斩
            elif img_sim > 0.6 and text_sim < 0.25:
                base = base * 0.75    # 中等矛盾，打七五折

        return round(base, 6)


# 创建全局单例实例
clip_service = CLIPService()