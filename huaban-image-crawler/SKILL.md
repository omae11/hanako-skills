---
name: huaban-image-crawler
description: 批量下载花瓣网（huaban.com）画板图片到本地。适用于：用户提到"下载花瓣网"、"拉取花瓣画板图片"、"花瓣数据集"、"迷彩图批量"、"huaban boards"、"huaban.com"、"花瓣网 92623632"等场景；或者提到要把某个 huaban 画板 ID 转成本地数据集；或者想做迷彩/伪装/设计/摄影类数据集采集时。如果用户**没说具体站点**或提到了其他反爬站（不是花瓣网），先用通用 skill [`anti-bot-bypass`](../anti-bot-bypass/SKILL.md) 探诊断，不要直接套用本 skill。MANDATORY TRIGGERS: 下载花瓣, 花瓣网, huaban, huaban.com, 画板图片, 迷彩数据集, 迷彩图片, 批量下载图片, camo dataset, board 92623632, 92623632
allowed-tools: Read, Write, Edit, Bash, WebFetch
compatibility: requires Playwright (Python) + Edge 浏览器 + 花瓣网登录 cookie
---

> **关联**：如果目标站不是花瓣网、是其他带反爬的网站，先用 [`anti-bot-bypass`](../anti-bot-bypass/SKILL.md) 探诊断 + 通用模板。

# Huaban Image Crawler

批量下载花瓣网（huaban.com）某个画板（board）下的所有图片到本地，输出元数据 JSON 与原始图。
已验证可处理 1000+ 张图的大画板。

## 何时触发

- 用户说"下载花瓣网画板 92623632 的图片"
- 用户说"把这个画板的图都拉下来"
- 用户做迷彩/伪装目标检测数据集，从花瓣网采集
- 用户提供 `https://huaban.com/boards/{id}` 链接并要求批量下载

如果用户只想要花瓣网某张特定图片，单条 curl 就够，**不要**用本 skill。

## 核心机制（这一段先读懂，下面所有步骤都依赖它）

花瓣网 2026 年的反爬栈：

| 层 | 行为 | 直接 requests 的后果 |
|---|---|---|
| WAF | 检查 TLS 指纹、UA、Header 完整性 | 405 Method Not Allowed |
| EO-Bot（F5） | 浏览器执行 JS 算 `EO_Bot_Ssid` cookie 才能继续 | 返回 JS 挑战页（HTML，~1KB） |
| Next.js + v3 API | pin 数据通过 `GET /v3/boards/{id}/pins` 分页拉 | API 也走同一层 EO-Bot 验证，裸请求同样被拦 |

**结论**：必须用真浏览器发请求。`requests` 直接调任何端点都会被拦；唯一可行路径是 **playwright 启动 Edge，在页面里 `fetch()` API**——浏览器引擎指纹 + 已设置的 `EO_Bot_Ssid` cookie 自动满足所有校验。

## 工作流程

### 用法速查

```powershell
# 单画板（用脚本顶部 BOARD_ID 配置）
python huaban_downloader.py --collect --download

# 多画板（逗号分隔）
python huaban_downloader.py --boards 92623632,98765432,12345678 --collect --download

# 多画板（文件方式，boards.txt 每行一个 board_id，支持 # 注释）
python huaban_downloader.py --boards-file boards.txt --collect --download

# 跳过 preflight 检查（调试 / cookie 临时过期时用）
python huaban_downloader.py --no-preflight --collect
```

多画板模式输出到 `dataset_<board_id>/` 各自目录。

### Step 0：环境检查（首次）

主脚本开头会自动跑 preflight（见 `scripts/preflight.py`），任何失败直接退出。也可以手动跑：

```powershell
& "G:\conda_env\sarread\python.exe" scripts\preflight.py        # 人类可读
& "G:\conda_env\sarread\python.exe" scripts\preflight.py --json # 机器可读
```

Preflight 检查项（覆盖踩过的坑）：
- Python ≥ 3.10、不是 WindowsApps wrapper
- 依赖包：playwright / pillow / pillow-heif / requests
- Edge 存在 + 没有 msedge 进程在跑（user data 锁文件冲突）
- cookie.txt 存在 + 包含必需字段（auth_key / token.prod / uid）
- 输出目录可写

手动准备依赖（preflight 失败时参照执行）：

```powershell
# 1. playwright（必须装到用户实际用的 python 环境）
& "G:\conda_env\sarread\python.exe" -m pip install playwright pillow-heif

# 2. Edge 浏览器（Windows 10/11 自带，不需要额外装）
Test-Path "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 3. 关闭所有 Edge 窗口（user data 锁文件冲突会导致启动失败）
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Step 1：拿 cookie

1. 浏览器打开 `https://huaban.com` 并登录
2. 打开目标画板（如 `https://huaban.com/boards/92623632`）
3. F12 → Network → 找到 `boards/92623632` 的请求 → 复制 Request Headers 里整段 `cookie:` 值
4. 把 cookie 存到工作目录的 `cookie.txt`（UTF-8 编码）

