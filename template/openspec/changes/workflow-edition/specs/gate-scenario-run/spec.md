## ADDED Requirements

### Requirement: G7 对 pytest 目标按实际运行结果判定
scenario 映射到 `.py` 测试时，G7 SHALL 在原有源码文本检查之外再实跑一次 pytest，只认 PASSED；XFAIL / XPASS / SKIPPED / FAILED / ERROR / 未被收集 SHALL 判未通过。切片门禁 SHALL 只跑本片的 scenario，final SHALL 跑全部 scenario。
Feature: gate-scenario-run

#### Scenario: g7-rejects-aliased-xfail
- **GIVEN** scenario `cap#adds` 映射的测试用别名装饰器 `XF = pytest.mark.xfail(strict=True)` 标记，断言尚未满足
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 里有一条 G7 点名 `cap#adds` 并含实际结果 XFAIL

#### Scenario: g7-rejects-imperative-skip
- **GIVEN** scenario `cap#adds` 映射的测试在测试体内调用 `pytest.skip()`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 里有一条 G7 点名 `cap#adds` 并含实际结果 SKIPPED

#### Scenario: g7-gate-checks-own-slice-outcome
- **GIVEN** 切片 S1 的 scenario 测试用别名装饰器标成 xfail，断言尚未满足
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** ok 为 false
- **AND** failed 里有一条 G7 含实际结果 XFAIL

#### Scenario: g7-reads-outcome-despite-addopts-quiet
- **GIVEN** 仓库根有 `pytest.ini` 写 `addopts = -q`；切片 S1 的 scenario 测试无标记、断言成立
- **WHEN** 运行 `slice-gate.py final`
- **THEN** failed 里没有任何 G7 条目

### Requirement: G7 沿用项目的测试环境并有超时
G7 的运行方式 SHALL 按序取 `gate.pytest` → 从 `gate.test` 推导到 pytest 为止的前缀 → 前缀含 shell 语法或找不到 pytest 时退回本解释器的 `-m pytest` 并在 warnings 里说明；超时 SHALL 取环境变量 `FLIGHT_G7_TIMEOUT`，否则全量耗时的 3 倍且不少于 120 秒，没有耗时记录时 600 秒；没收集到结果时 SHALL 附上 pytest 退出码与输出里的错误行。

#### Scenario: g7-uses-runner-from-gate-test
- **GIVEN** scenario 测试导入的 `envonly` 只在 `venv-bin/pytest` 这个项目测试环境里可用；`gate.test` 是它加 `-q tests`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 true，scenarios.passed 为 1

#### Scenario: g7-prefers-explicit-pytest-config
- **GIVEN** `gate.pytest` 指向会留下调用记录的 pytest 包装脚本，`gate.test` 仍是 `python3 -m pytest -q tests`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 包装脚本被调用过
- **AND** ok 为 true

#### Scenario: g7-falls-back-with-warning
- **GIVEN** `gate.test` 是 `cd . && python3 -m pytest -q tests`（含 shell 语法），没有 `gate.pytest`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 true
- **AND** warnings 里有一条以 G7 开头、含 `gate.pytest` 的说明

#### Scenario: g7-times-out
- **GIVEN** `gate.pytest` 指向先睡 5 秒再运行的 pytest 包装脚本；环境变量 `FLIGHT_G7_TIMEOUT` 为 1
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 里有一条 G7 含「运行超时」

#### Scenario: g7-reports-collection-failure-detail
- **GIVEN** scenario 测试所在文件在模块级抛出 RuntimeError，收集即失败
- **WHEN** 运行 `slice-gate.py final`
- **THEN** ok 为 false
- **AND** failed 里有一条 G7 含「未被收集运行」、`rc=` 与 RuntimeError
