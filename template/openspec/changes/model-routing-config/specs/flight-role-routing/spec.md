## ADDED Requirements

### Requirement: 飞行工作流按 5 个角色派发
`template/.claude/workflows/opsx-apply.js` SHALL 按以下角色派发：
- 轮次档为 `large` 的切片执行体：`models['executor-large']` / `efforts['executor-large']`；
- 批量修复（label `fix`）与 wave 跨片修复（label `fix:w<i>`）：`models.fixer` / `efforts.fixer`；
- 其余切片执行体、评审、integrator：仍按原来的 `executor` / `reviewer` / `integrator`。

`executor-large` 与 `fixer` 缺省时 SHALL 取 `executor` 的值（model 与 effort 分别回落），只传 3 个角色的旧调用行为不变。任一角色的 effort 不在 `low | medium | high | xhigh | max` 之内时，MUST 抛错拒绝起飞。返回值里的 `models` 与 `efforts` SHALL 含全部 5 个角色。

Feature: 飞行角色路由
Rule: 大片档与修复各有路由，缺省同执行体

#### Scenario: workflow-routes-large-slice-to-executor-large
- **GIVEN** 两片计划：S1 的 turns 为 `large`，S2 为标准档
- **AND** args 的 `models['executor-large']` 为 `fable`、`efforts['executor-large']` 为 `high`，`models.executor` 为 `opus`、`efforts.executor` 为 `medium`
- **WHEN** 运行工作流
- **THEN** S1 的执行体派发带 model `fable`、effort `high`
- **AND** S2 的执行体派发带 model `opus`、effort `medium`

#### Scenario: workflow-routes-fixes-to-fixer
- **GIVEN** 一片计划，评审返回一条 HIGH finding；args 的 `models.fixer` 为 `fable`、`efforts.fixer` 为 `high`
- **WHEN** 运行工作流
- **THEN** label 为 `fix` 的派发带 model `fable`、effort `high`

#### Scenario: workflow-defaults-new-roles-to-executor
- **GIVEN** args 只有 executor / reviewer / integrator 三个角色，`efforts.executor` 为 `medium`
- **WHEN** 运行工作流（含一片大片档与一次批量修复）
- **THEN** 大片档执行体与 `fix` 的派发都带 `models.executor` 与 effort `medium`
- **AND** 返回值的 `models` 与 `efforts` 含 5 个角色

#### Scenario: workflow-rejects-unknown-effort
- **GIVEN** args 的 `efforts.reviewer` 为 `huge`
- **WHEN** 运行工作流
- **THEN** 工作流抛错，错误信息点名 `reviewer` 与允许的 effort 集合，且没有派发任何 agent
