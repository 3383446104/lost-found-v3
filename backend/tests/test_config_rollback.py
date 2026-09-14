"""配置参数化与回滚单测（T05）——不加载真实模型。

覆盖设计 §5.6 / §3.1：
- ``CLIP_BACKEND=open_clip`` 返回 ``OpenClipBackend``（回滚可用）；
- ``CLIP_BACKEND=cn_clip`` 返回 ``ChineseClipBackend``；
- 未知取值抛 ``RuntimeError``（禁止静默降级）；
- ``cn_clip`` 为 lazy import（构造后端不触发 ``import cn_clip``）；
- 前端图例派生（C5）。
"""
import sys

import pytest

from app import clip_backend
from app.clip_service import clip_service
from app.config import settings


def test_open_clip_backend_selected(monkeypatch):
    monkeypatch.setattr(settings, "CLIP_BACKEND", "open_clip")
    backend = clip_backend.get_backend(settings)
    assert isinstance(backend, clip_backend.OpenClipBackend)
    assert backend.name == "open_clip"
    assert backend.embed_dim == settings.CLIP_OPEN_EMBED_DIM == 512
    assert backend.model_name == settings.CLIP_OPEN_MODEL_NAME


def test_cn_clip_backend_selected(monkeypatch):
    monkeypatch.setattr(settings, "CLIP_BACKEND", "cn_clip")
    backend = clip_backend.get_backend(settings)
    assert isinstance(backend, clip_backend.ChineseClipBackend)
    assert backend.name == "cn_clip"
    assert backend.embed_dim == settings.CLIP_CN_EMBED_DIM == 1024
    assert backend.context_length == settings.CLIP_CN_CONTEXT_LENGTH


def test_unknown_backend_raises_runtime_error(monkeypatch):
    monkeypatch.setattr(settings, "CLIP_BACKEND", "definitely_not_a_backend")
    with pytest.raises(RuntimeError):
        clip_backend.get_backend(settings)


def test_cn_clip_is_lazy_imported(monkeypatch):
    """构造 ChineseClipBackend 不得在模块/构造期导入 cn_clip。

    顺序无关化：同一会话内其它用例可能已把 ``cn_clip`` 导入 ``sys.modules``
    （如 ``test_qa_v350_dimension`` 的架构静态核验），故先清掉残留，
    再验证「**本次构造**」不触发 lazy import，避免用例因执行顺序不同而假红。
    """
    sys.modules.pop("cn_clip", None)  # 隔离外部污染，使本用例与执行顺序无关
    monkeypatch.setattr(settings, "CLIP_BACKEND", "cn_clip")
    backend = clip_backend.ChineseClipBackend()
    # 仅构造，不调用 encode_* → 不应触发 lazy import
    assert backend._model is None
    assert "cn_clip" not in sys.modules, "顶层/构造期不得 import cn_clip"


def test_legend_derived_from_thresholds(monkeypatch):
    from app.api.items import resolve_legend

    monkeypatch.setattr(settings, "MATCH_LEGEND_HIGH", None)
    monkeypatch.setattr(settings, "MATCH_LEGEND_MID", None)
    monkeypatch.setattr(settings, "MATCH_THRESHOLD_AUTO", 0.55)
    monkeypatch.setattr(settings, "MATCH_THRESHOLD_MANUAL", 0.35)
    legend = resolve_legend()
    assert legend == {"high": 0.55, "mid": 0.35}


def test_legend_override(monkeypatch):
    from app.api.items import resolve_legend

    monkeypatch.setattr(settings, "MATCH_LEGEND_HIGH", 0.9)
    monkeypatch.setattr(settings, "MATCH_LEGEND_MID", 0.6)
    assert resolve_legend() == {"high": 0.9, "mid": 0.6}


def test_weights_read_from_config(monkeypatch):
    """权重只从 config 读：改 settings 即改变打分。"""
    monkeypatch.setattr(settings, "CROSS_PENALTY_ENABLED", False)
    import numpy as np

    q = np.zeros(512, dtype=np.float32); q[0] = 1.0
    t = np.zeros(512, dtype=np.float32); t[0] = 1.0

    monkeypatch.setattr(settings, "MATCH_W_IMG_IMG", 1.0)
    monkeypatch.setattr(settings, "MATCH_W_CROSS", 0.0)
    monkeypatch.setattr(settings, "MATCH_W_TEXT_TEXT", 0.0)
    monkeypatch.setattr(settings, "MATCH_W_COLOR", 0.0)
    assert clip_service.compute_weighted_similarity(q, None, t, None) == pytest.approx(1.0, abs=1e-6)
