## ADDED Requirements

### Requirement: 合并状态与档位由脚本判定
Rule: 脚本 `merged-cleanup.py plan` SHALL 对每个 linked worktree、本地 `worktree-*` 分支、已合并的远端 `worktree-*` 分支、已落地 change 的 `refs/flight/*` 各输出一项。每项包含：
- `merged`：`ancestor` / `content` / `fresh` / `unmerged` / `landed` / `-`；
- `tier`：`safe` / `manual` / `keep`；
- `force`；
- 以稳定标记开头的 `reasons`；
- 确切的 `command`。

判定依据 `target_ref`：有 `<remote>/<target>` 时用它，否则用本地 `<target>`。

- tip 在 target 第一父链上 → `fresh`，`keep`；
- tip 是 target 的祖先 → `ancestor`；
- 不是祖先，但 `merge-tree` 结果与 target 树相同 → `content`；
- 其余 → `unmerged`，`keep`。

#### Scenario: plan-removes-merged-clean-worktree
- **GIVEN** 分支 `worktree-a` 带一个提交，已在远端以 `--no-ff` 合并提交合入 `main`，本地 `main` 已同步
- **AND** 它的 worktree `.worktrees/a` 没有未提交改动
- **WHEN** 在主 worktree 运行 `merged-cleanup.py plan`
- **THEN** worktree 项 `.worktrees/a` 的 `merged` 为 `ancestor`、`tier` 为 `safe`、`force` 为假，`command` 为 `git worktree remove .worktrees/a`
- **AND** 分支项 `worktree-a` 的 `tier` 为 `safe`，`command` 为 `git branch -d worktree-a`

#### Scenario: plan-detects-squash-merge
- **GIVEN** 分支 `worktree-s` 的改动在远端以 squash 方式合入 `main`，tip 不是 `main` 的祖先，worktree 干净
- **WHEN** 运行 `plan`
- **THEN** 分支项 `worktree-s` 的 `merged` 为 `content`、`tier` 为 `manual`，`command` 为 `git branch -D worktree-s`，`reasons` 有以 `content` 开头的一条
- **AND** 它的 worktree 项 `tier` 为 `safe`（删除干净的 worktree 不丢提交）

#### Scenario: plan-keeps-fresh-and-unmerged
- **GIVEN** 刚从 `main` 当前提交建出的 `.worktrees/f`（分支 `worktree-f`，无独有提交）
- **AND** 分支 `worktree-u` 带一个未合并提交，worktree 为 `.worktrees/u`
- **WHEN** 运行 `plan` 再运行 `apply --no-fetch`
- **THEN** 两个 worktree 与两个分支的 `tier` 均为 `keep`，`merged` 分别为 `fresh` 与 `unmerged`
- **AND** `apply` 之后两个 worktree 目录与两个分支都还在

### Requirement: 是否需要 --force 按改动与子仓判定
Rule: 脚本 SHALL 把未提交改动按 `status --porcelain --ignore-submodules=none --untracked-files=all` 列到文件，并按以下规则判定档位：
- 全部是飞行记录（`.openspec-slice`，或任意前缀下 `openspec/changes/<c>/` 的 `timeline.md` / `gate-report.md` / `evidence.log`）→ `safe` 且 `force`，原因标 `flight-records`；
- 还有其他改动 → `manual` 且 `force`，原因标 `dirty`，并列出文件；
- 被 lock → `manual`，原因标 `locked`；
- 路径不在 `.worktrees/` 或 `.claude/worktrees/` 下 → `manual`，原因标 `outside`；
- `manual` 档的命令汇总进 `manual`，`apply` 不执行它们。

#### Scenario: plan-forces-flight-records-only
- **GIVEN** 已合并的临时 worktree `.claude/worktrees/wf_1`
- **AND** 它的未提交改动只有已跟踪的 `openspec/changes/c/timeline.md` 被改，以及未跟踪的 `openspec/changes/c/gate-report.md`
- **WHEN** 运行 `plan`
- **THEN** 该 worktree 项 `tier` 为 `safe`、`force` 为真，`command` 为 `git worktree remove --force .claude/worktrees/wf_1`，`reasons` 有以 `flight-records` 开头的一条

#### Scenario: plan-defers-other-dirty-to-user
- **GIVEN** 已合并的 worktree `.worktrees/d` 里有一个未跟踪的 `src/new.py`
- **WHEN** 运行 `plan`、`plan --markdown`，再运行 `apply --no-fetch`
- **THEN** 该项 `tier` 为 `manual`、`force` 为真，`dirty` 含 `src/new.py`，`reasons` 有以 `dirty` 开头的一条
- **AND** 顶层 `manual` 含 `git worktree remove --force .worktrees/d`，markdown 输出也含这条命令
- **AND** `apply` 之后 `.worktrees/d` 与其中的 `src/new.py` 仍在，`apply` 的 `manual` 含这条命令

#### Scenario: plan-defers-locked-and-outside-worktrees
- **GIVEN** 已合并且干净的 `.worktrees/l`，被 `git worktree lock --reason "agent running"` 锁定
- **AND** 已合并且干净的 worktree 位于仓库目录之外
- **WHEN** 运行 `plan` 再运行 `apply --no-fetch`
- **THEN** 前者 `tier` 为 `manual`，`reasons` 有以 `locked` 开头且含 `agent running` 的一条
- **AND** 后者 `tier` 为 `manual`，`reasons` 有以 `outside` 开头的一条
- **AND** `apply` 之后两个 worktree 都还在

