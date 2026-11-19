## ADDED Requirements

### Requirement: wave 集成检查运行守护与受影响的测试
`slice-gate.py wave-check --change-dir DIR [--wave N] [--of M]` SHALL 在所在工作树的 git 顶层依次运行：计划里每个带 `slice` 的检查（环境变量 `GATE_PHASE` 为 `wave`，日志 `.gate-wave.log`，基线记录的核对与切片门禁相同，红或超时记 `G15 guard <名>`）；然后是受影响的测试——按与增量 final 相同的步骤取锚点与选中集合（锚点到当前树的全部改动），只重跑选中的测试文件，失败或出错的用例里去掉基线预存红与锚点失败清单后还有剩余时记 `G16 wave test` 并点名用例，超时或异常退出同样记 `G16 wave test`。stdout SHALL 打印一个 JSON：`slice` 恒为 `"wave"`，另有 `ok`、`commit`、`failed`、`warnings`、`summary`、`wave`、`of`、`guards`、`tests`（`mode` 为 `impacted` / `skipped` / `none`，以及 `why`、`files`、`rerun_tests`、`est_sec`、`sec`、`budget_sec`）、`lock`；退出码按 `ok`。它 SHALL 向 `gate-report.md` 追加切片列为 `wave` 的一行，并在时间线记一条 `wave-check` 事件，备注以 `wave N/M` 开头、含守护与测试各自的秒数、结论词在末尾。
Feature: 每个 wave 合回后检查合在一起还对不对
Rule: 守护全跑，测试只跑受影响的

#### Scenario: wave-check-runs-guards-and-impacted-tests
- **GIVEN** 依赖图已测的仓库，检查 `layering` 带 `slice` 命令，基线已绿；之后提交了一处只被 `tests/test_a.py` 依赖的源码改动
- **WHEN** 运行 `slice-gate.py wave-check --wave 1 --of 2`
- **THEN** 退出 0，JSON 的 `slice` 为 `wave`、`wave` 为 1，`guards.layering.exit` 为 0
- **AND** `slice` 命令这次收到的 `GATE_PHASE` 为 `wave`
- **AND** `tests.mode` 为 `impacted`，`tests.files` 只有 `tests/test_a.py`
- **AND** `gate-report.md` 多了一行 `wave`，时间线的 `wave-check` 备注以 `wave 1/2` 开头、含「测试 」、以 `ok` 结尾

#### Scenario: wave-check-reds-on-new-test-failure
- **GIVEN** 依赖图已测的仓库，基线已绿；之后提交的源码改动让 `tests/test_a.py::test_a` 失败
- **WHEN** 运行 `slice-gate.py wave-check`
- **THEN** 退出 1，`failed` 有一项以 `G16 wave test` 开头并点名 `tests/test_a.py::test_a`
- **AND** 时间线的 `wave-check` 备注以 `red` 结尾

#### Scenario: wave-check-reds-on-guard
- **GIVEN** 检查 `layering` 的 `slice` 命令在基线上是绿的；之后提交的改动让它以非 0 退出
- **WHEN** 运行 `slice-gate.py wave-check`
- **THEN** 退出 1，`failed` 有一项以 `G15 guard layering` 开头
- **AND** `gate-report.md` 里 `wave` 的最新一行是红的

### Requirement: 测试那一半有界且不退化成全量
出现下列任一情形时，`wave-check` MUST NOT 运行测试，`tests.mode` 为 `skipped`、`tests.why` 写明原因，且不因此判红：openspec 根有 `test-tiers.json`；计划配了 `gate.impacted`；取不到可用锚点或改动命中全量触发项（原因取自与 final 预告相同的判定）；锚点带逐用例耗时且选中文件的耗时之和超过预算。预算 SHALL 取计划的 `gate.wave_test_budget_sec`（正数，其他取值 lint 判计划不合法），缺省 120 秒；锚点没有逐用例耗时时不估算、照常运行。时间线备注在跳过时 SHALL 含「测试跳过」与原因。`wave-check` MUST NOT 写锚点、MUST NOT 写测试账本。它 SHALL 持一把全机测试锁：会运行测试且选中集合非空时为独占，否则为共享。
Feature: 集成检查的成本有上限
Rule: 选不出受影响的测试、或估算太贵时，把测试留给 final 并说清楚

#### Scenario: wave-check-skips-tests-without-anchor
- **GIVEN** 依赖图测不到的仓库（`gate.test` 是丢掉插件参数的包装脚本），基线已绿；之后提交了一处源码改动
- **WHEN** 运行 `slice-gate.py wave-check`
- **THEN** 退出 0，`tests.mode` 为 `skipped`，`tests.why` 非空，`tests.files` 为空
- **AND** 时间线的 `wave-check` 备注含「测试跳过」

#### Scenario: wave-check-skips-tests-over-budget
- **GIVEN** 依赖图已测的仓库，基线已绿，锚点里 `tests/test_a.py::test_a` 的耗时被记为 500 秒；之后提交了一处只影响 `tests/test_a.py` 的改动
- **WHEN** 运行 `slice-gate.py wave-check`；再把计划的 `gate.wave_test_budget_sec` 设为 1000 后运行
- **THEN** 第一次 `tests.mode` 为 `skipped`，`tests.est_sec` 为 500，`tests.why` 含「预算」，退出 0
- **AND** 第二次 `tests.mode` 为 `impacted`

