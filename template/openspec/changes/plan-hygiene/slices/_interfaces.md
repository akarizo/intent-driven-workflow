# 切片间接口（规划时的约定；合回后由 integrator 按实际签名刷新）

## S1 提供

- `suite_sec(change_dir, data=None) -> int | float | None`（`slice-gate.py`）：最近一次已知的全量耗时。`gate-baseline.json`（含运行标记）顶层 `full_suite_sec` → 计划里旧的 `gate.full_suite_sec` → `None`；布尔值不算数值。
- `gate-baseline.json` 顶层 `full_suite_sec`：全量基线 = 本次全量墙钟；增量基线 = 沿用值（可能为 `null`）。运行标记在已知时也带这个字段。
- 基线池条目多一个键 `full_suite_sec`。
- `slice-gate.py baseline` 不再写 `slices.json`；`gate.test` 缺失时退出 2，stderr 含 `gate.test`。
- `_snapshot` 的返回值里，有未提交改动的 gitlink 路径 → 子仓 HEAD 的 commit。

- 实际签名核对（wave 1 合回）：`def suite_sec(change_dir, data=None)`、`def _snapshot(root, change_rel)`，与上列一致。

## S2 提供

- 常量 `RUNNER_UNMEASURED = "runner:deps-unmeasured"`（`slice-gate.py`）。
- 选测复核（`_lint_scope` / `_final_scope_guard`）在基线未测时追加该触发项；违规文字含触发项、`gate.scope_full_reason`、未测类别与 `.claude/flight-runner-contract.md`。
- lint 通过时可能多打印一行以 `runner:` 开头的提示（stderr）。
- 增量基线（非锚点复用）沿用来源的 `deps_unmeasured`；基线池条目多一个键 `deps_unmeasured`。

- 实际签名核对（wave 2 合回）：`RUNNER_UNMEASURED` 已定义；`_lint_scope(gate, change_dir, run_scope, data=None, phase="lint")`、`_final_scope_guard(root, change_dir, data, why, triggers)` 存在；基线池条目键含 `deps_unmeasured`，与上列一致。

## S3 提供

- `final_forecast(change_dir, data, baseline) -> (mode, why)`（`slice-gate.py`）：`mode` ∈ `impacted` / `full` / `incremental` / `unknown`，文字与原 `flight-doctor.py` 的 `_final_part` 相同。
- `ship` 的过期理由形如 `final 过期：记录 <10 位>，HEAD <10 位>；补跑将是增量（…）` / `…；补跑将是全量（…）` / `…；补跑由 gate.impacted 选测`。

- 实际签名核对（wave 3 合回）：`def final_forecast(change_dir, data, baseline)`（slice-gate.py:5777）、`def suite_sec(change_dir, data=None)` 存在，与上列一致。

## S4 提供

- 无公开代码接口：只改文档（opsx-propose 命令与同名 skill、flight-runner-contract、schema.yaml、README）与 `tests/test_plan_hygiene_docs.py`。
