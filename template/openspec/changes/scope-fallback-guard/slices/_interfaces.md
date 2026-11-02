# 切片间接口

- **S1 → S2**：同改 `slice-gate.py`，故 S2 依赖 S1 串行。S1 只动锚点与 final（`_tiers_key`、`tiers_detail`、`GLOBAL_FILES`、`_full_why`、`cmd_final`、`cmd_baseline` 的锚点写入）；S2 只动 lint / preflight（`lint_plan` 签名加 `run_scope`、`cmd_lint`、`cmd_preflight`、新增选测范围函数与常量）。两片不改同一函数。
- **S3、S4**：只依赖 design 里的字段名与契约，与 S1 / S2 无代码接口：
  - 计划字段：`gate.scope`（字符串）、`gate.scope_full_reason`（对象：触发项 → 理由）；
  - 仓库默认：`<openspec 根>/gate-scope.json` = `{"cmd": "<命令>"}`；
  - 报告：`GATE_SCOPE_OUT` 指向的文件里 `{"full": bool, "triggers": [str], "count": int?}`。

## 合回签名摘要（wave 1）

### S1（`template/.claude/hooks/slice-gate.py`）
- `def cmd_final(args)` 全量 / 增量 final 门禁入口
- `def cmd_baseline(args)` 写入基线与锚点
- `def _tiers_key(root, change_dir, tiers)` 分层文件按条目的锚点键
- `def _tiers_detail(tiers)` 分层条目明细
- `def _full_why(root, full, pick, baseline, snap_why, impacted=False, gate=None, tier_rel=None)` 判定走全量的原因

### S3（`template/.claude/hooks/spec_html.py`）
- `def render_scope(gate, change_dir)` 审批页渲染选测范围小节
- `def render(change_dir, template_path, out_path, now_arg)` 总渲染入口

### S4（文档 / schema，无代码签名）
- `template/openspec/schemas/intent-driven/schema.yaml` 选测范围契约
- `opsx-propose.md` / `openspec-propose/SKILL.md` 同步

## 合回签名摘要（wave 2）

### S2（`template/.claude/hooks/slice-gate.py`）
- `SCOPE_FILE` / `SCOPE_REPORT_FIELDS` / `SCOPE_TIMEOUT` 选测范围常量
- `def _scope_default(change_dir)` 读取仓库默认 gate-scope.json
- `def _scope_report_errors(r)` 校验 GATE_SCOPE_OUT 报告字段
- `def _run_scope(cmd, root)` 执行选测范围命令并取报告
- `def _scope_reason_errors(report, reasons)` 校验 scope_full_reason 与触发项
- `def _lint_scope(gate, change_dir, run_scope)` lint 阶段选测范围检查
- `def lint_plan(data, change_dir=None, run_scope=False)` 计划 lint（新增 run_scope）
- `def cmd_lint(args, print_waves=True)` / `def cmd_preflight(args)` 接入选测范围