### Requirement: 子仓提交不能存活时不进 safe 档
Rule: worktree 含已填充的子仓时 SHALL 需要 `force`。

如果子仓库本体会随 worktree 一起删除（common dir 位于该 worktree 的 gitdir 或路径之下），则子仓 HEAD 与本地分支 tip 必须满足下面任一条件：
- 存在于主 checkout 的子仓；
- 能从子仓的 remote-tracking ref 到达。

否则判 `manual`，原因标 `unpushed-submodule`。

子仓若是从家子仓借出的 linked worktree，则判 `safe`。`apply` 删除后在家子仓运行 `worktree prune`。

#### Scenario: plan-guards-unpushed-submodule-commit
- **GIVEN** 主仓含 submodule `mods/sub`
- **AND** change worktree `.worktrees/c` 里初始化了子仓，在子仓提交了一个未推送的提交，父仓钉了 gitlink
- **AND** 分支 `worktree-c` 已在远端合入 `main`
- **WHEN** 运行 `plan`
- **THEN** `.worktrees/c` 的 `tier` 为 `manual`、`force` 为真，`reasons` 有以 `unpushed-submodule` 开头且含 `mods/sub` 的一条
- **AND** 把该子仓提交推送到子仓远端后再运行 `plan`，`tier` 变为 `safe`，`reasons` 有以 `submodule` 开头的一条

#### Scenario: apply-prunes-borrowed-submodule-worktree
- **GIVEN** 同上的 change 家 `.worktrees/c`，其子仓提交未推送
- **AND** 临时 worktree `.claude/worktrees/wf_1`（分支 `worktree-wf_1`）的 `mods/sub` 是从家子仓借出的 linked worktree
- **AND** `worktree-wf_1` 的提交经 `worktree-c` 合入远端 `main`，`wf_1` 干净
- **WHEN** 运行 `apply --no-fetch`（此前已 fetch）
- **THEN** `.claude/worktrees/wf_1` 被删除，`done` 含 `git worktree remove --force .claude/worktrees/wf_1`
- **AND** 家子仓的 `git worktree list` 不再列出 wf_1 的子仓路径
- **AND** `.worktrees/c` 仍在（`unpushed-submodule`，`manual`）

### Requirement: branch -d 按 git 规则推算，target 落后先同步
Rule: 脚本 SHALL 按 git 自身规则推算 `branch -d` 的参照点：分支有 upstream 且能解析时用 upstream，否则用有效 HEAD。

满足以下全部条件时，`sync` SHALL 为 `git merge --ff-only <remote>/<target>`，此时有效 HEAD 取 `target_ref`：
- 主 worktree 的当前分支就是 target；
- HEAD 落后于 `target_ref`，且是它的祖先；
- 没有已跟踪文件的改动。

`apply` SHALL 先同步，再删除分支。

#### Scenario: apply-syncs-target-before-branch-delete
- **GIVEN** 分支 `worktree-wf_1`（无 upstream）经 change 分支 `worktree-c` 合入远端 `main`，远端已删除 `worktree-c`
- **AND** 两者的 worktree 已不存在
- **AND** 主 worktree 在 `main` 上、没有改动，但落后于 `origin/main`
- **WHEN** 运行 `apply`
- **THEN** 本地 `main` 快进到 `origin/main`
- **AND** `worktree-wf_1` 与 `worktree-c` 被删除，`done` 依次含 `git merge --ff-only origin/main`、`git branch -d worktree-wf_1`
- **AND** `failed` 为空，退出码为 0

#### Scenario: plan-lists-remote-delete-for-user
- **GIVEN** 分支 `worktree-a` 已合入远端 `main`，远端分支 `worktree-a` 仍在
- **WHEN** fetch 之后运行 `plan`，再运行 `apply --no-fetch`
- **THEN** remote 项 `origin/worktree-a` 的 `tier` 为 `manual`，`command` 为 `git push origin --delete worktree-a`
- **AND** `apply` 之后远端分支 `worktree-a` 仍在

### Requirement: 已落地 change 的飞行快照 ref 一并清理
Rule: `refs/flight/<change>/*` 的 change 目录（任意前缀下的 `openspec/changes/<change>/`）已在 target 树里时，SHALL 判 `landed`、`safe`，`command` 为 `git update-ref -d <ref>`；未落地的不列出。

#### Scenario: apply-removes-landed-flight-refs
- **GIVEN** 远端 `main` 树里有 `openspec/changes/c/proposal.md`，没有 `openspec/changes/d/`
- **AND** 本地有 `refs/flight/c/S1` 与 `refs/flight/d/S1`
- **WHEN** 运行 `apply --no-fetch`（此前已 fetch）
- **THEN** `refs/flight/c/S1` 被删除，`refs/flight/d/S1` 仍在

### Requirement: 只在主 worktree 运行
Rule: 在 linked worktree 里运行 `plan` 或 `apply` 时，SHALL 退出 2，stdout 为 `{"ok": false, "reasons": [...]}`，不做任何改动。

#### Scenario: plan-refuses-outside-main-worktree
- **GIVEN** 已合并且干净的 `.worktrees/a`
- **WHEN** 以 `.worktrees/a` 为当前目录运行 `plan` 与 `apply --no-fetch`
- **THEN** 两次都退出 2，JSON `ok` 为假，`reasons` 有以 `not-main-worktree` 开头的一条
- **AND** `.worktrees/a` 与分支 `worktree-a` 都还在
