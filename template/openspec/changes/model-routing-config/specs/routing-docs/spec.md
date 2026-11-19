## ADDED Requirements

### Requirement: 飞行文档从钉住的路由起飞
`/opsx-apply` 命令与 `openspec-apply-change` skill（同改）SHALL 做到：
- 起飞前运行 `python3 .claude/hooks/model-routing.py resolve --change-dir …`，非 0 即停下报告；
- 把 stdout 的 `models` / `efforts` 原样作为 Workflow args，并在起飞时打印路由表；
- 回退路径的 Agent 派发显式传 `model` 与 `effort`；
- 收口时 `session-decompose.py` 带 `--expect-models`、`--expect-efforts` 与 `--turns`。

两者 MUST NOT 再出现 `<main>`、`--model=` 或用 `session-model.py` 判定路由。

`/opsx-propose` 命令与 `openspec-propose` skill（同改）SHALL 在 tasks 阶段 lint 绿之后运行 `model-routing.py pin --change-dir …`。

Feature: 飞行文档的路由
Rule: 起飞用 resolve，规划用 pin

#### Scenario: apply-docs-resolve-routing-from-pin
- **GIVEN** `template/.claude/commands/opsx-apply.md` 与 `template/.claude/skills/openspec-apply-change/SKILL.md`
- **WHEN** 读两者全文与回退路径段
- **THEN** 两者都含 `model-routing.py resolve`、`--expect-efforts` 与 `--turns`，都不含 `<main>`、`--model=` 与 `session-model.py`
- **AND** 两者的回退路径段都写明 Agent 派发传 `effort`

#### Scenario: propose-docs-pin-routing
- **GIVEN** `template/.claude/commands/opsx-propose.md` 与 `template/.claude/skills/openspec-propose/SKILL.md`
- **WHEN** 读两者全文
- **THEN** 两者都含 `model-routing.py pin --change-dir`，且出现在 `slice-gate.py lint` 之后

### Requirement: 辅助派发点按键取值
下列派发点 SHALL 先运行 `model-routing.py get <键>`，再按其 `model` 与 `effort` 派发：

| 派发点 | 键 |
|---|---|
| `/pr-ship` 的评审与复核 | `ship.reviewer` / `ship.followup` |
| `/opsx-archive` 命令与 `openspec-archive-change` skill 的 sync | `archive.sync` |
| `/claudemd-standardize` 的证据调查 | `claudemd.evidence` |
| `/opsx-bulk-apply` 命令与 `openspec-bulk-apply-change` skill 的子 agent | `bulk.apply` |
| legacy 逐 task 模式的实现 / 修复 / 评审 | `flight.executor` / `flight.fixer` / `flight.reviewer` |

这些文件 MUST NOT 再出现 `<main>` 或写死的 `model: "sonnet"` / `model: sonnet`。

Feature: 辅助派发点
Rule: 每个执行层派发都从配置取值

#### Scenario: auxiliary-dispatches-read-routing
- **GIVEN** 上表列出的 7 个文件
- **WHEN** 逐个读取
- **THEN** 每个文件都含 `model-routing.py get` 与它对应的键
- **AND** 都不含 `<main>`、`model: "sonnet"` 与 `model: sonnet`

### Requirement: 规划期不进路由（机械检查）
`model-routing.py` 拒收的规划期组名（propose / explore / new / continue / mini）与扫描范围 MUST 是同一份清单：每个组名 `<g>` 都有命令 `opsx-<g>.md`。

扫描范围是这 5 个命令，加上 4 个规划类 skill（`openspec-explore` / `openspec-new-change` / `openspec-continue-change` / `openspec-propose`），要求：
- frontmatter MUST NOT 含 `model:` 或 `effort:`；
- 正文 MUST NOT 含 `subagent_type` 或 `model: "` 形式的派发。

Feature: 规划期不变式
Rule: 规划期产出只来自主会话或 fork

#### Scenario: planning-docs-carry-no-routing
- **GIVEN** `model-routing.py` 登记的规划期组名，以及由它们得到的 5 个命令和 4 个规划类 skill
- **WHEN** 读取这些文件的 frontmatter 与正文
- **THEN** 规划期组名正好是 propose / explore / new / continue / mini，且每个组名都有对应的命令文件
- **AND** 没有一个文件的 frontmatter 含 `model:` 或 `effort:`，正文也不含 `subagent_type` 或 `model: "`
