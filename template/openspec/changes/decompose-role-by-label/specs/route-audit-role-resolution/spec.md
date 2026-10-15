## ADDED Requirements

### Requirement: 对账按 agentType、label、阶段的顺序确定 Workflow agent 的角色
`session-decompose.py --expect-models` 对每个 Workflow agent 确定路由角色时，SHALL 依次：
- meta 的 `agentType` 是 `slice-executor` / `code-reviewer` / `integrator` 时，取对应角色 executor / reviewer / integrator；
- 否则看 label（meta 的 `description`）：以 `integrate:` 或 `final-gate` 开头 → integrator；以 `review:` 开头 → reviewer；
- 否则按阶段：Implement / Fix → executor，Review → reviewer，Finalize → integrator；
- 仍判不出时不参与对账。

角色确定后，按路由表比对实际模型的别名；输出格式与退出码不变。

#### Scenario: integrator-label-without-agent-type-matches
- **GIVEN** 一个 workflow journal，各 agent 的 meta 都没有 `agentType`：`S1`（Implement，claude-opus-5）、`integrate:w1`（Implement，claude-sonnet-5）、`integrate:w2:retry`（Implement，claude-sonnet-5）、`review:S1`（Review，claude-opus-5）
- **WHEN** 带路由表 `{"executor":"opus","reviewer":"opus","integrator":"sonnet"}` 运行收口对账
- **THEN** 退出 0；输出没有 ❌
- **AND** 对账结论把 integrator 记成 sonnet

#### Scenario: integrator-label-on-wrong-model-flagged
- **GIVEN** 一个 workflow journal，各 agent 的 meta 都没有 `agentType`：`S1`（Implement，claude-opus-5）、`integrate:w1`（Implement，claude-opus-5）、`review:S1`（Review，claude-opus-5）
- **WHEN** 带同一路由表运行收口对账
- **THEN** 退出非 0
- **AND** 有一条 ❌ 行点名 `integrate:w1`，期望 sonnet，实际 claude-opus-5

#### Scenario: unknown-label-falls-back-to-phase
- **GIVEN** 一个 workflow journal，各 agent 的 meta 都没有 `agentType`，label 都不匹配显式格式：`S1`（Implement，claude-opus-5）、`fix`（Fix，claude-opus-5）、`judge`（Review，claude-opus-5）、`final`（Finalize，claude-sonnet-5）
- **WHEN** 带同一路由表运行收口对账
- **THEN** 退出 0；输出没有 ❌
- **AND** 对账结论同时记有 executor=opus、reviewer=opus、integrator=sonnet

### Requirement: label 格式是工作流脚本与对账之间的契约
`opsx-apply.js` 派发 integrator 与 code-reviewer 时写下的 label 模板，SHALL 与对账认的 label 格式一一对应：模板展开后的样例 label（含 `:retry` 变体）按对账判出的角色，等于同一派发调用里 `agentType` 对应的角色。

#### Scenario: label-contract-matches-workflow-script
- **GIVEN** `template/.claude/workflows/opsx-apply.js` 与 `template/.claude/hooks/session-decompose.py`
- **WHEN** 读出脚本里 integrator 与 code-reviewer 的 label 模板，并把样例 `integrate:w1`、`integrate:w1:retry`、`final-gate`、`final-gate:retry`、`review:S1` 交给对账的 label 判定
- **THEN** 每个模板都和它对应的 `typed('integrator')` / `typed('code-reviewer')` 写在同一个派发调用里
- **AND** 前四个样例判为 integrator，`review:S1` 判为 reviewer
