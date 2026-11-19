# 已合回切片的公开接口摘要

## S1 · template/.claude/hooks/plan-kit.py
- CLI 子命令 `instructions` / `tasks` / `packets`（`--change` / `--change-dir`），退出码 `EXIT_FAIL = 2`
- `cmd_instructions(args)` 取 openspec 工件指令；`cmd_tasks(args)` 由 slices.json 生成 tasks.md（头注释 `TASKS_HEADER`）
- `cmd_packets(args)` 渲染切片包，区域标记 `BEGIN` / `END`（`<!-- plan-kit:begin/end -->`）
- `scenario_lines(change_dir, cap, name)` 抽 scenario 的 GIVEN/WHEN/THEN 行；`load_plan(change_dir)` 读 slices.json

## S2 · template/.claude/hooks/plan-scaffold.py
- CLI `plan-scaffold.py scaffold|gwt --change-dir <dir>`
- `PLACEHOLDER = "PLAN-SCAFFOLD-PLACEHOLDER"` 占位标记
- `cmd_scaffold(change_dir)` 生成测试骨架；`cmd_gwt(change_dir)` 校验 GWT 步骤
- `scenario_steps(change_dir, cap, name)` / `render_func(func, slice_id, steps)` / `placeholder_funcs(full, funcs)`

## S3 · template/.claude/hooks/slice-gate.py
- `SCAFFOLD_PLACEHOLDER = "PLAN-SCAFFOLD-PLACEHOLDER"`
- `_scaffold_errors(data, change_dir)` lint 阶段检出残留占位
- `_run_baseline(change_dir, data, full, warm=False)` 基线运行支持 warm
- `cmd_warm(args)` 基线预热子命令；辅助 `_pid_alive` / `_wait_warm` / `_warm_source` / `_adopt_wrapper(root, src_dir, change_dir, cmds)`
