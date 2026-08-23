# Playwright Cookbook

按场景分的 Playwright 代码片段。
配合主 SKILL.md 的 browser_crawler.py 模板用：模板覆盖 80% 场景，剩下的从这里挑。

## 1. 接管系统 Edge 的 user data

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\<user>\AppData\Local\Microsoft\Edge\User Data",
        channel="msedge",          # 用系统 Edge 二进制
        headless=False,            # 必须 headful
        no_viewport=True,          # 让窗口自适应
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
```

**坑**：Edge 不允许用默认 user data + remote debugging（"DevTools requires a non-default data directory"）。
**解法**：用独立目录 `output_dir / "_browser_profile"`。

## 2. 接管系统 Chrome（替代 Edge）

```python
user_data = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
browser = p.chromium.launch_persistent_context(
    user_data_dir=str(user_data),
    channel="chrome",
    headless=False,
)
```

**坑**：Chrome 必须先完全关闭（user data 锁文件）。
**解法**：`Get-Process chrome | Stop-Process -Force`（PowerShell）。

## 3. 注入 cookie

```python
# 从文件读 cookie.txt（每行 "name=value"，或分号分隔）
cookies = []
for kv in Path("cookie.txt").read_text(encoding="utf-8").split(";"):
    kv = kv.strip()
    if "=" in kv:
        n, _, v = kv.partition("=")
        cookies.append({
            "name": n.strip(),
            "value": v.strip(),
            "domain": ".example.com",   # 注意前面有点
            "path": "/",
        })

for c in cookies:
    try:
        browser.add_cookies([c])
    except Exception as e:
        print(f"跳过 {c['name']}: {e}")
```

**坑**：cookie value 里有非 ASCII / 控制字符会被 playwright 拒绝。
**解法**：try/except 单条跳过，不影响其他。

## 4. 屏蔽 webdriver 标志

```python
page.add_init_script("""
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
""")
```

**注意**：这只能骗过最浅层的检查。EO-Bot / Akamai 还会查：
- `navigator.plugins`（长度和内容）
- `navigator.languages`
- `navigator.platform`
- canvas fingerprint
- WebGL renderer

深度伪装需要 `playwright-stealth` 库或 `undetected-playwright`。

## 5. 监听 network / console / pageerror

```python
# network 响应
api_calls = []
def on_response(r):
    if r.url.startswith("https://api.example.com"):
        try:
            api_calls.append({
                "url": r.url[:200],
                "status": r.status,
                "body": r.text()[:500],
            })
        except Exception:
            pass
page.on("response", on_response)

# console 日志
page.on("console", lambda m: print(f"[console.{m.type}] {m.text}"))

# 页面 JS 异常
page.on("pageerror", lambda e: print(f"[pageerror] {e}"))
```

**用途**：找出真正的 API 端点。多数 SPA 的数据通过 XHR/fetch 加载，监听 response 能看到完整 URL + payload。

## 6. 页面内 fetch API（绕过 API 层 JS 挑战）

```python
data = page.evaluate("""async (url) => {
    const r = await fetch(url, {credentials: 'include'});
    const t = await r.text();
    try { return {ok: true, json: JSON.parse(t)}; }
    catch (e) { return {ok: false, status: r.status, text: t.slice(0, 500)}; }
}""", "https://api.example.com/v1/items?limit=20")
```

**为什么**：浏览器引擎已经过 JS 挑战，session cookie（如 `EO_Bot_Ssid`）齐全。fetch 从浏览器内部发起，自动带这些 cookie + 引擎指纹。

## 7. 等 JS 挑战完成

```python
# 通用模式：等到某个目标元素出现 = 验证通过
page.goto(url, wait_until="domcontentloaded", timeout=60000)
for i in range(60):
    time.sleep(1)
    ok = page.evaluate("() => !!document.querySelector('[data-ready], .board-content')")
    if ok:
        break
    if i % 10 == 9:
        # 调试：截图看状态
        page.screenshot(path="debug.png")
```

**关键**：不要用 `wait_for_load_state('networkidle')`（JS 挑战页本身可能让 network "idle"）。

## 8. 滚动加载翻页

```python
last_count = 0
idle = 0
for i in range(50):
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(2)
    n = page.evaluate("() => window.app?.store?.items?.length || 0")
    if n == last_count:
        idle += 1
        if idle >= 3:
            break
    else:
        idle = 0
    last_count = n
```

## 9. 提取嵌入 JSON（__NEXT_DATA__ / app.page / __INITIAL_STATE__）

```python
# Next.js
data = page.evaluate("() => window.__NEXT_DATA__?.props?.pageProps || {}")

# 旧版 SPA（花瓣网 2025 之前）
data = page.evaluate("() => window.app?.page?.board?.pins || []")

