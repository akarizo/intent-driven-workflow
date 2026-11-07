## ADDED Requirements

### Requirement: start 为隔离 worktree 借出 change 家的子仓
Rule: `slice-gate.py start` SHALL 先通过 G0 基点校验，再处理父仓索引里的每个 gitlink：
- **未填充，且 change 家的同一子仓已初始化** → SHALL 在家子仓执行 `worktree add --detach <隔离 worktree>/<子仓路径> <HEAD 的 gitlink>`，借出一个 linked worktree：
  - 与家共享对象库，不访问远端；
  - 本地未 push 的 gitlink 也能检出。
- **已填充** → SHALL NOT 改动它；检出与 gitlink 不一致时只给 warning。

change 家定位方式：在 `git worktree list --porcelain` 中找检出 `--expect-branch` 分支的那个 worktree。

基点校验不通过时，SHALL NOT 填充任何子仓。

#### Scenario: start-populates-isolated-submodule
- **GIVEN** 从主 checkout 建出的隔离 worktree，HEAD 为 change 分支 tip，其中 `mods/sub` 是空目录
- **AND** 家里子仓的 gitlink 是本地未 push 的提交
- **WHEN** 在隔离 worktree 运行 `start S1 --expect-branch worktree-c`
- **THEN** 退出 0
- **AND** 隔离 worktree 的子仓检出在 gitlink 上
- **AND** 家里子仓的 worktree 列表登记了该目录

#### Scenario: executor-commit-visible-at-home
- **GIVEN** 隔离 worktree 已 start，子仓已填充
- **WHEN** 执行体在隔离 worktree 的子仓里提交
- **THEN** 不经 fetch，家里子仓的对象库就能找到这个提交

#### Scenario: start-skips-populate-when-base-check-fails
- **GIVEN** 隔离 worktree 从 change 分支 tip 的上一个提交分叉
- **WHEN** 运行 `start S1 --expect-branch worktree-c`
- **THEN** 以 `G0 base` 拒绝（退出 1）
- **AND** 子仓不被填充

### Requirement: 子仓无法就绪时以 G0 submodule 拒绝起跑
Rule: 本片 owns 落在某个子仓内，而该子仓无法就绪时，`start` SHALL 退出 1，在 stdout 打印 `ok` 为 false 的门禁 JSON，SHALL NOT 写切片标记。无法就绪包括三种情况：
- 定位不到 change 家；
- 家里该子仓未初始化；
- gitlink 不在家子仓的对象库。

失败项 SHALL 以 `G0 submodule` 开头，点名子仓路径与修法（如 `git submodule update --init <路径>`）。

#### Scenario: start-refuses-when-home-submodule-missing
- **GIVEN** change 家里的子仓被 deinit，隔离 worktree 的子仓为空
- **WHEN** 在隔离 worktree 运行 `start S1 --expect-branch worktree-c`
- **THEN** 退出 1
- **AND** stdout JSON 的 `failed` 首项以 `G0 submodule` 开头，含 `mods/sub` 与 `submodule update --init`
- **AND** 没有 `.openspec-slice` 标记

### Requirement: 重派续跑按新 gitlink 填充
Rule: 重派时，`start` SHALL 按运行时 HEAD 的 gitlink 填充子仓，使上一轮的子仓提交在场。处理顺序：
1. 执行体在新的隔离 worktree 里，先 cherry-pick 上一轮的父仓提交（gitlink 随之更新）；
2. 再运行 `start`。

#### Scenario: retry-after-cherry-pick-populates-new-gitlink
- **GIVEN** 上一轮执行体在隔离 worktree A 提交了子仓 s1 与父仓 C1（gitlink → s1）
- **AND** 重派开了新的隔离 worktree B
- **WHEN** 在 B 里 cherry-pick C1，再运行带上一轮 `--base` 的 `start`
- **THEN** 退出 0
- **AND** B 的子仓检出在 s1 上，上一轮的文件在场

### Requirement: 快照与恢复覆盖子仓
Rule: `checkpoint` hook SHALL 对每个已填充、且有本片 owns 落在其中的子仓，单独做快照：
- 快照内容为子仓里 owns 内的未提交改动，以及相对 gitlink 的子仓提交；
- 快照写在子仓的同名 ref `refs/flight/<change>/<S>`。

`start --resume-checkpoint` SHALL 在子仓填充之后，把子仓快照里 owns 内的文件恢复为未提交改动。恢复的路径带 `<子仓路径>/` 前缀，计入 `checkpoint.restored`。

首轮 start 与门禁绿时清理快照，SHALL 同时清理子仓里的同名 ref。

#### Scenario: checkpoint-covers-submodule
- **GIVEN** 隔离 worktree A 已 start S1，子仓里写了 owns 内的 `lib1.py` 但未提交
- **AND** 快照 hook 跑过一次，执行体随后未返回
- **WHEN** 在新的隔离 worktree B 运行 `start S1 --resume-checkpoint --expect-branch worktree-c`
- **THEN** 退出 0，`checkpoint.restored` 含 `mods/sub/lib1.py`
- **AND** B 的子仓里该文件内容与 A 的半成品一致

### Requirement: preflight 校验子仓就绪
Rule: 计划里有切片 owns 落在某个子仓内时，`slice-gate.py preflight` SHALL 在检查基线之前校验 change 家里该子仓：
- 已初始化；
- 父仓 HEAD 的 gitlink 在子仓对象库里；
- 子仓检出等于该 gitlink。

任一不满足即退出非 0，点名子仓路径与 gitlink，并给出修法。

#### Scenario: preflight-refuses-unsynced-home-submodule
- **GIVEN** change 家里子仓多了一个本地提交，父仓 gitlink 没跟上
- **AND** 计划的切片 owns 落在 `mods/sub` 里
- **WHEN** 在家里运行 `slice-gate.py preflight`
- **THEN** 退出非 0，stderr 含 `mods/sub` 与 `gitlink`，不含「缺基线」

### Requirement: sub-sync 子命令供 fix 执行体填充子仓
Rule: `slice-gate.py sub-sync [--expect-branch <branch>] [--change-dir <dir>]` SHALL 对当前 worktree 执行与 `start` 相同的填充规则：
- 给了 `--change-dir` 时，计划里任一切片 owns 所在的子仓都算必需；
- 输出 JSON `{ok, synced, failed, warnings}`，退出 0（ok）或 1；
- 重复运行幂等。

#### Scenario: sub-sync-cli-for-fix
- **GIVEN** 一个子仓为空的隔离 worktree
- **WHEN** 运行 `slice-gate.py sub-sync --expect-branch worktree-c --change-dir openspec/changes/c`
- **THEN** 退出 0，JSON 的 `ok` 为 true、`synced` 为 `["mods/sub"]`，子仓检出在 gitlink 上
- **AND** 再运行一次仍 `ok`，`synced` 为空
