## S1

文件 template/.claude/hooks/slice-gate.py

- `def _slices_commit_times(parent)`：新增，取各切片临时 worktree 的最后提交时间
- `def _warm_source(change_dir)`：按 git 最后提交时间选 warm 来源
- `def _run_baseline(change_dir, data, full, warm=False)`：锚点条目带 full_suite_sec 并沿链继承
- `def cmd_final(args)`、`def _anchor_forward(root, old, sel, d, fails, outcomes, ran=None)`：final 锚点保留 full_suite_sec
