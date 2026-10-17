"""重嵌入脚本「编码器接线 + 失败不静默」契约守卫（纯测试，**不加载真实模型**）。

背景（v3.5.0 真实权重实测暴露的**同型缺陷第 4 例**）
--------------------------------------------------
``scripts/reembed_all_vectors.py`` 原按 ``encoder.encode_image/encode_text`` 调用；
真实 ``clip_service`` 只有 ``get_image_feature/get_text_feature``。干跑实测 ``ok=0 /
failed_encode=12``，且 ``main()`` 恒返回 0 ⇒ 真跑会「成功退出」但**一条都没迁移**
（假绿迁移）。

本文件锁死两点：
  A. :class:`_ServiceEncoderAdapter` 正确把 ``clip_service`` 的冻结接口接到
     ``encode_image/encode_text``，且 ``name/model_name`` 委托给后端（断点指纹安全）。
  B. :func:`_exit_code` 在真跑时：``failed_encode>0`` 退出码 2、``ok==0 且 total>0``
     退出码 3，**禁止**恒返回 0。

作者：team-lead（齐活林）—— 修复者自留守卫。
"""
import importlib.util
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(BACKEND_DIR, "scripts")
for _p in (BACKEND_DIR, SCRIPTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_reembed():
    name = "_script_reembed_guard"
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(SCRIPTS_DIR, "reembed_all_vectors.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


reembed = _load_reembed()


# --------------------------------------------------------------------------- #
# 适配器接线（防「假编码器定义接口、真实编码器从未接上」复发）
# --------------------------------------------------------------------------- #
class _StubBackend:
    name = "cn_clip"
    model_name = "ViT-H-14"


class _StubService:
    """最小可观测的 ``clip_service`` 替身：记录所有调用，``get_backend`` 返回缓存。"""

    def __init__(self):
        self.image_calls = []
        self.text_calls = []
        self.backend_calls = 0
        self._backend = _StubBackend()  # 缓存：真实 CLIPService 也返回同一实例

    def get_backend(self):
        self.backend_calls += 1
        return self._backend

    def get_image_feature(self, path):
        self.image_calls.append(path)
        return [0.1, 0.2]

    def get_text_feature(self, text):
        self.text_calls.append(text)
        return [0.3, 0.4]


def test_adapter_encode_image_delegates_to_get_image_feature():
    enc = reembed._ServiceEncoderAdapter(_StubService())
    assert enc.encode_image("uploads/x.jpg") == [0.1, 0.2]


def test_adapter_encode_text_delegates_to_get_text_feature():
    enc = reembed._ServiceEncoderAdapter(_StubService())
    assert enc.encode_text("描述") == [0.3, 0.4]


def test_adapter_name_model_name_delegate_to_backend():
    """委托给真实后端：``name/model_name`` 写死会破坏 ``model_fingerprint`` 的断点安全。"""
    enc = reembed._ServiceEncoderAdapter(_StubService())
    assert enc.name == "cn_clip"
    assert enc.model_name == "ViT-H-14"


def test_adapter_get_backend_passthrough_for_fingerprint_path():
    enc = reembed._ServiceEncoderAdapter(_StubService())
    assert enc.get_backend() is enc.service.get_backend()


# --------------------------------------------------------------------------- #
# 失败退出码（防「恒返回 0 ⇒ 假绿迁移」复发）
# --------------------------------------------------------------------------- #
def test_exit_code_dry_run_always_zero_even_with_failures():
    """``--dry-run`` 是只读预览，失败只提示不判失败（避免干跑直接 exit 非 0 吓到人）。"""
    s = reembed.ReembedStats(ok=0, failed_encode=99, total=99)
    assert reembed._exit_code(s, dry_run=True) == 0


def test_exit_code_any_failed_encode_returns_2():
    """真跑时任何编码失败 ⇒ 退出码 2（部分迁移 = 新旧维度混杂，比统一旧维度更危险）。"""
    s = reembed.ReembedStats(ok=3, failed_encode=2, total=5)
    assert reembed._exit_code(s, dry_run=False) == 2


def test_exit_code_total_positive_but_zero_ok_returns_3():
    """真跑时一条都没成功 ⇒ 退出码 3（等于没迁移）。"""
    s = reembed.ReembedStats(ok=0, failed_encode=0, total=5)
    assert reembed._exit_code(s, dry_run=False) == 3


def test_exit_code_full_success_returns_zero():
    s = reembed.ReembedStats(ok=6, failed_encode=0, total=6)
    assert reembed._exit_code(s, dry_run=False) == 0
