## ADDED Requirements

### Requirement: 分层文件可声明时间预算与放行期限
`openspec/test-tiers.json` 的单元层与每个区域 SHALL 可带可选的 `budget` 对象，只认 `case_sec`（单条上限，秒）与 `total_sec`（层总量预算，秒）两个字段，各自可选，写了就必须是大于 0 的数（布尔不算数）。部件形态下 `parts.<部件>.unit` 与 `parts.<部件>.regions.<区域>` 同样可带。`slow_allow` 的条目 SHALL 可带可选的 `limit_sec`（大于 0 的数）与 `expires`（`YYYY-MM-DD`，须是真实日期）。形状不合法时 `slice-gate.py lint` MUST 判红并点名所在的层（或用例 id）与字段；没有这些字段的分层文件 MUST 与现在一样通过校验。`slice-gate.py` SHALL 提供 `tier_budgets(tiers)`，把预算摊平成 `{范围: {kind, case_sec, total_sec, part}}`：简写形态的范围是 `unit` 与各区域名，部件形态是 `<部件>/unit` 与各区域名；单元层没写 `case_sec` 时取 3 秒，区域没写时为 `null`。`budget_scope_of(tiers)` SHALL 返回一个把（用例 id，账本里的层）映射到范围的函数：区域名原样返回；`unit` 在简写形态返回 `unit`，在部件形态按用例 id 定出所属部件（id 首段等于部件名，或 id 的路径落在该部件 `root` 之下，多个命中取 `root` 最长的）。
Feature: 预算与放行期限写在仓库级分层文件里，随 PR 评审
Rule: 没写的一律按现状；写错了在 lint 就红

#### Scenario: budget-shape-validated
- **GIVEN** 一份分层文件：`unit.budget` 为 `{"case_sec": 1.5, "total_sec": 60}`，区域 `hooks` 的 `budget` 为 `{"case_sec": 30}`
- **WHEN** 读取并校验分层文件
- **THEN** 没有任何形状错误
- **AND** 把 `unit.budget.case_sec` 改成 0、把 `total_sec` 改成字符串、给区域 `hooks` 的 `budget` 加一个未知字段 `max` 后分别校验，各得到一条以 `tiers:` 开头的错误，点名 `unit` 或 `区域 hooks` 以及对应的字段名

#### Scenario: allow-entry-limit-and-expires-validated
- **GIVEN** `slow_allow` 里一条放行带 `limit_sec` 90 与 `expires` `2027-02-01`，另一条只有 `reason` 与 `approved`
- **WHEN** 读取并校验分层文件
- **THEN** 没有任何形状错误
- **AND** 把 `limit_sec` 改成 -1、把 `expires` 改成 `2027-13-40`、改成 `明年` 后分别校验，各得到一条点名该用例 id 与字段名的错误

#### Scenario: parts-budget-shape-validated
- **GIVEN** 一份部件形态的分层文件：部件 `py` 的 `unit.budget` 为 `{"total_sec": 100}`，它的区域 `api` 的 `budget` 为 `{"case_sec": 60}`
- **WHEN** 读取并校验分层文件
- **THEN** 没有任何形状错误
- **AND** 把区域 `api` 的 `case_sec` 改成 0 后校验，得到一条同时含「部件 py」「区域 api」与 `case_sec` 的错误

#### Scenario: budget-scopes-resolved
- **GIVEN** 一份简写形态的分层文件（单元层没写 `budget`，区域 `hooks` 写了 `case_sec` 30），与一份部件形态的分层文件（部件 `py` 的 `root` 是 `svc/py`，部件 `sh` 的 `root` 是 `svc/sh`，部件 `py` 的 `unit.budget.total_sec` 是 100）
- **WHEN** 分别调用 `tier_budgets` 与 `budget_scope_of`
- **THEN** 简写形态得到范围 `unit`（`case_sec` 为 3、`total_sec` 为 `null`）与 `hooks`（`case_sec` 为 30）
- **AND** 部件形态得到范围 `py/unit`（`total_sec` 为 100）与 `sh/unit`
- **AND** 用例 `svc/py/tests/unit/test_p.py::test_ok`（层 `unit`）映射到 `py/unit`，用例 `sh::sh::TestS`（层 `unit`）映射到 `sh/unit`，层为 `hooks` 的任何用例映射到 `hooks`

