# 公开接口摘要

## S1 · template/.claude/hooks/slice-gate.py
- `_nonblank(v)`：判断值是否为去空白后非空的 str
- `_lint_checks(gate)`：校验 `gate.checks` / `gate.checks_skip` 形状，返回问题列表
- `_repo_default_checks(change_dir)`：读仓库默认检查文件 `gate-checks.json`，返回默认检查名与解析问题
- `lint_plan(data, change_dir=None)`：计划 lint，新增 checks 相关检查（无 checks 时返回不变）

## S4 · 文档
- 无代码接口；`gate.checks` 配置、时机与契约见 README.md、schema.yaml、opsx-propose / opsx-verify 命令与同名 skill。

## S2 · template/.claude/hooks/slice-gate.py
- `_check_dir(root, change, name)`：解析检查脚本所在目录
- `_check_env(phase, change, base_commit, cdir)`：构造检查运行环境变量
- `_run_check(cmd, root, env, timeout)`：运行单个检查命令，返回结果
- `_check_log(cdir, phase, out)`：把检查输出写入日志
- `_check_msg(head, log, out)`：拼装检查失败消息

## S3 · template/.claude/hooks/slice-gate.py
- `_final_checks(root, change_dir, checks, baseline)`：final 半（G9），按 gate.checks 顺序先核对基线记录再运行 final，返回 failed 项列表；G7 红时 final 不跑并给 warning
