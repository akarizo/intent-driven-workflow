## ADDED Requirements

### Requirement: 工作流在每个 wave 合回后要一次集成检查
`opsx-apply` 工作流 SHALL 在 integrator 的 wave 合回派发里，把运行 `slice-gate.py wave-check --change-dir <dir> --wave <i> --of <n>` 作为合回、记录、接口摘要与 `integrate` 事件之后的一步，并要求把它打印的 JSON 原样放进返回值的 `check` 字段；prompt SHALL 写明子命令不存在（`invalid choice`）时 `check` 给 `null`。合回失败时 MUST NOT 要求集成检查的结论。返回值没有 `check` 或为 `null` 时工作流 MUST NOT 派修复、MUST NOT 记 blocked，只在返回值的 `waves` 里记一条带 `skipped` 的条目。工作流的返回值 SHALL 多一个 `waves` 数组，每个做过或跳过集成检查的 wave 一条（`wave`、`ok`、`failed`、`fix`、`skipped`）。`template/.claude/agents/integrator.md` SHALL 说明：集成检查仅当 prompt 点名时运行；子命令不存在时返回里的 `check` 为 `null`；integrator 不自己修红。
Feature: 合回的同一次派发里顺带检查
Rule: 检查由脚本做，integrator 只负责运行并带回结论

#### Scenario: workflow-asks-integrator-for-wave-check
- **GIVEN** 两个 wave 的飞行，全部切片门禁绿，integrator 带回的 `check` 是绿的
- **WHEN** 跑完整个工作流
- **THEN** 第一个 wave 的合回 prompt 含 `slice-gate.py wave-check --change-dir openspec/changes/c --wave 1 --of 2`，且它出现在 `slice-gate.py merge` 之后
- **AND** prompt 提到 `check` 与 `invalid choice`
- **AND** 没有派任何跨片修复；返回值的 `waves` 第一条是 wave 1、`ok` 为真

#### Scenario: workflow-skips-when-integrator-has-no-check
- **GIVEN** integrator 的返回值没有 `check`（hooks 未升级）
- **WHEN** 跑完整个工作流
- **THEN** 没有派跨片修复，`blocked` 为空
- **AND** 返回值的 `waves` 每条都带非空的 `skipped`

#### Scenario: integrator-contract-describes-wave-check
- **GIVEN** `template/.claude/agents/integrator.md`
- **WHEN** 阅读正文
- **THEN** 写明 `wave-check` 仅当 prompt 点名时运行、子命令不存在（`invalid choice`）时 `check` 为 `null`
- **AND** 仍然写着合回 commit、`_interfaces.md` 与 `slice-gate.py final`

### Requirement: 集成检查红时当场派一次跨片修复
`check.ok` 为假时，工作流 SHALL 在进入下一个 wave 之前派一个修复执行体：`label` 为 `fix:w<i>`，带 `isolation: worktree`，用执行体的模型与 `slice-executor` 定义。prompt SHALL 包含：这是跨片修复、不运行 `start` 与 `gate`、不受任何切片的 owns 限制；与批量修复相同的基点校验与 `sub-sync`；`check.failed` 的原文；不提交飞行记录；收尾运行带 `--fix-base <开工时的 HEAD>` 的 `wave-check` 并把 JSON 原样返回。修复执行体未返回、抛错或以 `G0` 被拒时 SHALL 重派一次（`label` 为 `fix:w<i>:retry`）。修复返回 `ok` 为真且带 commit 时，工作流 SHALL 派 integrator（`label` 为 `integrate:w<i>:fix`）用 `slice-gate.py merge wavefix<i>=<commit>` 合回、用 `record --json` 把修复返回的 JSON 写回、记 `wave-fix` 事件；随后 SHALL 为该 commit 派一个评审（`label` 为 `review:wavefix<i>`），其 finding 与切片评审一并汇总。`template/.claude/agents/slice-executor.md` SHALL 有一段说明跨片修复这种派发：不走 `start` / `gate`、收尾跑带 `--fix-base` 的 `wave-check`。
Feature: 跨片问题在下一个 wave 之前修掉
Rule: 修复不受 owns 限制，但只修红的那几项，并且绿了才合回

#### Scenario: workflow-dispatches-cross-slice-fix-on-red
- **GIVEN** 第一个 wave 的 `check` 是红的（`G15 guard layering`）；修复执行体返回绿的 JSON，commit 为 9…9，`fix.outside_owns` 有一个文件
- **WHEN** 跑完整个工作流
- **THEN** 有一次 `label` 为 `fix:w1` 的派发，带 `isolation: worktree`、执行体模型与 `slice-executor` 类型，prompt 含 `G15 guard layering`、「不受」、`--fix-base`、`wave-check` 与基点校验命令
- **AND** 有一次 `label` 为 `integrate:w1:fix` 的派发，integrator 类型，prompt 含 `merge wavefix1=9…9` 与 `record --change-dir`
- **AND** 有一次 `label` 为 `review:wavefix1` 的评审派发
- **AND** 第二个 wave 的切片照常派发，`blocked` 里没有 `wave1`；返回值 `waves` 第一条的 `fix.commit` 是 9…9