### Requirement: 单元层单条上限取预算，放行带上限与期限
单元层的 G10 判定 SHALL 以该层的 `case_sec` 为线（没写时 3 秒），判定方式不变：首跑不低于线的用例是候选，单独重跑仍不低于线（或重跑拿不到）才确认。确认的用例在 `slow_allow` 里有条目时：条目已过期（今天晚于 `expires`）→ 判红，文本含「到期」与该日期；条目带 `limit_sec` 且确认耗时（有重跑取首跑与重跑的较小值，否则取首跑）超过它 → 判红，文本含「放行上限」；其余 → 与现在一样只警告，且距到期不超过 14 天时警告文本带「将于 <日期> 到期」。没有 `limit_sec` 与 `expires` 的旧条目 MUST 与现在一样只警告。部件形态下各部件用自己 `unit.budget.case_sec` 的线。
Feature: 单元层必须一直干净，放行是有边界、有期限的例外
Rule: 放行不是无限放行；到期后回到判红

#### Scenario: unit-case-budget-replaces-default-line
- **GIVEN** 单元层单条上限是 1 秒；用例 `test_mid` 首跑 1.5 秒、单独重跑 1.4 秒
- **WHEN** 判定单元层
- **THEN** 恰有一条以 `G10` 开头的失败，点名该用例，文本含 `≥1s`
- **AND** 同样的耗时在单条上限为缺省值时没有任何 G10 失败

#### Scenario: unit-case-budget-applies-in-baseline
- **GIVEN** 被测仓库的单元层单条上限是 0.1 秒，单元层有一条睡 0.3 秒的纯函数用例
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出码非 0，`reasons` 里有一条以 `G10` 开头，点名该用例，文本含 `≥0.1s`

#### Scenario: allowed-slow-over-limit-is-red
- **GIVEN** 用例 `test_big` 在 `slow_allow` 里，`limit_sec` 是 5；它首跑 6.0 秒、重跑 5.5 秒
- **WHEN** 判定单元层
- **THEN** 有一条以 `G10` 开头的失败，点名该用例，文本含「放行上限」与 `5`
- **AND** 首跑 4.0 秒、重跑 3.9 秒时没有 G10 失败，警告里有一条点名它的放行说明

#### Scenario: expired-allow-is-red-and-soon-is-flagged
- **GIVEN** 用例 `test_big` 首跑 3.4 秒、重跑 3.3 秒，在 `slow_allow` 里
- **WHEN** 分别以 `expires` 早于今天、晚于今天 3 天、晚于今天 60 天判定单元层
- **THEN** 第一种有一条以 `G10` 开头的失败，文本含「到期」与那个日期
- **AND** 第二种没有 G10 失败，放行警告含「将于」与那个日期
- **AND** 第三种没有 G10 失败，放行警告不含「将于」

#### Scenario: part-unit-budget-applies-per-part
- **GIVEN** 部件 `sh` 的单元层单条上限是 1 秒；它的一个用例首跑 1.5 秒、重跑 1.5 秒
- **WHEN** 以该上限判定部件 `sh` 的单元层
- **THEN** 有一条以 `G10` 开头的失败，同时含「部件 sh」与该用例 id
- **AND** 以缺省上限判定时没有 G10 失败

### Requirement: 集成层单条上限按棘轮判
`test-ledger.py` SHALL 提供 `budget(final, base, budgets, scope_of, allow=None, phase="final")`，对写了 `case_sec` 的区域里**本次实测且有耗时**的用例按棘轮判定：耗时超过该用例的线，且用例不在基线账本里 → 记一条以 `G13 slow integration test` 开头的失败，写明用例 id、耗时、区域与线；用例在基线账本里 → 只进警告，并按「基线时已超线」（老债）与「基线时未超线」分开计数。用例的线：有未过期的放行且带 `limit_sec` → 取它；有未过期的放行而没有 `limit_sec` → 不设线；否则取区域的 `case_sec`。沿用的用例、没有耗时的用例、所在区域没写 `case_sec` 的用例 MUST NOT 被判。`phase` 为 `baseline` 时全部超线用例计为老债。`phase` 为 `final` 而基线账本缺失或不完整时 MUST NOT 产生任何 G13 失败，返回值的 `judged` 为假、`why` 写原因，超线用例只进警告。放行名单的键是 nodeid；账本是 junit 形式时 SHALL 把键正向换算后再匹配。
Feature: 集成层历史包袱重，只保证不再变坏
Rule: 新增的超线判红；已有的只报告。单次测量区分不了「真的变慢」与噪声，所以已有用例涨过线不判红

