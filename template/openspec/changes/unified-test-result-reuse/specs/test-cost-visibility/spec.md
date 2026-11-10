## ADDED Requirements

### Requirement: 起飞前预告测试成本
Rule: `python3 .claude/hooks/flight-doctor.py forecast --change-dir <dir> [--json]` SHALL 只读 `gate-baseline.json`、锚点池、`gate-scope.json` 与 `slices.json`，给出三段：
- `baseline`：
  - `mode` 取 `full` / `incremental` / `pending` / `missing`；
  - 附原因与秒数；
- `final`：
  - `mode` 取 `incremental` / `full` / `impacted` / `unknown`；
  - 全量时 `why` 写第一条原因（依赖图未测的类别与修法、不是 pytest 且没配 `gate.impacted`、锚点链耗尽、没有可用锚点等）；
  - `sec` 取 `gate.full_suite_sec`；
- `checks`：检查名单。

无论结论如何，都 exit 0、不阻断。`--json` 打印一个 JSON 对象，否则打印人读的三行。

#### Scenario: forecast-predicts-full-final-when-deps-unmeasured
- **GIVEN** change 的基线 `deps_unmeasured.kind` 为 `plugins-dropped`，`slices.json` 的 `gate.full_suite_sec` 为 816
- **WHEN** 运行 `forecast --json`
- **THEN** 退出 0
- **AND** `final.mode` 为 `full`、`final.sec` 为 816，`final.why` 含 `plugins-dropped` 与 `FLIGHT_PYTEST_ARGS`

#### Scenario: forecast-reports-incremental-when-anchor-usable
- **GIVEN** change 刚跑完测到依赖图的全量基线
- **WHEN** 运行 `forecast --json`
- **THEN** `final.mode` 为 `incremental`

#### Scenario: forecast-pending-while-baseline-running
- **GIVEN** `gate-baseline.json` 是运行标记
- **WHEN** 运行 `forecast --json`
- **THEN** 退出 0，`baseline.mode` 为 `pending`

### Requirement: 收口时归因每一次全量
Rule: `python3 .claude/hooks/flight-doctor.py cost --change-dir <dir> [--json]` SHALL 从 `timeline.md` 的 `baseline` / `final` 事件，统计全量与增量（含同树沿用）次数，以及能读到的全量秒数之和，再把每次全量的原因归为两类：
- `必要`：`--full`、全局文件或声明的 `global`、锚点链上限、分层恒全量、首次没有锚点；
- `可避免`：依赖图未测（各类别）、候选基线是红的、cmd_key 不同、有非测试改动但锚点不可用。

认不出的原因归 `未分类`。命令恒 exit 0。

#### Scenario: cost-tallies-full-runs-by-reason
- **GIVEN** `timeline.md` 有三条 baseline 事件：
  - `exit 0, 410.0s ok；全量：锚点不可用（依赖图未测：plugins-dropped）`
  - `exit 0, 500.0s ok；全量：无可用候选（锚点池为空）`
  - 一条增量
- **AND** 有两条 final 事件：`全量（没有可用锚点） ok` 与 `增量 ok`
- **WHEN** 运行 `cost --json`
- **THEN** `baseline` 计数为全量 2、增量 1，全量秒数之和为 910
- **AND** `final` 计数为全量 1、增量 1
- **AND** 依赖图未测那一条归 `可避免`，锚点池为空那一条归 `必要`

### Requirement: 项目级体检
Rule: `python3 .claude/hooks/flight-doctor.py doctor [--openspec-root <dir>]` SHALL 只读体检，分节打印：
- `[runner]`：在途 change 的基线里依赖图未测的份数，按类别计，附修法；
- `[anchors]`：锚点池条数、测到依赖图的比例、`hops` 分布；
- `[gate.test]`：不是 pytest、又没配 `gate.impacted` 的在途 change 数；
- `[declare]`：`gate-scope.json` 是否声明了 `global` / `blind` / `anchor_max_hops`。

命令恒 exit 0，不改任何文件。

#### Scenario: doctor-reports-unforwarded-wrapper
- **GIVEN** 两个在途 change 的基线 `deps_unmeasured.kind` 都是 `plugins-dropped`
- **WHEN** 运行 `doctor`
- **THEN** 退出 0
- **AND** `[runner]` 段写明 2 份基线是 `plugins-dropped`，并点名 `FLIGHT_PLUGIN_PATH` 与 `FLIGHT_PYTEST_ARGS`

### Requirement: 预告与体检出现在人看得见的地方
Rule: 预告与体检 SHALL 出现在下列位置：
- `install.sh --upgrade` 结束时，对目标项目跑 `flight-doctor.py doctor` 并原样打印；doctor 失败不影响 install 的退出码。
- `spec_html.py` 渲染「测试成本预告」段，取 `forecast --json`；取不到时保留占位。
- `/opsx-apply` 在 preflight 之后打印 `forecast`；`/opsx-propose` 报告 baseline 结束的那一行附上 `forecast` 的结论；两处都写明只预告、不阻断；命令与同名 skill 同改。

#### Scenario: upgrade-runs-doctor-report-only
- **GIVEN** 一个已安装模板的目标项目
- **WHEN** 运行 `install.sh --upgrade <目标>`
- **THEN** 退出 0，输出含 `[runner]` 段标题

#### Scenario: spec-html-shows-cost-forecast
- **GIVEN** 一个有基线的 change
- **WHEN** 运行 `spec_html.py --change-dir <dir>`
- **THEN** 生成的 `spec.html` 含「测试成本预告」段

#### Scenario: apply-and-propose-docs-print-forecast
- **GIVEN** 模板仓库
- **WHEN** 读 `opsx-apply.md`、`opsx-propose.md` 与两者的同名 skill
- **THEN** 四处都含 `flight-doctor.py forecast`，且都写明「只预告，不阻断」
