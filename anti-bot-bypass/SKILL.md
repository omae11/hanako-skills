---
name: anti-bot-bypass
description: 绕过带 JS 挑战的反爬网站（EO-Bot、Cloudflare、Akamai、极验等），用真浏览器自动化采集数据。适用于：用户提到"网站有反爬"、"被 WAF 拦截"、"405/403"、"Cloudflare 验证"、"JS 挑战"、"EO-Bot"、"极验验证码"、"想爬某网站但 requests 不行"、"浏览器自动化采集"、"playwright 爬虫"等场景；当目标站对裸 requests 返回挑战页或拒绝服务、需要 JS 引擎指纹才能放行时使用。如果提到的是**花瓣网**（huaban.com）或画板 ID（如 92623632），直接用专用 skill [`huaban-image-crawler`](../huaban-image-crawler/SKILL.md)，不要再走通用方法。MANDATORY TRIGGERS: 反爬绕过, JS挑战, 爬虫被拦, 405, 403, Cloudflare验证, EOBot, 极验, Akamai, captcha, 浏览器爬虫, playwright爬虫, headful爬虫, 网站登录后爬, 浏览器自动化采集
allowed-tools: Read, Write, Edit, Bash, WebFetch
compatibility: requires Playwright (Python) + Edge 或 Chromium 浏览器
---

> **关联**：如果确定目标是花瓣网（huaban.com），直接用 [`huaban-image-crawler`](../huaban-image-crawler/SKILL.md) — 已沉淀 7 个踩过的坑 + 现成可跑脚本。

# Anti-Bot Bypass

通用方法论：用真浏览器自动化采集被反爬挡住的网站数据。
不针对具体网站，给的是「决策树 + 工作流 + 调试指南」，具体脚本可复用 `scripts/browser_crawler.py` 模板。

## 何时触发

- 用户说"requests 试了但 403 / 405 / 拿不到数据"
- 用户说"网站有 Cloudflare / 验证码 / JS 挑战"
- 用户说"想爬 XX 网站但不知道怎么过反爬"
- 用户提供了某个网站的 URL，说"把这个站的数据批量拉下来"
- 用户问"playwright 怎么接管已登录的浏览器"

**不要**用本 skill：
- 目标站对 requests 没拦（直接用 requests + BeautifulSoup 就行）
- 单页静态 HTML，没有分页、没有 API（curl 就够了）
- 目标站是私有 API 且需要鉴权 token（先搞清楚授权机制再说）

## 决策树（先看这一段，再决定走哪条路）

```
目标站
├─ 用 web_fetch 能拿到内容？
│   ├─ 是 → 直接解析 HTML（最快，零依赖）
│   └─ 否 → 下一步
├─ 用 requests 能 200 + 拿到 HTML/JSON？
│   ├─ 是 → 解析 HTML/JSON（最快）
│   └─ 否（405/403/429/空响应）→ 下一步
├─ 返回的是 JS 挑战页（<script> 里的混淆代码）？
│   ├─ 是 → 必须真浏览器（EO-Bot / Cloudflare / Akamai / 极验都是这种）
│   └─ 否（IP 封禁、协议错误）→ 用代理 / 换 UA 重试
└─ 进了真浏览器方案 ↓
    ├─ 找到真正的 API 端点？
    │   ├─ 是 → 页面内 fetch（带 JS 引擎指纹，自动过验证）
    │   └─ 否 → 解析 DOM / 监听 XHR 找数据
    └─ 资源（图片/视频）走公开 CDN？
        ├─ 是 → requests 直接拉（不需要 cookie）
        └─ 否 → 浏览器下载
```

## 核心机制

所有现代反爬都基于一个事实：**JS 引擎特征 + 真实浏览器行为**很难被纯 HTTP 客户端伪造。
具体实现各家不同，但都需要：

| 反爬栈 | 验证方式 | 怎么过 |
|---|---|---|
| Cloudflare Turnstile / Bot Fight | 浏览器执行 JS 算 token + 检查 `navigator.webdriver` | 真浏览器 headful |
| F5 EO-Bot | 算 `EO_Bot_Ssid` cookie，校验 JS 引擎指纹 | 真浏览器 headful |
| Akamai Bot Manager | 行为分析（鼠标轨迹、滚动速度）+ TLS 指纹（JA3） | 真浏览器 + 人类节奏 |
| 极验 (GeeTest) | 滑块 / 点选 + JS 引擎指纹 | 真浏览器 + 滑块识别（cv2） |
| reCAPTCHA v3 | 行为评分 + JS 引擎指纹 | 真浏览器 + 慢节奏 |
| 花瓣网 EO-Bot + Next.js | JS 挑战 + 校验客户端 fetch 行为 | 真浏览器 + 页面内 fetch |

**共同解法**：playwright 接管真浏览器（headful 模式），让 JS 引擎跑起来、设好 cookie，后续 API 调用走页面内 fetch。