#### Scenario: new-integration-case-over-line-is-red
- **GIVEN** 区域 `hooks` 的单条上限是 30 秒；收口账本里用例 `test_new` 是本次实测、耗时 42.0 秒、层为 `hooks`，基线账本里没有它
- **WHEN** 调用 `budget`
- **THEN** `failed` 恰有一条，以 `G13 slow integration test` 开头，含该用例 id、`42.0` 与 `hooks`
- **AND** 返回值的 `new_n` 为 1，`judged` 为真

#### Scenario: existing-cases-over-line-only-warn
- **GIVEN** 区域 `hooks` 的单条上限是 30 秒；基线账本里 `test_debt` 是 50 秒、`test_drift` 是 20 秒；收口账本里两条都是本次实测，分别为 55 秒与 35 秒
- **WHEN** 调用 `budget`
- **THEN** `failed` 为空
- **AND** `debt_n` 为 1、`cross_n` 为 1
- **AND** `warnings` 里有一条含「老债」并点名 `test_debt`，另有一条含「未判红」并点名 `test_drift`

#### Scenario: unmeasured-and-unbudgeted-cases-not-judged
- **GIVEN** 收口账本里三条不在基线账本的用例都是 90 秒：一条在写了单条上限的区域 `hooks` 里但是沿用的；一条在 `hooks` 里是实测但耗时为 `null`；一条是实测，所在区域 `docs` 没写 `case_sec`
- **WHEN** 调用 `budget`
- **THEN** `failed` 为空，`new_n`、`debt_n`、`cross_n` 都是 0

#### Scenario: allow-entry-moves-integration-case-line
- **GIVEN** 区域 `hooks` 的单条上限是 30 秒；新增用例 `test_big` 实测 74 秒；放行名单里有它
- **WHEN** 分别以「放行未过期、`limit_sec` 为 90」「放行未过期、`limit_sec` 为 60」「放行未过期、没有 `limit_sec`」「放行已过期」调用 `budget`
- **THEN** 第一种与第三种 `failed` 为空，`allowed_n` 为 1
- **AND** 第二种与第四种各有一条 G13 失败；第二种的文本含「放行上限」
- **AND** 账本是 junit 形式（用例 id 为 `tests.integration.hooks.test_h::test_big`）而放行名单的键是 nodeid 时，第一种的结果相同

#### Scenario: missing-baseline-ledger-degrades-to-warning
- **GIVEN** 区域 `hooks` 的单条上限是 30 秒；收口账本里有一条实测 42 秒的用例；基线账本为空
- **WHEN** 以 `phase` 为 `final` 调用 `budget`
- **THEN** `failed` 为空，`judged` 为假，`why` 非空
- **AND** `warnings` 里有一条含「未判」并点名区域 `hooks`
- **AND** 基线账本的 `complete` 为假时结果相同

### Requirement: 层总量预算按账本里逐用例耗时之和判
`budget` SHALL 对每个写了 `total_sec` 的范围，把收口（或基线）账本里属于该范围的全部用例（实测与沿用）的耗时相加：单元层范围超过预算 → 记一条以 `G14 tier budget` 开头的失败，写明范围、合计与预算；区域超过预算 → 只进警告，文本列出该区域耗时最大的至多 3 条用例与本 change 新增用例的耗时之和（没有基线账本时不写新增）。账本的 `complete` 为假，或该范围里没有耗时的用例超过一成时 MUST NOT 判，只进一条含「未判」的警告。返回值的 `totals` SHALL 按范围给出用例数、耗时合计、无耗时条数、预算与是否超预算（未判为 `null`）。
Feature: 每次门禁都要付的固定成本有上限
Rule: 合计取整层，不取本次墙钟；数字不全就不判

#### Scenario: unit-total-over-budget-is-red
- **GIVEN** 单元层总量预算是 10 秒；账本里单元层 30 条用例各 0.5 秒（其中 20 条是沿用的）
- **WHEN** 调用 `budget`
- **THEN** `failed` 恰有一条，以 `G14 tier budget` 开头，含 `15.0` 与 `10`
- **AND** `totals` 里 `unit` 的 `sec` 为 15.0、`over` 为真
- **AND** 预算改成 20 秒时 `failed` 为空、`over` 为假

