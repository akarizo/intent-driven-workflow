## ADDED Requirements

### Requirement: 收口对账覆盖 effort 与新角色
`session-decompose.py` SHALL 新增两个参数：
- `--expect-efforts '<JSON>'`：角色 → effort，与 `--expect-models` 一样需要 `--workflow`；
- `--turns '<JSON>'`：`slice-gate.py turns` 的输出。

**effort 取值**：每个 agent 的实际 effort 取它转录里第一条带 `effort` 字段的 assistant 行。
- 所有 agent 都没有该字段时，SHALL 打印「转录无 effort 字段，effort 对账跳过」，effort 对账不判红；
- 有字段且与期望不符时，MUST 列出不符项（标签 · 期望 · 实际），并以 exit 3 退出。

**角色判定**按以下顺序：
1. label 去掉 `:retry` 后等于 `fix` 或以 `fix:` 开头 → `fixer`；
2. label 在 `--turns` 里为 `large` → `executor-large`；
3. 其余沿用 agentType → label 前缀 → 阶段；agentType `slice-executor-large` 判为 `executor-large`。

**回落**：期望表里没有 `fixer` / `executor-large` 时，这两个角色按 `executor` 对账。

**零覆盖**：`fixer` 与 `executor-large` 没有被采样到时 MUST NOT 判为零覆盖。核心三角色的零覆盖规则不变。

Feature: 收口路由对账
Rule: model 与 effort 都机械对账，可选角色未派发不算缺

#### Scenario: audit-flags-effort-mismatch
- **GIVEN** 一个 workflow 目录：S1（Implement）实际 opus、effort `high`，review:S1 实际 opus、effort `high`，integrate:w1 实际 sonnet、effort `low`
- **WHEN** 带 `--expect-models`（executor / reviewer = opus，integrator = sonnet）与 `--expect-efforts`（executor 为 `medium`，其余与实际相同）运行
- **THEN** exit 3，输出含 S1、期望 `medium` 与实际 `high`

#### Scenario: audit-maps-fix-labels-to-fixer
- **GIVEN** 一个 workflow 目录：S1 实际 opus · medium，`fix:w1` 实际 fable · high，review 与 integrate 与期望一致
- **WHEN** 期望表 executor = opus · medium、fixer = fable · high，运行对账
- **THEN** 退出 0，路由对账一致，且列出 `fixer=fable`

#### Scenario: audit-maps-large-slices-by-turns
- **GIVEN** 一个 workflow 目录：S2（Implement，meta 的 agentType 为 `workflow-subagent`）实际 fable，其余与期望一致
- **WHEN** 期望表 executor = opus、executor-large = fable，并传 `--turns '{"S2": "large"}'`
- **THEN** 退出 0，S2 按 `executor-large` 对账通过

#### Scenario: audit-skips-undispatched-optional-roles
- **GIVEN** 一个只有执行体、评审、integrator 的 workflow 目录，取值都与期望一致
- **WHEN** 期望表含全部 5 个角色
- **THEN** 退出 0，输出不含 `fixer` 或 `executor-large` 的「未采样到角色」

#### Scenario: audit-warns-when-effort-unrecorded
- **GIVEN** 一个 workflow 目录，所有 assistant 行都没有 `effort` 字段，模型与期望一致
- **WHEN** 带 `--expect-efforts` 运行
- **THEN** 退出 0，输出含「转录无 effort 字段，effort 对账跳过」
