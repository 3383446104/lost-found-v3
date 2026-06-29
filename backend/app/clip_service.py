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

    def compute_weighted_similarity(
        self,
        img1: np.ndarray,
        text1: np.ndarray,
        img2: np.ndarray,
        text2: np.ndarray,
        img_weight: float = 0.6,
        text_weight: float = 0.4
    ) -> float:
        """
        计算加权相似度
        - 图像权重 0.6（更客观）
        - 文本权重 0.4（补充描述）
        - 当双方均无图像时，使用纯文本相似度（权重 1.0），
          确保纯文本匹配也能达到自动推送阈值
        """
        has_both_images = img1 is not None and img2 is not None
        has_both_texts = text1 is not None and text2 is not None

        img_sim = float(np.dot(img1, img2)) if has_both_images else 0.0
        text_sim = float(np.dot(text1, text2)) if has_both_texts else 0.0

        # 纯文本匹配：直接返回文本相似度（不受图像权重惩罚）
        if has_both_texts and not has_both_images:
            return text_sim

        # 图文混合 / 纯图像匹配
        return img_weight * img_sim + text_weight * text_sim


# 创建全局单例实例
clip_service = CLIPService()