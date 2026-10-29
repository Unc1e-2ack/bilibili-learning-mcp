# bilibili-learning-mcp

[![CI](https://github.com/Unc1e-2ack/bilibili-learning-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Unc1e-2ack/bilibili-learning-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-stdio-8a2be2.svg)](https://modelcontextprotocol.io)

让 Codex、Claude Desktop 等 MCP 客户端直接「看」B 站学习视频的 server：
搜索视频、读取简介、抓取字幕、查看热门评论。

> **只提供数据，不调用任何 LLM API。** 总结、笔记、问答全部由客户端模型完成；
> Server 不含任何模型调用、不下载视频、不持久化内容。

**状态**：`0.1.0`（Alpha），当前仅支持 stdio 传输。

## 它能做什么

| 工具 | 作用 | 登录 Cookie |
| --- | --- | --- |
| `search_videos` | 关键词搜索，返回标题 / UP主 / BV号 / 时长 / 播放量 | ⚪ 可选 |
| `get_video_info` | 标题、简介、UP主、分P（含 cid）、播放/点赞/收藏、时长 | ❌ 不需要 |
| `get_subtitles` | 字幕逐行输出 `[mm:ss] 文本`（超过 1 小时为 `[h:mm:ss]`），支持按秒级时间段截取 | ⚠️ 通常需要 |
| `get_hot_comments` | 按点赞排序的热门评论，用来判断视频口碑 | ❌ 不需要 |

> 搜索、视频信息、热门评论均可匿名使用；字幕（尤其 AI 字幕）需要登录 Cookie。
> 配置 Cookie 还能降低搜索触发风控的概率。

典型用法：

> 帮我找「线性代数 期末速成」的视频，挑播放量最高的那个，读字幕整理一份带时间戳的笔记。

## 快速开始

### 1. 准备环境

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 可选：Node.js 18+（仅使用 MCP Inspector 调试时需要）

### 2. 安装

```bash
git clone https://github.com/Unc1e-2ack/bilibili-learning-mcp.git
cd bilibili-learning-mcp
uv sync
```

### 3. 接入客户端

#### Claude Desktop

编辑 `claude_desktop_config.json`（Windows：`%APPDATA%\Claude\`；macOS：`~/Library/Application Support/Claude/`）：

```json
{
  "mcpServers": {
    "bilibili-learning": {
      "command": "uv",
      "args": [
        "--directory",
        "G:\\path\\to\\bilibili-learning-mcp",
        "run",
        "bilibili-learning-mcp"
      ]
    }
  }
}
```

macOS / Linux 把示例里的 Windows 路径换成 `/path/to/...`。如果客户端找不到 `uv`，
把 `command` 换成 `uv` 的绝对路径。

需要字幕时，在同一层级加上 `env`：

```json
"env": {
  "BILIBILI_COOKIE": "SESSDATA=xxx; bili_jct=yyy"
}
```

#### Codex

```bash
codex mcp add bilibili-learning -- uv --directory "/path/to/bilibili-learning-mcp" run bilibili-learning-mcp
```

需要字幕时，先移除再带 Cookie 注册：

```bash
codex mcp remove bilibili-learning
codex mcp add bilibili-learning \
  --env BILIBILI_COOKIE="SESSDATA=xxx; bili_jct=yyy" \
  -- uv --directory "/path/to/bilibili-learning-mcp" run bilibili-learning-mcp
```

Windows 下路径建议用绝对路径并加引号（例如 `"G:\path\to\bilibili-learning-mcp"`）。
注册后新开一个会话才会生效。

#### 其它 MCP 客户端

stdio 命令：

```bash
uv --directory /path/to/bilibili-learning-mcp run bilibili-learning-mcp
```

### 4. 可选：配置 Cookie（字幕需要）

1. 浏览器登录 [bilibili.com](https://www.bilibili.com)；
2. 按 `F12` 打开开发者工具 → **Network**，筛选 `api.bilibili.com`；
3. 随便点一个请求，复制请求头里完整的 `Cookie:` 值（至少包含 `SESSDATA`）；
4. 复制配置模板并填入：

```bash
cp .env.example .env
# 或者在 shell 里导出
export BILIBILI_COOKIE='SESSDATA=xxx; bili_jct=yyy; ...'
```

> ⚠️ Cookie 等同于账号凭证。`.env` 已在 `.gitignore` 中，**不要提交、不要贴到 issue 里**。

## 使用示例

```text
我：帮我总结一下 BV1xx411c7mD 讲了什么，要带时间戳。

模型：-> get_video_info(bv_id="BV1xx411c7mD")
      -> get_subtitles(bv_id="BV1xx411c7mD", page=1)
      -> 用字幕生成带 [mm:ss] 的笔记
```

`BV1xx411c7mD` 只是占位示例，请换成实际 BV 号。没有字幕的视频会在 `get_subtitles` 处得到明确提示。

字幕过长时会自动截断到 8000 行并提示总行数，可以用 `start_sec` / `end_sec` 分段读取：

```text
get_subtitles(bv_id="BV1xx411c7mD", page=1, start_sec=600, end_sec=1200)
```

## 常见问题

**一定要配置 Cookie 吗？**
不需要。搜索、视频信息、热门评论都能匿名使用；字幕接口通常需要登录 Cookie，AI 字幕尤其如此。

**为什么提示「没有可用字幕」？**
可能该视频没有生成字幕、该分P没有字幕，或者当前请求缺少有效 Cookie。可以换一个视频，或改用 `get_video_info` 看简介。

**会不会导致账号被封？**
项目只调用只读 Web 接口，不下载视频、不批量抓取，所有请求串行间隔 ≥ 1 秒。仍建议低频使用并自行承担风险。

**支持 HTTP / SSE 吗？**
当前只支持 stdio。如果客户端只接受 HTTP，可以自行用 `mcp-proxy` 之类的工具转换。

**支持哪些平台？**
Windows、macOS、Linux；CI 覆盖 Python 3.10–3.13。

## 错误处理

工具层会把所有错误转成给模型看的中文说明，而不是抛异常或只返回错误码：

| 情况 | 返回 |
| --- | --- |
| 需要登录但未配置 Cookie | 提示 `BILIBILI_COOKIE` 的配置方法 |
| 匿名搜索被 412 / 风控拦截 | 提示配置 Cookie 后重试 |
| `-101` 未登录 / Cookie 失效 | 提示重新获取 Cookie |
| `-352` WBI 校验失败 | 提示稍后重试，持续失败则更新 Cookie |
| 网络超时（10s） | 提示稍后重试 |
| 返回非 JSON | 说明可能被风控页拦截 |
| 无字幕 | 提示改用 `get_video_info` 看简介 |

## 设计说明

- **匿名优先，Cookie 可选**：搜索默认匿名请求，配置了 Cookie 会自动携带，用来提高风控下的成功率。
- **请求节流**：所有请求串行间隔 ≥ 1 秒，避免给 B 站造成压力。
- **WBI 签名**：从 `nav` 接口取 `img_key` / `sub_key`，缓存 6 小时，按社区文档的置换表计算 `w_rid`（参考 [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)）。
- **凭据最小暴露**：Cookie 只发往 `api.bilibili.com`，请求字幕 CDN 时不会携带。
- **防御式解析**：所有接口字段用 `.get()` 读取，字段缺失不会 KeyError。
- **不做的事**：不下载视频、不落盘任何内容、不调用 LLM、不上传用户数据。
- **BV 号**：支持完整链接，自动提取；`BV` 前缀统一大写，但**主体大小写保持不变**（BV 号主体区分大小写，改动会导致查不到视频）。

## 开发

```bash
uv sync                     # 安装依赖（含开发依赖）
uv run pytest               # 36 个测试，全部 mock，不请求真实 B 站
uv run ruff check .         # 静态检查
uv run ruff format --check .  # 格式检查
uv run mcp dev main.py      # MCP Inspector（需要 Node.js）
uv run main.py              # 以 stdio 方式启动
```

项目结构：

```text
.
├── src/bilibili_learning_mcp/
│   ├── __init__.py
│   ├── server.py        # FastMCP 实例 + 4 个 tool
│   ├── bilibili_api.py  # HTTP 封装、节流、错误映射
│   ├── wbi_sign.py      # WBI 签名
│   └── py.typed
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_tools.py
│   └── test_wbi_sign.py
├── .github/
│   ├── workflows/ci.yml
│   └── ISSUE_TEMPLATE/
├── main.py
├── pyproject.toml
├── uv.lock
├── CHANGELOG.md
├── LICENSE
└── README.md
```

## 贡献与安全

- 提交规范、开发约定见 [CONTRIBUTING.md](CONTRIBUTING.md)
- 漏洞报告方式见 [SECURITY.md](SECURITY.md)
- 版本变更见 [CHANGELOG.md](CHANGELOG.md)

## 合规与免责

- 本项目仅调用 B 站公开 Web 接口，用于个人学习与内容检索；
- 请遵守 [B 站用户协议](https://www.bilibili.com/protocol/) 与 `robots.txt`，不要高频抓取；
- 字幕与评论版权归原作者所有，请勿二次分发；
- 本项目与哔哩哔哩官方无关。

## License

[MIT](LICENSE)
