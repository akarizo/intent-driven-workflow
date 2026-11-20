## ADDED Requirements

### Requirement: fork 汇报包含计划、结果与验证
`/clean-after-merged` 在 fork 子 agent 里运行时，命令 SHALL 要求最后一条回复依次包含三部分：step 2 清理计划的原文（safe / manual / keep 三段）、step 4 的 `done` / `failed` 与 manual 档命令代码块、step 5 的验证输出。计划与验证 SHALL NOT 只出现在中间步骤里。

Feature: 合并后清理的汇报
Rule: 用户只看得到最后一条回复，所以该看的都要放进去

#### Scenario: cleanup-final-reply-carries-plan-result-verify
- **GIVEN** 模板的 `/clean-after-merged` 命令文件
- **WHEN** 读取它对最后一条回复的约定，以及 step 2 与 step 5 对输出的要求
- **THEN** 最后一条回复的约定依次点名 step 2 的计划原文、step 4 的 `done` / `failed` 与 manual 档代码块、step 5 的验证输出
- **AND** step 2 与 step 5 都要求把输出放进最后一条回复

### Requirement: 起始 CWD 的依据写进文档
`/clean-after-merged` 命令 SHALL 写明子 agent 的起始 CWD 是主会话当前所在目录（主会话 `cd` 过也一样）及其实测依据，并要求 `--protect` 传绝对路径；原因表的 `session-cwd` 一行 SHALL 说明保护只覆盖传入的路径。

Feature: 保护主会话所在的 worktree
Rule: 前提写明依据，参数写明形状

#### Scenario: cleanup-doc-states-cwd-basis
- **GIVEN** 模板的 `/clean-after-merged` 命令文件
- **WHEN** 读取运行方式一节与原因表
- **THEN** 运行方式写明起始 CWD 是主会话当前所在目录、主会话 `cd` 过也一样，并给出实测日期 2026-11-20
- **AND** 写明 `--protect` 传绝对路径
- **AND** 原因表的 `session-cwd` 一行说明只保护 `--protect` 传入的路径
