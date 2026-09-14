"""QA 独立回归（v3.5.0）——CLIP 后端维度自洽性（D）。

**不需要下载任何权重**：两个后端的「真实输出维度」由各自随包分发的
``model_configs/*.json`` 唯一确定——权重只影响数值、不影响输出形状。因此可用
「包内 config（外部真值）+ 同构小模型（机制证明）」两条互相独立的证据链推导，
确定性、零下载地判定 ``encode_image`` / ``encode_text`` 的真实输出维度。

独立推导链（R2 复检）
----------------------
1. **外部真值**（``model_configs/*.json``，不来自被测实现）：
   ``cn_clip`` ViT-H-14 ``embed_dim=1024``（且 ``vision_width=1280``）、
   RoBERTa-wwm-ext-large ``text_hidden_size=1024``；``open_clip`` ViT-B-32
   ``embed_dim=512``。
2. **机制证明**（构造同构小模型，仅用真值 ``embed_dim`` 作参数）：``CLIP`` 视觉塔
   以 ``output_dim=embed_dim`` 构造、文本投影为 ``(hidden_size, embed_dim)`` →
   ``encode_image`` / ``encode_text`` 的输出维度**都等于 embed_dim**。
   两条并起来 ⇒ 「真实模型输出 1024 / 512」。
3. **契约核验**：被测实现 ``ChineseClipBackend.embed_dim`` / ``OpenClipBackend.embed_dim``
   必须等于上述外部真值，且二者不等。实现一旦写错（如声明 512）即红。

> 反模式规避：**不把实现里的常量（``settings.CLIP_CN_EMBED_DIM`` 等）当期望值**——
> 那是「镜像实现」，实现错了断言也跟着错。期望值一律来自包内 config 或构造模型。

作者：yan-qa（本文件归 yan-qa 维护；R2 后由本人重新独立推导断言）。
"""
import importlib.util
import json
import os

import numpy as np
import pytest

from app.clip_backend import ChineseClipBackend, OpenClipBackend
from app.clip_service import clip_service
from app.config import settings

VISION_CFG = "ViT-H-14.json"
TEXT_CFG = "RoBERTa-wwm-ext-large-chinese.json"


# --------------------------------------------------------------------------- #
# 两个包各自的模型配置读取（真值来源，互不依赖被测代码）
# --------------------------------------------------------------------------- #
def _cn_clip_cfgdir():
    spec = importlib.util.find_spec("cn_clip")
    if spec is None or not spec.origin:
        pytest.skip("cn_clip 未安装，无法做静态维度核验")
    return os.path.join(os.path.dirname(spec.origin), "clip", "model_configs")


def _cn_cfg(name):
    with open(os.path.join(_cn_clip_cfgdir(), name), encoding="utf-8") as f:
        return json.load(f)


