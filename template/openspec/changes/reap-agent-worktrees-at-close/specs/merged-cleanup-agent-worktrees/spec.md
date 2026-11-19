## ADDED Requirements

### Requirement: 已被合进其他分支的临时 worktree 不再因未合入 target 而保留
对 `.claude/worktrees/` 下相对 target 为 `unmerged` 的 worktree，`merged-cleanup.py` SHALL 检查它的 HEAD 是否被 merge 进了另一个本地分支 B，判据是：
- HEAD 在 B 的历史里；
- 不在 B 的 first-parent 链上；
- B 不是它自己的分支。

命中时 MUST NOT 再因此落进 keep，SHALL 按现有的 dirty / submodule / locked / outside 规则分档，并加一条以 `landed:` 开头、写明 B 的原因。只在 B 的 first-parent 链上的（被派生，而不是被合入）MUST 维持原判。相对 target 为 `fresh` 的 MUST 维持 keep，即使某个本地分支预合并 target 后包含了它的 HEAD。`.worktrees/` 下的 worktree 行为 MUST 不变。

Feature: 合并后清理识别执行体临时 worktree
Rule: `.claude/worktrees/` 下被 merge 进其他分支的 worktree 按现有规则分档，原因以 `landed:` 开头

#### Scenario: cleanup-removes-worktree-merged-into-change-branch
- **GIVEN** change 分支 `worktree-c` 尚未合入 main
- **AND** 临时 worktree `.claude/worktrees/wf_1` 的提交已用 `--no-ff` 合进 `worktree-c`，它只剩飞行记录改动
- **WHEN** 在主 worktree 运行 `merged-cleanup.py plan`
- **THEN** `.claude/worktrees/wf_1` 落在 safe 档，原因里有以 `landed:` 开头且写明 `worktree-c` 的一条
- **AND** 运行 `apply --no-fetch` 后这间 worktree 不再存在，`worktree-c` 分支不受影响

#### Scenario: cleanup-keeps-worktree-only-forked-from
- **GIVEN** `.claude/worktrees/base` 停在 change 分支 `worktree-c` 的某个提交上，没有独有提交
- **AND** 临时 worktree `.claude/worktrees/wf_1` 从同一个提交派生，提交后被 `--no-ff` 合进 `worktree-c`；`worktree-c` 尚未合入 main
- **WHEN** 运行 `plan`
- **THEN** `.claude/worktrees/wf_1` 的原因里有以 `landed:` 开头的一条
- **AND** `.claude/worktrees/base` 仍落在 keep 档，原因不含 `landed:`（它只在 `worktree-c` 的 first-parent 链上，是被派生，不是被合入）

#### Scenario: cleanup-keeps-fresh-worktree-after-branch-premerges-main
- **GIVEN** change 分支 `worktree-c` 有自己的提交，main 随后前进了一个提交
- **AND** 在 main tip 新开一间干净的 `.claude/worktrees/x`，之后 `worktree-c` 预合并了 main
- **WHEN** 运行 `plan`
- **THEN** `.claude/worktrees/x` 仍落在 keep 档，原因不含 `landed:`

### Requirement: 已落地 change 的作废尝试进入清理
对 `.claude/worktrees/` 下未命中 landed、相对 target 为 `unmerged` 的 worktree，`merged-cleanup.py` SHALL 从切片标记（`change_dir` 的目录名）或飞行记录改动的路径认出它所属的 change C。认出 C 且 C 已落地时：
- 有自己分支的，MUST NOT 再落进 keep，SHALL 按现有规则分档，并加一条以 `dead-attempt:` 开头、写明 C 的原因；
- 游离 HEAD 的，SHALL 落进 manual，原因写明提交只在该 worktree、删除会丢失。

已落地的判据是 target 树里有 `openspec/changes/C/` 或 `openspec/changes/archive/<YYYY-MM-DD>-C/`。后者同样适用于 `refs/flight/C/*` 的清理判定。未合入 target 的分支项 MUST 维持 keep。

Feature: 作废尝试的清理
Rule: 所属 change 已落地（含已归档）时，有分支的进 safe，游离 HEAD 的进 manual

#### Scenario: cleanup-removes-dead-attempt-of-landed-change
- **GIVEN** main 树里有 `openspec/changes/c/`
- **AND** 临时 worktree `.claude/worktrees/wf_2` 在自己的分支上有一个没进任何其他分支的提交，未提交改动只有 `openspec/changes/c/` 下的飞行记录
- **WHEN** 运行 `plan`
- **THEN** `.claude/worktrees/wf_2` 落在 safe 档，原因里有以 `dead-attempt: c` 开头的一条
- **AND** 它的分支 `worktree-wf_2` 仍落在 keep 档

#### Scenario: cleanup-defers-detached-dead-attempt
- **GIVEN** main 树里有 `openspec/changes/c/`
- **AND** 一间游离 HEAD 的临时 worktree 带一个只存在于它自己的提交，切片标记指向 change `c`
- **WHEN** 运行 `plan`
- **THEN** 这间 worktree 落在 manual 档，`dead-attempt:` 原因写明删除会丢失提交

#### Scenario: cleanup-treats-archived-change-as-landed
- **GIVEN** main 树里没有 `openspec/changes/c/`，但有 `openspec/changes/archive/2026-11-19-c/`
- **AND** 本地有 `refs/flight/c/S1`，以及一间属于 `c`、在自己分支上的作废尝试 `.claude/worktrees/wf_3`
- **WHEN** 运行 `plan`
- **THEN** `refs/flight/c/S1` 与 `.claude/worktrees/wf_3` 都落在 safe 档

### Requirement: 清理命令文档说明新原因
`template/.claude/commands/clean-after-merged.md` 的原因标记表 SHALL 各用一行说明 `landed` 与 `dead-attempt` 的含义。

Feature: 原因标记文档
Rule: `/clean-after-merged` 的原因表说明 `landed` 与 `dead-attempt`

#### Scenario: cleanup-doc-explains-new-reasons
- **GIVEN** `template/.claude/commands/clean-after-merged.md`
- **WHEN** 读它的原因标记表
- **THEN** 表里有 `landed` 与 `dead-attempt` 两行，各自写明含义
