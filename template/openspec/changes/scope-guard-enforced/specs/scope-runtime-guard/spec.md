## ADDED Requirements

### Requirement: baseline 开跑前复核选测范围
Rule: `slice-gate.py baseline` SHALL 在写运行标记之前，按 lint 的同一套规则复核选测范围：
- 解析提供方；
- 运行或计算报告；
- 核对 `gate.scope_full_reason`。

复核不通过（未声明且不是本 change 建立声明、提供方失败、全选触发项缺理由）时，SHALL 退出非 0 并点名违规，SHALL NOT 运行 `gate.test`，也 SHALL NOT 改动现有的 `gate-baseline.json`。

#### Scenario: baseline-refuses-unapproved-full
- **GIVEN** 计划 `gate.scope` 的替身命令报告 `{"full": true, "triggers": ["x"]}`，计划没写 `gate.scope_full_reason`
- **AND** `gate.test` 一运行就会在仓库根写出 `ran.marker`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0，stderr 点名 `x` 缺理由
- **AND** 仓库根没有 `ran.marker`，change 目录没有 `gate-baseline.json`

#### Scenario: baseline-runs-when-full-is-approved
- **GIVEN** 同上，但计划写了 `{"x": "已知并接受"}`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** `gate.test` 被运行，仓库根有 `ran.marker`

#### Scenario: baseline-refuses-undeclared
- **GIVEN** 没有任何选测声明，切片 owns 不含 `gate-scope.json`
- **AND** `gate.test` 一运行就会写出 `ran.marker`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0，stderr 含「未声明选测范围」
- **AND** 仓库根没有 `ran.marker`

### Requirement: final 开跑前复核选测范围
Rule: `slice-gate.py final` SHALL 在运行测试之前复核一次，未通过时把一条以 `G2 scope` 开头的失败写进结果，跳过测试运行，final 判红：
- 内建提供方：final 将全量（`_full_why` 有原因）时，取同一套规则得到的全部触发项；有触发项不在已批准的理由键里，即不通过。
- cmd 提供方：重跑提供方（环境变量同 lint）；报告全选且有触发项不在已批准的理由键里，或提供方失败，即不通过。
- 未声明：判红（例外同 lint）。

`final --full` 是显式要求的全量，SHALL 豁免本复核。

#### Scenario: final-refuses-unapproved-builtin-full
- **GIVEN** 仓库声明 `{"builtin": true}`，基线已跑；`tests/test_mark.py` 一运行就写出 `ran.marker`，基线跑完后删除该标记
- **AND** 随后提交了对 `scripts/helper.sh` 的修改（任何用例都没触及它），计划没写理由
- **WHEN** 运行 `slice-gate.py final`
- **THEN** final 红，失败项里有一条以 `G2 scope` 开头、含 `scripts/helper.sh`
- **AND** 仓库根没有 `ran.marker`

#### Scenario: final-runs-approved-full
- **GIVEN** 同上，但计划写了 `{"scripts/helper.sh": "脚本只给人用，接受全量"}`，并且没有 approve 提交
- **WHEN** 运行 `slice-gate.py final`
- **THEN** final 走全量，测试被运行，仓库根有 `ran.marker`

#### Scenario: final-refuses-unapproved-cmd-full
- **GIVEN** 计划 `gate.scope` 的替身命令在仓库根没有 `flag` 时报告不全选，有 `flag` 时报告 `{"full": true, "triggers": ["y"]}`；基线已跑（当时没有 `flag`）
- **AND** 随后提交了 `flag`，计划没写理由
- **WHEN** 运行 `slice-gate.py final`
- **THEN** final 红，失败项里有一条以 `G2 scope` 开头、含 `y`
- **AND** 仓库根没有 `ran.marker`

#### Scenario: manual-full-flag-is-exempt
- **GIVEN** 与「final-refuses-unapproved-builtin-full」相同的仓库与修改
- **WHEN** 运行 `slice-gate.py final --full`
- **THEN** 测试被运行，仓库根有 `ran.marker`

### Requirement: 理由以 approve 提交为准
Rule: change 的 `timeline.md` 在 git 历史里有 approve 行时，「已批准的理由」= 最近一次新增 approve 行的提交里 `slices.json` 的 `gate.scope_full_reason`。final 复核时，当前计划的 `gate.scope_full_reason` 与之不同（键或理由文字）时 SHALL 判红，失败项写明「批准后被修改」。没有 approve 提交时，以当前计划为准。

#### Scenario: reasons-edited-after-approval-are-red
- **GIVEN** 仓库声明 `{"builtin": true}`，基线已跑；随后有一次提交只新增了 `timeline.md` 的 approve 行，当时计划没写理由
- **AND** 之后计划被改，加上 `{"scripts/helper.sh": "补写"}` 并提交，又提交了对 `scripts/helper.sh` 的修改
- **WHEN** 运行 `slice-gate.py final`
- **THEN** final 红，失败项里有一条以 `G2 scope` 开头、含「批准后被修改」
- **AND** 仓库根没有 `ran.marker`
