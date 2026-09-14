"""下载 Chinese-CLIP 预训练权重到 ``backend/models/``，支持断点续传。

背景
----
v3.5.0 将匹配模型的图像/文本编码器切换为 Chinese-CLIP（OFA-Sys）。
真实权重体积大（ViT-H/14 约 3.83GB），本机此前未能下载，
导致所有结论停留在「已打桩验证」档。本脚本用于补齐这一环。

设计要点
--------
1. **零新增依赖**：只用标准库 ``urllib``，不需要 ``modelscope`` 包。
2. **断点续传**：依赖 ModelScope 的 HTTP Range（206）支持；
   若服务端忽略 Range 返回 200，则自动从头重下，避免拼接出损坏文件。
3. **落盘即生产路径**：下载到 ``backend/models/<file>``，
   随后仅需 ``CLIP_CN_CKPT_PATH`` 指向该文件，即可零网络加载
   （见 ``app/clip_backend.py`` 的权重加载优先级：
   ``CLIP_CN_CKPT_PATH`` > ``CLIP_CN_USE_MODELSCOPE`` > HF Hub）。

用法::

    venv\\Scripts\\python.exe scripts\\download_cn_clip_weights.py
    venv\\Scripts\\python.exe scripts\\download_cn_clip_weights.py --variant vit-base
    venv\\Scripts\\python.exe scripts\\download_cn_clip_weights.py --verify-only
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

# 仓库 ID -> (文件名, 字节数)。字节数取自 ModelScope 文件列表 API，
# 用于最终校验与断点位置推算，不得凭记忆填写。
VARIANTS = {
    "vit-huge": ("AI-ModelScope/chinese-clip-vit-huge-patch14", "clip_cn_vit-h-14.pt", 3830716726),
    # vit-base 的精确字节数未实测，留 None 由远端 Content-Range 决定
    "vit-base": ("AI-ModelScope/chinese-clip-vit-base-patch16", "clip_cn_vit-b-16.pt", None),
}

_REPO_URL = (
    "https://modelscope.cn/api/v1/models/{repo}/repo"
    "?Revision=master&FilePath={path}"
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) lost-found-v3 weight fetcher"


def _project_root() -> str:
    """返回 ``backend/`` 目录（本脚本位于 ``backend/scripts/``）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _target_path(filename: str) -> str:
    return os.path.join(_project_root(), "models", filename)


def _remote_size(url: str, timeout: int = 30) -> Optional[int]:
    """通过 HEAD/首字节探测远端总大小；失败返回 None。"""
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            cr = resp.headers.get("Content-Range")  # e.g. bytes 0-0/3830716726
            if cr and "/" in cr:
                return int(cr.rsplit("/", 1)[1])
            cl = resp.headers.get("Content-Length")
            return int(cl) if cl else None
    except Exception:
        return None


def _fmt(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return "%.2f %s" % (n, unit)
        n /= 1024.0
    return "%.2f GB" % n


def download(variant: str, expected_size: Optional[int], timeout: int = 60) -> int:
    repo, filename, default_size = VARIANTS[variant]
    url = _REPO_URL.format(repo=repo, path=filename)
    dest = _target_path(filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)

    total = _remote_size(url) or default_size or expected_size
    if expected_size:
        total = expected_size

    start = os.path.getsize(dest) if os.path.exists(dest) else 0

    # 已完整，直接返回
    if total and start == total:
        print("[skip] 已存在且大小一致：%s (%s)" % (dest, _fmt(start)))
        return 0
    if total and start > total:
        print("[warn] 本地文件比远端大（%s > %s），从头重下以排除损坏。"
              % (_fmt(start), _fmt(total)))
        start = 0

    headers = {"User-Agent": _UA}
    if start:
        headers["Range"] = "bytes=%d-" % start

    print("[info] 仓库      : %s" % repo)
    print("[info] 目标文件  : %s" % dest)
    print("[info] 远端总大小: %s" % (_fmt(total) if total else "未知"))
    print("[info] 起始偏移  : %s%s" % (_fmt(start), "（断点续传）" if start else "（全新下载）"))

    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    written = start
    last_report = t0

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # 服务端忽略 Range 返回 200 -> 必须从头写，否则会拼接出损坏文件
            if start and resp.status == 200:
                print("[warn] 服务端未响应 Range（200），改为从头下载。")
                start = 0
                written = 0
                mode = "wb"
            else:
                mode = "ab" if start else "wb"

            with open(dest, mode) as fh:
                while True:
                    chunk = resp.read(262144)
                    if not chunk:
                        break
                    fh.write(chunk)
                    written += len(chunk)

                    now = time.time()
                    if now - last_report >= 5.0:
                        el = now - t0
                        speed = (written - start) / el if el > 0 else 0
                        if total:
                            pct = written * 100.0 / total
                            eta = (total - written) / speed if speed > 0 else 0
                            print("[progress] %6.2f%%  %s / %s  %s/s  ETA %s"
                                  % (pct, _fmt(written), _fmt(total),
                                     _fmt(speed), _fmt_time(eta)), flush=True)
                        else:
                            print("[progress] %s  %s/s" % (_fmt(written), _fmt(speed)),
                                  flush=True)
                        last_report = now
    except urllib.error.HTTPError as e:
        if e.code == 416:  # Range 超出 -> 本地可能已完整
            print("[warn] 416 Range 越界，本地文件可能已完整，请用 --verify-only 确认。")
            return 2
        print("[error] HTTP %s: %s" % (e.code, e))
        return 1
    except Exception as e:
        print("[error] 下载中断：%s: %s" % (type(e).__name__, e))
        print("[hint] 直接重跑本脚本即可从 %s 处续传。" % _fmt(
            os.path.getsize(dest) if os.path.exists(dest) else 0))
        return 1

    el = time.time() - t0
    final = os.path.getsize(dest)
    print("[done] 已写入 %s，用时 %.1fs（平均 %s/s）"
          % (_fmt(final), el, _fmt((final - start) / el if el > 0 else 0)))

    if total and final != total:
        print("[error] 大小不匹配：本地 %s != 远端 %s。请重跑续传。"
              % (_fmt(final), _fmt(total)))
        return 1
    print("[ok] 校验通过，大小一致。")
    return 0


def _fmt_time(sec: float) -> str:
    sec = int(max(sec, 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%dh%02dm" % (h, m)
    if m:
        return "%dm%02ds" % (m, s)
    return "%ds" % s


def verify(variant: str) -> int:
    _, filename, default_size = VARIANTS[variant]
    dest = _target_path(filename)
    if not os.path.exists(dest):
        print("[fail] 不存在：%s" % dest)
        return 1
    size = os.path.getsize(dest)
    ok = size == default_size
    print("[%s] %s  本地 %s / 期望 %s"
          % ("ok" if ok else "fail", dest, _fmt(size), _fmt(default_size)))
    if ok:
        print("[hint] 设置 CLIP_CN_CKPT_PATH=%s 即可零网络加载。" % dest)
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="下载 Chinese-CLIP 权重到 backend/models/（支持断点续传）")
    p.add_argument("--variant", choices=sorted(VARIANTS), default="vit-huge",
                   help="要下载的变体（默认 vit-huge）")
    p.add_argument("--size", type=int, default=None,
                   help="覆盖期望字节数（一般不需要）")
    p.add_argument("--timeout", type=int, default=60, help="读超时秒数（默认 60）")
    p.add_argument("--verify-only", action="store_true",
                   help="只校验本地文件大小，不下载")
    args = p.parse_args(argv)

    if args.verify_only:
        return verify(args.variant)
    return download(args.variant, args.size, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
