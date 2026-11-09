## ADDED Requirements

### Requirement: /claudemd-commit 自动录入，较大差异才对齐
Rule: `claudemd-commit.md` 中通过准入四问与预算闸的新增条目 SHALL 直接写入，不逐条问询。不丢含义的迁移（指针化、分流）同样直接执行。

「较大差异」条目 SHALL 与用户对齐，包括：
- 删除或反转既有含义；
- 与既有条目或在役 ADR 矛盾；
- 改动铁律或核心约束段；
- 写到全局 `~/.claude/CLAUDE.md`。

对齐方式分两种：单独运行时用 AskUserQuestion；被 `/pr-ship` 调用时不落盘，返回给调用方列进 PR 正文。

`claudemd-standard.md` §13 的合约表同步写明自动录入。

#### Scenario: claudemd-commit-auto-records
- **GIVEN** `claudemd-commit.md` 与 `claudemd-standard.md`
- **WHEN** 读取 claudemd-commit 的 step 6 与 standard §13 的 `/claudemd-commit` 一行
- **THEN** step 6 写明自动录入，且不再有「与用户逐类确认」
- **AND** 列出四种较大差异：「删除或反转」「矛盾」「铁律」「~/.claude/CLAUDE.md」，较大差异条目才用 AskUserQuestion
- **AND** 写明被 `/pr-ship` 调用时较大差异条目不落盘
- **AND** standard §13 的 `/claudemd-commit` 行含「自动录入」

### Requirement: E 类反复错误有上限
Rule: 候选 SHALL 新增 E 类「反复错误」，准入条件是同一错误本轮至少出现 2 次，且每次都有证据指针。证据可以是门禁红记录、`review-findings.json` 条目、fix commit，或用户原话。

只出现 1 次的照旧进 backlog。能写成测试、lint 或 hook 的，进 backlog 立项，常驻层只留一行带 backlog 指针的过渡条目。C 类维持废除。

#### Scenario: claudemd-commit-bounded-recurring-errors
- **GIVEN** `claudemd-commit.md`
- **WHEN** 读取 step 3 的候选分类
- **THEN** 有「E. 反复错误」，写明「至少 2 次」与「证据」，并列出 `review-findings.json` 与 fix commit
- **AND** 写明只出现 1 次进 backlog，Q4 ✓ 进 backlog 立项并留一行过渡条目
- **AND** 仍写明 C 类废除

### Requirement: /pr-ship step 2b 不问询地沉淀记忆层
Rule: `pr-ship.md` 的 step 2 与 step 3 之间 SHALL 有 step 2b「记忆层沉淀」，内容如下：
- 按 `/claudemd-commit` 的自动模式运行；
- 巡视本会话对话（含 compact 摘要）、分支 diff，以及飞行记录与评审（`timeline.md` / `gate-report.md` / `review-findings.json` / `fix:` commit）；
- 产出独立的 `docs(memory)` commit，`claudemd-lint` 与 `memory-lint` 须全绿；
- 飞行模式下，沉淀 commit 之后重跑 `slice-gate.py final`。

全文 SHALL 不出现 `AskUserQuestion`，Guardrails 仍写「全程不问询」。

#### Scenario: pr-ship-sediments-before-commit
- **GIVEN** `pr-ship.md`
- **WHEN** 找出 step 2b 的正文（位于 step 2 标题之后、step 3 标题之前）
- **THEN** 含 `/claudemd-commit`、「对话」、`timeline.md`、`review-findings.json`、`docs(memory)`、`claudemd-lint`、`memory-lint`
- **AND** 全文无 `AskUserQuestion`，Guardrails 含「全程不问询」

#### Scenario: pr-ship-reruns-final-after-sediment
- **GIVEN** `pr-ship.md` 的 step 2b
- **WHEN** 读取飞行模式那一段
- **THEN** 写明沉淀 commit 之后重跑 `slice-gate.py final`，且该命令出现在 step 6 的 `slice-gate.py ship` 之前

### Requirement: 需对齐条目进 PR 正文，收尾提示清理
Rule: step 6 的正文 SHALL 追加「## 记忆层沉淀」与「## 记忆层：需与你对齐」两段。Output Summary SHALL 有记忆层沉淀统计一行。step 11 SHALL 提示合并后在主仓根运行 `/clean-after-merged`。

#### Scenario: pr-ship-lists-alignment-items-in-pr
- **GIVEN** `pr-ship.md`
- **WHEN** 读取 step 6、Output Summary 与 step 11
- **THEN** step 6 含「## 记忆层沉淀」与「## 记忆层：需与你对齐」
- **AND** Output Summary 含「记忆层」
- **AND** step 11 含 `/clean-after-merged`