### Step 2：跑下载脚本

```powershell
& "G:\conda_env\sarread\python.exe" scripts\huaban_downloader.py --collect --download
```

脚本会：
1. 启动 playwright + Edge（独立 user data 目录，复用 cookie.txt 注入的登录态）
2. 访问画板，等 EO-Bot 挑战通过（首次约 1~3 秒）
3. 在页面内 `fetch('/v3/boards/{id}/pins?limit=40&sort=seq&max={last_pin_id}&fields=pins:PIN|board:BOARD_DETAIL|check')` 翻页
4. 把所有 pin 元数据写到 `<output_dir>/_pins_meta.json`
5. 退出浏览器，用 requests 直接拉 `https://hbimg.huabanimg.com/{file.key}` 原图（CDN 公开，不需要 cookie）

输出命名：`huaban_{pin_id}.{ext}`（避免重复 + 方便追溯原始 pin）

### Step 3：转换 webp/heif（可选）

```powershell
& "G:\conda_env\sarread\python.exe" scripts\convert_to_png.py
```

把 webp/heif 转成 png（无损），同时更新 `_pins_meta.json` 的 `file.type` 字段。

## 配置项（脚本顶部常量）

```python
BOARD_ID   = "92623632"      # 画板 ID（URL 最后那段数字）
OUTPUT_DIR = Path("camo_dataset")  # 输出目录
PER_PAGE   = 40              # v3 API 单页大小（写死，别改）
EDGE_PROFILE = OUTPUT_DIR / "_edge_profile"  # playwright 复用的 user data
COOKIE_FILE  = Path("cookie.txt")
```

## 踩过的坑（每个坑的根因和解法都列在这里，下次别再重新踩）

### ❌ 坑 1：requests 直接 GET 画板 → 405

**根因**：WAF 层 UA/TLS/Header 检查太严
**症状**：`HTTP 405: Method Not Allowed`
**解法**：放弃 requests，用 playwright 启动真浏览器

### ❌ 坑 2：playwright 接管 Edge 默认 profile → DevTools 报错

**根因**：Edge 不允许用默认 user data + remote debugging（安全限制）
**症状**：`DevTools remote debugging requires a non-default data directory`
**解法**：用 `EDGE_PROFILE = OUTPUT_DIR / "_edge_profile"`（独立目录）

### ❌ 坑 3：cookie 注入后直接 requests 调 v3 API → EO-Bot 挑战页

**根因**：API 端点也走 EO-Bot 验证，缺 `EO_Bot_Ssid` cookie
**症状**：返回 `text/html`，body 是 EO-Bot JS 挑战代码
**解法**：在浏览器里用 `page.evaluate('() => fetch(...)')` 发请求，让浏览器引擎处理 JS 验证

### ❌ 坑 4：cookie 解析出来只有 1 条

**根因**：花瓣网 cookie 段之间用 `;` 分隔但**不带空格**，用 `"; "` 分割会丢
**解法**：用 `;` 分割，然后每段 `strip()`

### ❌ 坑 5：`page.evaluate('window.app.page.board.pins')` 返回 undefined

**根因**：花瓣网 2026 年从 SPA 切到 Next.js + v3 REST API，数据不再放在 `window.app` 里
**症状**：`__NEXT_DATA__.props.pageProps` 是空的 `{}`
**解法**：监听 network 找真正的 API 端点（这次是 `GET /v3/boards/{id}/pins`），页面内 fetch 翻页

### � 坑 6：webp/heif PIL 默认读不了 / 转不了

**根因**：PIL 默认不支持 HEIF；webp 支持但转 png 后文件大 7~8 倍
**解法**：
- `pip install pillow-heif` + `from pillow_heif import register_heif_opener; register_heif_opener()`
- webp → png 是无损转换，但 webp 本身是有损编码，无法逆转

### ❌ 坑 7：默认 `python` 不是 conda 环境

**根因**：Windows 默认 `python` 是 Microsoft Store 的 wrapper（`%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe`），独立 conda 环境装不到这里
**解法**：用绝对路径调用 `& "G:\conda_env\sarread\python.exe"`，或者 `conda activate sarread` 后再 `python`

### ❌ 坑 8：OUTPUT_DIR 下冒出 `resources/` 缓存目录

**根因**：花瓣网是 PWA，访问时注册 Service Worker。SW 预缓存（推荐画板图标）默认写到当前工作目录的 `resources/<category>/icon/`（**不走 user_data_dir**），里面会有几十张迷彩推荐图。删了下次跑又出现。
**症状**：`<OUTPUT_DIR>/resources/background_clothing_conf/icon/` 下不断冒出 .png / .jpg-lx2 文件
**解法**（脚本里已经内置，3 层防御）：
1. Edge 启动参数加 `--disk-cache-size=1048576` 限制 SW 缓存体积
2. 跑前 `cleanup_sw_cache()` 清理一次
3. 跑完 `browser.close()` 后再清理一次
4. 手动删也不影响：`Remove-Item <OUTPUT_DIR>/resources -Recurse -Force`

