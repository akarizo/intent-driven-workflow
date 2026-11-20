## ADDED Requirements

### Requirement: 起点依据写明实测范围
`/clean-after-merged` 命令的运行方式一节 SHALL 写明「主会话 `cd` 过也一样」的实测依据只覆盖 Agent 工具派发的子 agent，`context: fork` 命令本身未单独实测。step 1 代码块里 `pwd` 的注释 SHALL 与运行方式一节使用同一说法「主会话当前所在目录」。

Feature: 合并后清理的文档
Rule: 依据说到实测为止，同一件事只用一种说法

#### Scenario: cleanup-doc-marks-fork-command-untested
- **GIVEN** 模板的 `/clean-after-merged` 命令文件
- **WHEN** 读取运行方式一节与 step 1 的代码块
- **THEN** 运行方式一节含整句「主会话 `cd` 过也一样」，并写明 `context: fork` 命令本身未单独实测
- **AND** step 1 代码块里 `pwd` 那一行的注释含「主会话当前所在目录」