#### Scenario: region-total-over-budget-only-warns
- **GIVEN** 区域 `hooks` 的总量预算是 100 秒；收口账本里它有 4 条用例共 130 秒，其中一条 12 秒的不在基线账本里
- **WHEN** 调用 `budget`
- **THEN** `failed` 为空
- **AND** `warnings` 里有一条以 `G14` 开头，含 `hooks`、`130.0`、`100` 与「新增 12.0s」，并点名耗时最大的那条用例
- **AND** `totals` 里 `hooks` 的 `over` 为真、`added_sec` 为 12.0

#### Scenario: total-not-judged-when-seconds-missing
- **GIVEN** 单元层总量预算是 1 秒；账本里单元层 10 条用例，其中 2 条耗时为 `null`，其余合计 5 秒
- **WHEN** 调用 `budget`
- **THEN** `failed` 为空，`totals` 里 `unit` 的 `over` 为 `null`
- **AND** `warnings` 里有一条以 `G14` 开头、含「未判」
- **AND** 10 条都有耗时而账本的 `complete` 为假时结果相同

### Requirement: 预算结论进「测试变更」，预算与放行的改动可见
`render` SHALL 在对账结果带 `budget` 时于「## 测试变更」里追加预算段：新增超线的用例、老债条数、基线时未超线而本次超线的条数、各范围的合计对预算、放行名单里已过期与 14 天内到期的条目、预算变更；对账结果不带 `budget` 时输出 MUST 与现在逐字相同。`test-ledger.py` SHALL 提供 `budget_changes(old_budgets, new_budgets, old_allow, new_allow)`，逐项比较两版预算与放行名单，返回文本行：预算数值变化（标「放宽」或「收紧」）、放行条目的新增、移除、`limit_sec` 或 `expires` 的变化；理由与人类原话的变化不算。对账 SHALL 不再对层为区域的用例计「变慢」，「某层耗时上涨」的建议行也不再对区域给出（数据依据见 design D8）。
Feature: 改判据的动作要让评审的人看得见
Rule: 报告由脚本生成，不经模型

#### Scenario: render-lists-budget-section
- **GIVEN** 一份对账结果，`budget` 里有 1 条新增超线、老债 2 条、区域 `hooks` 合计 130 秒对预算 100 秒、1 条已过期的放行、一行预算变更
- **WHEN** 调用 `render`
- **THEN** 输出里各有一行含「新增超线」与该用例 id、含「老债 2 条」、含 `hooks` 与 `130.0s / 100s`、含「已过期」与该放行的用例 id、含「预算变更」
- **AND** 去掉 `budget` 后的输出不含上述任何一行，且与只调用原有逻辑时逐字相同

#### Scenario: budget-changes-are-listed
- **GIVEN** 旧预算里 `unit` 的 `case_sec` 是 3、区域 `hooks` 的 `total_sec` 是 300；新预算里分别是 10 与未设；放行名单新增一条带 `limit_sec` 90 的条目，另一条的 `limit_sec` 从 60 改成 90、理由文字也改了
- **WHEN** 调用 `budget_changes`
- **THEN** 返回的行里有一行含 `unit`、`3s → 10s` 与「放宽」，一行含 `hooks`、`300s` 与「放宽」
- **AND** 有一行含「放行新增」与新条目的用例 id，一行含「放行改动」、`60s → 90s`
- **AND** 两版完全相同、或只有理由文字不同时返回空列表

#### Scenario: noisy-delta-items-skip-region-cases
- **GIVEN** 基线账本与收口账本各有两条实测用例：单元层的从 1.0 秒到 3.0 秒，区域 `hooks` 的从 10 秒到 40 秒
- **WHEN** 对账
- **THEN** `slower_n` 为 1，`slower` 里只有单元层那一条
- **AND** 建议行里没有以 `hooks 层耗时` 开头的行

