## ADDED Requirements

### Requirement: 检查可以声明每片门禁都运行的 slice 命令
`gate.checks` 的每一项 MAY 带 `slice`（非空字符串；缺省或 `null` 表示不是全局守护）。`slice-gate.py lint` SHALL 接受它，`slice` 是空白串或非字符串时 MUST 判计划不合法并点名该检查与 `slice`。`<openspec 根>/gate-checks.json` 的某项带非空 `slice` 时，计划里的同名检查 MUST 也带非空 `slice`，否则计划不合法（点名该检查与 `slice`）；该检查写进 `gate.checks_skip` 时按跳过处理。任一检查带 `slice` 时 `plan_sha` SHALL 把各检查的 `[name, slice]` 计入；没有检查带 `slice`（含显式 `null`）时 `plan_sha` MUST 与不认识该字段时相同。
Feature: 仓库把秒级的全局守护交给每一片的门禁
Rule: 守护是检查的第三条命令，沿用检查已有的清单、跳过与超时

#### Scenario: lint-accepts-slice-command
- **GIVEN** 计划的检查 `layering` 带 `slice` 命令与 `final` 命令
- **WHEN** 运行 `slice-gate.py lint`；再把 `slice` 改成空白串后运行
- **THEN** 第一次退出 0
- **AND** 第二次以 2 退出，stderr 点名 `layering` 与 `slice`

#### Scenario: lint-requires-slice-declared-by-repo-default
- **GIVEN** `gate-checks.json` 里的检查 `layering` 带 `slice`；计划里的 `layering` 只有 `final`
- **WHEN** 运行 `slice-gate.py lint`；再把计划里的 `layering` 挪进 `gate.checks_skip` 并写理由后运行
- **THEN** 第一次以 2 退出，stderr 点名 `layering` 与 `slice`
- **AND** 第二次退出 0

#### Scenario: slice-command-is-part-of-plan-sha
- **GIVEN** 两份只差检查 `layering` 有没有 `slice` 命令的计划，以及一份把 `slice` 写成 `null` 的计划
- **WHEN** 分别计算 `plan_sha`
- **THEN** 带 `slice` 命令的那份与另外两份不同
- **AND** 没有 `slice` 与 `slice` 为 `null` 的两份相同

### Requirement: 基线先证明守护是绿的
`slice-gate.py baseline` SHALL 对每个带 `slice` 的检查，在它的 `baseline` 命令之后运行 `slice` 命令，环境变量 `GATE_PHASE` 为 `slice`，其余与检查的运行契约相同；结果记在 `gate-baseline.json` 的 `checks.<名>.slice`（`exit`、`sec`、`cmd`）。`slice` 命令非 0 或超时时基线 MUST 为红，`reasons` 点名该检查与 `slice`。
Feature: 守护在起点是红的就不起飞
Rule: 守护红在基线上，比红在每一片的门禁里便宜

#### Scenario: baseline-runs-and-records-slice-command
- **GIVEN** 检查 `layering` 没有 `baseline` 命令，`slice` 命令把收到的环境变量写进共用目录
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0，`gate-baseline.json` 的 `checks.layering.slice.exit` 为 0、`cmd` 等于计划里的 `slice` 命令
- **AND** `slice` 命令运行过一次，收到的 `GATE_PHASE` 为 `slice`

#### Scenario: baseline-red-when-slice-command-fails
- **GIVEN** 检查 `layering` 的 `slice` 命令以 3 退出
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0，`ok` 为假
- **AND** `reasons` 有一条同时含 `layering` 与 `slice`

### Requirement: 切片门禁运行守护并以 G15 判定
`slice-gate.py gate` SHALL 在本片 `verify` 与 `gate.lint` / `gate.typecheck` 之后、仍持全机测试锁时，按 `gate.checks` 的顺序运行每个带 `slice` 的检查：环境变量 `GATE_PHASE` 为 `slice`，共用目录与 baseline / final 相同，日志写在共用目录的 `.gate-slice-<切片 id>.log`。命令非 0 → `failed` 增加一项以 `G15 guard <名>` 开头、含退出码、日志路径与输出末尾；超时同样以 `G15 guard <名>` 开头并写明超时。基线没有该检查绿的 `slice` 记录、或记录的命令与计划不同时，MUST NOT 运行该命令，`failed` 增加一项以 `G15 guard <名>` 开头并提示重跑 baseline。计划里有守护时门禁 JSON SHALL 多一个 `guards`（`{名: {exit, sec}}`），时间线的 gate 备注多一段以「守护」开头的片段；计划里没有守护时 JSON 与备注 MUST 与没有本功能时相同。
Feature: 引入问题的那一片自己就红
Rule: 守护在每一片的门禁里跑，不靠规划的人记得把它写进 verify

