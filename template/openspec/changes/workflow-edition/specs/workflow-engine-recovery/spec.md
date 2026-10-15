## ADDED Requirements

### Requirement: 执行体抛错按未返回处理并重派一次
工作流 SHALL 把执行体 `agent()` 调用抛错（没交回结构化结果）与返回空值同样处理：重派同一切片一次；重派仍失败时 SHALL 记 blocked（infra），原因 SHALL 如实写明未返回且已重派。
Feature: workflow-engine-recovery

#### Scenario: workflow-retries-when-executor-throws
- **GIVEN** waves 为 [[S1, S2], [S3]]；S1 首轮 `agent()` 调用抛错，重派后门禁绿；S2、S3 一次绿
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** 派发了 `S1:retry`，其 `start` 带 `--resume-checkpoint`
- **AND** blocked 为空

#### Scenario: workflow-blocks-after-retry-throws
- **GIVEN** waves 为 [[S1, S2], [S3]]，S3 依赖 S1；S1 首轮与重派的 `agent()` 调用都抛错
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** S1 与 `S1:retry` 各派发一次
- **AND** blocked 中 S1 的 kind 为 infra、原因含「未返回」与「已重派」
- **AND** S3 记 blocked 且未派发

### Requirement: 每个执行体一律在临时 worktree 里跑并由 integrator 合回
每个执行体（含单片 wave 与 fix）SHALL 带 `isolation: worktree`；每个 wave SHALL 派 integrator 合回；fix 的 commit SHALL 在 final 之前合回。

#### Scenario: single-slice-wave-runs-isolated
- **GIVEN** waves 为 [[S1, S2], [S3]]，全部一次门禁绿，S3 的 commit 为 f…f
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** S3 的派发带 `isolation: worktree`
- **AND** wave 2 之后有一次合回派发，其 prompt 含 f…f

#### Scenario: workflow-merge-dispatch-forbids-final
- **GIVEN** waves 为 [[S1, S2], [S3]]，全部切片与合回都成功
- **WHEN** 用 mock agent 跑完工作流，取全部合回派发
- **THEN** 每个 wave 各一次合回（`integrate:w1`、`integrate:w2`）
- **AND** 首次合回派发的返回结构必填项含 ok 与 failed、不含 slice 与 commit；prompt 含「不要运行第 3 项」；blocked 里没有 wave 开头的条目

#### Scenario: fix-runs-isolated-and-merges-before-final
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 返回的 commit 为 9…9
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** fix 的派发带 `isolation: worktree`
- **AND** finalize 派发的 prompt 含 9…9，且它出现在 `slice-gate.py final` 之前

### Requirement: fix 先做基点校验，失败重派一次后照常 finalize
fix 第一步 SHALL 校验 HEAD 是 change 分支最新 commit 的后代（G0）；fix 抛错、未返回或被 G0 拒绝时 SHALL 重派一次；仍无可合回结果时 SHALL 记 blocked（infra）且不合回，final SHALL 照跑。

