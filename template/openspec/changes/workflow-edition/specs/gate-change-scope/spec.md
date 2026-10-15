## ADDED Requirements

### Requirement: 跑测试的副产物与切片标记不算切片改动
未提交的 `__pycache__` 目录与 `.pyc` 文件是跑测试的副产物，SHALL NOT 计入切片改动（已提交的 SHALL 照常受所有权检查）；G3 源码配对 SHALL NOT 把 `.openspec-slice` 标记当成源码。
Feature: gate-change-scope

#### Scenario: gate-ignores-uncommitted-bytecode
- **GIVEN** 切片 S1 已提交合规的实现与测试；工作树里另有未提交、未被 git 忽略的 `src/__pycache__/mod.cpython-39.pyc`，owns 不含它
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** ok 为 true
- **AND** failed 里没有点名这个字节码文件的项

#### Scenario: gate-flags-committed-bytecode
- **GIVEN** 切片 S1 的提交里夹带了 `src/__pycache__/mod.cpython-39.pyc`（`git add -f`），owns 不含它
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** G6 点名这个已提交的字节码

#### Scenario: gate-pairing-ignores-marker
- **GIVEN** 切片 S1 已 start，区间内没有任何提交，工作树里只有未提交的 `.openspec-slice` 标记
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 输出 JSON 的 failed 里没有以「G3」开头的项

### Requirement: final 新鲜度只放行记账文件
final 之后的提交只改了同一 changes 根下任一 change 的记账文件（timeline.md · gate-report.md · evidence.log · review-findings.json · tasks.md · slices/_interfaces.md）时，ship SHALL 仍视 final 为新鲜；任何其它改动 SHALL 让它过期。

#### Scenario: final-fresh-ignores-other-change-bookkeeping
- **GIVEN** changes 下有 c、b 两个 change；c 的 final 记在提交 X 且 ok；X 之后一次提交只改了 b 的 gate-report.md 与 timeline.md
- **WHEN** 对 c 运行 ship；之后再提交一次代码改动，再对 c 运行 ship
- **THEN** 前者 reasons 没有「过期」
- **AND** 代码改动之后 reasons 含「过期」

#### Scenario: final-fresh-ignores-interfaces-summary
- **GIVEN** change c 的 final 记在提交 X 且 ok；X 之后一次提交只改了 c 的 `slices/_interfaces.md`
- **WHEN** 对 c 运行 ship
- **THEN** reasons 没有「过期」
