"""R4：``embed_dim`` 运行期契约——把「声明」变成「被强制执行的契约」。

背景：``embed_dim`` 此前**只被声明、无任何运行期校验**。R2 修的那类 bug（声明 512、
实际 1024）当初不会被任何断言拦住，纯靠人读源码才发现。R4 在 ``encode_*`` 归一化之后、
返回之前加了 :func:`_assert_embed_dim`，本文件即证明该防线**不是摆设**：

- 打桩一个返回**错误长度**向量的后端 → 断言抛出**明确错误**（含后端名 / 期望维度 /
  实际维度 / config 键），而非静默通过；
- 长度正确时正常返回，证明断言并非「永远抛」。

作者：software-engineer（R4）。
"""
import numpy as np
import pytest

from app.clip_backend import ChineseClipBackend, OpenClipBackend, _assert_embed_dim


# --------------------------------------------------------------------------- #
# 契约辅助函数：报文完整性
# --------------------------------------------------------------------------- #
def test_assert_embed_dim_direct_mismatch_message():
    """维度不符时，报文须含后端名、期望维度、实际维度、config 键。"""
    vec = np.ones(100, dtype=np.float32)
    with pytest.raises(RuntimeError) as ei:
        _assert_embed_dim(vec, "cn_clip", 1024, "CLIP_CN_EMBED_DIM")
    msg = str(ei.value)
    assert "cn_clip" in msg
    assert "1024" in msg          # 期望维度
    assert "100" in msg           # 实际维度
    assert "CLIP_CN_EMBED_DIM" in msg


def test_assert_embed_dim_matching_passes():
    """维度相符时不得抛异常。"""
    vec = np.ones(512, dtype=np.float32)
    _assert_embed_dim(vec, "open_clip", 512, "CLIP_OPEN_EMBED_DIM")  # 不抛即通过


# --------------------------------------------------------------------------- #
# open_clip 后端：错误长度 → 真触发明确错误
# --------------------------------------------------------------------------- #
class _FakeModel:
    """打桩模型：encode_* 返回**任意指定长度**的向量（忽略输入）。"""

    def __init__(self, out_dim: int) -> None:
        self.out_dim = out_dim

    def encode_text(self, _tokens):  # noqa: ANN001
        import torch

        return torch.ones(1, self.out_dim)

    def encode_image(self, _tensor):  # noqa: ANN001
        import torch

        return torch.ones(1, self.out_dim)


def _stub_openclip(monkeypatch, backend: OpenClipBackend, out_dim: int) -> None:
    """把 open_clip 后端打桩成「不加载模型、直接返回 out_dim 维向量」。"""
    import torch

    monkeypatch.setattr(backend, "_ensure_loaded", lambda: None)
    backend._device = "cpu"
    backend._tokenizer = lambda texts: torch.zeros(len(texts), 3)
    backend._preprocess = lambda _img: torch.zeros(3, 8, 8)
    backend._model = _FakeModel(out_dim)


def test_open_clip_encode_text_wrong_dim_raises(monkeypatch):
    """open_clip encode_text 返回错误长度（999≠512）→ 抛明确错误。"""
    backend = OpenClipBackend()
    _stub_openclip(monkeypatch, backend, out_dim=999)
    with pytest.raises(RuntimeError) as ei:
        backend.encode_text("任意文本")
    msg = str(ei.value)
    assert "[open_clip]" in msg
    assert "512" in msg and "999" in msg and "CLIP_OPEN_EMBED_DIM" in msg


def test_open_clip_encode_image_wrong_dim_raises(monkeypatch, tmp_path):
    """open_clip encode_image 返回错误长度（777≠512）→ 抛明确错误。"""
    from PIL import Image

    backend = OpenClipBackend()
    _stub_openclip(monkeypatch, backend, out_dim=777)
    img_path = tmp_path / "dummy.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(img_path)
    with pytest.raises(RuntimeError) as ei:
        backend.encode_image(str(img_path))
    msg = str(ei.value)
    assert "[open_clip]" in msg
    assert "512" in msg and "777" in msg and "CLIP_OPEN_EMBED_DIM" in msg


def test_open_clip_encode_text_ok_when_dim_matches(monkeypatch):
    """长度正确（512）→ 正常返回，证明断言并非「永远抛」。"""
    backend = OpenClipBackend()
    _stub_openclip(monkeypatch, backend, out_dim=backend.embed_dim)
    vec = backend.encode_text("任意文本")
    assert vec.shape == (backend.embed_dim,)
    assert float(np.linalg.norm(vec)) == pytest.approx(1.0, abs=1e-5)


# --------------------------------------------------------------------------- #
# Chinese-CLIP 后端：错误长度 → 真触发明确错误
# --------------------------------------------------------------------------- #
def test_cn_clip_encode_text_wrong_dim_raises(monkeypatch):
    """cn_clip encode_text 返回错误长度（5≠1024）→ 抛明确错误。"""
    pytest.importorskip("cn_clip")
    import torch

    backend = ChineseClipBackend()
    monkeypatch.setattr(backend, "_ensure_loaded", lambda: None)
    backend._device = "cpu"
    backend._model = _FakeModel(out_dim=5)
    with pytest.raises(RuntimeError) as ei:
        backend.encode_text("任意文本")
    msg = str(ei.value)
    assert "[cn_clip]" in msg
    assert "1024" in msg and "5" in msg and "CLIP_CN_EMBED_DIM" in msg


def test_cn_clip_encode_image_wrong_dim_raises(monkeypatch, tmp_path):
    """cn_clip encode_image 返回错误长度（2048≠1024）→ 抛明确错误。"""
    pytest.importorskip("cn_clip")
    import torch
    from PIL import Image

    backend = ChineseClipBackend()
    monkeypatch.setattr(backend, "_ensure_loaded", lambda: None)
    backend._device = "cpu"
    backend._preprocess = lambda _img: torch.zeros(3, 8, 8)
    backend._model = _FakeModel(out_dim=2048)
    img_path = tmp_path / "dummy.png"
    Image.new("RGB", (8, 8), (1, 2, 3)).save(img_path)
    with pytest.raises(RuntimeError) as ei:
        backend.encode_image(str(img_path))
    msg = str(ei.value)
    assert "[cn_clip]" in msg
    assert "1024" in msg and "2048" in msg and "CLIP_CN_EMBED_DIM" in msg