#### Scenario: fix-prompt-checks-base-first
- **GIVEN** branch 为 `worktree-c`，waves 为 [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH
- **WHEN** 用 mock agent 跑完整个工作流，取 fix 派发的 prompt
- **THEN** prompt 含基点校验命令 `git merge-base --is-ancestor $(git rev-parse worktree-c) HEAD`，且它先于 `start`
- **AND** 不成立时返回 `G0 base`；`start fix` 带 `--expect-branch worktree-c`

#### Scenario: workflow-retries-fix-after-throw
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 首轮 `agent()` 调用抛错，重派返回 commit 9…9
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** `fix:retry` 带 `isolation: worktree`
- **AND** finalize 派发的 prompt 含 9…9；blocked 为空

#### Scenario: workflow-finalizes-when-fix-throws
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 首轮与重派的 `agent()` 调用都抛错
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** fix 与 `fix:retry` 各派发一次；final-gate 仍被派发
- **AND** blocked 中 fix 的 kind 为 infra、原因含「未返回」与「已重派」

#### Scenario: workflow-skips-merge-when-fix-base-rejected
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 首轮与重派都以 `G0 base` 拒绝，返回的 commit 为 8…8
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** `fix:retry` 派发了一次
- **AND** finalize 的 prompt 不含 8…8；blocked 中 fix 的原因含 `G0 base`

### Requirement: 机械角色抛错重派一次，评审员抛错只记录
integrator 与 final-gate 抛错或未返回时 SHALL 重派一次，仍失败 SHALL 记 blocked（infra）且工作流照常走完；评审员抛错 SHALL NOT 重派，SHALL 记 blocked（infra，「评审未返回」），由 `/pr-ship` 的整 PR 评审兜底。

#### Scenario: mechanical-roles-retry-once
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；wave 1 的合回与 final-gate 的首次 `agent()` 调用都抛错，重派后都成功
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** 派发了 `integrate:w1:retry` 与 `final-gate:retry`
- **AND** blocked 为空，返回的 final 是重派的结果

#### Scenario: mechanical-roles-blocked-after-retry
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；wave 1 的合回与 final-gate 的首次和重派调用都抛错
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** 工作流正常结束，S3 仍被派发
- **AND** blocked 里有 wave1 与 final，kind 为 infra，原因含「未返回」与「已重派」

#### Scenario: reviewer-failure-recorded
- **GIVEN** waves 为 [[S1, S2], [S3]] 全部门禁绿；S1 的评审员调用抛错，S2 的评审给出 1 条 MEDIUM
- **WHEN** 用 mock agent 跑完整个工作流
- **THEN** blocked 里有 `review:S1`（infra、原因含「评审未返回」）
- **AND** deferred 含 S2 的那条 MEDIUM；final-gate 已派发

### Requirement: 门禁结论由判定器留存，重派时按基点找回
切片门禁绿时，`slice-gate.py` SHALL 把结论写成以切片 commit 为父的提交，挂到 `refs/flight/<change>/gate-<S>`；重派的 `start --resume-checkpoint` SHALL 只在 HEAD 等于留存结论的 base 或 commit 时以 3 退出并原样交出结论；`record` 写回后与首轮起跑时 SHALL 清掉这条引用。

#### Scenario: gate-ok-records-result-ref
- **GIVEN** 已 start 且实现完整的切片 S1（门禁会绿）
- **WHEN** 运行切片门禁
- **THEN** 门禁绿
- **AND** `refs/flight/c/gate-S1` 的父提交是门禁输出里的 commit，其 `gate.json` 的 slice / ok / commit / base 与门禁输出一致

#### Scenario: resume-start-returns-recorded-gate
- **GIVEN** 切片 S1 在基点 X 上提交并门禁通过（结论已留存），随后从 X 新开一个干净 worktree（模拟隔离模式重派）
- **WHEN** 在新 worktree 里运行 `start S1 --resume-checkpoint`
- **THEN** 以 3 退出；stdout 是留存的门禁结论（ok 为 true、commit 为原切片 commit、recovered 为 true）
- **AND** 新 worktree 里没有切片标记

#### Scenario: resume-start-ignores-foreign-gate-record
- **GIVEN** 切片 S1 的门禁结论已留存（base X、commit C）；C 之后又有提交 Y，在 Y 上新开 worktree
- **WHEN** 在 Y 上运行 `start S1 --resume-checkpoint`
- **THEN** 以 0 退出并按原有逻辑起跑（输出含 checkpoint、不含 recovered）
- **AND** 留存的门禁结论引用保持不变

#### Scenario: resume-start-refuses-record-after-replan
- **GIVEN** 切片 S1 门禁绿、结论已留存，随后飞行中断；人改了计划（proposal.md）并提交，又按批准提交了一次，再从新的分支尖端开 worktree
- **WHEN** 新一轮飞行里首轮执行体未返回，重派在新 worktree 里运行 `start S1 --resume-checkpoint`
- **THEN** 结论确实还留着
- **BUT** 不找回（以 0 退出、输出不含 recovered），旧计划下的 commit 不会被交出

#### Scenario: record-and-fresh-start-clear-gate-ref
- **GIVEN** 切片 S1 门禁通过、结论已留存
- **WHEN** integrator 以 `record` 写回该结论；之后人为放回一份旧结论，再首轮 `start S1`
- **THEN** 写回后引用已不存在
- **AND** 首轮 `start` 后旧结论也被清掉

### Requirement: 命令、skill 与 git 纪律写明同一套恢复语义
`opsx-apply` 命令与同名 skill 的 Agent 回退段、`slice-executor` 的开工段、`openspec-git-discipline` 的临时 worktree 例外条款 SHALL 与工作流脚本的行为一致。

#### Scenario: apply-docs-describe-recovered-gate
- **GIVEN** `slice-executor.md`、`opsx-apply.md` 与 `openspec-apply-change/SKILL.md`
- **WHEN** 取执行体开工段与两份回退路径段
- **THEN** 开工段写明「以 3 退出」时打印的是已留存的门禁结论、原样返回
- **AND** 两份回退路径都写明 agent 调用抛错与未返回同样重派

#### Scenario: apply-docs-mirror-always-isolate
- **GIVEN** `opsx-apply.md`、`openspec-apply-change/SKILL.md` 与 `openspec-git-discipline/SKILL.md`
- **WHEN** 取两份回退路径段与 git 纪律的 Worktree Isolation 节
- **THEN** 两份回退路径都含 `isolation: worktree` 并点明单片 wave 与 fix 也隔离，且不再有「同 wave 多切片各自」「多切片 wave 各自」的限定
- **AND** 例外条款点明单片 wave 与 fix 同样适用

#### Scenario: apply-docs-mirror-fix-base-check
- **GIVEN** `opsx-apply.md` 与 `openspec-apply-change/SKILL.md`
- **WHEN** 取两份回退路径段
- **THEN** 两份都写明 fix 先做 `merge-base --is-ancestor` 基点校验
- **AND** 都写明 fix 抛错 / 未返回时重派一次后仍跑 final

#### Scenario: apply-docs-mirror-agent-failure-handling
- **GIVEN** `opsx-apply.md` 与 `openspec-apply-change/SKILL.md`
- **WHEN** 取两份回退路径段
- **THEN** 都写明 integrator 与 final 抛错或未返回时重派一次
- **AND** 都写明「评审未返回」只记录、不重派
