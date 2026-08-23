# -*- coding: utf-8 -*-
"""
通用浏览器爬虫模板
==================
针对具体站需要改以下几处：
  1. TARGET_URL：入口页面 URL
  2. COOKIE_FILE：cookie.txt 路径
  3. BROWSER_PROFILE：playwright user data 目录
  4. META_PATH：元数据输出
  5. DATA_EXTRACTOR：怎么从页面里拿数据（fetch API / 滚动 / 解析 DOM）
  6. RESOURCE_DOWNLOADER：怎么下载资源（CDN URL 模式）

具体写法见 references/playwright-cookbook.md。

用法：
  1. 复制本文件到 my_crawler.py
  2. 编辑顶部配置 + DATA_EXTRACTOR + RESOURCE_DOWNLOADER
  3. python my_crawler.py
"""

import json
import os
import sys
import time
from pathlib import Path

# ============== 用户配置（按需改） ==============
TARGET_URL      = "https://example.com/path"
COOKIE_FILE     = Path("cookie.txt")
BROWSER_PROFILE = Path("_browser_profile")
META_PATH       = Path("_meta.json")
# ================================================


def load_cookies():
    """读 cookie.txt，转成 playwright add_cookies 需要的列表。"""
    if not COOKIE_FILE.exists():
        return []
    raw = COOKIE_FILE.read_text(encoding="utf-8").strip()
    out = []
    for kv in raw.split(";"):
        kv = kv.strip()
        if "=" not in kv:
            continue
        n, _, v = kv.partition("=")
        out.append({
            "name": n.strip(),
            "value": v.strip(),
            "domain": ".example.com",   # ← 改成目标域名
            "path": "/",
        })
    return out


def data_extractor(page):
    """
    在浏览器页面里拿数据的核心逻辑。

    几种常见模式（按需替换）：
      1. 页面内 fetch API（带 JS 引擎指纹，自动过 JS 挑战）
      2. 滚动触发翻页 + window 全局变量读取
      3. 解析 DOM（querySelectorAll + 提取属性）

    返回 list[dict]，每条 dict 至少包含一个标识字段（如 id）。
    """
    raise NotImplementedError("请根据目标站实现 data_extractor")


def resource_downloader(items, output_dir):
    """
    下载每个 item 对应的资源文件（图片/视频等）。

    CDN 公开 → 直接 requests 拉（快）
    需要 cookie → 浏览器下载（慢）

    返回 success / failed 计数。
    """
    import requests
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    success = failed = 0
    for item in items:
        url = item.get("url")  # ← 改成实际字段名
        if not url:
            continue
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and len(r.content) > 1024:
                fp = output_dir / f"{item['id']}.jpg"  # ← 改扩展名
                fp.write_bytes(r.content)
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1
        time.sleep(0.2)
    return success, failed


def run(target_url=TARGET_URL, cookie_file=COOKIE_FILE,
        browser_profile=BROWSER_PROFILE, meta_path=META_PATH,
        output_dir=Path("output")):
    """主流程：浏览器采集 → 写元数据 → 下载资源。"""
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    browser_profile.mkdir(parents=True, exist_ok=True)
    cookies = load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(browser_profile),
            channel="msedge",        # ← 也可以换成 "chrome"
            headless=False,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = browser.new_page()

        # 反检测基础措施
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        # 注入 cookie
        for c in cookies:
            try:
                browser.add_cookies([c])
            except Exception as e:
                print(f"跳过 cookie {c['name']}: {e!r}")

        # 调试：监听网络 / console
        page.on("console", lambda m: print(f"  [console.{m.type}] {m.text[:200]}"))
        page.on("pageerror", lambda e: print(f"  [pageerror] {e}"))

        # 访问入口页，等 JS 挑战通过
        print(f"[1/3] 访问 {target_url}")
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        # ← 按需加：等某个元素出现 = JS 挑战通过
        # for i in range(60):
        #     time.sleep(1)
        #     if page.evaluate("() => !!document.querySelector('...')"):
        #         break

        # 采集数据
        print(f"[2/3] 采集数据...")
        items = data_extractor(page)
        print(f"  ✓ 拿到 {len(items)} 条")

        # 写元数据
        meta_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  ✓ 元数据写到 {meta_path}")

        browser.close()

    # 下载资源（独立于浏览器，CDN 公开就用 requests）
    print(f"[3/3] 下载资源...")
    success, failed = resource_downloader(items, output_dir)
    print(f"  ✓ 成功 {success} / 失败 {failed}")

    return items, success, failed


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
    except NotImplementedError as e:
        print(f"\n{e}")
        print("请按目标站实现 data_extractor() 和 resource_downloader()")
        sys.exit(1)