# Nuxt.js
data = page.evaluate("() => window.__NUXT__?.data || {}")
```

**坑**：现代 SPA 数据往往不在初始 HTML 里，而是 API 异步加载。
**解法**：监听 network 找真实端点，再走 #6 页面内 fetch。

## 10. 文件下载（CDN 公开资源）

图片/视频 CDN 通常公开，不需要登录。直接用 requests 拉，绕过 playwright：

```python
import requests
r = requests.get(
    f"https://cdn.example.com/{key}",
    headers={"Referer": "https://example.com/"},
    timeout=20,
)
if r.status_code == 200:
    Path(f"output/{key}.jpg").write_bytes(r.content)
```

**好处**：playwright 慢、占内存。CDN 公开就 requests 并发（用 `concurrent.futures.ThreadPoolExecutor`）。

## 11. 截图留档

```python
# 全页截图
page.screenshot(path="full.png", full_page=True)

# 当前视口
page.screenshot(path="viewport.png")

# 元素截图
el = page.query_selector(".board-item")
el.screenshot(path="element.png")
```

**用途**：调试 JS 挑战卡哪一步、记录页面状态。

## 12. 下载 PDF / 二进制

```python
# 触发浏览器下载（适用于需要 cookie 的资源）
with page.expect_download() as dl_info:
    page.click("a.download-link")
download = dl_info.value
download.save_as("output/file.pdf")

# 或者 CDN 直接拉（同 #10）
```

## 13. 多 page 并发（同一 browser 内）

```python
context = browser.new_context()
pages = [context.new_page() for _ in range(3)]
for i, p in enumerate(pages):
    p.goto(f"https://example.com/page/{i}")
# 注意：playwright 不支持多 browser 并发，但同一 browser 多 page 可以
```

## 14. 拦截请求 / 修改请求头

```python
def handle(route, request):
    headers = {**request.headers, "X-Custom": "value"}
    route.continue_(headers=headers)
page.route("**/api/**", handle)
```

## 15. 优雅退出

```python
try:
    # 主逻辑
    ...
except KeyboardInterrupt:
    print("用户中断")
finally:
    browser.close()  # 不写可能进程残留
```

## 调试 checklist

拿不到数据时按顺序排查：

1. **浏览器启动了吗？** 加 `time.sleep(3); page.screenshot(path="debug1.png")` 看第一帧
2. **页面渲染了吗？** `print(page.title())` 看标题
3. **JS 挑战通过了吗？** 看 URL 里 `?tads` 之类参数是否去掉
4. **网络请求正常吗？** 加 `page.on("response", ...)` 监听
5. **页面里有数据吗？** `print(page.content()[:500])` 看 HTML 头部
6. **window 全局变量是什么？** `print(list(window.__dict__.keys())[:30])`
7. **控制台有错吗？** `page.on("pageerror", ...)` 监听

## 性能 tips

- 复用 `browser.contexts[0]` 而不是每次 `new_context()`
- `wait_for_selector` 比 `time.sleep` 更精准
- 批量下载用 `requests` + ThreadPoolExecutor（10~20 线程够用）
- `headless="new"` 比 `headless=True` 更难被识别（如果实在不能用 headful）

## 16. Playwright + PWA 网站的陷阱

很多现代网站是 PWA（Progressive Web App），访问时会注册 Service Worker 预缓存资源。SW 缓存默认写到**当前工作目录**的 `resources/`，**不走 playwright 的 user_data_dir**，所以你换 profile 也没用。

**症状**：
```
<output_dir>/resources/<topic_name>/icon/*.png   几十张推荐资源图
<output_dir>/resources/<topic_name>/icon/*.jpg-lx2
```
删了下次跑又出现，跟 Edge 的 user_data 缓存无关。

**根因**：Service Worker Cache API 的存储位置之一是 `${cwd}/resources/`（取决于浏览器实现）。

**解法（3 层防御）**：

```python
import shutil
from pathlib import Path

# 在脚本最前面定义
def cleanup_sw_cache(output_dir):
    """清理 PWA 的 Service Worker 缓存到 output_dir/resources/ 的文件。"""
    for name in ("resources", "background_clothing_conf"):
        target = Path(output_dir) / name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            print(f"  ✓ 清理 SW 缓存: {target.name}/")
```

```python
# 1. Edge args 加限制（从源头减少）
args=[
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disk-cache-size=1048576",   # 限制 SW 缓存到 1MB
]

# 2. 启动 browser 前清一次
cleanup_sw_cache(OUTPUT_DIR)

# 3. browser.close() 之后再清一次
browser.close()
cleanup_sw_cache(OUTPUT_DIR)
```

**不要用** `--disable-features=ServiceWorker`：很多 PWA 站点的核心功能依赖 SW（比如花瓣网），关掉会直接导致页面不正常工作。

**判断是否 PWA**：跑 probe.py 后看返回 HTML 里有没有 `<link rel="manifest">` 或者 navigator.serviceWorker 注册代码。