### Requirement: baseline 与 final 按预算判定并在争抢下降级
分层文件里任一范围写了 `budget` 时，`slice-gate.py baseline` 与 `final` SHALL 在落账之后调用预算判定：`G13` / `G14` 的失败并入 final 的 `failed`（baseline 并入 `reasons`），警告并入 `warnings`；final 输出 JSON 的 `tests` 多一个 `budget`（判定摘要），`delta.json` 同样带上它。锁状态为 `timeout` 的那次运行 MUST 把以 `G13 slow integration test`、`G14 tier budget` 开头的失败与 G10 一样降为警告（原文保留并注明原因）；`off` 与 `unavailable` 照常判。final SHALL 把当前分层文件的预算、放行名单与基线 commit 上的版本比较，有变动时在 `warnings` 里加一条以「预算变更」开头的说明，并把各行放进 `tests.budget.changes`。账本模块不可用、预算判定抛错时 MUST NOT 改变 baseline / final 的结论，只在 `warnings` 里留一条以「预算未判」开头的说明。部件形态下单元层合计 SHALL 按部件分别判（范围 `<部件>/unit`），G14 的文本写明部件名。没有任何范围写 `budget` 时，baseline 与 final 的输出 MUST 没有 `budget`，也没有任何 G13 / G14 文本。
Feature: 预算是门禁的一部分，不是事后体检
Rule: 判定依赖账本；账本出问题时退回到没有预算的行为

#### Scenario: final-red-on-new-slow-integration-case
- **GIVEN** 被测仓库的区域 `hooks` 单条上限是 0.4 秒，基线已跑且通过；之后提交了一个新的区域测试文件，里面一条用例睡 1 秒
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出码为 1，`failed` 里有一条以 `G13 slow integration test` 开头并点名该用例
- **AND** 输出 JSON 的 `tests.budget.new_n` 为 1

#### Scenario: debt-keeps-baseline-and-final-green
- **GIVEN** 被测仓库的区域 `hooks` 单条上限是 0.4 秒，区域里已有一条睡 1 秒的用例
- **WHEN** 运行 baseline；提交该区域另一个测试文件的改动（让 final 重跑这个区域）后运行 final
- **THEN** 两次的退出码都是 0
- **AND** baseline 的 `warnings` 与 final 的 `warnings` 各有一条含「老债」
- **AND** final 的 `tests.budget.debt_n` 为 1、`new_n` 为 0

#### Scenario: baseline-red-on-unit-total-over-budget
- **GIVEN** 被测仓库的单元层总量预算是 0.05 秒，单元层有一条睡 0.3 秒的纯函数用例
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出码非 0，`reasons` 里有一条以 `G14 tier budget` 开头
- **AND** 把预算改成 60 秒后重跑，退出码为 0

#### Scenario: contended-run-downgrades-budget-verdicts
- **GIVEN** 被测仓库的单元层总量预算是 0.05 秒，单元层有一条睡 0.3 秒的用例；另一个进程持有独占锁且已超过它的持有上限
- **WHEN** 以同一锁目录运行 baseline
- **THEN** 退出码为 0，`lock.state` 是 `timeout`
- **AND** `reasons` 里没有 G14；`warnings` 里有一条同时含 `G14` 与「降为警告」

#### Scenario: budget-failure-does-not-fail-gate
- **GIVEN** 一份不含 `test-ledger.py` 的 hooks 目录副本；被测仓库的区域 `hooks` 单条上限是 0.4 秒，基线已用这份副本跑过，之后提交了一条睡 1 秒的新区域用例
- **WHEN** 用这份副本里的 `slice-gate.py` 运行 final
- **THEN** 退出码为 0，`failed` 为空
- **AND** `warnings` 里有一条以「预算未判」开头

#### Scenario: final-reports-budget-changes
- **GIVEN** 被测仓库的区域 `hooks` 单条上限是 30 秒，基线已跑；之后把它改成 300 秒并提交
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `warnings` 里有一条以「预算变更」开头，含 `hooks`、`30s → 300s` 与「放宽」
- **AND** `tests.budget.changes` 非空

#### Scenario: parts-unit-total-judged-per-part
- **GIVEN** 部件形态的被测仓库：部件 `py` 的单元层总量预算是 0.05 秒（它有一条睡 0.3 秒的纯函数用例），部件 `sh` 没写预算
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出码非 0，`reasons` 里有一条以 `G14 tier budget` 开头并含「部件 py」
- **AND** `reasons` 里没有提到部件 `sh` 的 G14

#### Scenario: no-budget-keeps-output-unchanged
- **GIVEN** 被测仓库有分层文件但没有任何 `budget`，区域 `hooks` 里有一条睡 1 秒的用例
- **WHEN** 运行 baseline；提交该区域一个测试文件的改动后运行 final
- **THEN** 两次的退出码都是 0
- **AND** `gate-baseline.json` 的 `ledger` 没有 `budget`，final 的 `tests` 没有 `budget`
- **AND** 两次的 `warnings` 与 `failed` 里都没有含 `G13` 或 `G14` 的文本

