## ADDED Requirements

### Requirement: 没有可用锚点时，只改了测试文件的 final 只重跑这些文件
`slice-gate.py final` 在没有可用锚点、没配 `gate.impacted`、不是 `--full` 时，若以下条件全部成立，SHALL 只重跑改动的测试文件，其余用例沿用本 change 上一次绿 final 的结论：
- 本 change 有一次绿 final，它的 `gate.test` / `gate.pytest` 指纹与分层指纹同当前；
- 其后的 Δ 去掉记账文件与按 `inert` 生效的路径后，只含文件名匹配 `test_*.py` 的路径，且都不命中 `global`；
- 改动的测试文件不含基线的预存红；
- 没有测试分层文件；增量重跑能等价复现 `gate.test`（直接的 pytest 调用，或配了 `gate.pytest`）。

`blind` 命中的测试文件 SHALL 一并重跑。锚点链到上限（`anchor_max_hops`）而没有可用锚点时 MUST NOT 走这条路。任一条件不成立时 SHALL 照常全量。这条路 MUST NOT 写锚点。
Feature: 没有依赖图也认得出最便宜的重跑
Rule: 安全级别与 baseline「只改了测试文件就复用」相同

#### Scenario: tests-only-rerun-after-green-final
- **GIVEN** 依赖图测不到的仓库（包装脚本丢掉插件参数，计划已表态，配了 `gate.pytest`），final 已绿
- **AND** 之后只提交了 `tests/test_a.py` 的改动
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出码为 0，`incremental.mode` 为 `incremental`，`incremental.source` 为 `tests-only`，`rerun` 恰为 `["tests/test_a.py"]`
- **AND** 时间线最后一条 final 备注以「增量（无图」开头、以 `ok` 结尾
- **AND** 另一个没配 `gate.pytest` 的同样仓库做同样的改动后，final 的 `incremental.mode` 为 `full`

#### Scenario: tests-only-refused-when-source-changed
- **GIVEN** 同样的仓库，final 已绿
- **AND** 之后提交了 `src/a.py` 的改动
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `incremental.mode` 为 `full`
- **AND** `full_why` 同时含「没有可用锚点」与 `src/a.py`

### Requirement: 重跑红即 final 红
无图退路重跑的测试文件里有失败或错误的用例时，final SHALL 判红并逐条点名，MUST NOT 退回全量；重跑超时或异常退出同样判红。
Feature: 红就是红
Rule: 不用一遍全量去确认一个已经看见的失败

#### Scenario: tests-only-red-when-rerun-fails
- **GIVEN** 同样的仓库，final 已绿
- **AND** 之后提交的 `tests/test_a.py` 里有一条会失败的新用例 `test_a_again`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出码为 1，`incremental.source` 为 `tests-only`
- **AND** failed 里有一条以 `G2 test` 开头、含「新增失败」与 `tests/test_a.py::test_a_again`

### Requirement: 结果交接标明 tests-only
走无图退路时，交给检查的结果文件（`GATE_TEST_RESULT`）`mode` SHALL 为 `tests-only`，`nodes` 与 `inherited` 为 `null`，`complete` 为假，`failed_nodes` 为本次重跑里失败的用例；检查的 `GATE_FINAL_MODE` 为 `incremental`。
Feature: 检查知道这份结果有多完整
Rule: 没有逐用例记录就不假装有

#### Scenario: tests-only-result-handoff-marks-mode
- **GIVEN** 同样的仓库，计划配了一项把 `GATE_TEST_RESULT` 复制到仓库外的检查，final 已绿
- **AND** 之后只提交了 `tests/test_a.py` 的改动
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出码为 0
- **AND** 复制出的结果 `mode` 为 `tests-only`，`nodes` 与 `inherited` 为 `null`，`complete` 为假，`failed_nodes` 为空

### Requirement: 预告与成本归因认得无图退路
`final_forecast`（`flight-doctor.py forecast` 与 `ship` 的「final 过期」理由共用）SHALL 在无图退路适用时预告增量，并说明是无图退路与重跑的测试文件数。`flight-doctor.py cost` SHALL 把这种 final 记为增量。
Feature: 事先说清这次要付多少
Rule: 预告与实际运行用同一个判定

#### Scenario: forecast-predicts-tests-only-rerun
- **GIVEN** 同样的仓库，final 已绿，之后只提交了 `tests/test_a.py` 的改动
- **WHEN** 运行 `flight-doctor.py forecast --json` 与 `slice-gate.py ship`
- **THEN** 预告的 `final.mode` 为 `incremental`，`final.why` 含「无图」与「1 个测试文件」
- **AND** ship 有一条理由同时含「final 过期」「补跑将是增量」与「无图」

#### Scenario: cost-attributes-tests-only-rerun
- **GIVEN** 同样的仓库先跑了一次全量 final，之后只改测试文件又跑了一次 final
- **WHEN** 运行 `flight-doctor.py cost --json`
- **THEN** `final.full` 为 1，`final.incremental` 为 1
