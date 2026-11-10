# tests/test_clip_load_singleflight.py
"""v3.6.3：CLIP 模型加载「单飞」与启动预热。

背景
----
`ChineseClipBackend._ensure_loaded` 原先只有 ``if self._model is not None: return``，
两个并发请求会**各加载一份 3.6GB 模型**（日志 2026-10-18 09:06/09:07 实测：两次
「正在加载」+ 两次「加载完成」，14.46s / 24.65s，内存翻倍）。本组用例锁住修复后的语义：

1. 并发调用 ``_ensure_loaded`` 时 ``_load_model`` 只执行**一次**；
2. 已加载后走快路径，不再取锁；
3. 预热失败只记日志，不向调用方抛异常（否则会拖垮启动流程）。
"""
import threading
import time


from app.clip_backend import ChineseClipBackend


def _make_backend() -> ChineseClipBackend:
    """构造后端但**不加载模型**。

    ``device="cpu"`` 显式指定，避免 ``_resolve_device("auto")`` 触发 ``import torch``
    （测试套件不需要真实 torch，那会让本文件多花数秒）。
    """
    return ChineseClipBackend(device="cpu")


def test_ensure_loaded_loads_once_under_concurrency(monkeypatch):
    """5 个线程同时触发加载 → ``_load_model`` 只执行 1 次（单飞 + 双检）。"""
    backend = _make_backend()
    calls = []

    def fake_load_model():
        calls.append(threading.current_thread().name)
        time.sleep(0.2)  # 模拟真实加载窗口（实际 8~18s），留出并发抢锁的机会
        backend._model = object()

    monkeypatch.setattr(backend, "_load_model", fake_load_model)

    threads = [
        threading.Thread(target=backend._ensure_loaded, name=f"w{i}")
        for i in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(calls) == 1, f"应只加载一次，实际 {len(calls)} 次：{calls}"
    assert backend._model is not None


def test_ensure_loaded_fast_path_skips_lock_when_loaded(monkeypatch):
    """已加载后直接返回，不再进入临界区（不阻塞正常业务请求）。"""
    backend = _make_backend()
    backend._model = object()

    entered = []
    monkeypatch.setattr(backend, "_load_model", lambda: entered.append(1))

    backend._ensure_loaded()  # 已有模型 → 快路径
    assert entered == []


def test_warmup_failure_does_not_raise(monkeypatch):
    """预热失败不得抛出（预热是优化项，不能阻断启动）。"""
    from app import main as main_module

    def boom(_text):
        raise RuntimeError("模拟模型缺失")

    monkeypatch.setattr(main_module.clip_service, "get_text_feature", boom)

    main_module._warmup_clip_model()  # 不抛即通过


def test_warmup_invokes_text_encoder(monkeypatch):
    """预热确实走一次文本编码（加载模型 + 首次前向）。"""
    from app import main as main_module

    seen = []
    monkeypatch.setattr(
        main_module.clip_service, "get_text_feature", lambda text: seen.append(text)
    )

    main_module._warmup_clip_model()
    assert len(seen) == 1 and seen[0] == main_module._CLIP_WARMUP_TEXT


def test_warmup_enabled_by_default():
    """默认开启预热；可显式关闭回滚到懒加载。"""
    from app.config import settings

    assert settings.CLIP_WARMUP_ENABLED is True
