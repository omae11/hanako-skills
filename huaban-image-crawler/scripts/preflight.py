# -*- coding: utf-8 -*-
"""
huaban-image-crawler preflight check
====================================
跑主脚本前的环境检查。基于踩过的坑，提前 fail-fast。

检查项：
  1. Python 版本 ≥ 3.10
  2. 依赖包：playwright / pillow / pillow-heif / requests
  3. Edge 浏览器是否存在
  4. Edge 是否有进程在跑（user data 锁文件冲突）
  5. cookie.txt 是否就绪（数量、关键字段）
  6. 输出目录父目录是否可写

用法：
  python preflight.py              # 人类可读输出
  python preflight.py --json       # JSON 输出（CI / 脚本调用）
  python preflight.py --strict     # 任何失败 exit 1

返回码：
  0  全部通过
  1  有失败（除非不加 --strict，否则默认也会 exit 1）
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

# ---------- 检查项 ----------

CHECKS = []

def check(name, fix_hint=""):
    """装饰器：注册一个检查函数。"""
    def decorator(fn):
        CHECKS.append({"name": name, "fn": fn, "fix": fix_hint})
        return fn
    return decorator


@check("Python 版本 ≥ 3.10", "Python 3.10 以下不支持 playwright")
def check_python():
    v = sys.version_info
    if v.major > 3 or (v.major == 3 and v.minor >= 10):
        return True, f"{v.major}.{v.minor}.{v.micro}"
    return False, f"{v.major}.{v.minor}.{v.micro}（需要 ≥ 3.10）"


@check("不是 Microsoft Store 的 python wrapper",
       "默认 python 可能指向 WindowsApps。脚本顶部改成绝对路径或 conda activate")
def check_python_path():
    bad = "WindowsApps"
    exe = Path(sys.executable)
    if bad in str(exe):
        return False, str(exe)
    return True, str(exe)


@check("playwright 已安装",
       f"{sys.executable} -m pip install playwright")
def check_playwright():
    try:
        importlib.import_module("playwright")
        try:
            from importlib.metadata import version
            v = version("playwright")
        except Exception:
            v = "?"
        return True, v
    except ImportError as e:
        return False, str(e)


@check("requests 已安装",
       f"{sys.executable} -m pip install requests")
def check_requests():
    try:
        importlib.import_module("requests")
        return True, "OK"
    except ImportError as e:
        return False, str(e)


@check("Pillow 已安装",
       f"{sys.executable} -m pip install pillow")
def check_pillow():
    try:
        importlib.import_module("PIL")
        from PIL import __version__ as v
        return True, v
    except ImportError as e:
        return False, str(e)


@check("pillow-heif 已安装（HEIF 支持）",
       f"{sys.executable} -m pip install pillow-heif")
def check_pillow_heif():
    try:
        importlib.import_module("pillow_heif")
        return True, "OK"
    except ImportError:
        return False, "未安装（HEIF/HEIC 图无法读取，不影响 JPEG/PNG/WebP）"


@check("Edge 浏览器存在",
       "Edge 是 Windows 10/11 自带的，没有的话这条会失败")
def check_edge_exists():
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in candidates:
        if p.exists():
            return True, str(p)
    return False, "未在标准路径找到 msedge.exe"


@check("没有 msedge 进程在跑",
       "Get-Process msedge | Stop-Process -Force  （user data 锁文件冲突）")
def check_edge_no_running():
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq msedge.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        # tasklist 输出像: "msedge.exe","12345","Console",... 或者 'INFO: No tasks...'
        lines = [l for l in out.strip().splitlines() if "msedge.exe" in l.lower()]
        if lines:
            return False, f"{len(lines)} 个进程: {lines[0][:80]}"
        return True, "无进程"
    except Exception as e:
        # 检查失败不算致命，让用户继续
        return True, f"无法检查（tasklist 异常: {e!r}）"


@check("cookie.txt 存在",
       "浏览器登录花瓣网 → F12 → Network → 复制 Request Headers 里的整段 cookie → 存到 cookie.txt")
def check_cookie_exists():
    fp = Path("cookie.txt")
    if not fp.exists():
        return False, "cookie.txt 不在工作目录"
    raw = fp.read_text(encoding="utf-8").strip()
    if not raw:
        return False, "cookie.txt 是空的"
    return True, f"{fp.stat().st_size} 字节"


@check("cookie 包含必要字段",
       "需要 auth_key、token.prod、uid 等；登录后从浏览器复制完整 cookie")
def check_cookie_fields():
    fp = Path("cookie.txt")
    if not fp.exists():
        return False, "cookie.txt 不存在（前置检查会先报告）"
    raw = fp.read_text(encoding="utf-8").strip()
    keys = []
    for kv in raw.split(";"):
        kv = kv.strip()
        if "=" in kv:
            keys.append(kv.split("=", 1)[0].strip())
    required = ["auth_key", "token.prod", "uid"]
    missing = [k for k in required if k not in keys]
    if missing:
        return False, f"缺少字段: {missing}（当前 {len(keys)} 条）"
    return True, f"{len(keys)} 条，必需字段齐全"


@check("输出目录可写",
       "检查当前目录的写权限")
def check_output_writable():
    try:
        test = Path(".").resolve() / ".preflight_write_test"
        test.write_text("test", encoding="utf-8")
        test.unlink()
        return True, str(Path(".").resolve())
    except Exception as e:
        return False, f"无法写入: {e!r}"


# ---------- 运行 ----------

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
    print("huaban-image-crawler preflight check")
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
        print("  可以跑主脚本了")
    else:
        print(f"✗ {summary}")
        print("  修复失败项后重试")
    print("=" * 60)
    return fail_n == 0


def main():
    p = argparse.ArgumentParser(description="huaban-image-crawler preflight")
    p.add_argument("--json", action="store_true", help="JSON 输出")
    p.add_argument("--strict", action="store_true", help="有失败就 exit 1")
    args = p.parse_args()

    results = run_all()
    all_pass = all(r["passed"] for r in results)

    if args.json:
        out = {
            "all_pass": all_pass,
            "results": results,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        all_pass = print_human(results)

    # 默认行为：有失败就 exit 1（除非显式加 --no-strict）
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