### Requirement: 只重跑区域的增量 final 不丢其余用例
有分层文件时，内建增量 final 若没有任何单元层文件需要重跑、只重跑了区域，本次写出的锚点的逐用例结局 SHALL 仍包含没重跑文件的旧结局（区域文件的换成本次结果），收口账本里这些用例 SHALL 记为沿用并带着沿用的耗时。
Feature: 层总量要按整层算，整层的用例一条都不能少
Rule: 没有重跑不等于没有结论

#### Scenario: region-only-rerun-keeps-unit-cases
- **GIVEN** 被测仓库有分层文件，基线已跑；之后只提交了区域 `hooks` 的一个新测试文件
- **WHEN** 运行 `slice-gate.py final`（增量，只重跑该区域）
- **THEN** 退出码为 0，收口账本里单元层用例仍在，`m` 为 0
- **AND** 本次写出的锚点的 `nodes` 含该单元层用例
- **AND** 输出 JSON 的 `tests.delta.unknown` 为 0

### Requirement: 放行命令可写上限与期限
`test-tiers.py allow-slow` SHALL 接受可选的 `--limit-sec N`（大于 0 的数）与 `--expires YYYY-MM-DD`（真实日期，且不早于今天），人类放行证据的判据不变；成立时把它们与 `reason`、`approved` 一起写进该条目。参数不合法时 MUST 以退出码 2 结束且不改分层文件。两个参数都没给时照常写入，并在 stderr 打印一行含 `--limit-sec` 与 `--expires` 的提示。
Feature: 放行时就把边界说清楚
Rule: 放行仍然只认人类原话；上限与期限是放行的一部分

#### Scenario: allow-slow-writes-limit-and-expires
- **GIVEN** 分层文件的 `slow_allow` 为空；转录里最新一条人类消息是「放行 test_big，读 40MB 真实样本」
- **WHEN** 运行 `test-tiers.py allow-slow <nodeid> --reason 读大样本 --limit-sec 90 --expires <今天之后 30 天>`
- **THEN** 退出码为 0，该条目的 `limit_sec` 为 90、`expires` 为所给日期，`reason` 与 `approved` 照常写入
- **AND** 写完的分层文件通过 `test-tiers.py check`
- **AND** 不带这两个参数再放行另一条用例时退出码为 0，stderr 有一行同时含 `--limit-sec` 与 `--expires`

#### Scenario: allow-slow-rejects-bad-limit-or-date
- **GIVEN** 同样的分层文件与转录
- **WHEN** 分别以 `--limit-sec 0`、`--expires 2027-13-40`、`--expires 2000-01-01` 运行 `allow-slow`
- **THEN** 三次的退出码都是 2，stderr 依次说明「须大于 0」「不是真实日期」「早于今天」
- **AND** 分层文件内容不变

### Requirement: 体检列出预算与放行
`flight-doctor.py doctor` 的 `[tests]` SHALL 在 openspec 根的分层文件写了预算或放行名单非空时追加：每个有预算的范围一行（单条上限、账本里的合计对总量预算、超预算时标出）、写了单条上限的区域里超线的用例条数与最慢的一条、放行名单一行（总数、已过期的条数与用例 id、14 天内到期的条数、没有上限的条数）。没有分层文件、或既没有预算也没有放行时 `[tests]` 的输出 MUST 与现在相同。`doctor` 恒以 0 退出的约定不变。
Feature: 随时能看一眼哪些预算快守不住、哪些放行该重新看
Rule: 体检只读，不阻断

#### Scenario: doctor-tests-lists-budgets
- **GIVEN** openspec 根的分层文件里单元层总量预算是 2 秒、区域 `hooks` 单条上限是 5 秒；在途 change `c` 的收口账本里单元层 12 条共 3.0 秒，区域 `hooks` 有一条 9.0 秒的用例
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** 退出码为 0；`[tests]` 里有一行同时含 `unit`、`3.0s / 2s` 与「超预算」
- **AND** 有一行同时含 `hooks`、「超线 1 条」与那条用例的 id

#### Scenario: doctor-tests-names-allow-entries
- **GIVEN** openspec 根的分层文件的放行名单有三条：一条 `expires` 是 `2000-01-01`，一条 `expires` 是今天之后 3 天，一条没有 `limit_sec` 也没有 `expires`
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** `[tests]` 里有一行以「放行」开头的说明，含「共 3 条」「已过期 1 条」与已过期那条的用例 id、「14 天内到期 1 条」「无上限 1 条」
- **AND** 分层文件没有预算也没有放行条目时，`[tests]` 里没有含「预算」或「放行」的行