#### Scenario: executor-contract-describes-cross-slice-fix
- **GIVEN** `template/.claude/agents/slice-executor.md`
- **WHEN** 阅读正文
- **THEN** 有一段写明「跨片修复」：不运行 `start` 与 `gate`，收尾运行带 `--fix-base` 的 `wave-check`
- **AND** frontmatter 的 `maxTurns` 仍是 40

### Requirement: 修不好时按红的种类定停飞范围
修复返回 `ok` 为假、重派后仍未返回、或修复的合回失败时，工作流 MUST NOT 合回修复的提交，SHALL 记一条 `blocked`（`slice` 为 `wave<i>`；修复交回了红结论或合回失败时 `kind` 为 `gate`，未返回时为 `infra`），理由带修复的 commit（有的话）。最后一次集成检查的 `failed` 里有以 `G15` 开头的项时，后面所有 wave 的切片 SHALL 全部记 blocked（`infra`，理由点名该 wave）且不派发；否则只有依赖本 wave 任一已合回切片的下游切片记 blocked，其余切片照常派发。无论哪种情形，评审汇总、批量修复与全量门禁照常进行。
Feature: 红着的分支上不白跑
Rule: 守护红全停，测试红只停下游

#### Scenario: workflow-stops-all-when-guard-still-red
- **GIVEN** 第一个 wave 的 `check` 因 `G15` 红；修复执行体返回的 JSON 仍因 `G15` 红
- **WHEN** 跑完整个工作流
- **THEN** 没有 `integrate:w1:fix` 的派发，第二个 wave 的切片没有被派发
- **AND** `blocked` 有 `wave1`（`kind` 为 `gate`）与第二个 wave 的切片（`kind` 为 `infra`，理由含 `wave 1`）
- **AND** 全量门禁的派发仍然发生

#### Scenario: workflow-stops-only-dependents-when-tests-red
- **GIVEN** 第二个 wave 有依赖 S1 的 S3 与没有依赖的 S4；第一个 wave 的 `check` 只因 `G16` 红，修复后仍红
- **WHEN** 跑完整个工作流
- **THEN** S3 记 blocked 且没有被派发
- **AND** S4 照常派发

#### Scenario: workflow-retries-fix-noreturn-then-blocks
- **GIVEN** 第一个 wave 的 `check` 是红的；修复执行体两次都没有交回结构化结果
- **WHEN** 跑完整个工作流
- **THEN** 有 `fix:w1` 与 `fix:w1:retry` 两次派发
- **AND** `blocked` 有 `wave1`，`kind` 为 `infra`，理由含「未返回」

### Requirement: 文档镜像集成检查与跨片修复
`template/.claude/commands/opsx-apply.md` 与 `template/.claude/skills/openspec-apply-change/SKILL.md` SHALL 在起飞步骤里写明运行 `slice-gate.py landed` 并把输出作为 `landed` 传给工作流，在回退路径里写明每个 wave 合回后运行 `slice-gate.py wave-check`、红时派一次跨片修复（收尾带 `--fix-base`）、绿了用 `merge wavefix<i>=<commit>` 合回、仍红时的停飞范围（`G15` 全停），并在收口步骤里写明把工作流返回的 `waves` 写进 `review-findings.json`。`template/.claude/commands/pr-ship.md` SHALL 写明 PR 正文列出 `review-findings.json` 的 `waves` 里的跨片修复（commit 与 owns 外的文件），以及 `ship` 的理由出现「wave 集成检查红」时修复后重跑 `slice-gate.py wave-check`。`README.md` SHALL 有说明全局守护、wave 集成检查、`owns_wide` 与 `landed` 的条目。
Feature: 两条派发路径语义一致
Rule: 命令与同名 skill 同改

#### Scenario: apply-docs-mirror-wave-check-and-fix
- **GIVEN** `opsx-apply.md` 与同名 skill
- **WHEN** 阅读这两份文档
- **THEN** 两份都含 `slice-gate.py landed`、`slice-gate.py wave-check`、「跨片修复」、`--fix-base`、`wavefix`、`G15`
- **AND** 两份都写明把 `waves` 写进 `review-findings.json`

#### Scenario: pr-ship-doc-lists-cross-slice-fixes
- **GIVEN** `pr-ship.md`
- **WHEN** 阅读全文
- **THEN** 写明正文列出 `waves` 里的「跨片修复」
- **AND** 写明理由出现「wave 集成检查红」时重跑 `slice-gate.py wave-check`

#### Scenario: readme-describes-wave-guard
- **GIVEN** `README.md`
- **WHEN** 阅读全文
- **THEN** 提到「全局守护」「wave 集成检查」`owns_wide` 与 `slice-gate.py landed`
