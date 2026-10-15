## ADDED Requirements

### Requirement: legacy 逐 task 守门的评审派发显式指定 model
legacy skill 派 code-reviewer（4b 守门、修复后的聚焦复核、整个 change 的累计评审）之前 SHALL 先跑 `python3 .claude/hooks/session-model.py` 判出 `<main>`（exit 3 → 停下交人工给出别名，禁模型自述），派发时 SHALL 显式带 `model: "<main>"`（铁律 11）。
Feature: legacy-review-routing

#### Scenario: legacy-review-dispatch-names-model
- **GIVEN** `template/.claude/skills/legacy/openspec-subagent-apply-change/SKILL.md`
- **WHEN** 取每一处派发 `code-reviewer` 的段落
- **THEN** 每一处都带 `model: "<main>"`，且写明 `<main>` 由 `session-model.py` 判定
- **AND** 文中没有 `flight:` 前缀的 agent 名
