# app/clip_backend.py
"""CLIP 模型后端抽象层（v3.5.0）。

采用 **策略（Strategy）+ 工厂（Factory）** 模式，把「用哪个 CLIP 模型」从业务代码里
彻底解耦出来，使业务侧（``CLIPService`` / ``match_service`` / ``api/items``）不感知具体模型：

- :class:`OpenClipBackend`  —— 旧模型 ``ViT-B-32``（回滚路径，行为等价 v3.4.1）；
- :class:`ChineseClipBackend` —— 中文模型 ``Chinese-CLIP ViT-H/14``（默认，跨模态检索核心）；
- :func:`get_backend`         —— 依据 ``settings.CLIP_BACKEND`` 选择实现。

工程铁律
--------
1. **未知 ``CLIP_BACKEND`` 取值必须抛 ``RuntimeError``**——新旧向量处于不同嵌入空间、
   不可混用，**禁止静默降级**（否则线上会拿新查询向量去比旧库向量，结果全错）。
2. **``cn_clip`` 必须 lazy import**——仅在 :meth:`ChineseClipBackend._ensure_loaded` 内
   ``import``。模块顶层**绝不**出现 ``import cn_clip``，否则在未安装该包的环境里，
   全部 pytest 会在**用例收集阶段**即崩。
3. 所有 ``encode_image`` / ``encode_text`` 必须返回 **各自 ``embed_dim`` 维、L2 归一化** 的
   ``numpy`` 向量（``OpenClipBackend`` = 512、``ChineseClipBackend`` = 1024；二者的原始输出
   均**未**做 L2 归一化，需显式除模）。维度取自 ``config``（``CLIP_*_EMBED_DIM``），
   **不在类里硬编码**——旧库向量与新模型维度不一致时，由 ``/match`` 的维度预检**响亮报错**。
4. **运行期契约（R4）**：每个 ``encode_*`` 在归一化之后、返回之前调用
   :func:`_assert_embed_dim`，断言输出维度 == ``self.embed_dim``，否则抛 ``RuntimeError``。
   这样「声明 512、实际 1024」这类契约漂移会被**当场拦下**，而非靠人读源码才发现。
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

import numpy as np

from .config import settings
from .logger import logger


# --------------------------------------------------------------------------- #
# 协议
# --------------------------------------------------------------------------- #
@runtime_checkable
class ClipBackend(Protocol):
    """CLIP 后端协议：统一的 ``encode_*`` 契约（各自 ``embed_dim`` 维、L2 归一化）。"""

    name: str
    embed_dim: int

    def is_available(self) -> bool:
        """当前环境是否具备运行该后端所需的依赖/权重。"""
        ...

    def encode_image(self, image_path: str) -> np.ndarray:
        """把图片文件编码为 ``embed_dim`` 维 L2 归一化向量。"""
        ...

    def encode_text(self, text: str) -> np.ndarray:
        """把一段文本编码为 ``embed_dim`` 维 L2 归一化向量。"""
        ...


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _resolve_device(device: Optional[str]) -> str:
    """把 ``"auto"`` 解析为具体设备（有 CUDA 用 cuda，否则 cpu）。

    传具体值（``"cpu"`` / ``"cuda"``）时原样返回，保证可强制指定。
    """
    if device and device != "auto":
        return device
    try:
        import torch  # 延迟导入：仅真正需要时加载

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:  # pragma: no cover - 环境无 torch 时兜底
        return "cpu"


def _assert_embed_dim(
    vec: np.ndarray,
    backend_name: str,
    expected_dim: int,
    config_key: str,
) -> None:
    """运行期契约（R4）：``encode_*`` 输出维度必须等于声明的 ``embed_dim``。

    把 ``embed_dim`` 从「纸面声明」提升为「被强制执行的契约」：模型实际输出维度
    与 config 声明不符时（如声明 512、实际 1024），在**归一化之后、返回之前**
    立即抛出明确错误，而不是把错误长度的向量静默喂给下游打分
    （下游只会把它吞成「匹配为空」，与「真的没找到」外观一致 → 静默全站失效）。

    Args:
        vec: 待返回的特征向量。
        backend_name: 后端名（``"open_clip"`` / ``"cn_clip"``），用于报错定位。
        expected_dim: 声明的期望维度（``self.embed_dim``）。
        config_key: 对应的 config 键（``CLIP_OPEN_EMBED_DIM`` / ``CLIP_CN_EMBED_DIM``）。

    Raises:
        RuntimeError: 当 ``vec`` 长度 ≠ ``expected_dim`` 时，报文含后端名、期望维度、
            实际维度与对应 config 键。
    """
    actual_dim = int(vec.shape[-1]) if getattr(vec, "shape", None) is not None else len(vec)
    if actual_dim != expected_dim:
        raise RuntimeError(
            f"[{backend_name}] 编码输出维度与声明不符：期望 {expected_dim} 维"
            f"（config 键 {config_key}），实际 {actual_dim} 维。"
            f"请核对 {config_key} 与所用模型权重是否匹配（不一致会导致下游打分静默失效）。"
        )


# --------------------------------------------------------------------------- #
# open_clip 后端（回滚用，行为等价 v3.4.1 clip_service）
# --------------------------------------------------------------------------- #
class OpenClipBackend:
    """基于 ``open_clip`` 的图像/文本编码后端（默认模型 ``ViT-B-32``）。

    行为与 v3.4.1 ``clip_service._initialize`` / ``get_image_feature`` /
    ``get_text_feature`` **完全等价**，用于「切配置即回滚」。
    """

    name = "open_clip"
    embed_dim = settings.CLIP_OPEN_EMBED_DIM  # 512（ViT-B-32 输出维度，回滚路径）

    def __init__(
        self,
        model_name: Optional[str] = None,
        pretrained: Optional[str] = None,
        device: str = "auto",
    ) -> None:
        self.model_name = model_name or settings.CLIP_OPEN_MODEL_NAME
        self.pretrained = pretrained or settings.CLIP_OPEN_PRETRAINED
        self._device = _resolve_device(device if device != "auto" else settings.CLIP_DEVICE)
        self._model = None
        self._preprocess = None
        self._tokenizer = None

    def is_available(self) -> bool:
        """``open_clip`` 是否可导入（不触发模型加载）。"""
        try:
            import importlib.util

            return importlib.util.find_spec("open_clip") is not None
        except Exception:  # pragma: no cover - 防御性
            return False

    def _ensure_loaded(self) -> None:
        """首次调用时加载模型（约 600MB）。"""
        if self._model is not None:
            return
        import open_clip  # 延迟导入

        logger.info("正在加载 CLIP 模型（open_clip %s，首次加载约 600MB，请耐心等待）...", self.model_name)
        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            self.model_name,
            pretrained=self.pretrained,
        )
        self._model.eval()
        self._tokenizer = open_clip.get_tokenizer(self.model_name)
        self._model = self._model.to(self._device)
        logger.info("CLIP 模型加载完成，运行设备: %s", self._device)

    def encode_image(self, image_path: str) -> np.ndarray:
        """提取图像 ``embed_dim``（512）维特征向量（L2 归一化）。"""
        self._ensure_loaded()
        import torch
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        tensor = self._preprocess(image).unsqueeze(0).to(self._device)
        with torch.no_grad():
            features = self._model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        vec = features.cpu().numpy().flatten()
        # R4 运行期契约：归一化之后、返回之前，强制校验输出维度 == 声明维度
        _assert_embed_dim(vec, self.name, self.embed_dim, "CLIP_OPEN_EMBED_DIM")
        return vec

    def encode_text(self, text: str) -> np.ndarray:
        """提取文本 ``embed_dim``（512）维特征向量（L2 归一化）。"""
        self._ensure_loaded()
        import torch

        tokens = self._tokenizer([text]).to(self._device)
        with torch.no_grad():
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        vec = features.cpu().numpy().flatten()
        # R4 运行期契约：归一化之后、返回之前，强制校验输出维度 == 声明维度
        _assert_embed_dim(vec, self.name, self.embed_dim, "CLIP_OPEN_EMBED_DIM")
        return vec


# --------------------------------------------------------------------------- #
# Chinese-CLIP 后端（默认）
# --------------------------------------------------------------------------- #
#: Chinese-CLIP 文本塔结构串（``load_from_name`` 用本地 .pt 时必须显式提供）
_CN_TEXT_MODEL_NAME = "RoBERTa-wwm-ext-large-chinese"
#: Chinese-CLIP 视觉塔输入分辨率（本地 .pt 时必须显式提供）
_CN_INPUT_RESOLUTION = 224


class ChineseClipBackend:
    """基于 ``cn_clip``（OFA-Sys）的中文图文跨模态编码后端。

    权重来源有三条路径（优先级从高到低）：

    1. ``ckpt_path``  （``CLIP_CN_CKPT_PATH`` 非空）—— 直接加载本地 ``.pt``，**运行期零网络**；
    2. ``use_modelscope=True`` —— 走 ModelScope（国内直连，需 ``pip install modelscope``）；
    3. ``use_modelscope=False`` —— 走 HuggingFace Hub（``OFA-Sys/chinese-clip-vit-huge-patch14``）。

    Notes
    -----
    - **Lazy import**：``import cn_clip`` 只发生在 :meth:`_ensure_loaded` 内部。
    - ``cn_clip`` 返回的向量**未做 L2 归一化**，此处显式 ``features / norm``（与 ``open_clip`` 一致）。
    - ``context_length=52`` 时，``tokenize`` 采用 ``[CLS] + tokens[:50] + [SEP]``，
      即**实际可用内容 token 上限为 50 个**（≈50 个汉字），超长部分静默截断。
    """

    name = "cn_clip"
    # ViT-H-14 联合投影维度 = 1024（= encode_image / encode_text 的真实输出维度）。
    # 依据 cn_clip 自带 model_configs/ViT-H-14.json：embed_dim=1024 而 vision_width=1280，
    # 二者不等 → embed_dim 为**联合投影维度**；model.py 以 output_dim=embed_dim 建视觉塔、
    # 以 text_projection(..., embed_dim) 建文本投影 → 两个 encode_* 均输出 1024 维。
    # ⚠️ 该值来自**源码/配置推断**，未用真实 3.8GB 权重实测确认。
    embed_dim = settings.CLIP_CN_EMBED_DIM

    def __init__(
        self,
        model_name: Optional[str] = None,
        context_length: Optional[int] = None,
        download_root: Optional[str] = None,
        ckpt_path: Optional[str] = None,
        use_modelscope: Optional[bool] = None,
        device: str = "auto",
    ) -> None:
        self.model_name = model_name or settings.CLIP_CN_MODEL_NAME
        self.context_length = int(
            context_length if context_length is not None else settings.CLIP_CN_CONTEXT_LENGTH
        )
        self.download_root = (
            download_root if download_root is not None else settings.CLIP_CN_DOWNLOAD_ROOT
        )
        self.ckpt_path = ckpt_path if ckpt_path is not None else settings.CLIP_CN_CKPT_PATH
        self.use_modelscope = bool(
            use_modelscope if use_modelscope is not None else settings.CLIP_CN_USE_MODELSCOPE
        )
        self._device = _resolve_device(device if device != "auto" else settings.CLIP_DEVICE)
        self._model = None
        self._preprocess = None

    def is_available(self) -> bool:
        """``cn_clip`` 是否可导入（不触发模型加载）。"""
        try:
            import importlib.util

            return importlib.util.find_spec("cn_clip") is not None
        except Exception:  # pragma: no cover - 防御性
            return False

    def _ensure_loaded(self) -> None:
        """首次调用时加载模型（Lazy import ``cn_clip``）。"""
        if self._model is not None:
            return

        # ---- 铁律：唯一允许 import cn_clip 的地方 ----
        try:
            from cn_clip.clip import load_from_name
        except ImportError as exc:  # 未安装 → 抛清晰错误，绝不静默降级
            raise RuntimeError(
                "未安装 cn_clip 包，无法使用 Chinese-CLIP 后端。请任选其一：\n"
                "  1) pip install cn_clip --no-deps\n"
                "  2) pip install --no-deps git+https://github.com/OFA-Sys/Chinese-CLIP.git\n"
                "或把 CLIP_BACKEND 切回 'open_clip'（回滚路径）。"
            ) from exc

        load_kwargs: dict = {"device": self._device}
        if self.ckpt_path:
            # 本地 .pt：必须同时给出 vision/text model_name 与 input_resolution，
            # 否则 utils.create_model() 内 assert 失败。
            load_kwargs.update(
                {
                    "vision_model_name": self.model_name,
                    "text_model_name": _CN_TEXT_MODEL_NAME,
                    "input_resolution": _CN_INPUT_RESOLUTION,
                }
            )
            source = self.ckpt_path
        else:
            load_kwargs["download_root"] = self.download_root
            load_kwargs["use_modelscope"] = self.use_modelscope
            source = self.model_name

        logger.info(
            "正在加载 Chinese-CLIP 模型（model=%s, source=%s, modelscope=%s, device=%s，"
            "首次需下载约 3.8GB 权重）...",
            self.model_name,
            source,
            self.use_modelscope,
            self._device,
        )
        self._model, self._preprocess = load_from_name(source, **load_kwargs)
        self._model.eval()
        try:
            self._model = self._model.to(self._device)
        except Exception:  # pragma: no cover - 已在 device 上时幂等
            pass
        logger.info("Chinese-CLIP 模型加载完成，运行设备: %s", self._device)

    def encode_image(self, image_path: str) -> np.ndarray:
        """提取图像 ``embed_dim``（1024）维特征向量（L2 归一化）。"""
        self._ensure_loaded()
        import torch
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        tensor = self._preprocess(image).unsqueeze(0).to(self._device)
        with torch.no_grad():
            features = self._model.encode_image(tensor)
            features = features / features.norm(dim=-1, keepdim=True)
        vec = features.cpu().numpy().flatten()
        # R4 运行期契约：归一化之后、返回之前，强制校验输出维度 == 声明维度
        _assert_embed_dim(vec, self.name, self.embed_dim, "CLIP_CN_EMBED_DIM")
        return vec

    def encode_text(self, text: str) -> np.ndarray:
        """提取文本 ``embed_dim``（1024）维特征向量（L2 归一化）。

        文本实际可用长度为 ``context_length - 2``（默认 52 - 2 = 50 个汉字），
        超出部分被 ``tokenize`` 静默截断。
        """
        self._ensure_loaded()
        import torch
        from cn_clip.clip import tokenize

        tokens = tokenize([text], context_length=self.context_length).to(self._device)
        with torch.no_grad():
            features = self._model.encode_text(tokens)
            features = features / features.norm(dim=-1, keepdim=True)
        vec = features.cpu().numpy().flatten()
        # R4 运行期契约：归一化之后、返回之前，强制校验输出维度 == 声明维度
        _assert_embed_dim(vec, self.name, self.embed_dim, "CLIP_CN_EMBED_DIM")
        return vec


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #
def get_backend(settings) -> ClipBackend:
    """按 ``settings.CLIP_BACKEND`` 选择后端实现。

    Args:
        settings: 配置对象（``app.config.settings``）。

    Returns:
        ``OpenClipBackend`` 或 ``ChineseClipBackend`` 实例（**尚未加载模型**）。

    Raises:
        RuntimeError: 当 ``CLIP_BACKEND`` 取未知值时。新旧向量空间不兼容，
            **禁止静默降级**，必须显式暴露配置错误。
    """
    backend_name = str(getattr(settings, "CLIP_BACKEND", "") or "").strip().lower()
    if backend_name == "open_clip":
        return OpenClipBackend()
    if backend_name == "cn_clip":
        return ChineseClipBackend()
    raise RuntimeError(
        f"未知的 CLIP_BACKEND 取值: {getattr(settings, 'CLIP_BACKEND', None)!r}；"
        "合法取值为 'cn_clip' 或 'open_clip'。新旧模型向量空间不兼容，禁止静默降级。"
    )
