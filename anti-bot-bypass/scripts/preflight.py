# -*- coding: utf-8 -*-
"""
anti-bot-bypass preflight
==========================
跑通用浏览器爬虫前的环境检查。

比 huaban-image-crawler 的 preflight 简化：通用项 + 浏览器项。
针对具体站的 cookie / 输出目录检查留给具体脚本。

检查项：
  1. Python ≥ 3.10
  2. playwright 已安装
  3. requests 已安装
  4. Edge / Chrome 存在
  5. 网络可达（默认探测 example.com）

用法：
  python preflight.py
  python preflight.py --json
"""

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path

CHECKS = []


def check(name, fix_hint=""):
    def deco(fn):
        CHECKS.append({"name": name, "fn": fn, "fix": fix_hint})
        return fn
    return deco


@check("Python ≥ 3.10", "playwright 最低支持 3.10")
def _python():
    v = sys.version_info
    if v.major > 3 or (v.major == 3 and v.minor >= 10):
        return True, f"{v.major}.{v.minor}.{v.micro}"
    return False, f"{v.major}.{v.minor}.{v.micro}"


@check("playwright 已安装", f"{sys.executable} -m pip install playwright")
def _playwright():
    try:
        importlib.import_module("playwright")
        try:
            from importlib.metadata import version
            return True, version("playwright")
        except Exception:
            return True, "?"
    except ImportError as e:
        return False, str(e)


@check("requests 已安装", f"{sys.executable} -m pip install requests")
def _requests():
    try:
        importlib.import_module("requests")
        return True, "OK"
    except ImportError as e:
        return False, str(e)


@check("Edge 或 Chrome 存在", "Windows 10/11 自带 Edge，没有就装 Chrome")
def _browser():
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for p in candidates:
        if p.exists():
            return True, p.name
    return False, "未找到"


@check("没有 msedge/chrome 进程在跑",
       "Get-Process msedge,chrome | Stop-Process -Force （user data 锁文件）")
def _no_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        procs = [l.split(",")[0].strip('"')
                 for l in out.splitlines()
                 if "msedge.exe" in l.lower() or "chrome.exe" in l.lower()]
        if procs:
            return False, f"{len(procs)} 个进程"
        return True, "无进程"
    except Exception as e:
        return True, f"无法检查: {e!r}"


@check("网络可达（example.com）", "检查防火墙 / 代理设置")
def _network():
    try:
        import requests
        r = requests.get("https://example.com", timeout=10)
        return True, f"HTTP {r.status_code}"
    except Exception as e:
        return False, f"无法访问: {e!r}"


def run_all():
    results = []
    for c in CHECKS:
        try:
            ok, detail = c["fn"]()
        except Exception as e:
            ok, detail = False, f"检查自身异常: {e!r}"
        results.append({
            "name": c["name"],
            "passed": ok,
            "detail": detail,
            "fix_hint": c["fix"],
        })
    return results


def print_human(results):
    print("=" * 60)
    print("anti-bot-bypass preflight")
    print("=" * 60)
    pass_n = fail_n = 0
    for r in results:
        mark = "✓" if r["passed"] else "�"
        if r["passed"]:
            pass_n += 1
        else:
            fail_n += 1
        print(f"\n[{mark}] {r['name']}")
        print(f"    {r['detail']}")
        if not r["passed"] and r["fix_hint"]:
            print(f"    → {r['fix_hint']}")

    print("\n" + "=" * 60)
    summary = f"通过 {pass_n} / 失败 {fail_n} / 总共 {len(results)}"
    if fail_n == 0:
        print(f"✓ {summary}")
        print("  可以跑浏览器爬虫了")
    else:
        print(f"✗ {summary}")
        print("  修复失败项后重试")
    print("=" * 60)
    return fail_n == 0


def main():
    p = argparse.ArgumentParser(description="anti-bot-bypass preflight")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    args = p.parse_args()

    results = run_all()
    all_pass = all(r["passed"] for r in results)

    if args.json:
        print(json.dumps({
            "all_pass": all_pass,
            "results": results,
        }, ensure_ascii=False, indent=2))
    else:
        print_human(results)

    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
