## ADDED Requirements

### Requirement: 工作流用脚本合回
Rule: `opsx-apply.js` 有两处合回，SHALL 都让 integrator 运行 `slice-gate.py merge`，并原样带上各片的 `<S>=<commit>`：
- 每个 wave 的合回；
- finalize 前合回 fix（`fix=<commit>`，位于 `slice-gate.py final` 之前）。

`merge` 退出非 0 时，integrator 把它的 `failed` 原样作为返回值。

#### Scenario: integrator-merges-via-script
- **GIVEN** waves `[[S1, S2], [S3]]` 门禁全绿，S1、S2 的 commit 为 a…a、b…b
- **AND** S1 评审给出 1 条 HIGH，fix 返回 9…9
- **WHEN** 用 mock agent 跑完工作流
- **THEN** `integrate:w1` 的 prompt 含 `slice-gate.py merge S1=a…a S2=b…b`
- **AND** `final-gate` 的 prompt 含 `slice-gate.py merge fix=9…9`，且在 `slice-gate.py final` 之前

### Requirement: fix 执行体先填充子仓
Rule: fix 的 prompt SHALL 在基点校验之后、`start fix` 之前，运行 `slice-gate.py sub-sync`，带 `--change-dir` 与 `--expect-branch`。它非 0 时，fix 不做改动，原样返回其 `failed`；以 `G0` 开头的失败按基点拒绝处理（重派一次）。

#### Scenario: fix-prompt-syncs-submodules
- **GIVEN** 一条 HIGH 触发 fix
- **WHEN** 跑完工作流，取 fix 派发的 prompt
- **THEN** prompt 里 `slice-gate.py sub-sync` 命令带 `--expect-branch worktree-c` 与 `--change-dir openspec/changes/c`
- **AND** 位于 `merge-base --is-ancestor` 之后、`slice-gate.py start fix` 之前

### Requirement: 评审读含子仓改动的 diff
Rule: 评审 prompt SHALL 用 `git show --submodule=diff <commit>` 读切片 commit，使子仓内的改动随 diff 展开。没有 submodule 时输出与原来相同。

#### Scenario: reviewer-reads-submodule-diff
- **GIVEN** S1 的 commit 为 a…a
- **WHEN** 跑完工作流，取 `review:S1` 的 prompt
- **THEN** prompt 含 `git show --submodule=diff a…a`

### Requirement: agent 定义与命令文档写明子仓纪律
Rule: agent 定义与命令文档 SHALL 写明以下内容：
- **`integrator.md` 第 1 项**：用 `slice-gate.py merge` 合回，并写明它逐片 `git merge --no-ff`、模型不手解冲突。
- **`slice-executor.md` 纪律段**：owns 落在 submodule 内时，先 `git -C <子仓路径>` 提交，再把 gitlink 与父仓 owns 文件并入同一个切片 commit；不在子仓里切分支、不 push。
- **`opsx-apply.md` 与 `openspec-apply-change/SKILL.md` 的回退段**：同样写明 `slice-gate.py merge` 与 `slice-gate.py sub-sync`。
- **`openspec-git-discipline/SKILL.md`**：新增 `## Submodule` 小节，写明隔离 worktree 借用家子仓的 linked worktree，以及 gitlink 的提交与合回规则。

#### Scenario: agent-docs-describe-submodule-discipline
- **GIVEN** `slice-executor.md` 与 `integrator.md`
- **WHEN** 取 integrator 第 1 项与执行体纪律段
- **THEN** 第 1 项含 `slice-gate.py merge` 与 `git merge --no-ff`
- **AND** 纪律段含 `git -C`、`gitlink`、`submodule`

#### Scenario: apply-docs-mirror-submodule
- **GIVEN** `opsx-apply.md`、`openspec-apply-change/SKILL.md`、`openspec-git-discipline/SKILL.md`
- **WHEN** 取命令与 skill 的回退段
- **THEN** 两处都含 `slice-gate.py merge` 与 `slice-gate.py sub-sync`
- **AND** git-discipline 含 `## Submodule` 小节与 `linked worktree`