## 翻页 API 详解

```
GET https://huaban.com/v3/boards/{board_id}/pins
  ?limit=40                          # 单页大小，花瓣网服务端写死 40 最佳
  &sort=seq                          # 画板内的顺序（不是时间）
  &max={last_pin_id}                 # 翻页游标，第一页不传
  &fields=pins:PIN|board:BOARD_DETAIL|check
```

第一页（不带 max）拿首屏 40 张，每页拿完用 `pins[-1]['pin_id']` 作为下一页的 `max`。
判断停止：返回的 `pins` 数组长度 < 40（到末尾）。

## 输出文件结构

```
<OUTPUT_DIR>/
├── huaban_<pin_id>.<ext>          # 原图（jpg/png/webp/heif）
├── huaban_<pin_id>.<ext>          # ……
├── _pins_meta.json                # 所有 pin 的完整元数据
│                                    {pin_id, file: {key, type, width, height}, …}
└── _edge_profile/                 # playwright 复用的 Edge user data（可保留可删）
```

`_pins_meta.json` 用途：追溯每张图对应哪个 pin、原始 URL、尺寸、类型。**别删**。

## 验证清单（脚本跑完后自检）

```powershell
# 1. 文件数对不对
$total = 328
$count = (Get-ChildItem camo_dataset -File | Where-Object { $_.Extension -in '.jpg','.png','.webp','.heif','.heic' }).Count
Write-Host "下载: $count / $total"

# 2. 元数据 pin 数对不对
$meta = (Get-Content camo_dataset\_pins_meta.json | ConvertFrom-Json).Count
Write-Host "元数据: $meta"

# 3. 每张图都能被 PIL 打开
& "G:\conda_env\sarread\python.exe" -c "from PIL import Image; from pathlib import Path; [Image.open(p).verify() for p in Path('camo_dataset').glob('huaban_*')]; print('OK')"
```

## 限制

- **必须登录**：未登录 cookie 会被 EO-Bot 拒绝，花瓣网公开画板也得登录
- **必须 Edge**：用了 `channel='msedge'`，其他浏览器（Chrome/Firefox）未验证
- **必须 headful**：`headless=True` 会被 EO-Bot 识别为 bot，必须能看到窗口
- **API rate limit**：脚本默认每页 sleep 2 秒，连续跑 1000+ 张没问题；想更快可以调小但不建议
- **不支持视频 pin**：脚本跳过没有 `file.key` 的 pin（即非图片类型，如视频/链接收藏）

## 进阶用法

### 自定义下载尺寸

原图 URL：`https://hbimg.huabanimg.com/{file.key}`
花瓣网支持固定宽度：`https://hbimg.huabanimg.com/{file.key}_fw1200`（宽 1200，比例缩放）
可以批量下载小尺寸版本用于预训练，再单独下载原图用于微调。

### 去重（迷彩画板常见）

```python
import imagehash
from PIL import Image
from pathlib import Path

def phash(p):
    with Image.open(p) as img:
        return imagehash.phash(img)

hashes = {}
for p in Path('camo_dataset').glob('huaban_*.jpg'):
    h = phash(p)
    if h in hashes:
        p.unlink()
        print(f'删重复 {p.name}')
    else:
        hashes[h] = p
```

### 过滤太小/太糊的图

```python
import json
pins = json.loads(Path('camo_dataset/_pins_meta.json').read_text())
for p in pins:
    f = p['file']
    if f.get('width', 0) < 800 or f.get('height', 0) < 800:
        Path(f"camo_dataset/huaban_{p['pin_id']}.{f['type'].split('/')[-1]}").unlink(missing_ok=True)
```

## 依赖项

- Python 3.10+
- `playwright`（含自动下载 chromium——但本 skill 用 `channel="msedge"` 调系统 Edge，不下载 chromium）
- `pillow` 10+（webp 支持）
- `pillow-heif`（HEIF/HEIC 支持，**注意装到用户实际用的 python 环境**）
- `requests`
- Microsoft Edge（Windows 10/11 自带）
- 花瓣网登录账号 + cookie

## 版本

- **v1.4** (2026-08)：加 `cleanup_sw_cache()` + `--disk-cache-size` 参数，解决 OUTPUT_DIR 下 `resources/` 缓存目录不断出现的问题（坑 8）
- **v1.3** (2026-08)：加 `--no-preflight` 参数，调试时可跳过环境检查
- **v1.2** (2026-08)：加 preflight.py（11 项检查），主脚本开头自动跑、失败直接退出
- **v1.1** (2026-08)：加 `--boards` / `--boards-file` 多画板 CLI、加"反触发清单"、写 evals 测试集
- **v1.0** (2026-08)：首版，踩过 7 个坑后沉淀