### Requirement: 部件形态的区域进账本
部件形态下，baseline 与 final 运行已选区域之后 SHALL 把该区域 junit 报告里的逐用例耗时上报进观测表（用例 id 按部件 junit 的现行规则换成顶层 id，层为区域名），使区域用例出现在账本里；拿不到 junit 时不上报，门禁照常。此后部件区域的 G13 / G14 与简写形态相同。
Feature: 多语言仓库的集成层同样有预算
Rule: 只补挡着预算判定的缺口；适配器部件的结局仍然未知

#### Scenario: parts-region-run-is-observed
- **GIVEN** 部件形态的被测仓库：部件 `py` 有区域 `api`（pytest，在部件 `root` 下运行），本 change 选了它
- **WHEN** 依次运行 baseline 与 final
- **THEN** 基线账本与收口账本里都有层为 `api` 的用例，带耗时、`m` 为 1
- **AND** 两次的退出码都是 0

#### Scenario: parts-region-new-slow-case-is-red
- **GIVEN** 同样的被测仓库，区域 `api` 的单条上限是 0.4 秒，基线已跑且通过；之后提交了一条睡 1 秒的新区域用例
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出码为 1，`failed` 里有一条以 `G13 slow integration test` 开头，含 `api` 与该用例名

### Requirement: 全机测试锁的持有上限取全量耗时
baseline、final 与切片门禁取锁时声明的预计耗时 SHALL 取最近一次已知的全量耗时：基线记录的 `full_suite_sec`、计划里旧的 `gate.full_suite_sec`、以及基线不是增量时的 `test.sec` 三者里的最大值；三者都没有时不声明（持有上限用缺省值 1800 秒）。增量基线的 `test.sec`（只是补跑的秒数）MUST NOT 被当作预计耗时。
Feature: 持锁的人说自己最多跑多久，要按整套的量说
Rule: 上限说短了，后到的飞行会把正常排队当成停滞而并跑

#### Scenario: lock-cap-uses-full-suite-seconds
- **GIVEN** 三份基线记录：增量、`test.sec` 为 25、`full_suite_sec` 为 400；增量、`test.sec` 为 25、没有 `full_suite_sec`；全量、`test.sec` 为 300、`full_suite_sec` 为 300
- **WHEN** 分别计算取锁时声明的预计耗时
- **THEN** 依次得到 400、不声明、300
- **AND** 第二种情形下计划里写着 `gate.full_suite_sec` 为 600 时得到 600

### Requirement: 文档说明时间预算与放行期限
`template/.claude/flight-runner-contract.md` SHALL 新增第 10 节「时间预算与放行」，写明：`budget` 的两个字段与各层的处置（单元层判红、区域新增判红、已有只警告、区域总量只警告）、`slow_allow` 的 `limit_sec` 与 `expires`、判定依赖测试账本且账本不可用时不判、排队放弃的那次降为警告、预算变更会进 PR 正文、总量预算留余量的建议；原有第 1–9 节的标题 MUST 保留，第 8 节关于放弃等待的那句 SHALL 把 G13 / G14 与 G10 并列。`template/.claude/commands/test-tiers.md` SHALL 在分层文件形状处写出 `budget`，在「放行慢单测」一节写出 `--limit-sec` 与 `--expires`。`README.md` SHALL 有一行同时含 `budget` 与 `limit_sec`。
Feature: 仓库的人知道怎么写预算、怎么放行
Rule: 命令文档与契约文档同步

#### Scenario: docs-describe-budgets-and-allow-fields
- **GIVEN** 模板仓库的文档
- **WHEN** 读契约文档的二级标题与第 10 节正文、`commands/test-tiers.md`、`README.md`
- **THEN** 契约文档有以 `## 10.` 开头且含「时间预算」的标题，原有 `## 1.` 至 `## 9.` 的标题都在
- **AND** 第 10 节正文含 `case_sec`、`total_sec`、`limit_sec`、`expires`、`G13`、`G14`、「老债」、「预算变更」
- **AND** 第 8 节有一行同时含 `G10`、`G13` 与 `G14`
- **AND** `commands/test-tiers.md` 含 `"budget"`、`--limit-sec` 与 `--expires`；`README.md` 有一行同时含 `budget` 与 `limit_sec`
