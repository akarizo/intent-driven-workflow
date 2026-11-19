## ADDED Requirements

### Requirement: 铁律 11 写明配置驱动的执行层路由与规划期不变式
仓库根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet` 的铁律 11 SHALL 同时写明以下几点：
- 执行层路由取自 `model-routing.json`；
- 只写模型名，禁 `main` / `inherit`；
- 路由在规划期钉进 `slices.json`；
- 收口时带 `--expect-efforts` 对账；
- 规划期产出只来自主会话或 fork。

两者 MUST NOT 再写「会话主模型 high」，也 MUST NOT 再要求用 `session-model.py` 判定路由。

README、`docs/WORKFLOW_zh.md` 与 `install.sh` 的路由说明 SHALL 指向 `model-routing.py` / `model-routing.json`，MUST NOT 再把执行体与评审员描述为「会话主模型」。

Feature: 铁律与对外文档
Rule: 铁律 11 与说明文档同步为配置驱动

#### Scenario: iron-rule-names-routing-config
- **GIVEN** 仓库根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`
- **WHEN** 取两者的铁律 11 一行
- **THEN** 两行都含 `model-routing.json`、`slices.json`、`--expect-efforts`、`main` 与「主会话或 fork」
- **AND** 都不含「会话主模型」

#### Scenario: readme-and-installer-describe-routing
- **GIVEN** `README.md`、`docs/WORKFLOW_zh.md` 与 `install.sh`
- **WHEN** 读三者全文
- **THEN** 三者都含 `model-routing`
- **AND** 都不含「会话主模型（`session-model.py` 判定）」或「会话主模型（session-model.py 判定）」，`docs/WORKFLOW_zh.md` 不含「会话主模型 `<main>`」
