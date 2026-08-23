# -*- coding: utf-8 -*-
"""
Anti-bot probe
==============
用 requests 探测目标站的反爬栈：返回码、body 特征、指纹字符串。

输出诊断报告 + 推荐方案。

用法：
  python probe.py --url https://example.com/path
  python probe.py --url https://example.com --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

import requests

# 各反爬栈的指纹字符串（regex，case-insensitive）
FINGERPRINTS = [
    # Cloudflare
    (r"cloudflare|cf-ray|__cf_bm|cf_clearance|Just a moment\.\.\.|cf-chl-bypass",
     "Cloudflare", "headful + 慢节奏"),
    # F5 EO-Bot / Shape
    (r"EO[-_]?Bot[-_]?Js[-_]?Token|EO_Bot_Ssid|EOBotJS",
     "F5 EO-Bot / Shape", "headful + 页面内 fetch（见 huaban skill）"),
    # Akamai
    (r"akamaihd|_abck|akamai|_pxhd|px-cdn",
     "Akamai Bot Manager", "headful + residential proxy"),
    # 极验
    (r"geetest|gt_token|_GeeTest|static\.geetest",
     "极验 (GeeTest)", "headful + 滑块识别 / 打码平台"),
    # reCAPTCHA
    (r"recaptcha|grecaptcha|google\.com/recaptcha",
     "reCAPTCHA", "headful + 慢节奏，复杂场景用 2Captcha"),
    # DataDome
    (r"datadome|datadome\.co",
     "DataDome", "headful + residential proxy"),
    # PerimeterX / HUMAN
    (r"px-cdn|_px3|perimeterx",
     "PerimeterX / HUMAN", "headful + residential proxy"),
    # 花瓣网 Next.js
    (r"__NEXT_DATA__|huaban\.com",
     "Next.js / 花瓣网", "走 huaban-image-crawler skill"),
    # 通用 WAF / 风控
    (r"access denied|forbidden|waf|denied|blocked",
     "通用 WAF", "检查 UA / Referer / Origin 是否完整"),
]

# 典型挑战页 size 范围（经验值）
CHALLENGE_SIZE_RANGE = (200, 5000)  # 太短说明被拦截、太长可能是真的页面


def detect_fingerprints(body):
    hits = []
    for pat, name, hint in FINGERPRINTS:
        if re.search(pat, body, re.IGNORECASE):
            hits.append({"name": name, "hint": hint})
    return hits


def probe(url, timeout=15):
    """对目标 URL 做一次请求，返回诊断信息。"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    result = {"url": url, "status": None, "size": 0, "ct": "",
              "fingerprints": [], "is_challenge": False,
              "recommendation": ""}

    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        result["status"] = r.status_code
        result["size"] = len(r.content)
        result["ct"] = r.headers.get("Content-Type", "")
        body = r.text
        result["fingerprints"] = detect_fingerprints(body)
        result["final_url"] = r.url

        # 判断是不是挑战页
        is_small = result["size"] < CHALLENGE_SIZE_RANGE[1]
        has_fingerprint = bool(result["fingerprints"])
        has_obvious = (
            "Just a moment" in body
            or "EO-Bot-Js-Token" in body
            or "Access Denied" in body
        )
        result["is_challenge"] = bool((is_small and has_fingerprint) or has_obvious)

        # 推荐方案
        if r.status_code == 200 and not result["is_challenge"]:
            result["recommendation"] = (
                "✓ requests 直连成功，可以走简单爬虫方案"
            )
        elif r.status_code in (403, 405, 429):
            result["recommendation"] = (
                f"✗ HTTP {r.status_code}：被 WAF 拦截，需要真浏览器或代理"
            )
        elif result["fingerprints"]:
            primary = result["fingerprints"][0]
            result["recommendation"] = (
                f"✗ 检测到 {primary['name']}：{primary['hint']}"
            )
        elif result["is_challenge"]:
            result["recommendation"] = (
                "✗ 返回了 JS 挑战页，需要真浏览器"
            )
        else:
            result["recommendation"] = (
                "? 不确定，可能是 IP 限流或风控，试试加 Header / 代理"
            )
    except requests.exceptions.RequestException as e:
        result["recommendation"] = f"✗ 请求失败: {e!r}"

    return result


def print_human(result):
    print("=" * 60)
    print("anti-bot probe")
    print("=" * 60)
    print(f"URL:       {result['url']}")
    print(f"Status:    {result.get('status', 'N/A')}")
    print(f"Size:      {result.get('size', 0)} bytes")
    print(f"Content-Type: {result.get('ct', 'N/A')}")
    if "final_url" in result:
        print(f"Final URL: {result['final_url']}")
    print()
    print(f"指纹命中: {len(result['fingerprints'])}")
    for fp in result["fingerprints"]:
        print(f"  - {fp['name']}: {fp['hint']}")
    if not result["fingerprints"]:
        print("  (无)")
    print()
    print(f"是否挑战页: {'是' if result['is_challenge'] else '否'}")
    print()
    print(f"推荐方案: {result['recommendation']}")
    print("=" * 60)


def main():
    p = argparse.ArgumentParser(description="anti-bot probe")
    p.add_argument("--url", required=True, help="目标 URL")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args()

    result = probe(args.url)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result)


if __name__ == "__main__":
    main()
