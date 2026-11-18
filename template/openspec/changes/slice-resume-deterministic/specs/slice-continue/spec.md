## ADDED Requirements

### Requirement: start 接上一轮的全部提交
`slice-gate.py start <S>` SHALL 接受 `--continue <commit>`，在基点校验之后、子仓填充之前把上一轮属于本片的提交接到当前 HEAD：`<commit>` 已是 HEAD 的祖先时不做任何事（`mode` 为 `noop`）；HEAD 是 `<commit>` 的祖先时快进到它（`mode` 为 `ff`）；否则把 `git rev-list --reverse <commit> --not HEAD` 列出的提交按原顺序逐个重放（`mode` 为 `pick`）。成功时 stdout 的 JSON SHALL 多一个 `continued`，形如 `{"from": <commit>, "mode": "noop" | "ff" | "pick", "applied": <接上的提交数>}`。`<commit>` 不在对象库、区间里有合并提交、或重放冲突时，脚本 MUST 自己撤销已做的重放并回到接续前的 HEAD，MUST NOT 写切片标记，stdout 打印 `{"slice", "ok": false, "commit": "", "failed": ["G0 base: 接续 …"], …}` 并以 1 退出；冲突时 `failed` 首项 MUST 点名冲突文件。子仓按接续之后的 gitlink 填充。
Feature: 重派的切片从上一轮停下的地方继续
Rule: 上一轮有几个提交就接几个；接不上就原样退回，不留半截

#### Scenario: continue-replays-all-previous-commits
- **GIVEN** 上一轮执行体在基点 T 上提交了两次
- **AND** change 分支随后多了一个飞行记录提交 R，重派的临时 worktree 从 R 分叉
- **WHEN** 在该 worktree 里运行 `start S1 --continue <第二个提交> --expect-branch <change 分支>`
- **THEN** 退出 0，两个提交按原顺序出现在 R 之上，两处改动的文件都在场
- **AND** 输出的 `continued` 为 `{"from": <第二个提交>, "mode": "pick", "applied": 2}`
- **AND** 输出与切片标记里的 `base` 都是 R

#### Scenario: continue-fast-forwards-descendant
- **GIVEN** 上一轮执行体在基点 T 上提交了两次，change 分支没有前进
- **AND** 重派的临时 worktree 从 T 分叉
- **WHEN** 运行 `start S1 --continue <第二个提交> --expect-branch <change 分支>`
- **THEN** 退出 0，HEAD 就是上一轮的第二个提交，没有产生新提交
- **AND** `continued` 的 `mode` 为 `ff`、`applied` 为 2，`base` 为 T

#### Scenario: continue-conflict-rolls-back-with-g0
- **GIVEN** 上一轮改了 `src/a.py`，change 分支随后合回了对同一文件的不同改动
- **AND** 重派的临时 worktree 从分支最新提交分叉
- **WHEN** 运行 `start S1 --continue <上一轮的提交> --expect-branch <change 分支>`
- **THEN** 退出 1，JSON 的 `ok` 为 false、`commit` 为空，`failed` 首项以 `G0 base` 开头并含「接续」与 `src/a.py`
- **AND** HEAD 回到分叉时的提交，工作树干净，没有切片标记

#### Scenario: continue-noop-when-already-applied
- **GIVEN** 上一轮的 worktree 里切片标记还在，HEAD 已含上一轮的全部提交
- **WHEN** 连续两次运行 `start S1 --continue <上一轮的最后一个提交> --expect-branch <change 分支>`
- **THEN** 两次都退出 0，HEAD 不变，`continued` 为 `{"from": …, "mode": "noop", "applied": 0}`
- **AND** 标记里的 `base` 仍是首轮记下的值

#### Scenario: continue-populates-submodule-at-new-gitlink
- **GIVEN** 带 submodule 的仓库，上一轮执行体提交了子仓 s1 与父仓 C1（gitlink 指向 s1）
- **AND** 重派开了一间子仓尚未填充的临时 worktree
- **WHEN** 运行 `start S1 --continue C1 --expect-branch <change 分支>`
- **THEN** 退出 0，父仓 HEAD 是 C1
- **AND** 该 worktree 的子仓检出在 s1 上，上一轮的文件在场

