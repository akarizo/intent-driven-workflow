## ADDED Requirements

### Requirement: /opsx-propose 先渲染审批面板，基线放后台
`/opsx-propose`（命令与同名 skill 同文）SHALL 在 lint 绿后先渲染 `spec.html`，再以后台方式运行 baseline、跑完报告一行；SHALL 写明基线跑完前起飞会被 preflight 拒绝；基线红时 SHALL 停下报告。
Feature: propose-parallel-baseline

#### Scenario: propose-renders-panel-before-baseline
- **GIVEN** `opsx-propose.md` 与 `openspec-propose/SKILL.md`
- **WHEN** 定位两者里 `spec_html.py` 与 `slice-gate.py baseline` 首次出现的位置，取 baseline 之后的正文
- **THEN** 两者都是 `spec_html.py` 在前
- **AND** baseline 之后写明后台运行、跑完报告一行、跑完前起飞会被 preflight 拒绝；hook 集合一致

#### Scenario: propose-baseline-red-stops
- **GIVEN** `opsx-propose.md` 与 `openspec-propose/SKILL.md`
- **WHEN** 取两者的 baseline 步骤段（从 `slice-gate.py baseline` 到下一个步骤标题）
- **THEN** 两者都含 `gate-baseline.json` 与「停下报告」，并说明 verify 在基线上必须绿
- **AND** hook 脚本集合一致

### Requirement: schema 写明 gate.test 必填与基线差分
schema 的 tasks instruction SHALL 写明 `gate.test` 必填、`gate.pytest` 可选，以及 pytest 预存红由基线记录、final 逐条差分、无需手写 deselect。

#### Scenario: schema-requires-gate-test
- **GIVEN** `schema.yaml` 的 tasks 工件 instruction
- **WHEN** 取 tasks 工件段
- **THEN** 写明 `gate.test` 必填
- **AND** 写明预存红按基线差分、无需手写 deselect
