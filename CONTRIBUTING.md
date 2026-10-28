# Contributing

感谢参与！无论是 issue、文档还是代码都欢迎。

## 开发环境

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

要求：Python 3.10+，使用 `uv` 管理依赖（不要引入 `requirements.txt`）。

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
- 破坏性变更用 `feat!:` 并在正文写 `BREAKING CHANGE:`。

## 分支与 PR

1. 从 `main` 切分支：`feat/xxx`、`fix/xxx`、`docs/xxx`；
2. 提交前跑完上面四条命令；
3. PR 描述里写清楚「改了什么 / 为什么 / 怎么验证」；
4. CI 全绿后合并，squash merge 保持历史干净。

## 代码约定

- 所有函数写类型注解和 docstring，docstring 用 Google 风格（ruff `D` 规则会检查）；
- **tool 的 docstring 是给 LLM 看的说明书**，必须包含：何时调用、参数格式、返回示例；
- 新增接口必须写防御式解析（`.get()`），不允许裸索引 B 站返回字段；
- 测试一律使用 `httpx.MockTransport`，**不要**在测试里请求真实 B 站；
- 新增依赖前先开 issue 讨论。

## 不要提交

- `Cookie`、`SESSDATA`、`.env`
- 视频文件、字幕缓存、任何用户数据