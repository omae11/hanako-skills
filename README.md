# hanako-skills

Custom skills for [HanaAgent](https://github.com/liliMozi/openhanako), the personal AI assistant platform.

These skills are designed to be dropped into `~/.hanako/skills/` and discovered automatically.

## Skills

### [huaban-image-crawler](./huaban-image-crawler/)

批量下载花瓣网（huaban.com）画板图片到本地。专门处理花瓣网 2026 年的反爬栈（EO-Bot + Next.js + v3 REST API）。

**特点**：
- 完整可跑脚本（无需自己实现）
- 11 项 preflight 检查（覆盖所有已知坑）
- 多画板 CLI（`--boards` / `--boards-file`）
- webp/heif → png 自动转换
- PWA Service Worker 缓存清理

适用：用户提到"花瓣网"、"迷彩数据集"、"画板 ID"、"92623632" 等场景。

### [anti-bot-bypass](./anti-bot-bypass/)

通用方法论：绕过带 JS 挑战的反爬网站（Cloudflare / EO-Bot / Akamai / 极验 / DataDome 等），用真浏览器自动化采集数据。

**特点**：
- 决策树 + 工作流（不针对具体站）
- 反爬栈对照表（8 种主流反爬的指纹 + 解法）
- Playwright 代码片段 cookbook（15 个常见场景）
- 通用探针（probe.py 自动识别反爬栈）
- 可复用模板（browser_crawler.py）

适用：用户提到"反爬绕过"、"Cloudflare 验证"、"JS 挑战"、"想爬 XX 网站但 requests 不行"。

## 两个 skill 的关系

```
huaban-image-crawler  ← 专用：花瓣网（已沉淀 8 个踩过的坑 + 现成脚本）
    ↑
    └── 互指
    ↓
anti-bot-bypass       ← 通用：任何反爬站（决策树 + 模板 + reference）
```

- 如果确定目标是花瓣网 → 直接用 `huaban-image-crawler`
- 如果是其他反爬站 → 用 `anti-bot-bypass` 探针诊断 + 通用模板

## 安装

### 方法 1：手动复制

```powershell
# 在 HanaAgent 的 skills 目录下
git clone https://github.com/omae11/hanako-skills.git _tmp
# 复制需要的 skill 进去
Copy-Item _tmp\huaban-image-crawler C:\Users\<user>\.hanako\skills\ -Recurse
Copy-Item _tmp\anti-bot-bypass C:\Users\<user>\.hanako\skills\ -Recurse
Remove-Item _tmp -Recurse
```

### 方法 2：单 skill 安装

```powershell
# 单独复制某个 skill
$src = "https://github.com/omae11/hanako-skills/tree/main/huaban-image-crawler"
# 浏览器下载 zip，解压到 skills 目录
```

### 方法 3：通过 HanaAgent skill 安装工具（如果支持）

```powershell
# 未来的 skill 安装命令（占位）
hanako skill install https://github.com/omae11/hanako-skills
```

## 开发

两个 skill 都在持续迭代中。每次新踩一个坑，会同步加到 SKILL.md 的"踩过的坑"清单 + bump 版本号。

## License

MIT
