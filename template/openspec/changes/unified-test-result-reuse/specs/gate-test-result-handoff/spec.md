## ADDED Requirements

### Requirement: final 把本次测试结果交给检查
Rule: final 跑完 gate.test（全量、内建增量或 `gate.impacted`）之后、运行任何 `gate.checks` 的 `final` 之前，SHALL 写出结果文件 `<git common dir>/flight-gate-checks/<change>/.gate-test-result.json`，并在每项检查的环境里设 `GATE_TEST_RESULT=<该文件绝对路径>`。

结果文件字段：
- `change`、`commit`、`at`；
- `mode`：`full` / `incremental` / `impacted`；
- `cmd`、`cmd_key`：gate.test 命令与它的指纹；
- `nodes`：`{仓库相对 nodeid: outcome}`，outcome 取 `passed` / `failed` / `error` / `skipped` / `xfailed` / `xpassed`；`impacted` 模式或依赖图未测时为 `null`；
- `inherited`：沿用锚点结论的用例数；全量为 0；`impacted` 为 `null`；
- `failed_nodes`：本次判为失败（`failed` / `error`）的 nodeid，排序；
- `junit`：本次 junit 副本（同目录 `.gate-test-junit.xml`）的绝对路径；增量时只含重跑部分，取不到时为 `null`；
- `complete`：`nodes` 覆盖锚点与本次重跑的全部用例时为真。

同树沿用的 final 不运行检查，也不写结果文件。

#### Scenario: final-full-hands-result-to-checks
- **GIVEN** 计划配了一项检查，它的 `final` 命令把 `GATE_TEST_RESULT` 指向的文件复制到仓库外
- **AND** baseline 已跑过
- **WHEN** 运行 `final --full`
- **THEN** 复制出的结果 `mode` 为 `full`、`inherited` 为 0、`complete` 为真
- **AND** `nodes` 里 `tests/test_a.py::test_a` 的结局为 `passed`
- **AND** `junit` 指向的文件存在

#### Scenario: final-incremental-result-composes-anchor-outcomes
- **GIVEN** baseline 已写下测到依赖图的锚点，之后只提交了 `src/a.py` 的改动
- **AND** 计划配了同样复制结果文件的检查
- **WHEN** 运行 final
- **THEN** 结果 `mode` 为 `incremental`、`complete` 为真、`inherited` 至少为 1
- **AND** `nodes` 同时含本次重跑的 `tests/test_a.py::test_a` 与沿用锚点的 `tests/test_b.py::test_b`，结局都是 `passed`

#### Scenario: baseline-checks-get-no-test-result
- **GIVEN** 计划配了一项检查，它的 `baseline` 与 `final` 命令都把环境里 `GATE_TEST_RESULT` 的值记到仓库外
- **WHEN** 依次运行 baseline 与 `final --full`
- **THEN** baseline 阶段记录到的值为空
- **AND** final 阶段记录到的值指向一个存在的文件

### Requirement: gate.test 的环境带阶段与 change 名
Rule: baseline 与 final 运行 gate.test、`gate.impacted` 与增量重跑时，SHALL 在环境里设 `GATE_PHASE`（`baseline` 或 `final`）与 `GATE_CHANGE`（change 目录名），让包装脚本不必把 change 名写死在脚本里。

#### Scenario: gate-test-env-carries-phase-and-change
- **GIVEN** change `c` 的 gate.test 是一个包装脚本：先把 `GATE_PHASE` 与 `GATE_CHANGE` 追加写到仓库外的记录文件，再运行 pytest
- **WHEN** 依次运行 baseline 与 `final --full`
- **THEN** 记录文件依次为 `baseline c` 与 `final c`
