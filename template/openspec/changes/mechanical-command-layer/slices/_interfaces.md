# 公开接口摘要

## S1 — template/.claude/hooks/model-routing.py
- `FORK_COMMANDS = {"cleanup.runner": "clean-after-merged.md"}` — fork 命令登记（路由键 → 命令文件）
- `REGISTRY` — 路由键内建默认登记表，含 `cleanup.runner`
- `render_frontmatter(text, model, effort)` — 把 model / effort 渲染进命令文件 frontmatter，返回新文本
- `cmd_frontmatter(args)` — 子命令 `frontmatter`：渲染、`--check` 漂移检查，拒绝非 fork 命令与非法配置
- `effective(root)` / `load_config(root)` / `validate(cfg)` / `check_value(name, value)` — 有效值解析与校验
- `cmd_get` / `cmd_pin` / `cmd_resolve` / `cmd_show` — 既有子命令

## S2 — install.sh / 命令 frontmatter / 测试
- `template/.claude/commands/clean-after-merged.md` — 改为 `context: fork`，model / effort 由 `model-routing.py frontmatter` 渲染（路由键 `cleanup.runner`）
- `install.sh` — 安装与升级时重渲 fork 命令 frontmatter；路由配置非法时安装不中断
- `tests/test_fork_commands_docs.py` — `test_cleanup_command_runs_as_fork` / `test_only_fork_commands_carry_model` / `test_stale_model_advice_removed` / `test_self_hosting_config_leaves_fork_keys` / `test_docs_register_cleanup_runner`
- `tests/test_install_routing.py` — `test_upgrade_rerenders_fork_frontmatter` / `test_install_survives_invalid_routing`
