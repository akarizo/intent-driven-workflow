## ADDED Requirements

### Requirement: 基线的依赖图未测时计划须表态
本 change 有一份跑完的基线且它带 `deps_unmeasured` 时，选测复核 SHALL 追加伪触发项 `runner:deps-unmeasured`，按现有 `gate.scope_full_reason` 的规则处置：`slice-gate.py lint` 与 `preflight` 在计划没为它写理由时 SHALL 判红，违规文字 SHALL 含该触发项、`gate.scope_full_reason`、未测类别与 `.claude/flight-runner-contract.md`；`final` 开跑前复核 SHALL 在它不在已批准的理由里时判 `G2 scope` 红且不运行测试（`final --full` 豁免）。计划配了 `gate.impacted`，或属于在役的设计边界（内建声明下的非 pytest 运行器、部件形态）时 MUST NOT 追加。基线测到了依赖图时，计划里留着的这条理由 SHALL 按「不是本次触发项」判红。理由 MUST NOT 计入 `plan_sha`。
Feature: 依赖图没接通不能再被无视
Rule: 要么修好，要么写理由给批准的人看；判定以基线为准，不以脚本文本为准

#### Scenario: unmeasured-baseline-needs-statement
- **GIVEN** 一个 change 的 `gate.test` 是只转发 `--junitxml`、丢掉 `-p` 插件参数的包装脚本，没配 `gate.impacted`，计划没写理由
- **AND** baseline 已跑完，`gate-baseline.json` 的 `deps_unmeasured.kind` 为 `plugins-dropped`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出码非 0，有一行违规同时含 `runner:deps-unmeasured`、`gate.scope_full_reason`、`plugins-dropped` 与 `flight-runner-contract.md`
- **AND** 给计划加上 `gate.impacted` 后再运行 lint，退出码为 0

#### Scenario: statement-lets-lint-and-preflight-pass
- **GIVEN** 同样的包装脚本，计划在 `gate.scope_full_reason` 为 `runner:deps-unmeasured` 写了理由
- **AND** baseline 已跑完并提交，依赖图未测
- **WHEN** 运行 `slice-gate.py lint` 与 `slice-gate.py preflight`
- **THEN** 两者退出码都为 0

#### Scenario: measured-baseline-rejects-leftover-statement
- **GIVEN** 一个 change 的 `gate.test` 是按契约转发两个变量的包装脚本，计划却为 `runner:deps-unmeasured` 写了理由
- **AND** baseline 已跑完，依赖图已测到（没有 `deps_unmeasured`）
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出码非 0，有一行违规同时含 `runner:deps-unmeasured` 与「删除」

#### Scenario: final-refuses-unstated-unmeasured
- **GIVEN** 一个 change 的基线依赖图未测，计划没写理由，没有 approve 提交
- **WHEN** 运行 `slice-gate.py final`
- **THEN** final 为红，失败项有一条以 `G2 scope` 开头、含 `runner:deps-unmeasured`
- **AND** `gate.test` 没有被运行

### Requirement: 基线跑出来之前可以预写理由，脚本文本只作提示
还没有跑完的基线时，以及 baseline 开跑前的复核里，`runner:deps-unmeasured` SHALL 是待定项：计划可以预写理由，不写也不判红。此时若 `gate.test` 不是可识别的直接测试命令、没配 `gate.impacted`，且命令里直接写出的仓库文件及其 shell 静态闭包的文本里没有同时出现 `FLIGHT_PYTEST_ARGS` 与 `FLIGHT_PLUGIN_PATH`，lint 通过时 SHALL 多打印一行以 `runner:` 开头的提示，点名命令里直接写出的脚本与这两个变量；这行提示 MUST NOT 影响退出码。
Feature: 计划期就能看见风险，但不凭猜测拦人
Rule: 文本是线索，基线是事实

#### Scenario: statement-may-be-prewritten-before-baseline
- **GIVEN** 一个还没跑过 baseline 的 change，`gate.test` 是 `bash tools/gate.sh`，脚本文本里没有 `FLIGHT_PYTEST_ARGS`
- **WHEN** 先不写理由运行 `slice-gate.py lint`；再为 `runner:deps-unmeasured` 写上理由运行一次
- **THEN** 两次退出码都为 0
- **AND** 第一次的 stderr 有一行以 `runner:` 开头，含 `tools/gate.sh` 与 `FLIGHT_PYTEST_ARGS`
- **AND** 把脚本换成按契约转发两个变量的版本后运行 lint，stderr 没有以 `runner:` 开头的行

### Requirement: 增量基线沿用来源的未测状态
经旧基线或基线池复用（不经锚点）得到的增量基线 SHALL 带上来源基线的 `deps_unmeasured`；基线池条目 SHALL 保存该字段。经锚点复用的增量基线 MUST NOT 带它。
Feature: 状态不因「这次没重测」而消失
Rule: 没有新的测量，就沿用上一次测量的结论

#### Scenario: incremental-baseline-keeps-unmeasured-state
- **GIVEN** 一个 change 的全量基线依赖图未测（`deps_unmeasured.kind` 为 `plugins-dropped`）
- **AND** 之后只改了一个测试文件并提交
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 新基线的 `mode` 为 `incremental`
- **AND** 它的 `deps_unmeasured.kind` 仍为 `plugins-dropped`

### Requirement: 文档写明未测须表态
`flight-runner-contract.md`、`README.md`、schema 的 tasks instruction 与 propose 的命令 / 同名 skill SHALL 写明伪触发项 `runner:deps-unmeasured`：何时出现、怎么消除（修包装脚本后重跑 baseline，或配 `gate.impacted`）、怎么表态（`gate.scope_full_reason`）。propose 的两份文档 SHALL 用同一句话要求 baseline 报告之后重跑一次 `slice-gate.py lint`。schema MUST 保持 `openspec schema validate intent-driven` 通过。
Feature: 接入方与写计划的模型都知道这条规则
Rule: 契约文档是项目侧的唯一依据

#### Scenario: docs-describe-runner-statement
- **GIVEN** `template/.claude/flight-runner-contract.md`、`README.md`、`template/openspec/schemas/intent-driven/schema.yaml` 与 propose 的两份文档
- **WHEN** 阅读其中关于依赖图未测的段落
- **THEN** 契约文档含 `runner:deps-unmeasured`、`gate.scope_full_reason` 与 `gate.impacted`
- **AND** `README.md` 有一行同时含 `runner:deps-unmeasured` 与「理由」
- **AND** schema 的 tasks instruction 含 `runner:deps-unmeasured`
- **AND** propose 的两份文档有同一行同时含 `slice-gate.py lint` 与 `runner:deps-unmeasured`
