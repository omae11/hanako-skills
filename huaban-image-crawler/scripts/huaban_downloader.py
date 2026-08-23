# -*- coding: utf-8 -*-
"""
花瓣网画板批量图片下载器（playwright v3 API 版）
================================================
花瓣网 2026 年切到 Next.js + v3 REST API（/v3/boards/{id}/pins），
但全站都有 F5 EO-Bot JS 挑战，必须在真浏览器里发请求才能通过。

流程：
  1. playwright 启动 Edge，加 cookie + 过 EO-Bot 挑战
  2. 在页面内 fetch v3 API 翻页拉所有 pin（带浏览器指纹，自动过验证）
  3. pin 元数据写到 _pins_meta.json
  4. requests 直接拉原图（图片 CDN 公开，不需要 cookie）

用法（单画板）：
  python huaban_downloader.py --collect --download
  # 用顶部 BOARD_ID 配置（默认 92623632，迷彩画板）

用法（多画板）：
  python huaban_downloader.py --boards 92623632,98765432 --collect --download
  python huaban_downloader.py --boards-file boards.txt --collect --download
  # boards.txt 每行一个 board_id，# 开头是注释
  # 输出到 dataset_<board_id>/ 目录
"""

import json
import os
import re
import sys
import time
from pathlib import Path

# ============== 默认配置（单画板模式） ==============
BOARD_ID       = "92623632"
OUTPUT_DIR     = Path("camo_dataset")
EDGE_PROFILE   = OUTPUT_DIR / "_edge_profile"
COOKIE_FILE    = Path("cookie.txt")
META_PATH      = OUTPUT_DIR / "_pins_meta.json"
PER_PAGE       = 40
PAGE_SLEEP     = 2.0
# ====================================================

FIELDS = "pins:PIN|board:BOARD_DETAIL|check"


# ---------- CLI 参数 ----------

def parse_boards():
    """
    解析命令行，返回要爬的画板列表 [(board_id, output_dir), ...]

    优先级：--boards / --boards-file > 顶部 BOARD_ID
    输出目录：多画板时为 dataset_<id>/，单画板时用顶部 OUTPUT_DIR
    """
    args = sys.argv[1:]
    boards = []

    # --boards 12345,67890
    for i, a in enumerate(args):
        if a == "--boards" and i + 1 < len(args):
            for b in args[i + 1].split(","):
                b = b.strip()
                if b:
                    boards.append(b)
            break

    # --boards-file boards.txt
    if not boards:
        for i, a in enumerate(args):
            if a == "--boards-file" and i + 1 < len(args):
                fp = Path(args[i + 1])
                if not fp.exists():
                    print(f"找不到 {fp}")
                    sys.exit(1)
                for line in fp.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        boards.append(line)
                break

    if boards:
        return [(b, Path(f"dataset_{b}")) for b in boards]
    return [(BOARD_ID, OUTPUT_DIR)]


# ---------- cookie 注入 ----------

def load_cookies():
    """把 cookie.txt 转成 playwright add_cookies 需要的列表。"""
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
            "domain": ".huaban.com",
            "path": "/",
        })
    return out


# ---------- 浏览器收集 pin ----------

def cleanup_sw_cache(output_dir):
    """清理 Edge Service Worker 在 output_dir 里创建的 resources/ 缓存。
    花瓣网是 PWA，访问时会触发 SW 预缓存，把相关推荐图批量下到 OUTPUT_DIR/resources/，
    不走 user_data_dir，手动删即可。
    """
    import shutil
    for name in ("resources", "background_clothing_conf"):
        target = output_dir / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            print(f"  ✓ 清理 SW 缓存: {target.name}/")


