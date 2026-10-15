## ADDED Requirements

### Requirement: final 先判 G7，G7 红就不跑全量
`slice-gate.py final` SHALL 先跑 scenario 状态（G7），再跑 lint / typecheck，最后跑全量测试；G7 红时 SHALL NOT 跑全量，SHALL 返回红并警告「G2 全量未跑」。
Feature: gate-full-suite-baseline

#### Scenario: final-skips-full-suite-when-g7-red
- **GIVEN** `cap#adds` 的测试仍带 strict xfail；`gate.test` 运行时写下 ran-g2，`gate.lint` 运行时写下 ran-lint
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false 且 failed 含点名 `cap#adds` 的 G7 项
- **AND** 全量没跑、lint 照跑；warnings 含「G2 全量未跑」

#### Scenario: final-runs-g7-before-full-suite
- **GIVEN** `cap#adds` 的测试通过、运行时向 order.log 追加 g7；`gate.test` 运行时向 order.log 追加 g2
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 true
- **AND** order.log 依次为 g7、g2

### Requirement: 全量测试按基线逐条差分
`gate.test` 是 pytest 且结果可度量时（退出码 1、junit 可解析、汇总行恰一行、汇总与 junit 的失败计数一致且非 0），baseline SHALL 把失败用例记进 `gate-baseline.json` 的 `test.failed` 并判 ok，final SHALL 只为基线之外的失败判红；不可度量时 SHALL 按退出码判，原因写明「按退出码」。

#### Scenario: baseline-records-preexisting-failures
- **GIVEN** `gate.test` 为 pytest；tests 里 `test_old` 失败、其余通过
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`gate-baseline.json` 的 ok 为 true，`test.failed` 恰 1 条且含 `test_old`
- **AND** warnings 含「预存红」

#### Scenario: final-excludes-baseline-failures
- **GIVEN** 上述基线已生成；`test_old` 仍失败，`cap#adds` 的测试通过
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 true，warnings 含「按基线排除」

#### Scenario: final-flags-new-failures
- **GIVEN** 上述基线已生成；又新增一个失败的 `test_new`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 有一项以「G2 test」开头、含「新增」与 `test_new`、不含 `test_old`

#### Scenario: diff-falls-back-when-unmeasurable
- **GIVEN** `gate.test` 先后运行两次 pytest（输出两行汇总），其中有失败
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 1；reasons 有一项含「按退出码」与「汇总行」

#### Scenario: non-pytest-gate-keeps-exit-code
- **GIVEN** `gate.test` 为 `sh -c 'exit 1'`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 1；reasons 有一项含「exit 1」与「按退出码」

#### Scenario: exit-1-without-failures-is-red
- **GIVEN** `gate.test` 为 pytest；全部用例通过，但 `tests/conftest.py` 在 sessionfinish 把 exitstatus 设成 1
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 有一项以「G2 test」开头且含「按退出码判」

### Requirement: 覆盖率未达标不被差分放过
输出里出现 pytest-cov 的覆盖率失败标记时，本次结果 SHALL 按不可度量处理、按退出码判红，原因 SHALL 提示可在 `gate.test` 加 `--no-cov`。

#### Scenario: final-red-on-coverage-failure
- **GIVEN** `gate.test` 为 pytest；基线已生成（`test_old` 预存红，其余通过）；之后提交了按 pytest-cov 做法报覆盖率未达标的 `tests/conftest.py`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 有一项以「G2 test」开头，含「按退出码判」与「覆盖率」

#### Scenario: baseline-red-on-coverage-failure
- **GIVEN** `gate.test` 为 pytest；`test_old` 失败，且 `tests/conftest.py` 按 pytest-cov 做法报覆盖率未达标
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 1
- **AND** reasons 有一项含「覆盖率」与 `--no-cov`

### Requirement: final 在脏工作树上如实标注
工作树有未提交改动（本 change 的记账文件除外）时，final 的结果 SHALL 带 `dirty: true` 并在 warnings 里列出路径（final 测的是工作树，合回只带已提交内容）。

#### Scenario: final-marks-dirty-worktree
- **GIVEN** 已提交的单片计划；工作树另有未跟踪的 `src/extra.py`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 结果带 `dirty: true`
- **AND** warnings 有一项含「未提交改动」与 `src/extra.py`

#### Scenario: final-ignores-bookkeeping-dirt
- **GIVEN** 已提交的单片计划；只有本 change 的 timeline.md 未提交
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 结果不带 dirty，warnings 不含「未提交改动」

### Requirement: gate.test 必须显式写出
`slice-gate.py lint` SHALL 要求 `slices.json` 的 `gate.test` 非空；baseline SHALL NOT 自动探测测试命令后写回 `slices.json`。

#### Scenario: lint-requires-gate-test
- **GIVEN** `slices.json` 合法，但 gate 里没有 test
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出码非 0，stderr 含 `gate.test`

### Requirement: 基线运行期间可识别，结束时不覆盖计划修改
baseline SHALL 开跑即把 `gate-baseline.json` 写成运行标记 `{running, pid, started}`，结束时整体覆盖为结果；结束时 SHALL 重读 `slices.json`、只写回全量耗时；运行期间 gate 命令或某片 verify 被改时 SHALL 判红「重跑 baseline」。preflight 见到运行标记时 SHALL 拒绝起飞：进程仍在说「仍在跑」，进程已不在说「中断」并提示重跑 baseline。

#### Scenario: baseline-marks-running
- **GIVEN** `gate.test` 是一个读取 `gate-baseline.json`、running 为 true 才退出 0 的脚本
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0
- **AND** 结束后 `gate-baseline.json` 的 ok 为 true，且没有 running 字段

#### Scenario: baseline-keeps-plan-edits-made-while-running
- **GIVEN** `gate.test` 运行时把 S1 的 owns 改成 ["src/**", "tests/**", "docs/**"]
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0
- **AND** `slices.json` 里 S1 的 owns 保留了 `docs/**`，且 `gate.full_suite_sec` 已写入

#### Scenario: baseline-red-when-verify-edited-while-running
- **GIVEN** `gate.test` 运行时把 S1 的 verify 改成 `test -d src`
- **WHEN** 运行 `slice-gate.py baseline`，再运行 preflight
- **THEN** baseline 退出非 0、reasons 有一项含「重跑 baseline」
- **AND** `slices.json` 保留新的 verify；preflight 拒绝起飞

#### Scenario: preflight-reports-running-baseline
- **GIVEN** `gate-baseline.json` 为运行标记，pid 是当前仍存活的进程
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出码非 0，stderr 含「仍在跑」

#### Scenario: preflight-reports-interrupted-baseline
- **GIVEN** `gate-baseline.json` 为运行标记，pid 是一个已经退出的进程
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出码非 0，stderr 含「中断」与 baseline
