# -*- coding: utf-8 -*-
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright

token = sys.argv[1]

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    ctx = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = ctx.new_page()
    page.add_init_script(
        "localStorage.setItem('access_token', %s);"
        "localStorage.setItem('user_info', '%s');" % (
            json.dumps(token),
            json.dumps({"id": 1, "username": "final_test", "role": "user", "status": "active"}),
        )
    )
    page.goto('http://localhost:5173/items', wait_until='domcontentloaded')
    page.wait_for_timeout(4500)

    cards = page.locator('.recommend-card')
    print('推荐卡片数:', cards.count())
    for i in range(cards.count()):
        c = cards.nth(i)
        has_img = c.locator('img').count() > 0
        title = c.locator('.recommend-item-title')
        meta = c.locator('.recommend-meta')
        print(f"卡片{i}: 有图={has_img} 标题='{title.inner_text() if title.count() else '-'}' 分类='{meta.inner_text() if meta.count() else '-'}'")
    browser.close()
