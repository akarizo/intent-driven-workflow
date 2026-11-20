# 公开接口摘要

## S1 — template/.claude/hooks/model-routing.py
- `FORK_COMMANDS = {"cleanup.runner": "clean-after-merged.md"}` — fork 命令登记（路由键 → 命令文件）
- `REGISTRY` — 路由键内建默认登记表，含 `cleanup.runner`
- `render_frontmatter(text, model, effort)` — 把 model / effort 渲染进命令文件 frontmatter，返回新文本
- `cmd_frontmatter(args)` — 子命令 `frontmatter`：渲染、`--check` 漂移检查，拒绝非 fork 命令与非法配置
- `effective(root)` / `load_config(root)` / `validate(cfg)` / `check_value(name, value)` — 有效值解析与校验
- `cmd_get` / `cmd_pin` / `cmd_resolve` / `cmd_show` — 既有子命令
