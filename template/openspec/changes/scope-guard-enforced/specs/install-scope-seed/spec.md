## ADDED Requirements

### Requirement: 新装与升级都种选测声明
Rule: `install.sh` 在安装模式和 `--upgrade` 模式下都 SHALL 调用模板自带的 `slice-gate.py scope-seed --openspec-root <目标>/openspec`，并把它的输出原样打印到 stdout。安装器不新增参数，也不交互。

`scope-seed` 的规则：
- 已有声明 → 保留，并打印其内容；
- 没有历史 change，或历史 `gate.test` 全部可识别 → 种 `{"builtin": true}`；
- 否则不种，打印醒目提示：本仓库自带选测，须实现只算范围的命令并写 `gate-scope.json` 的 `cmd`；在此之前，新 change 的 lint 会判「未声明选测范围」。

没有 python3 时，打印手动声明的指引，安装照常完成。

#### Scenario: fresh-install-seeds-builtin
- **GIVEN** 一个空目录
- **WHEN** 运行 `install.sh <目录>`
- **THEN** 以 0 退出
- **AND** `openspec/gate-scope.json` 解析后等于 `{"builtin": true}`
- **AND** stdout 提到 `gate-scope.json`

#### Scenario: upgrade-seeds-builtin-when-history-plain
- **GIVEN** 一个已安装、但没有 `openspec/gate-scope.json` 的项目，`openspec/changes/x/slices.json` 的 `gate.test` 是 `python3 -m pytest -q tests`
- **WHEN** 运行 `install.sh --upgrade <项目>`
- **THEN** 以 0 退出
- **AND** `openspec/gate-scope.json` 解析后等于 `{"builtin": true}`

#### Scenario: upgrade-warns-when-history-opaque
- **GIVEN** 一个已安装、但没有 `openspec/gate-scope.json` 的项目，`openspec/changes/archive/x/slices.json` 的 `gate.test` 是 `bash openspec/changes/x/verify/full_suite.sh`
- **WHEN** 运行 `install.sh --upgrade <项目>`
- **THEN** 以 0 退出
- **AND** 没有 `openspec/gate-scope.json`
- **AND** stdout 含「自带选测」与 `gate-scope.json`

#### Scenario: existing-declaration-kept-and-printed
- **GIVEN** 一个已安装的项目，`openspec/gate-scope.json` 是 `{"cmd": "my-scope"}`
- **WHEN** 运行 `install.sh --upgrade <项目>`
- **THEN** 以 0 退出
- **AND** 文件内容不变
- **AND** stdout 含 `my-scope`

### Requirement: 文档描述契约 v2
Rule: 以下文档 SHALL 描述契约 v2：
- schema、`/opsx-propose` 及同名 skill：写明 `{"builtin": true}`、`GATE_SCOPE_PLANNED`、`GATE_SCOPE_CHANGE` 与伪触发项 `scope:undeclared`；
- `/opsx-apply`、`/opsx-verify` 及各自同名 skill：写明 baseline / final 的「开跑前复核」；
- README：写明 `{"builtin": true}`、`GATE_SCOPE_PLANNED`、「开跑前复核」与 `scope-seed`。

#### Scenario: docs-describe-scope-contract-v2
- **GIVEN** 本 change 的文档改动已完成
- **WHEN** 检查 schema、三个命令及各自同名 skill、README
- **THEN** schema、`/opsx-propose` 命令与同名 skill 都含 `{"builtin": true}`、`GATE_SCOPE_PLANNED`、`GATE_SCOPE_CHANGE`、`scope:undeclared`
- **AND** `/opsx-apply`、`/opsx-verify` 命令与各自同名 skill 都含「开跑前复核」
- **AND** README 含 `{"builtin": true}`、`GATE_SCOPE_PLANNED`、「开跑前复核」、`scope-seed`
