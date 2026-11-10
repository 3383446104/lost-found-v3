# backend/scripts/send_test_mail.py
"""发一封测试邮件，验证 SMTP 通路与 HTML 版式（答辩现场演示用）。

为什么单独有这个脚本
--------------------
邮件是「发布者收不到通知」这类问题最容易被忽略的一环：代码对了但 SMTP 没通、
或版式退化回纯文本，界面上完全看不出来（站内消息照常）。本脚本用**与线上完全相同的
模板与发信函数**发一封样张，30 秒内可确认：

1. SMTP 账号密码有效（`.env` 的 `MAIL_USERNAME` / `MAIL_PASSWORD`）；
2. 邮件是 HTML 卡片（品牌绿按钮）而不是纯文本；
3. 同时带 `text/plain` 副本（`multipart/alternative`），客户端不支持 HTML 时仍可读。

用法（backend 目录）::

    venv\\Scripts\\python.exe scripts\\send_test_mail.py                 # 发到 .env 里的发件邮箱
    venv\\Scripts\\python.exe scripts\\send_test_mail.py -t someone@qq.com
    venv\\Scripts\\python.exe scripts\\send_test_mail.py --title "自定义标题"
"""
from __future__ import annotations

import argparse
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
# app.config 按「相对 CWD」加载 .env，固定到 backend/，任意目录下都能跑
os.chdir(BACKEND_DIR)

from app.config import settings  # noqa: E402
from app.utils.email_utils import render_email_html, send_email  # noqa: E402

DEFAULT_TITLE = "[认领申请] 用户 'qhm' 想要认领您的物品"
DEFAULT_CONTENT = (
    "物品 '一本蓝色的笔记本' 收到认领申请。"
    "申请人描述物品特征：深蓝色硬壳，封面印着南京大学校徽，内页写了两页笔记。"
    "申请人联系方式：159****0538。请及时处理。"
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="发送一封 HTML 测试邮件")
    ap.add_argument("-t", "--to", default=settings.MAIL_USERNAME, help="收件地址（默认发件箱自己）")
    ap.add_argument("--title", default=DEFAULT_TITLE)
    ap.add_argument("--content", default=DEFAULT_CONTENT)
    ap.add_argument("--link", default="/items/95", help="按钮跳转的站内路径")
    args = ap.parse_args(argv)

    if not args.to:
        print("[×] 未指定收件人，且 .env 中 MAIL_USERNAME 为空")
        return 2

    body = render_email_html(args.title, args.content, link=args.link, cta="查看详情")
    print(f"[*] 收件人: {args.to}")
    print(f"[*] HTML 长度: {len(body)} 字节")
    ok = send_email(args.to, args.title, body, html=True, text=args.content)
    print("[✓] 发送成功，请到收件箱查看（QQ 邮箱注意「广告/垃圾邮件」文件夹）" if ok
          else "[×] 发送失败，详见上方日志（检查 SMTP 授权码/网络）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
