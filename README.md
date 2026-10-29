# bilibili-learning-mcp

[![CI](https://github.com/Unc1e-2ack/bilibili-learning-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Unc1e-2ack/bilibili-learning-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-stdio-8a2be2.svg)](https://modelcontextprotocol.io)

让 Codex、Claude Desktop 等 MCP 客户端直接「看」B 站学习视频的 server：
搜索视频、读取简介、抓取字幕、查看热门评论。

> **只提供数据，不调用任何 LLM API。** 总结、笔记、问答全部由客户端模型完成，
> Server 不含任何模型调用、不下载视频、不存储内容。

## 它能做什么

| 工具 | 作用 | 需要登录 Cookie |
| --- | --- | --- |
| `search_videos` | 关键词搜索，返回标题 / UP主 / BV号 / 时长 / 播放量 | ⚪ 可选 |
| `get_video_info` | 标题、简介、UP主、分P（含 cid）、播放/点赞/收藏、时长 | ❌ |
| `get_subtitles` | 字幕逐行输出 `[mm:ss] 文本`，支持按秒级时间段截取 | ⚠️ AI 字幕需要 |
| `get_hot_comments` | 按点赞排序的热门评论，用来判断视频口碑 | ❌ |

> 搜索、视频信息、热门评论均无需登录即可使用；只有 AI 字幕必须登录，
> Cookie 还能提高搜索在风控下的成功率。

典型用法：

> 帮我找「线性代数 期末速成」的视频，挑播放量最高的那个，读字幕整理一份带时间戳的笔记。

## 安装

### 1. 准备环境

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### 2. 获取代码

```bash
git clone https://github.com/Unc1e-2ack/bilibili-learning-mcp.git
cd bilibili-learning-mcp
uv sync
```

### 3. 配置 B 站 Cookie

AI 字幕需要登录 Cookie（搜索、视频信息、热门评论可匿名使用）：

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

## 接入客户端

### Claude Desktop

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
      ],
      "env": {
        "BILIBILI_COOKIE": "SESSDATA=xxx; bili_jct=yyy"
      }
    }
  }
}
```

### Codex

```bash
codex mcp add bilibili-learning \
  --env BILIBILI_COOKIE="SESSDATA=xxx; bili_jct=yyy" \
  -- uv --directory "/path/to/bilibili-learning-mcp" run bilibili-learning-mcp
```

### 其它 MCP 客户端

stdio 命令：

```bash
uv --directory /path/to/bilibili-learning-mcp run bilibili-learning-mcp
```

调试时可以用官方 Inspector：

```bash
uv run mcp dev main.py
```

## 使用示例

```text
我：帮我总结一下 BV1GJ411x7h7 讲了什么，要带时间戳。

模型：-> get_video_info(bv_id="BV1GJ411x7h7")
      -> get_subtitles(bv_id="BV1GJ411x7h7", page=1)
      -> 用字幕生成带 [mm:ss] 的笔记
```

字幕过长时会自动截断到 8000 行并提示总行数，可以用 `start_sec` / `end_sec` 分段读取：

```text
get_subtitles(bv_id="BV1GJ411x7h7", page=1, start_sec=600, end_sec=1200)
```

## 错误处理

所有错误都会转成给模型看的中文说明，而不是抛异常或只返回错误码：

| 情况 | 返回 |
| --- | --- |
| 未配置 Cookie | 提示 `BILIBILI_COOKIE` 的配置方法 |
| HTTP 412 / 风控 | 提示更新 Cookie、降低频率后重试 |
| `-101` 未登录 | 提示 Cookie 已失效，重新获取 |
| 网络超时（10s） | 提示稍后重试 |
| 返回非 JSON | 说明可能被风控页拦截 |
| 无字幕 | 提示改用 `get_video_info` 看简介 |

## 设计说明

- **请求节流**：所有请求串行间隔 ≥ 1 秒，避免给 B 站造成压力。
- **WBI 签名**：从 `nav` 接口取 `img_key` / `sub_key`，缓存 6 小时，按社区文档的置换表计算 `w_rid`。
- **不做的事**：不下载视频、不落盘任何内容、不调用 LLM、不上传用户数据。
- **防御式解析**：所有接口字段用 `.get()` 读取，字段缺失不会 KeyError。
- **BV 号**：支持完整链接，自动提取；`BV` 前缀统一大写，但**主体大小写保持不变**（BV 号主体区分大小写，改动会导致查不到视频）。

## 开发

```bash
uv sync                  # 安装依赖
uv run pytest            # 运行测试（全部 mock，不请求真实 B 站）
uv run ruff check .      # 静态检查
uv run ruff format .     # 格式化
uv run main.py           # 以 stdio 方式启动
```

项目结构：

```text
.
├── src/bilibili_learning_mcp/
│   ├── server.py        # FastMCP 实例 + 4 个 tool
│   ├── bilibili_api.py  # HTTP 封装、节流、错误映射
│   └── wbi_sign.py      # WBI 签名
├── tests/
│   ├── test_api.py
│   ├── test_tools.py
│   └── test_wbi_sign.py
├── main.py
└── pyproject.toml
```

提交规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题见 [SECURITY.md](SECURITY.md)。

## 合规与免责

- 本项目仅调用 B 站公开 Web 接口，用于个人学习与内容检索；
- 请遵守 [B 站用户协议](https://www.bilibili.com/protocol/) 与 `robots.txt`，不要高频抓取；
- 字幕与评论版权归原作者所有，请勿二次分发；
- 本项目与哔哩哔哩官方无关。

## License

[MIT](LICENSE)