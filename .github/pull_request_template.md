## 变更内容

<!-- 简要说明改了什么 -->

## 关联 issue

Closes #

## 自查

- [ ] `uv run ruff check .` 通过
- [ ] `uv run ruff format --check .` 通过
- [ ] `uv run pytest` 通过
- [ ] 新增/修改的 tool 有完整 docstring（何时调用 / 参数 / 返回示例）
- [ ] 测试使用 mock，没有请求真实 B 站
- [ ] 没有提交 Cookie、`.env` 或用户数据