#### Scenario: gate-runs-guards-in-slice-phase
- **GIVEN** 已开工的切片 S1，改动都在 owns 内；检查 `layering` 的 `slice` 命令在基线上是绿的
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁通过，`guards.layering.exit` 为 0
- **AND** `slice` 命令收到的 `GATE_PHASE` 为 `slice`
- **AND** 时间线的 gate 备注含「守护 layering」

#### Scenario: gate-reds-g13-when-guard-fails
- **GIVEN** 已开工的切片 S1；检查 `layering` 的 `slice` 命令打印 `boom` 后以 3 退出
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁红，`failed` 有一项以 `G15 guard layering` 开头，含 `exit 3` 与 `boom`
- **AND** 该项含日志路径 `.gate-slice-S1.log`

#### Scenario: gate-g13-needs-green-baseline-record
- **GIVEN** 已开工的切片 S1；计划里的检查 `layering` 带 `slice` 命令，但没有基线；另一种情形是基线记录的 `slice` 命令与计划不同
- **WHEN** 分别运行 `slice-gate.py gate S1`
- **THEN** 两次都红，`failed` 有一项以 `G15 guard layering` 开头并含「重跑 baseline」
- **AND** 两次 `slice` 命令都没有被运行

#### Scenario: gate-without-guards-unchanged
- **GIVEN** 已开工的切片 S1；计划里没有任何检查带 `slice`
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁 JSON 没有 `guards`，`failed` 没有 `G15` 开头的项
- **AND** 时间线的 gate 备注不含「守护」

### Requirement: 审批页与文档说明全局守护
`spec_html.py` 渲染的审批页 SHALL 列出计划里带 `slice` 的检查（名字与命令）并标明它们是全局守护；计划写了 `gate.wave_test_budget_sec` 时显示它；切片写了 `owns_wide` 时显示通配与理由。`template/.claude/flight-runner-contract.md` SHALL 新增一节说明：检查的 `slice` 字段、`GATE_PHASE` 的 `slice` 与 `wave` 两个取值、`slice` 命令会被并行调用且对共用目录只读、日志名 `.gate-slice-<切片 id>.log`、`G15` 与 `G16`、`gate.wave_test_budget_sec`；原有各节的标题 MUST 保留。`template/.claude/commands/opsx-propose.md`、同名 skill 与 `template/openspec/schemas/intent-driven/schema.yaml` SHALL 说明 `slice`、`owns_wide`、`gate.wave_test_budget_sec` 与 owns 条数上限随轮次档变化。
Feature: 批准的人看得到每片都会跑什么
Rule: 新字段在审批页与契约里各有一处说明

#### Scenario: spec-html-shows-guards-and-wide-owns
- **GIVEN** 计划的检查 `layering` 带 `slice` 命令，`gate.wave_test_budget_sec` 为 300，切片 S1 的 `owns_wide` 为某条通配写了理由
- **WHEN** 渲染审批页
- **THEN** 页面含「全局守护」与该 `slice` 命令原文
- **AND** 页面含 300 与该通配的理由

#### Scenario: contract-describes-guards-and-wave-check
- **GIVEN** `template/.claude/flight-runner-contract.md`
- **WHEN** 阅读全文
- **THEN** 有一节含「全局守护」，写明 `slice`、`GATE_PHASE` 的两个新取值、并行与只读、`.gate-slice-`、`G15`、`G16`、`gate.wave_test_budget_sec`
- **AND** 原有九节的标题都还在

#### Scenario: propose-docs-describe-guards-and-owns-tiers
- **GIVEN** `opsx-propose.md`、同名 skill 与 `schema.yaml`
- **WHEN** 阅读这三份文档
- **THEN** 每一份都提到「全局守护」、`owns_wide` 与 `wave_test_budget_sec`
- **AND** 每一份都写明 owns 条数上限按轮次档（标准档 12、大片档 30）
