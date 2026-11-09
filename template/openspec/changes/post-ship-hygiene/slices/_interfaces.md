# 公开接口摘要

## S1
`template/.claude/hooks/merged-cleanup.py`（CLI：plan / apply；判定合并状态、清理 worktree 与分支）
- `class Refuse(Exception)` 拒绝执行
- `main_root(cwd)` 定位主仓库根
- `resolve_target(root, remote, target)` 解析目标分支
- `class Ctx` 运行上下文
- `list_worktrees(root)` / `worktree_item(ctx, wt)` / `branch_item(ctx, b, eff_head, wt_item)` 生成清理项
- `check_subs(ctx, wt, item)` 子仓存活校验
- `plan_sync(ctx, warnings)` 目标分支 ff 同步
- `compute(ctx)` 计算计划；`public(plan)` / `markdown(plan)` 渲染
- `apply(root, args)` 执行清理
- `main(argv=None)` 入口

## S3
文档类切片，无代码符号。
- `template/.claude/commands/pr-ship.md` step 2b 记忆层沉淀
- `template/.claude/commands/claudemd-commit.md` 自动录入与较大差异对齐
- `template/.claude/claudemd-standard.md` §13 E 类反复错误

## S2
文档类切片，无代码符号。
- `template/.claude/commands/clean-after-merged.md` 新命令，调用 S1 的 `merged-cleanup.py` plan / apply
- `template/.claude/skills/openspec-git-discipline/SKILL.md` 清理条款
- `CLAUDE.md` / `template/CLAUDE.md.snippet` 铁律 6 授权例外；`README.md` / `docs/WORKFLOW_zh.md` / `install.sh` 同步
