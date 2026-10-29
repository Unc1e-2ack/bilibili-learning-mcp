# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与
[Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Fixed

- CI：将 `astral-sh/setup-uv` 固定到 `v10.3.3`（该仓库没有 `v10` 浮动标签，
  `@v10` 会导致所有 job 在 Set up job 阶段失败）

## [0.1.0] - 2026-10-29

### Added

- 4 个 MCP 工具：`search_videos`、`get_video_info`、`get_subtitles`、`get_hot_comments`
- 字幕按 `[mm:ss]` 输出，支持 `start_sec` / `end_sec` 时间窗与 8000 行截断
- WBI 请求签名，签名 key 缓存 6 小时
- 搜索默认匿名可用，Cookie 可选；412 / -101 / -352 / -509 时返回配置指引
- 11 类 B 站业务错误码与 HTTP、超时、非 JSON 响应的统一中文提示
- `.env` 加载（不覆盖已有环境变量）
- 36 个基于 `httpx.MockTransport` 的离线测试
- GitHub Actions：Linux 上覆盖 Python 3.10–3.13，另含 Windows / macOS 3.12
- Issue / PR 模板、安全策略、贡献指南与 Dependabot

### Security

- Cookie 只发往 `api.bilibili.com`，请求字幕 CDN 时不携带
- 不落盘、不记录 Cookie，不下载视频，不调用 LLM
