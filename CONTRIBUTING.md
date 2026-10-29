# Contributing

感谢参与！无论是 issue、文档还是代码都欢迎。

## 开发环境

要求 Python 3.10+，使用 `uv` 管理依赖（不要引入 `requirements.txt`）。

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

提交 PR 前，后三条必须全部通过。

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

```text
feat: add get_hot_comments tool
fix: handle empty subtitle body
test: cover wbi key caching
docs: document cookie setup
chore: bump mcp to 1.31
```

- 一个 commit 只做一件事；
- 标题用英文，正文可中文；
- 破坏性变更用 `feat!:`，并在正文写 `BREAKING CHANGE:`。

## 分支与 PR

1. 从 `main` 切分支：`feat/xxx`、`fix/xxx`、`docs/xxx`；
2. 提交前跑完上面的检查命令；
3. PR 描述写清楚「改了什么 / 为什么 / 怎么验证」；
4. CI 全绿后 squash merge，保持历史干净。

## 新增一个 tool

1. 在 `server.py` 用 `@mcp.tool` 注册，docstring 必须包含：**何时调用 / 参数 / 返回示例 / 失败时**；
2. HTTP 逻辑写在 `bilibili_api.py`，tool 层只负责校验与文本渲染；
3. 解析 B 站返回一律用 `.get()`，不允许裸索引；
4. 在 `tests/test_api.py` 与 `tests/test_tools.py` 各补用例，统一使用 `httpx.MockTransport`；
5. 更新 README 的工具表、错误处理与 CHANGELOG 的 `Unreleased`。

## 代码约定

- 所有函数写类型注解和 docstring，docstring 用 Google 风格（ruff `D` 规则会检查）；
- **tool 的 docstring 是给 LLM 看的说明书**，它会直接影响模型是否选对工具；
- 新增接口必须做防御式解析，字段缺失不能抛 `KeyError`；
- 测试一律使用 `httpx.MockTransport`，**不要**在测试里请求真实 B 站；
- 新增运行时依赖前先开 issue 讨论，优先使用标准库与现有依赖。

## 文档同步

修改以下内容时，必须同步更新对应文档：

| 改动 | 需要更新 |
| --- | --- |
| 工具行为 / 参数 / 错误文案 | `server.py` 的 tool docstring、README |
| 安装或接入方式 | README |
| 安全模型 | SECURITY.md |
| 用户可见变更 | CHANGELOG.md |

## 不要提交

- `Cookie`、`SESSDATA`、`.env`
- 视频文件、字幕缓存、任何用户数据
- `.probe/` 等本地调试产物

## License

提交代码即表示同意以 [MIT](LICENSE) 协议发布。
