# 切片间接口

- **S1 → S2**：同改 `slice-gate.py`，故 S2 依赖 S1 串行。S1 只动锚点与 final（`_tiers_key`、`tiers_detail`、`GLOBAL_FILES`、`_full_why`、`cmd_final`、`cmd_baseline` 的锚点写入）；S2 只动 lint / preflight（`lint_plan` 签名加 `run_scope`、`cmd_lint`、`cmd_preflight`、新增选测范围函数与常量）。两片不改同一函数。
- **S3、S4**：只依赖 design 里的字段名与契约，与 S1 / S2 无代码接口：
  - 计划字段：`gate.scope`（字符串）、`gate.scope_full_reason`（对象：触发项 → 理由）；
  - 仓库默认：`<openspec 根>/gate-scope.json` = `{"cmd": "<命令>"}`；
  - 报告：`GATE_SCOPE_OUT` 指向的文件里 `{"full": bool, "triggers": [str], "count": int?}`。
