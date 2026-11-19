# 公开接口摘要

## S1（template/.claude/hooks/slice-gate.py）

- `cmd_reap(args)`：`slice-gate.py reap` 子命令入口，飞行收口回收本次飞行的临时 worktree。
- `_reap_close_one(root, wt, lines, change, root_head, reaped, archived, kept, warnings)`：单个 worktree 的收口回收。
- `_attic(wt, head, change, keep)`：回收前归档保留物。
- `_own_sub_clone(root, wt)` / `_disk_bytes(top)` / `_within(path, top)` / `_git_dir_abs(base, flag)`：辅助。

## S2（template/.claude/hooks/merged-cleanup.py）

- `ARCHIVE_RE`：匹配 `openspec/changes/archive/<date>-<name>/` 的归档路径。
- `landed_into(ctx, wt)`：worktree 是否已被合进其他分支（landed）。
- `attempt_change(path, changes)`：判定 worktree 内改动属于已落地 change 的作废尝试（dead-attempt）。

## S3（文档与测试，无公开源码接口）

- 仅改 CLAUDE.md / README.md / clean-after-merged.md / opsx-apply.md / openspec-apply-change SKILL.md / CLAUDE.md.snippet 与 tests/test_close_reap_docs.py；无新增签名。