def collect_pins_via_browser(board_id, output_dir, edge_profile):
    """playwright 接管 Edge，页面内 fetch v3 API 翻页。"""
    from playwright.sync_api import sync_playwright

    output_dir.mkdir(parents=True, exist_ok=True)
    edge_profile.mkdir(parents=True, exist_ok=True)

    # 启动前先清理一次（防止上次残留）
    cleanup_sw_cache(output_dir)

    board_url = f"https://huaban.com/boards/{board_id}"
    api_url   = f"https://huaban.com/v3/boards/{board_id}/pins"
    cookies   = load_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(edge_profile),
            channel="msedge",
            headless=False,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                # 缩小 SW / 磁盘缓存体积，减少 OUTPUT_DIR 下的 stray files
                "--disk-cache-size=1048576",
            ],
        )
        page = browser.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

        for c in cookies:
            try:
                browser.add_cookies([c])
            except Exception:
                pass

        print(f"[1/2] 访问画板 {board_id}，过 EO-Bot 挑战...")
        page.goto(board_url, wait_until="domcontentloaded", timeout=60000)
        for i in range(30):
            time.sleep(1)
            ok = page.evaluate(
                "() => !!document.querySelector('[data-board-id]')"
            )
            if ok:
                print(f"  ✓ 挑战通过 ({i+1}s)")
                break

        print(f"[2/2] 在浏览器内 fetch v3 API 翻页...")
        all_pins = []
        last_pin_id = None
        page_idx = 0
        while True:
            page_idx += 1
            if last_pin_id is None:
                url = f"{api_url}?limit={PER_PAGE}&sort=seq&fields={FIELDS}"
            else:
                url = (
                    f"{api_url}?limit={PER_PAGE}&sort=seq"
                    f"&max={last_pin_id}&fields={FIELDS}"
                )
            data = page.evaluate(
                """async (u) => {
                    const r = await fetch(u, {credentials: 'include'});
                    const t = await r.text();
                    try { return {ok: true, json: JSON.parse(t)};}
                    catch (e) { return {ok: false, status: r.status, text: t.slice(0,500)};}
                }""",
                url,
            )
            if not data.get("ok"):
                print(f"  ✗ 第 {page_idx} 页失败: {data}")
                break
            pins = data["json"].get("pins") or []
            if not pins:
                print(f"  第 {page_idx} 页无 pin，停止")
                break
            all_pins.extend(pins)
            last_pin_id = pins[-1]["pin_id"]
            print(
                f"  第 {page_idx:>2} 页: {len(pins):>2} 张, "
                f"累计 {len(all_pins)} / last_pin_id={last_pin_id}"
            )
            if len(pins) < PER_PAGE:
                print(f"  本页不足 {PER_PAGE} 张，到达末尾")
                break
            time.sleep(PAGE_SLEEP)

        browser.close()

    # 跑完再清理一次（Edge SW 在浏览过程中可能在 OUTPUT_DIR 下创建 resources/）
    cleanup_sw_cache(output_dir)

    meta_path = output_dir / "_pins_meta.json"
    meta_path.write_text(
        json.dumps(all_pins, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n✓ board={board_id} 共 {len(all_pins)} 个 pin，元数据写到 {meta_path}")
    return all_pins, meta_path


# ---------- requests 下载图片 ----------

def download_images(pins, output_dir, board_id):
    import requests
    if not pins:
        print(f"board={board_id} pin 列表为空，跳过下载")
        return

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://huaban.com/",
    }

    type_counter = {}
    for p in pins:
        t = (p.get("file") or {}).get("type", "unknown")
        type_counter[t] = type_counter.get(t, 0) + 1
    print(f"  board={board_id} 文件类型分布: {type_counter}")

    success = failed = skipped = 0
    for i, pin in enumerate(pins, 1):
        file_info = pin.get("file") or {}
        key = file_info.get("key")
        if not key:
            skipped += 1
            continue

        mime = (file_info.get("type") or "image/jpeg").split("/")[-1].lower()
        ext_map = {"jpeg": "jpg", "png": "png", "webp": "webp", "gif": "gif", "bmp": "bmp"}
        ext = ext_map.get(mime, mime or "jpg")
        fp = output_dir / f"huaban_{pin['pin_id']}.{ext}"

        if fp.exists() and fp.stat().st_size > 1024:
            skipped += 1
            continue

        url = f"https://hbimg.huabanimg.com/{key}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200 and len(r.content) > 1024:
                fp.write_bytes(r.content)
                success += 1
                if i % 50 == 0 or i <= 5:
                    print(f"    [{i}/{len(pins)}] ✓ {fp.name} ({len(r.content)//1024} KB)")
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if i <= 5:
                print(f"    [{i}/{len(pins)}] ✗ {e!r}")
        time.sleep(0.2)

    print(f"  board={board_id} 完成: 成功 {success} / 失败 {failed} / 跳过 {skipped}")


# ---------- 入口 ----------

def preflight_check():
    """跑前环境检查，失败直接退出。"""
    # 脚本可能在不同目录下被调用，preflight.py 可能在同目录或 skill scripts 里
    candidates = [
        Path(__file__).parent / "preflight.py",
        Path("G:/hanako/preflight.py"),
    ]
    for fp in candidates:
        if fp.exists():
            sys.path.insert(0, str(fp.parent))
            break
    try:
        from preflight import run_all, print_human
    except ImportError:
        # preflight.py 找不到时跳过（不强制依赖）
        return
    results = run_all()
    all_pass = print_human(results)
    if not all_pass:
        print("\n[主脚本] preflight 未通过，先修复上面失败项")
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if "--no-preflight" not in args:
        preflight_check()
    boards = parse_boards()

    do_collect = "--collect" in args
    do_download = "--download" in args

    if not do_collect and not do_download:
        print(__doc__)
        print("\n当前任务:")
        for b, d in boards:
            print(f"  board={b} → {d.resolve()}")
        print("\n加 --collect 或 --download 开始（可同时加）")
        return

    summary = []
    for board_id, output_dir in boards:
        print(f"\n======== board {board_id} ========")
        meta_path = output_dir / "_pins_meta.json"
        if do_collect:
            pins, meta_path = collect_pins_via_browser(
                board_id, output_dir,
                edge_profile=output_dir / "_edge_profile",
            )
        elif do_download:
            if not meta_path.exists():
                print(f"  ✗ 找不到 {meta_path}，先跑 --collect")
                continue
            pins = json.loads(meta_path.read_text(encoding="utf-8"))

        if do_download:
            download_images(pins, output_dir, board_id)
            summary.append((board_id, output_dir, len(pins)))

    if summary:
        print("\n======== 全部完成 ========")
        for b, d, n in summary:
            print(f"  board={b}: {n} 张 → {d.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(1)
