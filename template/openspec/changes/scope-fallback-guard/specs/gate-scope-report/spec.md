## ADDED Requirements

### Requirement: 选测命令的声明与运行契约
计划 MAY 在 `gate.scope` 写选测范围命令（非空字符串，只算范围、不跑测试）；仓库 MAY 在 openspec 根放 `gate-scope.json`，内容是只含 `cmd`（非空字符串）的对象。有效的选测命令 = `gate.scope`（若有），否则 `gate-scope.json` 的 `cmd`（若有）。`gate.scope` 不是非空字符串、`gate.scope_full_reason` 不是「键 → 非空字符串」的对象、`gate-scope.json` 无法解析或字段不对时，`slice-gate.py lint` SHALL 退出非 0，违规行以 `scope:` 开头并点名对象。

有有效选测命令时，`slice-gate.py lint` 与 `slice-gate.py preflight` SHALL 实跑它一次；`slice-gate.py waves` SHALL NOT 运行它。运行契约：

- 在 git 顶层目录运行，超时 300 秒；
- 环境变量 `GATE_SCOPE_OUT` 指向库准备的临时文件路径；
- 命令往该文件写一个 JSON 对象，只含 `full`（布尔，必填）、`triggers`（字符串数组，必填；`full` 为真时非空，每项非空）、`count`（可选，非负整数）。

命令退出非 0、超时、没写出文件、文件不是合法 JSON 或形状不符时，lint / preflight SHALL 退出非 0，违规行以 `scope:` 开头并写明原因（退出码、超时、缺文件，或哪个字段不合法）。

核对通过时，lint SHALL 在 stderr 打印一行以 `scope:` 开头的摘要（是否全选、`count`、全选时的触发项）；stdout 的 waves JSON 不变。

`gate.scope` 与 `gate.scope_full_reason` SHALL NOT 计入 `plan_sha`。

#### Scenario: scope-lint-rejects-malformed-declarations
- **GIVEN** 计划的 `gate.scope` 是空白串，`gate.scope_full_reason` 里 `a.json` 的理由是空白
- **AND** openspec 根的 `gate-scope.json` 带未知字段 `args`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `scope:` 开头的行分别点名 `gate.scope`、`a.json`、`args`

#### Scenario: scope-command-failure-is-red
- **GIVEN** 计划的 `gate.scope` 命令退出码为 3
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、含 `exit 3`

#### Scenario: scope-bad-report-is-red
- **GIVEN** 计划的 `gate.scope` 命令退出 0，但写进 `GATE_SCOPE_OUT` 的是 `{"full": "yes", "triggers": "a"}`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、点名 `full`

#### Scenario: scope-not-full-passes
- **GIVEN** 计划的 `gate.scope` 是 `python3 tools/scope.py`，它从仓库相对路径读报告、写进 `GATE_SCOPE_OUT`：`{"full": false, "triggers": [], "count": 12}`
- **WHEN** 在仓库的子目录 `openspec` 里运行 `slice-gate.py lint`
- **THEN** 退出 0，stdout 是 waves JSON
- **AND** stderr 有一行以 `scope:` 开头、含「未全选」与 `12`

#### Scenario: repo-default-used-when-plan-silent
- **GIVEN** openspec 根的 `gate-scope.json` 是 `{"cmd": "python3 tools/scope.py"}`，它报告全选、触发项 `tools/infra.txt`
- **AND** 计划没写 `gate.scope` 与 `gate.scope_full_reason`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、同时含 `tools/infra.txt` 与 `gate.scope_full_reason`

#### Scenario: plan-scope-overrides-repo-default
- **GIVEN** openspec 根的 `gate-scope.json` 的命令退出码为 1
- **AND** 计划的 `gate.scope` 报告未全选、`count` 为 7
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0
- **AND** stderr 有一行以 `scope:` 开头、含「未全选」与 `7`

#### Scenario: waves-does-not-run-scope
- **GIVEN** 计划的 `gate.scope` 命令退出码为 1
- **WHEN** 运行 `slice-gate.py waves`
- **THEN** 退出 0，stdout 是 waves JSON

#### Scenario: preflight-runs-scope
- **GIVEN** 计划的 `gate.scope` 报告全选、触发项 `tools/infra.txt`，计划没写 `gate.scope_full_reason`
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、含 `tools/infra.txt`

