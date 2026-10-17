"""真实 Chinese-CLIP 冒烟测试（T05）——**默认 skip**。

仅在显式设置环境变量时运行（会加载约 3.8GB 权重）::

    set RUN_REAL_CLIP=1
    venv\\Scripts\\python.exe -m pytest tests\\test_real_clip_smoke.py -v

未设置时全部 skip，CI 不下载权重。
"""
import os
import sys
import tempfile

import numpy as np
import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_REAL_CLIP"), reason="需真实权重（设置 RUN_REAL_CLIP=1 启用）"
)

PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _active_embed_dim() -> int:
    """当前后端声明的嵌入维度（R2：cn_clip=1024 / open_clip=512），构造后端不加载模型。"""
    from app.clip_backend import get_backend
    from app.config import settings

    return int(get_backend(settings).embed_dim)


def test_real_image_embedding_dim_l2_normalized():
    from app.clip_service import clip_service

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(PNG_1X1)
        path = f.name
    try:
        vec = clip_service.get_image_feature(path)
    finally:
        os.unlink(path)
    assert vec.shape == (_active_embed_dim(),)
    assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-3)


def test_real_long_text_embedding_dim_l2_normalized():
    from app.clip_service import clip_service

    long_text = (
        "黑色真皮长款钱包，正面有一条金属拉链和一个圆形银色徽章，"
        "里面夹着一张蓝色校园卡和两张银行卡，边角略有磨损，"
        "是我在图书馆三楼自习时丢的，非常重要，希望能找回。"
    )
    assert len(long_text) >= 33
    vec = clip_service.get_text_feature(long_text)
    assert vec.shape == (_active_embed_dim(),)
    assert np.isclose(np.linalg.norm(vec), 1.0, atol=1e-3)
