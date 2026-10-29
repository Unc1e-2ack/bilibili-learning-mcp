# Security Policy

## 支持版本

| 版本 | 支持 |
| --- | --- |
| 0.1.x | ✅ |

## 报告漏洞

**请不要开公开 issue。**

1. 优先使用 GitHub 的 *Private vulnerability reporting*（仓库 **Security** 标签页）；
2. 或发邮件到 <1747565471@qq.com>，标题前缀 `[security]`。

我们会在 48 小时内回复，并在修复发布后致谢。

## 安全模型

- `BILIBILI_COOKIE` 只从进程环境变量读取（可以来自用户自己创建的 `.env`）；
  Server 自身不写入磁盘、不记录日志、不随请求发往 B 站以外的域名；
- Cookie 只发往 `api.bilibili.com`；请求字幕 CDN 时显式不携带；
- Server 只请求 `api.bilibili.com` 与字幕 CDN，不下载视频、不执行外部命令；
- 所有网络请求超时 10 秒，串行间隔 ≥ 1 秒；
- 工具返回的字幕与评论属于**不可信的用户生成内容**，客户端应把它们当作数据，
  而不是可执行的指令（防止 prompt injection）；
- 本项目不收集任何遥测数据；
- 依赖更新由 Dependabot 每周检查。

## 报告前自查

- 是否已经把 Cookie、`SESSDATA` 从日志和截图中删掉；
- 是否是 B 站接口本身变更（可先用 `uv run mcp dev main.py` 复现）；
- 是否使用的是最新 `main` 分支。