## 工作流程

### Step 1：探针（5 分钟内搞清楚目标站的反爬栈）

```powershell
python scripts/probe.py --url https://example.com/path
```

Probe 会做：
1. 用 requests 直接 GET，看返回码、body 长度、Content-Type
2. 用 web_fetch 再 GET，对比
3. 检查 body 里有没有反爬栈的指纹字符串（`EO-Bot-Js-Token`、`cf-chl-bypass`、`__gdt0`、`_abck` 等）
4. 输出诊断报告 + 推荐方案

### Step 2：环境检查（用通用 preflight）

```powershell
python scripts/preflight.py        # 人类可读
python scripts/preflight.py --json # CI / 自动化
```

通用 preflight 检查 6 项：Python ≥ 3.10、playwright、requests、Edge/Chromium 存在、目标域名网络可达。

### Step 3：跑通用模板

`scripts/browser_crawler.py` 是可复用模板，针对具体站需要改几个点（见脚本顶部注释）。

```powershell
# 复制模板，按目标站改配置
cp scripts/browser_crawler.py my_crawler.py
# 编辑 my_crawler.py 顶部 TARGET_URL / COOKIE_FILE / DATA_EXTRACTOR
python my_crawler.py
```

### Step 4：调试（如果没拿到数据）

常见 4 类失败，对应 4 个解法（详见 references/playwright-cookbook.md）：

| 现象 | 排查 |
|---|---|
| 浏览器没启动 / 立刻退出 | 检查 Edge/Chromium 路径、user data 锁文件冲突 |
| 页面是白屏 / JS 错误 | 检查 console 日志、加 `wait_for_load_state('networkidle')` |
| API 调用返回 JS 挑战页 | 必须在页面内 fetch，不能从外部 requests |
| 拿到的 JSON 是空 / 字段错 | 用 `page.evaluate` 打印 window 全局变量、监听 network 找真实端点 |

## 反爬栈对照表（详见 `references/anti-bot-stacks.md`）

每个反爬栈的指纹、检测项、解法速查。遇到 probe 报出某个名字时直接查表。

## Playwright 代码片段（详见 `references/playwright-cookbook.md`）

按场景分的代码模板：
- 接管系统 Chrome/Edge 的 user data
- 注入 cookie
- 屏蔽 webdriver 标志
- 监听 network / console / pageerror
- 页面内 fetch API
- 滚动加载翻页
- 文件下载 / 截图

## 验证清单

跑完采集后自检：

```powershell
# 1. 文件数对不对
$count = (Get-ChildItem output -File).Count
Write-Host "下载: $count 张"

# 2. 元数据条数对不对
$meta = (Get-Content output/_meta.json | ConvertFrom-Json).Count

# 3. 抽样打开看图
& "G:\conda_env\sarread\python.exe" -c "from PIL import Image; [Image.open(p).verify() for p in Path('output').glob('*.jpg')[:5]]; print('OK')"
```

## 反触发清单（什么时候*不要*用本 skill）

- **目标站对 requests 没拦**：直接 requests + BeautifulSoup，本 skill 是杀鸡用牛刀
- **目标站要登录但用户没 cookie**：先去帮用户准备 cookie，本 skill 的 cookie 注入是假定已有 cookie
- **目标站有复杂验证码（reCAPTCHA 图像识别）**：本 skill 只覆盖 JS 挑战类，复杂验证码需要 2Captcha / 打码平台
- **目标站有 IP 限流**：本 skill 不解决 IP 封禁，需要代理池
- **法律 / ToS 风险**：先确认用户爬的是公开数据还是用户自己账号下的数据，私域数据爬取有合规风险

## 限制

- **必须 headful**：headless=True 大概率被识别（headless 标志、缺少 GPU 等），用 headless=False + 可见窗口
- **必须有真实浏览器**：playwright 默认下载 chromium（~150 MB），或用 `channel="msedge"` 调系统 Edge
- **必须有人登录态**：未登录用户的 cookie 过不了多数反爬
- **必须慢节奏**：连续发请求会被行为分析标记，每页 sleep 1~3 秒

## 进阶用法（详见各 reference 文件）

- 多页翻页：scroll 加载 / 翻页参数 / "Load more" 按钮
- 并发：playwright 不支持多 browser 并发，但一个 browser 多 page 可以
- 持久化：user data 目录复用，第二次跑免登录
- 截图：page.screenshot(path=...) 留档

## 依赖项

- Python 3.10+
- `playwright`（首次用 `playwright install chromium` 下载）
- `requests`
- 系统浏览器（Edge / Chrome / Chromium 任一）

## 版本

- **v1.1** (2026-08)：playwright-cookbook.md 加 "PWA + Service Worker 陷阱" 章节（含 cleanup 代码模板）
- **v1.0** (2026-08)：从 huaban-image-crawler 提炼出来的通用方法论
