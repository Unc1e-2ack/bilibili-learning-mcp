# bilibili-learning-mcp

给 Codex / Claude Desktop 等 MCP 客户端使用的 **B 站学习视频** MCP server：
搜索视频、读取视频信息、抓取字幕、查看热门评论。

> Server 只负责取数据，**不调用任何 LLM API**；总结与笔记由客户端模型完成。

## 状态

早期开发中（0.1.x）。四个工具：`search_videos`、`get_video_info`、
`get_subtitles`、`get_hot_comments`。

## 快速开始

```bash
git clone https://github.com/Unc1e-2ack/bilibili-learning-mcp.git
cd bilibili-learning-mcp
uv sync
cp .env.example .env   # 填入 BILIBILI_COOKIE
uv run main.py
```

## License

MIT