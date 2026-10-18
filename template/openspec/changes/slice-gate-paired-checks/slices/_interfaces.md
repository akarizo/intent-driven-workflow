# 公开接口摘要

## S1 · template/.claude/hooks/slice-gate.py
- `_nonblank(v)`：判断值是否为去空白后非空的 str
- `_lint_checks(gate)`：校验 `gate.checks` / `gate.checks_skip` 形状，返回问题列表
- `_repo_default_checks(change_dir)`：读仓库默认检查文件 `gate-checks.json`，返回默认检查名与解析问题
- `lint_plan(data, change_dir=None)`：计划 lint，新增 checks 相关检查（无 checks 时返回不变）

## S4 · 文档
- 无代码接口；`gate.checks` 配置、时机与契约见 README.md、schema.yaml、opsx-propose / opsx-verify 命令与同名 skill。
