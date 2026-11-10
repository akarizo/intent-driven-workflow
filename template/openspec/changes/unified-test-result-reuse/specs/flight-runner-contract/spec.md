## ADDED Requirements

### Requirement: 导出供包装脚本转发的契约变量
Rule: `run_test_gate` 加载 flight 插件时，SHALL 在保留现有 `PYTEST_ADDOPTS` / `PYTHONPATH` 注入的同时，另外导出两个变量：
- `FLIGHT_PLUGIN_PATH`：flight 插件与 `sitecustomize.py` 所在目录；
- `FLIGHT_PYTEST_ARGS`：本次要传给 pytest 的 `-p` 插件参数与 `--junitxml` 参数，按 shell 规则引号。

会重建子进程环境的包装脚本，只要把前者放进被测进程的 `PYTHONPATH`、把后者原样传给 pytest，依赖图即可测到。去掉插件的重跑（`_plain`）不导出这两个变量。

#### Scenario: wrapper-forwarding-contract-measures-deps
- **GIVEN** gate.test 是一个包装脚本：清空 `PYTEST_ADDOPTS` 与 `PYTHONPATH`，再以 `PYTHONPATH=$FLIGHT_PLUGIN_PATH` 和 `$FLIGHT_PYTEST_ARGS` 调 pytest
- **WHEN** 运行 baseline
- **THEN** 基线 warnings 里没有「依赖图未测」
- **AND** 最新锚点 `measured` 为真

### Requirement: 依赖图未测的原因分四类
Rule: 依赖图没测到时，SHALL 给出机读类别和带修法的人话。类别：
- `not-pytest`：既没有 junit 输出，也没有 pytest 汇总行；
- `plugins-dropped`：pytest 跑了（有 junit 或汇总行），但外层防护标记没写、也没有插件导入错误——包装脚本没把 `-p` 参数传给 pytest；
- `plugin-import-failed`：输出里有 flight 插件导入错误（沿用现有的去插件重跑）；
- `incomplete`：依赖图记录有开始、没有结束，或已损坏。

基线写 `deps_unmeasured: {kind, why}`，锚点写 `deps_kind`；`plugins-dropped` 与 `plugin-import-failed` 的 why 点名 `FLIGHT_PLUGIN_PATH` / `FLIGHT_PYTEST_ARGS` 与契约文档路径。

#### Scenario: wrapper-dropping-plugins-classified
- **GIVEN** gate.test 是一个包装脚本：只把 `PYTEST_ADDOPTS` 里的 `--junitxml` 参数传给 pytest，丢掉 `-p` 参数
- **WHEN** 运行 baseline
- **THEN** 基线 `deps_unmeasured.kind` 为 `plugins-dropped`
- **AND** `deps_unmeasured.why` 含 `FLIGHT_PYTEST_ARGS`

#### Scenario: non-pytest-gate-classified
- **GIVEN** gate.test 是 `true`
- **WHEN** 运行 baseline
- **THEN** 基线 `deps_unmeasured.kind` 为 `not-pytest`

### Requirement: 项目可以声明全局路径、盲区与锚点链上限
Rule: 门禁 SHALL 认得 `<openspec 根>/gate-scope.json` 在恰含 `cmd` 或 `builtin` 之一之外的三个可选字段：
- `global`：仓库相对路径 glob 的数组。Δ 中有路径匹配时，final 与经锚点的基线都自动全量，原因点名该 glob；内建选测提供方把它当作全选触发项。
- `blind`：测试文件 glob 的数组。匹配的现存测试文件每次增量都重跑。
- `anchor_max_hops`：正整数，锚点链上限（缺省 5）。

字段形状不合法时，lint 与 preflight 判红并点名字段。

#### Scenario: declared-global-forces-full
- **GIVEN** `gate-scope.json` 声明 `global: ["plugins/**"]`；baseline 之后只提交了一个没有任何用例加载的 `plugins/p.py`
- **WHEN** 运行 final
- **THEN** `incremental.mode` 为 `full`，`full_why` 含 `plugins/**`

#### Scenario: declared-blind-always-rerun
- **GIVEN** `gate-scope.json` 声明 `blind: ["tests/test_c.py"]`；baseline 之后只提交了 `src/a.py` 的改动
- **WHEN** 运行 final
- **THEN** `incremental.mode` 为 `incremental`，`rerun_files` 为 2（依赖命中的 `tests/test_a.py` 与声明盲区的 `tests/test_c.py`）

#### Scenario: scope-decl-extras-shape-checked
- **GIVEN** `gate-scope.json` 是 `{"cmd": "<恒未全选>", "global": "plugins/**", "anchor_max_hops": 0}`
- **WHEN** 运行 lint
- **THEN** 退出非 0
- **AND** stderr 点名 `global` 须是字符串数组、`anchor_max_hops` 须是正整数

### Requirement: 运行器契约文档随模板下发
Rule: 模板 SHALL 提供 `template/.claude/flight-runner-contract.md`，随 `install.sh` 下发到项目的 `.claude/`。文档写明：
- 包装脚本要转发的两个变量与转发方法；
- 检查可读的 `GATE_TEST_RESULT` 及其字段；
- `GATE_PHASE` / `GATE_CHANGE`；
- `FLIGHT_` 与 `GATE_` 两个前缀的变量每次运行都会变，项目侧任何按环境做键的缓存都必须剔除它们（建议改用白名单）；
- 依赖图未测的四类原因与修法；
- `gate-scope.json` 的 `global` / `blind` / `anchor_max_hops`。

`/opsx-propose` 命令与同名 skill SHALL 用同一措辞要求：新写的包装脚本转发契约变量，用 `$GATE_CHANGE` 代替写死的 change 名。

#### Scenario: contract-doc-shipped-with-template
- **GIVEN** 模板仓库
- **WHEN** 读 `template/.claude/flight-runner-contract.md`
- **THEN** 文档含 `FLIGHT_PLUGIN_PATH`、`FLIGHT_PYTEST_ARGS`、`GATE_TEST_RESULT`、`GATE_CHANGE`、`anchor_max_hops` 与四个类别名
- **AND** 写明 `FLIGHT_` 与 `GATE_` 前缀的变量须从项目缓存键中剔除

#### Scenario: propose-guidance-forwards-contract
- **GIVEN** 模板仓库
- **WHEN** 读 `template/.claude/commands/opsx-propose.md` 与 `template/.claude/skills/openspec-propose/SKILL.md`
- **THEN** 两处都含同一句要求：包装脚本转发 `FLIGHT_PLUGIN_PATH` / `FLIGHT_PYTEST_ARGS`，用 `$GATE_CHANGE`，不写死 change 名
