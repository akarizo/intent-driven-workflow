# 公开接口摘要

## S1
`template/.claude/hooks/model-routing.py`：`validate(cfg)` / `effective(root)` / `pinned_errors(routing)` / `cmd_show|pin|resolve|get|frontmatter(args)` / `render_frontmatter(text, model, effort)` / `main(argv=None)`
`template/.claude/hooks/flight-doctor.py`：`forecast(change_dir)` / `cost(change_dir)` / `doctor_routing(openspec_root)` / `doctor(openspec_root)` / `main()`

## S2
`template/.claude/hooks/merged-cleanup.py`：`resolve_target(root, remote, target)` / `list_worktrees(root)` / `worktree_item(ctx, wt)` / `branch_item(ctx, b, eff_head, wt_item)` / `compute(ctx)` / `markdown(plan)` / `apply(root, args)` / `main(argv=None)`
