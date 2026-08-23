# Anti-Bot Stacks Reference

各反爬栈的指纹、检测项、解法速查。
配合主 SKILL.md 的 probe.py 用：probe 报出某个名字时直接来这查表。

## Cloudflare

**指纹**：
- HTML: `<script src="/cdn-cgi/challenges/...">` 或 `<title>Just a moment...</title>`
- Header: `Server: cloudflare`、`cf-ray`、`cf-cache-status`
- Cookie: `cf_clearance`（验证通过后才有）、`__cf_bm`
- JS 变量: `window._cf_chl_opt`

**检测项**：
- TLS 指纹（JA3）
- `navigator.webdriver`
- 行为（鼠标轨迹、键盘事件）
- 头部一致性

**解法**：
- 真浏览器 headful
- 不能用 `cf-clearance` cookie 跨 session 复用（会失效）
- 高频访问需要 residential proxy

**经验阈值**：
- 普通页面：headful 一次过
- 受保护页面：可能被二次挑战（Cloudflare Turnstile）

## F5 EO-Bot / Shape Security

**指纹**：
- HTML: `<script>function a(a){function n(){...}}` 这种混淆 JS
- Cookie: `EO-Bot-Js-Token`、`EO_Bot_Ssid`
- 行为：setTimeout 跳转、location.replace

**检测项**：
- JS 引擎指纹
- TLS 指纹
- 请求时序分析

**解法**：
- 真浏览器 headful
- JS 跑完会跳转到去掉 `?tads` 参数的 URL
- 等到 `document.querySelector` 找到 board container 类元素 = 验证通过

**案例**：花瓣网 2026

## Akamai Bot Manager

**指纹**：
- HTML: `<script src="https://...akamaihd.net/...">`
- Cookie: `_abck`（验证通过后）、`bm_sz`
- Header: `X-Akamai-...`

**检测项**：
- TLS 指纹（JA3 + JA4）
- HTTP/2 指纹
- 行为分析

**解法**：
- 真浏览器 + 人类节奏（sleep 1~3 秒）
- 不能用裸 curl_cffi 简单伪装（Akamai 升级后也会查 HTTP/2）

**经验阈值**：
- 低风险路径：headful 直接过
- 高风险路径（搜索、API）：容易被二次挑战

## 极验 (GeeTest)

**指纹**：
- HTML: `<script src="https://static.geetest.com/...">`
- Cookie: `gt_token`、`user_id`
- JS 变量: `window._GeeTest`

**检测项**：
- 滑块 / 点选 / 旋转验证码
- JS 引擎指纹
- 行为轨迹

**解法**：
- 真浏览器 + 滑块识别（cv2 模板匹配 / 深度学习模型）
- 或用打码平台（2Captcha、YesCaptcha）
- 简单文字点选可以人工介入 + 半自动化

**案例**：12306、部分政府网站

## reCAPTCHA v3

**指纹**：
- HTML: `<script src="https://www.google.com/recaptcha/...">`
- 隐藏的 `grecaptcha` 元素
- Token: `03AGdBq25...`

**检测项**：
- 行为评分（0.0~1.0，< 0.3 判定 bot）
- JS 引擎指纹
- Cookie 历史

**解法**：
- 真浏览器 + 慢节奏
- 高频场景需要 residential proxy + 随机 UA
- 实在过不去用 2Captcha

## DataDome

**指纹**：
- HTML: `<script src="https://...datadome.co/...">`
- Cookie: `datadome`
- Header: `x-dd-b`

**检测项**：
- TLS 指纹
- 行为分析
- 设备指纹（canvas、fonts）

**解法**：
- 真浏览器 + 慢节奏 + 随机 viewport
- residential proxy 几乎必须

## PerimeterX / HUMAN

**指纹**：
- HTML: `<script src="https://...px-cdn.net/...">`
- Cookie: `_pxhd`、`_pxvid`、`_px3`

**检测项**：
- 设备指纹
- 行为分析

**解法**：
- 真浏览器
- 高频场景需要 residential proxy

## 自研 WAF（无品牌）

**指纹**：
- HTML: 返回的可能是空白页 / 403 / 重定向到登录页
- Header: 自定义 `X-WAF-...`

**检测项**：
- 看不出来，但 UA / Header 不对就会被拦

**解法**：
- 用 probe.py 测一下，看请求头哪个被拦
- 逐步加：`User-Agent`、`Referer`、`Origin`、`Accept-Language`、`Sec-Fetch-*`
- 多数 WAF 只要头部完整就放行

## 决策速查

| probe 输出 | 大概率反爬栈 | 快速解法 |
|---|---|---|
| `Just a moment` / `cf-ray` | Cloudflare | headful + 慢节奏 |
| `EO-Bot-Js-Token` / `EO_Bot_Ssid` | F5 EO-Bot | headful + 页面内 fetch |
| `akamaihd` / `_abck` | Akamai | headful + residential proxy |
| `geetest` / `gt_token` | 极验 | headful + 滑块识别 / 打码 |
| `recaptcha` / `grecaptcha` | reCAPTCHA | headful + 慢节奏 |
| `datadome` | DataDome | headful + residential proxy |
| `x-cf-` / 空白页 | Cloudflare（旧版） | headful + 慢节奏 |
| 自定义 WAF | 自研 | probe 测 UA/Header |

## 通用反检测 tips

不管哪个反爬栈，下面这些都有效：

1. **headful 永远优于 headless**——headless 有大量可识别特征
2. **真人节奏**——sleep 1~3 秒、不要固定间隔
3. **完整 Header**——Referer、Origin、Accept-Language、Sec-Fetch-* 都加上
4. **复用 user data**——不要每次重新启动浏览器
5. **不要修改 UA**——playwright 默认的 Edge UA 就行，改了反而可疑
6. **行为多样**——滚动、点击、停留，不要纯机械式翻页