#### Scenario: wave-check-leaves-anchors-and-ledger-alone
- **GIVEN** 依赖图已测的仓库，基线已绿
- **WHEN** 先在没有任何改动时运行 `wave-check`，再提交一处源码改动后运行一次
- **THEN** 两次之后锚点池的条目数与基线刚跑完时相同，测试账本目录里没有 `final.json`
- **AND** 第一次 `tests.mode` 为 `none`、锁的方式是共享；第二次锁的方式是独占

### Requirement: 跨片修复的收尾复查列出改动范围
`wave-check` 带 `--fix-base SHA` 时 SHALL 取 `SHA..HEAD` 的改动文件，在 JSON 里给出 `fix`（`base`、`files`、`outside_owns`，后者是不被计划里任何切片的 owns 匹配的文件），时间线备注多一段写明跨片修复改了几个文件、其中 owns 外几个。改动里有本 change 的飞行记录文件时 `failed` MUST 增加一项以 `G6 flight-record` 开头。`SHA` 不在对象库或不是 HEAD 的祖先时 MUST 以 `G0 base` 判红且不运行守护与测试。
Feature: 不受 owns 限制的修复，改了什么由脚本算
Rule: 所有权不放宽，越界的范围单列出来给人看

#### Scenario: wave-check-fix-base-lists-files-outside-owns
- **GIVEN** 切片 S1 的 owns 是 `src/**`；从某个 commit 起先后提交了 `src/a.py` 与 `data/b.json` 的改动
- **WHEN** 以该 commit 为 `--fix-base` 运行 `wave-check`；再提交一处时间线文件的改动后运行；再以对象库里没有的 sha 运行
- **THEN** 第一次的 `fix.files` 是这两个文件，`fix.outside_owns` 只有 `data/b.json`，时间线备注含「跨片修复 2 个文件（owns 外 1 个）」
- **AND** 第二次的 `failed` 有一项以 `G6 flight-record` 开头
- **AND** 第三次的 `failed` 有一项以 `G0 base` 开头

### Requirement: wave 行可写回并参与收口裁决
`slice-gate.py record --json` 收到 `slice` 为 `wave` 的 JSON 时 SHALL 幂等地写一行 `wave` 进 `gate-report.md`，并在时间线记 `wave-check` 事件（备注由 JSON 的 `wave` / `of` / `guards` / `tests` / `fix` 拼出），MUST NOT 另记 `gate` 事件。`slice-gate.py ship` SHALL 在 `gate-report.md` 里 `wave` 的最新一行为红时把一条以「wave 集成检查红」开头的理由加进 `reasons`（判 draft）；没有 `wave` 行或最新一行为绿时不产生该理由。`ship` 的输出键 MUST 不变。
Feature: 在临时 worktree 里复查出的结论能回到分支，红着就不收口
Rule: 门禁红不收口同样适用于集成检查

#### Scenario: record-writes-back-wave-row
- **GIVEN** 一份 `slice` 为 `wave` 的 JSON：wave 2/3，守护 `layering` 1.2 秒，测试跳过并带原因
- **WHEN** 运行 `slice-gate.py record --json`
- **THEN** `gate-report.md` 有一行 `wave`
- **AND** 时间线多一条 `wave-check` 事件，备注以 `wave 2/3` 开头、含「守护 layering 1.2s」与「测试跳过」、以 `ok` 结尾
- **AND** 时间线没有备注以 `wave` 开头的 `gate` 事件

#### Scenario: ship-drafts-on-red-wave-row
- **GIVEN** `gate-report.md` 里 `wave` 的最新一行是红的，失败项是 `G15 guard layering`
- **WHEN** 运行 `slice-gate.py ship`；再写回一行绿的 `wave` 后运行
- **THEN** 第一次 `ready` 为假，`reasons` 有一条以「wave 集成检查红」开头并含 `G15`
- **AND** 第二次的 `reasons` 没有以「wave 集成检查红」开头的项

### Requirement: 成本归因列出 wave 集成检查
`flight-doctor.py cost` SHALL 从时间线的 `wave-check` 事件汇总：JSON 输出多一个 `wave`（`count`、`guard_sec`、`test_sec`、`skipped`），文本输出在有 `wave-check` 事件时多一行含「wave 集成检查」与次数。没有该事件时 `wave.count` 为 0、文本不多这一行；其余键与行 MUST 不变。
Feature: 集成检查花的时间看得见
Rule: 度量必打印

#### Scenario: cost-reports-wave-checks
- **GIVEN** 时间线有两条 `wave-check` 事件：一条守护 1.2 秒、测试 12.3 秒，一条守护 0.4 秒、测试跳过
- **WHEN** 运行 `flight-doctor.py cost --json` 与不带 `--json` 的 `cost`
- **THEN** JSON 的 `wave` 为 count 2、guard_sec 1.6、test_sec 12.3、skipped 1
- **AND** 文本输出有一行含「wave 集成检查 2 次」