def _open_clip_cfg(model_name):
    import open_clip  # importorskip in caller

    base = os.path.dirname(open_clip.__file__)
    with open(os.path.join(base, "model_configs", f"{model_name}.json"), encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# 证据一：环境事实核验（真值来源为包内 config，不依赖被测代码；应恒绿）
# --------------------------------------------------------------------------- #
def test_D_cn_clip_vit_h_14_joint_embed_dim_is_1024():
    """cn_clip ViT-H-14 的联合嵌入维度 embed_dim = 1024。

    同时钉住「embed_dim 是**联合投影维度**而非视觉宽度」这一事实：ViT-H-14 的
    ``vision_width=1280 ≠ embed_dim=1024``。若有人误把视觉宽度当嵌入维度
    （把 ``CLIP_CN_EMBED_DIM`` 设成 1280），后文的「实现 == 真值」断言会一并变红。
    """
    vis = _cn_cfg(VISION_CFG)
    assert vis["embed_dim"] == 1024
    assert vis["vision_width"] != vis["embed_dim"], "embed_dim 不应等于视觉宽度（1280）"
    assert _cn_cfg(TEXT_CFG)["text_hidden_size"] == 1024


def test_D_open_clip_vit_b_32_joint_embed_dim_is_512():
    """open_clip ViT-B-32 的联合嵌入维度 embed_dim = 512（回滚路径的真值来源）。"""
    pytest.importorskip("open_clip")
    assert _open_clip_cfg("ViT-B-32")["embed_dim"] == 512


# --------------------------------------------------------------------------- #
# 证据二：机制证明（同构小模型，参数取自真值；证明两个 encode_* 输出 == embed_dim）
# --------------------------------------------------------------------------- #
def _tiny_cn_clip_model(embed_dim):
    """构造一个结构同构、参数极小的 ``cn_clip.clip.model.CLIP`` 实例。

    仅保留与「输出维度」相关的结构：视觉塔 ``output_dim=embed_dim``、文本
    ``text_projection`` 形状 ``(text_hidden_size, embed_dim)``；其余超参（层数/宽度/
    隐藏维度）缩小以秒级构建。**权重不加载**（随机初始化），因为输出形状与权重无关。
    """
    torch = pytest.importorskip("torch")
    from cn_clip.clip.model import CLIP

    text_cfg = dict(_cn_cfg(TEXT_CFG))
    text_cfg.update(
        text_hidden_size=64,          # 输出维度对 embed_dim，与 hidden_size 无关
        text_num_attention_heads=4,
        text_num_hidden_layers=1,
        text_intermediate_size=128,
        text_max_position_embeddings=16,
    )
    cfg = dict(
        embed_dim=embed_dim,          # ← 唯一取自真值、不可缩放的维度
        image_resolution=32,
        vision_layers=1,
        vision_width=64,
        vision_patch_size=16,
        vision_head_width=64,
    )
    cfg.update(text_cfg)
    model = CLIP(**cfg)
    model.eval()
    return torch, model


def test_D_cn_clip_model_both_encoders_output_embed_dim():
    """``CLIP.encode_image`` 与 ``CLIP.encode_text`` 的输出维度都等于 ``embed_dim``。

    ``embed_dim`` 取自真值（ViT-H-14 config = 1024）。这补齐了「config.embed_dim →
    模型输出维度」这一环：单看 config 只能知道「配置声明」，本用例证明「该配置下模型
    确实按 embed_dim 输出」——二者合一才能推出「真实模型输出 1024 维」。
    """
    embed_dim = _cn_cfg(VISION_CFG)["embed_dim"]
    torch, model = _tiny_cn_clip_model(embed_dim)
    with torch.no_grad():
        img_feat = model.encode_image(torch.randn(1, 3, 32, 32))
        txt_feat = model.encode_text(torch.tensor([[101, 704, 2245, 102]]))
    assert tuple(img_feat.shape) == (1, embed_dim), (
        f"encode_image 输出 {tuple(img_feat.shape)}，应为 (1, {embed_dim})"
    )
    assert tuple(txt_feat.shape) == (1, embed_dim), (
        f"encode_text 输出 {tuple(txt_feat.shape)}，应为 (1, {embed_dim})"
    )


# --------------------------------------------------------------------------- #
# 证据三：维度契约（实现声明 == 外部真值，且两后端维度不同）
# --------------------------------------------------------------------------- #
def test_D_cn_backend_declares_real_embed_dim():
    """``ChineseClipBackend.embed_dim`` 必须等于 cn_clip ViT-H-14 真实输出维度（1024）。

    历史：R2 前 ``clip_backend.py`` 声明为 512（错误）；R2 改为 ``settings.CLIP_CN_EMBED_DIM``。
    本断言以 **config 外部真值** 为期望（非实现常量），故实现若再写错（如写死 512）必红。
    """
    real_dim = _cn_cfg(VISION_CFG)["embed_dim"]
    assert ChineseClipBackend.embed_dim == real_dim, (
        f"ChineseClipBackend.embed_dim={ChineseClipBackend.embed_dim} 与真实 {real_dim} 不一致"
    )


def test_D_open_backend_declares_real_embed_dim_and_dims_differ():
    """``OpenClipBackend.embed_dim`` 必须等于 open_clip ViT-B-32 真实维度（512），
    且两后端维度必须不同（换模型 = 换嵌入空间维度）。
    """
    pytest.importorskip("open_clip")
    real_open = _open_clip_cfg(settings.CLIP_OPEN_MODEL_NAME)["embed_dim"]
    real_cn = _cn_cfg(VISION_CFG)["embed_dim"]
    assert OpenClipBackend.embed_dim == real_open == 512
    assert ChineseClipBackend.embed_dim == real_cn
    assert OpenClipBackend.embed_dim != ChineseClipBackend.embed_dim
    assert {OpenClipBackend.embed_dim, ChineseClipBackend.embed_dim} == {512, 1024}


# --------------------------------------------------------------------------- #
# 纯函数层：维度不同的向量做点积必须显式报错（而非静默垃圾）
# --------------------------------------------------------------------------- #
def test_D_dim_mismatch_raises_in_dot():
    """维度不同（1024 vs 512，均取自外部真值）的向量做 ``np.dot`` → 抛 ValueError；
    维度相同时**不抛**（正向对照，排除「报错来自其它原因」）。
    """
    cn_dim = _cn_cfg(VISION_CFG)["embed_dim"]
    pytest.importorskip("open_clip")
    open_dim = _open_clip_cfg(settings.CLIP_OPEN_MODEL_NAME)["embed_dim"]
    assert cn_dim != open_dim

    q_img = np.ones(cn_dim, dtype=np.float32)
    stale = np.ones(open_dim, dtype=np.float32)
    with pytest.raises(ValueError):
        clip_service.compute_weighted_similarity(q_img, None, stale, None)

    # 正向对照：同维度点积正常返回数值（证明上面的 ValueError 确由「维度不符」触发）
    ok = clip_service.compute_weighted_similarity(
        q_img, None, np.ones(cn_dim, dtype=np.float32), None
    )
    assert isinstance(ok, float)
