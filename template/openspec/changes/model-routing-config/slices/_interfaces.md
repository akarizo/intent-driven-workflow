# 已合回切片公开接口摘要（wave 1）

## S1 — 路由配置 hook
`template/.claude/hooks/model-routing.py`（另有 `template/openspec/model-routing.json`）
- `die(code, lines)` / `openspec_root(args)` / `config_path(root)` / `load_config(root)`
- `check_value(name, value)` / `validate(cfg)` / `effective(root)`
- `load_slices(change_dir)` / `pinned_errors(routing)` / `source_label(root)` / `env_overrides()`
- 子命令：`cmd_show` / `cmd_pin` / `cmd_resolve` / `cmd_get`；入口 `main(argv=None)`

## S2 — 工作流角色路由
`template/.claude/workflows/opsx-apply.js`
- `tierOf(s)` / `execDef(s)` / `execRole(s)`：大切片路由到 executor-large
- `typed(name)` / `rules(name)` / `gateCmd(s)` / `startCmd(s, cont, resume)`
- `executorPrompt(s, retryOf)` / `reviewPrompt(s, gate, fixOf)` / `pushReview(s, prompt)`
- `callFinal(retry)`

## S3 — 路由审计 effort
`template/.claude/hooks/session-decompose.py`
- `label_role(label)` / `role_for(label, phase, atype, expect, turns)`
- `audit_routes(agents, expect, alias_of, turns=None)` / `audit_efforts(agents, expect, turns=None)`
- `workflow_agents(wf_dir)` / `main()`

## S4 — spec.html 路由渲染
`template/.claude/hooks/spec_html.py`
- `slice_turns(change_dir)` / `render_routing(data)` / `render_flight(change_dir)`
- `render_scope(gate, change_dir, owns=())` / `render_guards(gate)` / `owns_wide_html(s)`
- `render(change_dir, template_path, out_path, now_arg)` / `main()`