### Requirement: 门禁区间的起点由脚本按 change 分支算
`start` 带 `--expect-branch <B>` 时，写进切片标记与输出的 `base` SHALL 是 HEAD 与 B 的合并基点（接续完成之后计算）；同时给了 `--base` 且与之不同的，MUST 以算出的为准。不带 `--expect-branch` 时 `--base` 照旧生效、缺省为 HEAD。同片标记已存在时标记 MUST 原样保留。切片门禁据此算出的区间 MUST NOT 包含 change 分支自己的提交。
Feature: 切片的改动范围不受分支上别的提交干扰
Rule: 有 change 分支可对照时，起点不采信调用方回传的旧值

#### Scenario: base-is-branch-merge-base
- **GIVEN** 上一轮在旧基点 T 上提交了一次，change 分支此后多了两个只改飞行记录的提交
- **AND** 重派的临时 worktree 从分支最新提交分叉，并已把上一轮的提交接上
- **WHEN** 运行 `start S1 --base T --expect-branch <change 分支>`，再运行 `gate S1`
- **THEN** `start` 退出 0，`base` 是分支最新提交，不是 T
- **AND** 门禁 JSON 的 `base` 与之相同，`failed` 里没有 `G6` 项

### Requirement: 工作流的重派经 start 接续
`opsx-apply` 工作流在上一轮交回了带 `commit` 的门禁 JSON 而需要重派时，执行体 prompt 里的 `start` 命令 SHALL 带 `--continue <上一轮 commit>` 与 `--expect-branch`，MUST NOT 带 `--base`，prompt MUST NOT 再有要求执行体手工接提交的「第零步」。prompt SHALL 写明 hooks 未升级时的回退：`start` 报 `unrecognized arguments` 时，HEAD 不是该提交就 `git cherry-pick` 它，再运行不带 `--continue` 的 `start`。执行体定义 `slice-executor.md` SHALL 说明 `--continue` 由脚本接上一轮的提交、输出里有 `continued`、`start` 非 0 退出时原样返回其 JSON。命令文档 `opsx-apply.md` 与同名 skill 的回退路径 SHALL 用同样的做法描述重派。
Feature: 重派 prompt 不再指挥 git
Rule: 接续交给 start；文档与脚本说同一件事

#### Scenario: workflow-retry-continues-via-start
- **GIVEN** 某切片首轮门禁红，门禁 JSON 带 `commit`
- **WHEN** 工作流重派该切片
- **THEN** 重派 prompt 里的 `start` 命令带 `--continue <该 commit>` 与 `--expect-branch`，不带 `--base`
- **AND** prompt 不含「第零步」，只在 hooks 未升级的回退句里提到 `cherry-pick` 与 `unrecognized arguments`
- **AND** prompt 仍要求只修上一轮红的门禁项

#### Scenario: executor-contract-describes-continue
- **GIVEN** 执行体定义 `slice-executor.md`
- **WHEN** 阅读它的开工段与预算条
- **THEN** 写明重派时 `start` 带 `--continue`、输出带 `continued`，不再有「第零步」
- **AND** 预算条指向 frontmatter 的上限并点名 `slice-executor-large`
- **AND** `--resume-checkpoint`、`--expect-branch`、`checkpoint.restored`、`recovered`、G12 的说明仍在

#### Scenario: apply-docs-mirror-continue-and-tiers
- **GIVEN** 命令文档 `opsx-apply.md` 与同名 skill `openspec-apply-change/SKILL.md`
- **WHEN** 阅读两份文档的起飞步骤与回退路径
- **THEN** 两份都写明起飞前运行 `slice-gate.py turns --change-dir …` 并把结果作为 `turns` 传给工作流
- **AND** 回退路径的重派用 `start --continue`，大片档派 `slice-executor-large`，全文不含「第零步」
- **AND** 回退路径写明未返回的 blocked 理由带档位与 `refs/flight/` 下的快照位置，`--resume-checkpoint` 的说明仍在