#### Scenario: scope-fields-not-in-plan-sha
- **GIVEN** 两份计划只差在 `gate.scope` 与 `gate.scope_full_reason`
- **WHEN** 分别计算 `plan_sha`
- **THEN** 两者相等

### Requirement: 选测退化为全选时计划须逐项表态
有效选测命令报告 `full` 为真时，计划 SHALL 在 `gate.scope_full_reason`（对象：触发项 → 非空理由）为每个触发项写理由，键集合 SHALL 与本次 `triggers` 完全相等。下列情形 lint / preflight SHALL 退出非 0，违规行以 `scope:` 开头：

- 缺键 → 点名缺理由的触发项，并提示在 `gate.scope_full_reason` 写理由或修选测；
- 多出的键（不是本次触发项）→ 点名该键；
- `full` 为假而 `gate.scope_full_reason` 非空 → 点名每个键，提示删除；
- 没有有效选测命令却写了 `gate.scope_full_reason` → 点名 `gate.scope_full_reason`。

#### Scenario: full-without-reason-is-red
- **GIVEN** 计划的 `gate.scope` 报告全选、触发项 `a.json` 与 `b.py`，计划没写 `gate.scope_full_reason`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `scope:` 开头的行点名 `a.json` 与 `b.py`，并含 `gate.scope_full_reason`

#### Scenario: full-with-matching-reasons-passes
- **GIVEN** 计划的 `gate.scope` 报告全选、触发项 `a.json` 与 `b.py`
- **AND** `gate.scope_full_reason` 为这两项各写了非空理由
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0
- **AND** stderr 有一行以 `scope:` 开头、含「全选」与 `a.json`、`b.py`

#### Scenario: reason-keys-must-match-triggers
- **GIVEN** 计划的 `gate.scope` 报告全选、触发项只有 `a.json`
- **AND** `gate.scope_full_reason` 写了 `a.json` 与 `old.txt` 两项
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、点名 `old.txt`

#### Scenario: reason-when-not-full-is-red
- **GIVEN** 计划的 `gate.scope` 报告未全选
- **AND** `gate.scope_full_reason` 写了 `a.json`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、点名 `a.json`

#### Scenario: reason-without-scope-command-is-red
- **GIVEN** 计划没写 `gate.scope`，openspec 根也没有 `gate-scope.json`
- **AND** `gate.scope_full_reason` 写了 `a.json`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头、含 `gate.scope_full_reason`

### Requirement: 审批页显示选测范围
`spec_html.py` 渲染飞行计划一节时，有有效选测命令或 `gate.scope_full_reason` 时 SHALL 渲染「选测范围」小节：选测命令原文与来源（计划 `gate.scope` / 仓库默认 `gate-scope.json`），以及 `gate.scope_full_reason` 的「触发项 → 理由」表。渲染 SHALL NOT 运行选测命令。

#### Scenario: spec-html-shows-scope-reasons
- **GIVEN** change 的 `slices.json` 里 `gate.scope` 是 `python3 tools/scope.py`，`gate.scope_full_reason` 是 `{"executor/tests/tiering_registry.json": "理由甲"}`
- **WHEN** 运行 `spec_html.py`
- **THEN** 生成的 HTML 含「选测范围」、`python3 tools/scope.py`、`executor/tests/tiering_registry.json` 与「理由甲」

#### Scenario: spec-html-shows-repo-default-scope
- **GIVEN** openspec 根的 `gate-scope.json` 是 `{"cmd": "bash tools/scope.sh"}`，change 的计划没写 `gate.scope`
- **WHEN** 运行 `spec_html.py`
- **THEN** 生成的 HTML 含「选测范围」、`bash tools/scope.sh` 与「仓库默认」

### Requirement: 文档描述选测范围契约
schema 的 tasks instruction、`/opsx-propose` 命令与同名 skill SHALL 写明 `gate.scope`、`gate-scope.json`、`GATE_SCOPE_OUT` 与 `gate.scope_full_reason`；README SHALL 提到 `gate.scope`。

#### Scenario: docs-describe-scope-contract
- **GIVEN** 本 change 的文档改动已完成
- **WHEN** 检查 schema、`/opsx-propose` 命令与同名 skill、README
- **THEN** schema、`/opsx-propose` 命令与同名 skill 都含 `gate.scope`、`gate-scope.json`、`GATE_SCOPE_OUT`、`gate.scope_full_reason`
- **AND** README 含 `gate.scope`
