## ADDED Requirements

### Requirement: /clean-after-merged 先展示再执行 safe 档
Rule: 命令 `template/.claude/commands/clean-after-merged.md` SHALL 按以下顺序执行：
1. 定位主 worktree 根；
2. 运行 `python3 .claude/hooks/merged-cleanup.py plan --markdown` 并展示结果；
3. 运行 `python3 .claude/hooks/merged-cleanup.py apply`；
4. 打印 `done` / `failed`；
5. 把 `manual` 命令原样输出成命令块交给用户；
6. 运行 `git worktree list` 验证。

命令 SHALL 有回退段：脚本不可用时只做 `fetch --prune` 与 `--ff-only` 同步，然后输出人工清单，不自动删除任何东西。

#### Scenario: command-runs-plan-then-apply
- **GIVEN** `template/.claude/commands/clean-after-merged.md`
- **WHEN** 读取其正文
- **THEN** `merged-cleanup.py plan --markdown` 出现在 `merged-cleanup.py apply` 之前
- **AND** 正文写明在主 worktree 根运行（含 `--git-common-dir`），以 `git worktree list` 验证
- **AND** 有回退段，含 `--ff-only`，且写明脚本不可用时不自动删除
- **AND** Guardrails 写明不执行 `git branch -D`、`push --delete` 与 `manual` 档命令，不 `cd` 进待删的 worktree

### Requirement: 铁律 6 与 git-discipline 写明授权例外
Rule: 根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet` 的铁律 6 SHALL 写明：显式运行 `/clean-after-merged` = 授权其 safe 档。

`openspec-git-discipline/SKILL.md` 的 Worktree Isolation 节 SHALL 指向该命令与 `merged-cleanup.py`，并保留「只在主仓库根」。飞行临时 worktree 的清理条款同样指向它。

#### Scenario: iron-rule-grants-cleanup-exception
- **GIVEN** 根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`
- **WHEN** 找出两者的铁律 6 那一行
- **THEN** 两行都含 `/clean-after-merged`，根 `CLAUDE.md` 那一行仍含「不删 worktree」与 `branch -D`
- **AND** snippet 不超过 8KB

#### Scenario: git-discipline-points-to-command
- **GIVEN** `template/.claude/skills/openspec-git-discipline/SKILL.md`
- **WHEN** 读取 Worktree Isolation 节
- **THEN** 清理条款含 `/clean-after-merged`、`merged-cleanup.py` 与「主仓库根」
- **AND** 飞行临时 worktree 的 carve-out 段含 `/clean-after-merged`

### Requirement: 命令清单文档同步
Rule: 以下文档 SHALL 同步更新：
- `README.md` 的命令表列出 `/clean-after-merged`；
- `install.sh` 的命令计数为 17，并列出它；
- `docs/WORKFLOW_zh.md` 写明合并后清理用它；
- `README.md` 对 `/claudemd-commit` 与 `/pr-ship` 的描述改为自动录入与 step 2b 记忆层沉淀，不再写「逐条与用户讨论」。

#### Scenario: docs-list-new-command
- **GIVEN** `README.md`、`install.sh`、`docs/WORKFLOW_zh.md`
- **WHEN** 读取三者
- **THEN** README 命令表有 `/clean-after-merged` 一行，install.sh 含「17 个 slash command」与 `/clean-after-merged`，WORKFLOW_zh 含 `/clean-after-merged`

#### Scenario: readme-describes-auto-sedimentation
- **GIVEN** `README.md`
- **WHEN** 读取 `/claudemd-commit` 的命令表行与 `/pr-ship` 的流程说明
- **THEN** `/claudemd-commit` 行含「自动」与「对齐」，全文不再含「逐条与用户讨论」
- **AND** `/pr-ship` 流程说明含「记忆层沉淀」
