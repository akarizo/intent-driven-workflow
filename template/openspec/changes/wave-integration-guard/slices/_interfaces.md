# 切片间接口约定

规划时写下的约定；各片合回后 integrator 会按实际签名覆盖对应的一节。

## S1（`slice-gate.py`：全局守护）

- 计划：`gate.checks[i].slice`，可选，非空字符串或 `null`。
- `gate-baseline.json`：`checks.<名>.slice = {"exit", "sec", "cmd"[, "reused"][, "timed_out"]}`。
- 给 S2 复用的两个函数（名字照此，S2 直接调用）：
  - `_guard_checks(gate) -> [检查对象…]`：`gate.checks` 里 `slice` 非空的那些，保持顺序。
  - `_run_guards(root, change_dir, checks, baseline, phase, log_tag) -> (failed, guards)`：逐个核对基线记录并运行；`phase` 是 `"slice"` 或 `"wave"`（进 `GATE_PHASE`），`log_tag` 决定日志名 `.gate-<log_tag>.log`（门禁传 `slice-<切片 id>`，集成检查传 `wave`）；`failed` 的每项以 `G15 guard <名>` 开头；`guards = {名: {"exit", "sec"}}`（没运行的不出现）。
- 门禁 JSON：有守护时多 `guards`；时间线 gate 备注多一段 `守护 a 1.2s / b 0.4s`。

## S2（`slice-gate.py`：wave 集成检查，已合回）

- `slice-gate.py wave-check --change-dir DIR [--wave N] [--of M] [--fix-base SHA]`（`cmd_wave_check(args)`），退出码按 `ok`，stdout 末行是 JSON：
  `{"slice": "wave", "ok", "commit", "failed", "warnings", "summary", "wave", "of", "guards", "tests": {"mode", "why", "files", "rerun_tests", "est_sec", "sec", "budget_sec"}, "lock"[, "fix": {"base", "files", "outside_owns"}]}`。
- `failed` 前缀：`G15 guard <名>`、`G16 wave test`、`G6 flight-record` 与 `G0 base`（仅 `--fix-base`）。
- 时间线事件 `wave-check`，备注由 `_wave_note(result)` 生成（`cmd_record` 共用）；`gate-report.md` 行切片列固定 `wave`。
- `record --json '<上面的 JSON>'`：写同样的行与事件；`ship` 见最新 `wave` 行红则判 draft。
- 常量 `WAVE_TEST_BUDGET_SEC = 120`；计划 `gate.wave_test_budget_sec`（正数，可选）覆盖。

## S3（`slice-gate.py`：owns 分档与 landed）

- `slice-gate.py landed --change-dir DIR` → stdout `{"<切片 id>": "<门禁行里的 commit，10 位>", …}`，退出 0；计划不合法退出 2。
- 计划：切片的 `owns_wide: {"<owns 条目原文>": "<理由>"}`，可选。

## S4（工作流）

- 新参数 `args.landed`（可选，`landed` 的输出）。
- integrator 的合回返回值多 `check`（`wave-check` 的 JSON 或 `null`）。
- 新的派发 label：`fix:w<i>`、`fix:w<i>:retry`（执行体）、`integrate:w<i>:fix`（integrator）、`review:wavefix<i>`（评审）。
- 返回值多 `waves: [{wave, ok, failed, tests, fix: {commit, ok, files, outside_owns} | null, skipped}]`。

## 实际签名（wave 1 合回后核对，S1 / S4 / S6）

- S1 `template/.claude/hooks/slice-gate.py:5764` `_guard_checks(gate)`；`:5770` `_run_guards(root, change_dir, checks, baseline, phase, log_tag)`，与上文约定一致。
- S4 `template/.claude/workflows/opsx-apply.js:39` `const landed = args.landed || {}`；派发 label `integrate:w<i>[:retry]`、`fix:w<i>[:retry]`、`integrate:w<i>:fix[:retry]`（`:244` `:263` `:276`）。
- S6 仅文档与 schema（`flight-runner-contract.md`、`opsx-propose.md`、`openspec-propose/SKILL.md`、`schema.yaml`），无代码签名。

## 实际签名（wave 3 合回后核对，S3 / S5 / S7）

- S3 `template/.claude/hooks/slice-gate.py:3621` `cmd_landed(args)`；`:2649` `_owned_file_count(root, commit, owns, cache=None)`，owns 分档与 `landed` 子命令与上文约定一致。
- S5 仅文档与测试（`opsx-apply.md`、`openspec-apply-change/SKILL.md`、`pr-ship.md`、`README.md`），无代码签名。
- S7 `template/.claude/hooks/spec_html.py:660` `render_guards(gate)`；`template/.claude/hooks/flight-doctor.py:241` `wave_cost(lines)`。
