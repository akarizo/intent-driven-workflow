## ADDED Requirements

### Requirement: propose 改用工具链，补断言按测试文件用 fork 并行
`/opsx-propose` 命令与 `openspec-propose` skill（同改）SHALL 按以下顺序使用工具链：
1. 建 change 目录之后，在后台运行 `slice-gate.py warm --change-dir …`；
2. 用 `plan-kit.py instructions --change` 一次读取全部 instruction；
3. 写完 `slices.json` 后，依次运行 `plan-kit.py packets`、`plan-scaffold.py scaffold`；
4. 补断言：按测试文件分组。多于 1 组时，在同一条消息里为每组派一个 fork；fork 报错或不可用时，由主会话串行补完；只有 1 组时由主会话自己写；
5. 然后依次运行 `plan-scaffold.py gwt`（须 exit 0）、`plan-kit.py tasks`、`slice-gate.py lint`、`model-routing.py pin`。

两份文档的工具调用顺序 MUST 一致。

Feature: propose 工具链
Rule: 机械产物由脚本生成，断言由主会话或 fork 写

#### Scenario: propose-docs-use-plan-kit-in-order
- **GIVEN** `opsx-propose.md` 与 `openspec-propose/SKILL.md`
- **WHEN** 依次查找 `slice-gate.py warm`、`plan-kit.py instructions`、`plan-kit.py packets`、`plan-scaffold.py scaffold`、`plan-scaffold.py gwt`、`plan-kit.py tasks`、`slice-gate.py lint --change-dir`、`model-routing.py pin` 的首次出现位置
- **THEN** 两份文档都含这 8 处，且按此顺序出现

#### Scenario: propose-docs-fork-with-serial-fallback
- **GIVEN** 两份 propose 文档
- **WHEN** 取补断言那一段（`plan-scaffold.py scaffold` 与 `plan-scaffold.py gwt` 之间）
- **THEN** 这一段写明按测试文件分组、派发 `subagent_type: "fork"`、fork 不可用时由主会话串行完成，并点名 `PLAN-SCAFFOLD-PLACEHOLDER`

### Requirement: 规划期派发只允许 fork
规划类命令与 skill 的正文里，每个 `subagent_type` MUST 是 `"fork"`，`model: "` 仍然 MUST NOT 出现。这些文件由 `model-routing.py` 的规划期组名得出，与 C1 相同。

Feature: 规划期派发不变式
Rule: 规划期只能 fork，不能派冷启动或降配子 agent

#### Scenario: planning-dispatch-allows-only-fork
- **GIVEN** 规划类命令与 skill
- **WHEN** 找出正文里每个 `subagent_type` 的取值
- **THEN** 每个取值都是 `"fork"`，且至少在 propose 文档里出现一次
- **AND** 没有一个文件含 `model: "`

### Requirement: 未补完的骨架不能通过 lint
`slice-gate.py lint --change-dir D` SHALL 在任何 `.py` scenario 测试函数仍含 `PLAN-SCAFFOLD-PLACEHOLDER` 时判红，错误以 `skeleton:` 开头并点名 `path::func`。`plan-scaffold.py` 与 `slice-gate.py` 识别的占位标记 MUST 是同一个字符串。

Feature: 骨架红线
Rule: scaffold 产出的占位断言补完之前不能起飞

#### Scenario: lint-rejects-unfilled-scaffold
- **GIVEN** 一个计划，用 `plan-scaffold.py scaffold` 生成了骨架，尚未补断言
- **WHEN** 运行 `slice-gate.py lint --change-dir`
- **THEN** exit 非 0，stderr 有以 `skeleton:` 开头、点名该函数的一条
- **AND** 把占位那行换成真实断言后再运行 lint，这一条消失
