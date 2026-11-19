## ADDED Requirements

### Requirement: 账本里的超线用例清单
`test-ledger.py` SHALL 提供纯函数 `violations(ledger, budgets, scope_of, allow=None)`，返回账本里全部超线用例的清单，每条为 `{"case": 用例 id, "scope": 范围, "kind": "unit" | "region", "sec": 秒, "line": 线, "by": "budget" | "allow"}`，按耗时由大到小、再按用例 id 排序。判定对象是账本里有耗时（`s` 不为 `null`）、所在范围在 `budgets` 里的每一条用例，实测（`m=1`）与沿用（`m=0`）都判。线的取法 MUST 与 `budget()` 相同：用例有未过期的放行 → 线取放行的 `limit`，`by` 为 `allow`，`limit` 为空则该用例不设线；否则线取范围的 `case_sec`，`by` 为 `budget`，`case_sec` 为空则不判。超线的含义：单元层范围在没有有效放行时为「耗时不小于线」（与 G10 相同），其余情形为「耗时大于线」。账本 `id_form` 为 `junit` 时 `allow` 的键 SHALL 按 `budget()` 的同一规则换算后匹配。`budget()` 的返回与文本 MUST 保持不变。函数不读文件、不取时间。
Feature: 体检要的是全部不合规用例，不是门禁那几条明细
Rule: 线的取法只有一处，体检与门禁读同一个结论

#### Scenario: violations-list-every-over-line-case
- **GIVEN** 预算：单元层单条 3 秒，区域 `hooks` 单条 30 秒；账本里单元层有一条沿用的 3.0 秒用例与一条 0.2 秒用例，`hooks` 有一条实测 42.0 秒、一条恰好 30.0 秒的用例
- **WHEN** 调用 `violations`
- **THEN** 返回两条：先是 `hooks` 的 42.0 秒（`kind` 为 `region`、`line` 为 30），再是单元层的 3.0 秒（`kind` 为 `unit`、`line` 为 3）
- **AND** 0.2 秒与恰好 30.0 秒的两条不在清单里
- **AND** 两条的 `by` 都是 `budget`

#### Scenario: violations-honor-allow-limit-and-expiry
- **GIVEN** 区域 `hooks` 单条 30 秒；四条 74.0 秒的用例分别带：上限 90 秒的放行、上限 60 秒的放行、没有上限的放行、已过期的放行
- **WHEN** 调用 `violations`
- **THEN** 清单里恰有两条：上限 60 秒的那条（`line` 为 60、`by` 为 `allow`）与放行已过期的那条（`line` 为 30、`by` 为 `budget`）

#### Scenario: violations-skip-unjudgeable-cases
- **GIVEN** 账本里有一条没有耗时的用例、一条所在层不在预算里的用例、一条在没写 `case_sec` 的区域 `docs` 里耗时 500 秒的用例
- **WHEN** 调用 `violations`
- **THEN** 返回空清单

#### Scenario: violations-match-junit-form-ledger
- **GIVEN** 账本 `id_form` 为 `junit`，用例 `tests.integration.hooks.test_h::test_big` 耗时 74.0 秒；放行名单的键是 nodeid 形式的 `tests/integration/hooks/test_h.py::test_big`，上限 90 秒
- **WHEN** 调用 `violations`
- **THEN** 返回空清单
- **AND** 把放行的上限改成 60 秒后返回一条，`case` 为 junit 形式的 id，`line` 为 60

### Requirement: 体检的数据来源与归层
`test-tiers.py audit` SHALL 只读地体检当前工作树：读 openspec 根的分层文件、git 跟踪与未忽略的测试文件、一份测量（测试账本与探针结果），不运行任何测试、不改任何文件（`--out` 指定的输出文件除外）。账本的选取：`--ledger PATH` 指定的文件 > `--change-dir DIR` 对应 change 的收口账本（没有则基线账本）> 本机 `<git common dir>/flight-ledger/` 下 `at` 最新的一份；`--no-ledger` 时不读账本。`--probe PATH`（可重复）读 `test-tiers.py probe --json` 的结果，其中的用例覆盖账本里同一用例的耗时并带上触碰记录；账本是 `junit` 形式时探针用例 SHALL 按同一换算规则并入。用例的层 SHALL 按当前分层文件由用例所在文件重新归层；定不出文件的用例保留账本里记的层；所在文件已不存在的用例 SHALL 丢弃并计入 `source.dropped`。分层文件不存在时 SHALL 只报一条 `no-tiers` 并说明先跑 `/test-tiers`；分层文件不合法、`--ledger` / `--probe` / `--change-dir` 读不了时 SHALL 以退出码 2 结束并说明原因。简写形态与部件形态 SHALL 都可用：部件形态的文件归属沿用 `check` 的判据，单元层范围名为 `<部件>/unit`。
Feature: 随时能问一句「现在哪些用例不合规」
Rule: 体检不跑测试，读最近一次测量；测量与工作树对不上的部分如实丢弃

#### Scenario: audit-without-tiers-file-points-to-test-tiers
- **GIVEN** 被测仓库没有 `openspec/test-tiers.json`，也没有账本
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 退出码为 1，`form` 为 `none`，`verdict` 为 `violations`
- **AND** `items` 恰有一条，`category` 为 `no-tiers`，`text` 提到 `/test-tiers`

#### Scenario: audit-lists-over-line-cases-from-ledger
- **GIVEN** 分层文件：单元层 `tests/unit/**`，区域 `hooks`（`tests/integration/hooks/**`）单条上限 5 秒；本机 change `c` 的收口账本里单元层有一条 4.0 秒的用例，`hooks` 有一条 9.0 秒的用例，其余都在线内，这些用例的文件都在
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 退出码为 1，`items` 里有 `unit-slow:<该单元用例>`（`sec` 4.0、`line` 3、`rule` 为 `R4`）与 `region-slow:<该区域用例>`（`sec` 9.0、`line` 5、`scope` 为 `hooks`、`rule` 为 `R6`）
- **AND** `source.ledger.change` 为 `c`，`source.ledger.phase` 为 `final`
- **AND** `scopes.unit` 与 `scopes.hooks` 各自给出用例数、合计秒数与 `p50` / `p95` / `max`

#### Scenario: audit-recomputes-layer-and-drops-missing-files
- **GIVEN** 账本里一条 4.0 秒的用例记的层是 `unit`，但按当前分层文件它所在的文件落在区域 `hooks`（单条上限 5 秒）；另一条 8.0 秒用例所在的文件已不存在
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 没有任何 `unit-slow` 与 `region-slow` 条目
- **AND** `source.dropped` 为 1

#### Scenario: audit-works-for-parts-form
- **GIVEN** 部件形态的分层文件：部件 `py`（`root` 为 `svc/py`，单元层 `svc/py/tests/unit/**`）；账本里 `svc/py/tests/unit/test_p.py::test_slow` 耗时 4.0 秒；另有一个不属于任何部件的测试文件 `misc/test_loose.py`
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 退出码为 1，`form` 为 `parts`
- **AND** `items` 里有 `unit-slow:svc/py/tests/unit/test_p.py::test_slow`，`scope` 为 `py/unit`
- **AND** `items` 里有 `layering:misc/test_loose.py`，`text` 含「不属于任何部件」

### Requirement: 体检的不合规类别
`test-tiers.py audit` SHALL 按下列类别列出不合规项（`level` 为 `violation`），每条带稳定的 `id`（`<类别>:<键>`）、`category`、`rule`、`scope`（没有则为 `null`）、`text` 与可选的去向 `fix`；类别、规则号、级别与可选去向 SHALL 以模块常量 `AUDIT_RULES` 为单一出处：

| 类别 | 规则 | 判据 | 键 | 可选去向 |
|---|---|---|---|---|
| `no-tiers` | R1 | 没有分层文件 | 空 | 无（先跑 `/test-tiers`） |
| `layering` | R2 | 测试文件未归层、匹配多层、不属于任何部件或属于多个部件（与 `check` 同一判据） | 文件路径 | `move` / `retier` |
| `unit-impure` | R3 | 探针记录里单元层用例有触碰 | 用例 id | `purify` / `move` / `split` |
| `unit-slow` | R4 | 单元层用例超线（`violations` 的结论） | 用例 id | `speedup` / `move` / `allow` |
| `no-case-limit` | R5 | 集成区域没写 `budget.case_sec` | 区域名 | `budget` |
| `region-slow` | R6 | 集成区域用例超线（`violations` 的结论） | 用例 id | `speedup` / `allow` / `delete` |
| `total-over` | R7 | 写了 `total_sec` 的范围合计超预算（单元层与区域都算不合规） | 范围名 | `speedup` / `delete` / `budget` |
| `allow-stale` | R8 | 放行条目的键指向的测试文件已不存在 | 放行的键 | `drop-allow` |
| `allow-expired` | R8 | 放行已过期 | 放行的键 | `allow` / `speedup` / `move` / `drop-allow` |
| `allow-unbounded` | R8 | 未过期的放行缺 `limit_sec` 或缺 `expires` | 放行的键 | `allow` / `drop-allow` |

一条放行只归入上面最靠前的一个放行类别。总量的判定沿用 `budget()` 的结论与它的「未判」条件。
Feature: 不合规项按类别点名，每类都有明确的出路
Rule: 判据都是机械的；集成层的老债在体检里就是不合规，不因门禁只警告而隐身

#### Scenario: audit-flags-layering-problems
- **GIVEN** 单元层 `tests/unit/**`，区域 `hooks` 的 `paths` 含 `tests/integration/**` 与 `tests/unit/test_both.py`；仓库里有 `tests/unit/test_both.py` 与 `tests/test_loose.py`
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 退出码为 1，`items` 里有 `layering:tests/test_loose.py`（`text` 含「未归层」）与 `layering:tests/unit/test_both.py`（`text` 含「匹配多层」），`rule` 都是 `R2`

#### Scenario: audit-flags-region-without-case-limit
- **GIVEN** 区域 `hooks` 写了单条上限，区域 `docs` 没写 `budget`
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** `items` 里有 `no-case-limit:docs`（`rule` 为 `R5`、`fix` 为 `["budget"]`），没有 `no-case-limit:hooks`

#### Scenario: audit-flags-total-over-budget
- **GIVEN** 单元层总量预算 2 秒、账本里单元层合计 3.0 秒；区域 `hooks` 总量预算 5 秒、账本里合计 9.0 秒
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** `items` 里有 `total-over:unit` 与 `total-over:hooks`，`level` 都是 `violation`，`text` 各自写出合计与预算

#### Scenario: audit-flags-allow-entries
- **GIVEN** 放行名单五条：已过期的；没有上限也没有期限的；所指测试文件已不存在的；3 天后到期、带上限的；远期到期、带上限的
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** `items` 里有 `allow-expired:<键>`、`allow-unbounded:<键>`、`allow-stale:<键>`，`level` 都是 `violation`
- **AND** 3 天后到期的那条只有 `allow-soon:<键>`，`level` 为 `advice`
- **AND** 远期到期的那条没有任何条目

#### Scenario: audit-probe-flags-impure-unit-cases
- **GIVEN** 一份探针结果：单元层用例 `test_spawns` 有「子进程」触碰；区域 `hooks` 的文件里两条用例中有一条无触碰且耗时 0.1 秒
- **WHEN** 分别带 `--probe` 与不带地运行 `test-tiers.py audit --json --no-ledger`
- **THEN** 带探针时 `items` 里有 `unit-impure:<该用例>`（`rule` 为 `R3`、`text` 含「子进程」）与 `pure-in-region:<该文件>`（`level` 为 `advice`）
- **AND** 不带探针时没有这两条，而有一条 `purity-unchecked`（`level` 为 `advice`）

### Requirement: 体检的提示、未判与结论
`test-tiers.py audit` SHALL 把不构成不合规的发现记为提示（`level` 为 `advice`）：`allow-soon`（放行 14 天内到期）、`allow-unneeded`（有测量且耗时已回到线内的有效放行）、`pure-in-region`（探针显示区域文件里有无触碰且低于单元层线的用例）、`purity-unchecked`（没有探针结果，纯度未在体检里核对）、`gwt-missing`（Python 用例缺 Given / When / Then 注释的条数，只计数）。判不了的范围 SHALL 记为未判（`level` 为 `unjudged`）：`unjudged:no-measure`（既没有账本也没有探针）、`unjudged:ledger`（来源账本不完整或来自 `gate.impacted` 的选测）、`unjudged:scope:<范围>`（该范围有测试文件没有任何测量，或无耗时的用例超过一成）；未判的范围不出 `total-over`，已量到的单条超线照常列出。范围里有定不出文件的用例时 SHALL 不做「测试文件没有测量」这一项判断。结论 `verdict`：有不合规项为 `violations`；否则有未判项为 `unjudged`；否则为 `compliant`。退出码：0 合规，1 有不合规项，3 没有不合规项但有未判项，2 输入不可用。
Feature: 判不了就说判不了，不把「没量到」当成「合规」
Rule: 提示不影响结论；未判单独一档

#### Scenario: audit-unjudged-when-no-measurement
- **GIVEN** 分层文件合法、每个测试文件恰属一层、区域都写了单条上限；本机没有账本
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 退出码为 3，`verdict` 为 `unjudged`，`items` 里有 `unjudged:no-measure`

#### Scenario: audit-unjudged-scope-with-unmeasured-files
- **GIVEN** 区域 `hooks` 写了总量预算；账本覆盖了单元层全部测试文件，但 `hooks` 的两个测试文件里只有一个有测量
- **WHEN** 运行 `test-tiers.py audit --json`
- **THEN** 退出码为 3，`items` 里有 `unjudged:scope:hooks`，`text` 点名没有测量的那个文件
- **AND** 没有 `total-over:hooks`，也没有 `unjudged:scope:unit`

#### Scenario: audit-compliant-exits-zero
- **GIVEN** 分层、预算、放行都合规，账本覆盖全部测试文件且都在线内；有一条 3 天后到期的放行、一条耗时已回到线内的放行，测试文件里有两条用例没写 Given / When / Then 注释
- **WHEN** 运行 `test-tiers.py audit`（不带 `--json`）与 `test-tiers.py audit --json`
- **THEN** 两次退出码都是 0；文本输出首行以「测试体检」开头，并有一行「结论：合规」
- **AND** JSON 的 `verdict` 为 `compliant`，`counts.violation` 为 0
- **AND** `items` 里有 `allow-soon`、`allow-unneeded`、`purity-unchecked`，以及 `gwt-missing`（`count` 为 2），`level` 都是 `advice`

### Requirement: 体检的输出与筛选
`test-tiers.py audit` 缺省打印文本（首行 `测试体检：不合规 N 条 · 提示 N 条 · 未判 N 项`，一行测量来源，各类别明细，各范围一行，末行 `结论：合规` / `结论：不合规` / `结论：判不全`）；`--json` 时 stdout SHALL 只有一个 JSON 对象：`{v, at, head, form, verdict, source: {ledger, probes, cases, dropped}, counts: {violation, advice, unjudged, by_category}, items, scopes, allow}`。`--out PATH` SHALL 把同一个 JSON 对象写进文件。`--scope <范围>`（可重复）只保留该范围的条目与 `scopes` 行，但没有分层文件（`no-tiers`）与全局未判（没有测量、来源账本不可判）对每个范围都成立，不受 `--scope` 影响；`--category <类别>`（可重复）只保留该类别，但未判条目（全局与各范围）与没有分层文件不受 `--category` 影响；`--top N` 让每个类别至多列出耗时最大的 N 条。`counts` SHALL 是 `--top` 截断之前的条数；`verdict` 与退出码按 `--scope` / `--category` 筛选之后、`--top` 截断之前的条目算。
Feature: 大仓库分批整：按层、按类别、按最慢 N 条取子集
Rule: 截断只影响明细，不影响计数与结论

#### Scenario: audit-filters-by-scope-category-top
- **GIVEN** 区域 `hooks` 有两条超线用例（9.0 秒与 7.0 秒），单元层有一条超线用例
- **WHEN** 运行 `test-tiers.py audit --json --category region-slow --top 1 --out <文件>`，再运行 `test-tiers.py audit --json --scope unit`
- **THEN** 第一次的 `items` 恰有一条，是 9.0 秒的那条；`counts.by_category["region-slow"]` 为 2；`<文件>` 的内容与 stdout 的 JSON 相同
- **AND** 第二次的 `items` 里没有任何 `scope` 为 `hooks` 的条目，`scopes` 只有 `unit`
- **AND** 两次退出码都是 1

### Requirement: 体检前后对比
`test-tiers.py audit --compare <之前的体检 JSON>` SHALL 以不合规项的 `id` 比较前后两次体检：之前有、现在没有 → 已解决；两边都有 → 仍在；现在有、之前没有 → 新增；结果放进 JSON 的 `compare = {before: {at, head}, resolved, remaining, new, targets, targets_remaining}`，文本输出一行 `前后对比：已解决 N 条 · 仍在 N 条 · 新增 N 条`。`--plan <整改稿>` SHALL 把稿里去向不是 `keep`、且出现在之前那份体检里的条目当作本轮目标：目标仍在不合规项里即 `targets_remaining`。带 `--compare` 时退出码改为：有新增或有目标未解决为 1；否则现在这次有未判项为 3（文本写明「未能确认」）；否则为 0——不在目标里的旧不合规项仍在不算失败。之前的体检文件读不了、不是体检 JSON，或给了 `--plan` 却没给 `--compare` → 退出码 2。
Feature: 整改之后复核：目标解决了没有，有没有改出新的不合规
Rule: 分批整改时，没排进本轮的老债不挡复核

#### Scenario: compare-reports-resolved-remaining-new
- **GIVEN** 之前的体检 JSON 里有不合规项 `region-slow:A` 与 `region-slow:B`；现在的仓库里 A 已不超线，B 仍超线，另有新的超线用例 C
- **WHEN** 运行 `test-tiers.py audit --json --compare <之前的 JSON>`
- **THEN** `compare.resolved` 为 `["region-slow:A"]`，`compare.remaining` 为 `["region-slow:B"]`，`compare.new` 为 `["region-slow:C"]`
- **AND** 退出码为 1

#### Scenario: compare-exits-zero-when-targets-resolved
- **GIVEN** 之前的体检有 A 与 B 两条不合规；整改稿只把 A 排进本轮（B 标 `keep`）；现在 A 已解决、B 仍在，没有新增，也没有未判项
- **WHEN** 运行 `test-tiers.py audit --compare <之前的 JSON> --plan <整改稿>`
- **THEN** 退出码为 0，文本输出有一行以「前后对比：已解决 1 条 · 仍在 1 条 · 新增 0 条」开头

#### Scenario: compare-fails-when-target-remains
- **GIVEN** 整改稿把 A 与 B 都排进本轮；现在 A 已解决、B 仍在
- **WHEN** 运行 `test-tiers.py audit --json --compare <之前的 JSON> --plan <整改稿>`
- **THEN** 退出码为 1，`compare.targets` 为 2，`compare.targets_remaining` 为 `["region-slow:B"]`

#### Scenario: compare-unconfirmed-when-unjudged
- **GIVEN** 整改稿的目标都已不在不合规项里、没有新增；但现在这次体检有一个范围未判（测试文件没有测量）
- **WHEN** 运行 `test-tiers.py audit --compare <之前的 JSON> --plan <整改稿>`，再用一个不是 JSON 的文件当 `--compare` 运行一次
- **THEN** 第一次退出码为 3，文本输出含「未能确认」
- **AND** 第二次退出码为 2

### Requirement: 整改稿审批页
`test-audit.py render --audit <体检 JSON> --plan <整改稿> --out <HTML>` SHALL 校验整改稿并写出单文件审批页。整改稿形如 `{"items": {<条目 id>: {"action", "dest", "note"}}, "tiers": <拟写入的分层文件，可选>, "support": [<随迁文件 glob，可选>]}`。去向与轨道以模块常量 `ACTIONS` 为单一出处：`move` / `split` / `retier` / `budget` / `drop-allow` 为命令内执行（`mechanical`），`allow` 为交人放行（`human`），`speedup` / `purify` / `delete` 为转 change（`change`），`keep` 为保留。校验 SHALL 逐条点名问题：条目 id 不在体检结果里；去向不在该条目的 `fix` 里（`keep` 恒可用）；`keep` 没写 `note`；`move` / `split` 没写 `dest`，或 `dest` 按目标分层文件（稿里的 `tiers`，没有则现行分层文件）不是恰落一层；`unit-slow` / `unit-impure` 的 `dest` 仍在单元层；`pure-in-region` 的 `dest` 不在单元层；`budget` 去向而稿里没有 `tiers`，或 `no-case-limit` 的区域在稿的 `tiers` 里仍没有 `case_sec`；稿里的 `tiers` 不合法。审批页 SHALL 含问题清单、各轨道条数（另列体检里没排进稿的不合规项条数「未安排」）、逐条明细（条目 id、类别、现状、去向、目标、轨道、备注，每条一个勾选框）、批注框与「导出 Markdown」「复制」按钮；模型不逐字写 HTML。stdout SHALL 打印一行 JSON `{"tracks": {"mechanical", "human", "change", "keep", "unplanned"}, "problems": N, "out": 路径}`。退出码：0 无问题；1 有问题（审批页照写，问题逐条进 stderr）；2 输入读不了。
Feature: 整改先出稿，人看着稿子批
Rule: 哪些命令内直接改、哪些只能人放行、哪些要另立 change，由脚本按去向归类，不靠模型自述

#### Scenario: render-writes-approval-page-with-tracks
- **GIVEN** 体检 JSON 里有 `unit-slow`、`region-slow`、`no-case-limit`、`allow-unbounded` 各一条；整改稿依次给出 `move`（目标在区域 `hooks`）、`speedup`、`budget`（稿的 `tiers` 给该区域写了 `case_sec`）、`allow`
- **WHEN** 运行 `test-audit.py render`
- **THEN** 退出码为 0，stdout 的 `tracks` 为 `{"mechanical": 2, "human": 1, "change": 1, "keep": 0, "unplanned": 0}`
- **AND** 审批页里有四个条目的 id、「导出 Markdown」按钮与每条一个勾选框

#### Scenario: render-rejects-inapplicable-actions
- **GIVEN** 整改稿里：给 `no-case-limit` 条目写了 `speedup`；有一个体检结果里不存在的条目 id；一条 `keep` 没写理由
- **WHEN** 运行 `test-audit.py render`
- **THEN** 退出码为 1，stderr 逐条点名这三处，审批页仍然写出且问题清单里有它们

#### Scenario: render-checks-move-destinations
- **GIVEN** 三条 `unit-slow` 条目的整改稿分别是：`move` 到仍在单元层的路径、`move` 到不属于任何层的路径、`move` 到区域 `hooks` 的路径
- **WHEN** 运行 `test-audit.py render`
- **THEN** 退出码为 1，stderr 点名前两条（分别含「仍在单元层」与「未归层」），不点名第三条

#### Scenario: render-lists-unplanned-violations
- **GIVEN** 体检 JSON 里有三条不合规项，整改稿只安排了其中一条
- **WHEN** 运行 `test-audit.py render`
- **THEN** 退出码为 0，stdout 的 `tracks.unplanned` 为 2，审批页里写出「未安排 2 条」

### Requirement: 整改护栏
`test-audit.py verify --plan <整改稿> --base <commit>` SHALL 在命令内执行的整改做完之后、交人提交之前，核对工作树相对 `--base` 的改动（含未跟踪文件）是否守住四条：

1. **改动范围**：每个改动的路径须是测试文件、分层文件、openspec 根之下的文件，或命中稿里 `support` 的 glob；其余路径 SHALL 判为「稿外的改动」；命中任一区域 `covers`（基线或当前分层文件）的路径 SHALL 判为「改了被测代码」，`support` 不能豁免它。
2. **用例与断言不变**：对改动的 Python 测试文件，比较基线与当前两边全部测试函数的集合（按 `类名.函数名` 计，跨文件移动不算改动）、每个函数的断言（`assert` 语句、名字以 `assert` 开头的调用、`pytest.raises` / `pytest.warns`）与参数化装饰器；有函数消失、新增、断言或参数化有改动 SHALL 逐条点名。
3. **分层文件的改动与稿一致**：放行条目的新增或改动须对应稿里去向为 `allow`、键为该用例的条目，删除须对应 `drop-allow`，预算放宽（含取消）须对应去向为 `budget`、键为该范围的条目；对不上的 SHALL 判为稿外改动（文本以「稿外」开头并带上那一行变动）。预算与放行的变动清单（`budget_changes` 的文本）恒打印。条目的键取条目 id 第一个冒号之后的部分。
4. **核对不了的如实列出**：改动的非 Python 测试文件、解析失败的 Python 文件 SHALL 列进「未核对」，不判失败。

输出文本逐条列出，末行「护栏通过」或「护栏未过」；`--json` 时输出 `{"ok", "violations": [文本], "unchecked": [路径], "changed": {"tests": 改动的测试文件数, "support": [命中 support 的路径], "tiers": 分层文件是否改动}, "budget_changes": [文本]}`。退出码：0 通过，1 有违反，2 整改稿读不了或 `--base` 不是本仓库的 commit。
Feature: 命令内的整改只许搬、拆、改分层文件
Rule: 护栏由脚本对着 git 改动核对，不接受自述

#### Scenario: verify-passes-pure-moves
- **GIVEN** 基线提交里 `tests/unit/test_a.py` 有两条用例；之后把其中一条原样拆到区域 `hooks` 下的新文件、另一条留在原处，分层文件未动，整改稿里有对应的 `split` 条目
- **WHEN** 运行 `test-audit.py verify --json`
- **THEN** 退出码为 0，`ok` 为真，`violations` 为空，`changed.tests` 为 2

#### Scenario: verify-flags-source-changes
- **GIVEN** 整改期间还改了 `src/a.py`（命中区域 `hooks` 的 `covers`）、`tools/helper.py` 与 `tests/conftest.py`；稿的 `support` 只写了 `tests/conftest.py` 与 `src/**`
- **WHEN** 运行 `test-audit.py verify --json`
- **THEN** 退出码为 1，`violations` 里有一条含「改了被测代码」与 `src/a.py`，一条含「稿外的改动」与 `tools/helper.py`
- **AND** 没有任何一条点名 `tests/conftest.py`，`changed.support` 含它

#### Scenario: verify-flags-assert-and-case-changes
- **GIVEN** 搬文件的同时：`test_x` 的断言从 `== 1` 改成了 `>= 1`，`test_y` 被删掉，`test_z` 的参数化少了一组，新加了 `test_w`
- **WHEN** 运行 `test-audit.py verify --json`
- **THEN** 退出码为 1，`violations` 里分别有「断言有改动」与 `test_x`、「用例消失」与 `test_y`、「参数化有改动」与 `test_z`、「用例新增」与 `test_w`

#### Scenario: verify-flags-unplanned-budget-and-allow-changes
- **GIVEN** 分层文件相对基线：区域 `hooks` 的总量预算从 100 秒放宽到 200 秒，放行名单多了一条、少了一条；整改稿里没有对应条目
- **WHEN** 运行 `test-audit.py verify --json`，再换一份带对应 `budget` / `allow` / `drop-allow` 条目的整改稿运行一次
- **THEN** 第一次退出码为 1，`violations` 里有三条稿外改动（预算放宽、放行新增、放行删除），`budget_changes` 非空
- **AND** 第二次退出码为 0

#### Scenario: verify-lists-non-python-files-as-unchecked
- **GIVEN** 改动里有一个非 Python 的测试文件 `web/a.test.ts` 与一个语法错误的 `tests/unit/test_bad.py`
- **WHEN** 运行 `test-audit.py verify --json`，再用一个不存在的 commit 当 `--base` 运行一次
- **THEN** 第一次退出码为 0，`unchecked` 含这两个路径
- **AND** 第二次退出码为 2

### Requirement: 合规标准有明文
`template/.claude/flight-runner-contract.md` SHALL 新增一节，标题含「测试套件合规标准」，写明：八条规则 R1–R8 各自的判据与数据来源；体检的全部类别名与各自的级别（不合规 / 提示 / 未判）；每个不合规类别的可选去向与各去向的轨道（命令内执行 / 交人放行 / 转 change）；体检读什么、不跑测试；`test-tiers.py audit` 的退出码 0 / 1 / 2 / 3；体检与门禁的区别（集成层老债门禁只警告、体检计为不合规）；整改护栏四条。原有各节的标题 MUST 保留。`template/.claude/commands/test-tiers.md` SHALL 有一行同时提到 `test-tiers.py audit` 与 `/test-audit`，说明建层之后的例行体检走哪条命令。
Feature: 标准写在文档里，脚本按它判，整改以它为目标
Rule: 标准不只存在于脚本里

#### Scenario: contract-states-compliance-standard
- **GIVEN** 模板仓库的运行器契约文档
- **WHEN** 取标题含「测试套件合规标准」的那一节
- **THEN** 该节存在，正文含 `R1` 到 `R8`、十个不合规类别名、五个提示类别名、`unjudged`、十个去向名与「命令内执行」「交人放行」「转 change」
- **AND** 正文写出退出码 `0` / `1` / `2` / `3` 的含义，并含「老债」
- **AND** 原有第 1–10 节的标题都还在

#### Scenario: test-tiers-doc-points-to-audit
- **GIVEN** `/test-tiers` 的命令文档
- **WHEN** 逐行查找
- **THEN** 有一行同时含 `test-tiers.py audit` 与 `/test-audit`

### Requirement: 体检与整改命令
模板 SHALL 新增 slash 命令 `/test-audit`（`template/.claude/commands/test-audit.md`，命令本身即逻辑，无同名 skill），步骤为：体检并存档（`test-tiers.py audit --out`）→ 起草整改稿 → `test-audit.py render` 渲染审批页并停下等人类批准 → 按轨道处置 → 复核。命令文档 SHALL 写明：命令内执行的只有机械处置（搬文件、拆文件、改分层文件、删失效放行），执行前先 `/opsx-mini` 留痕，执行后跑 `test-audit.py verify`，再对受影响的层重新取测量（`test-tiers.py probe --json`）并以 `test-tiers.py audit --probe … --compare … --plan …` 复核；放行只能由人类原话经 `test-tiers.py allow-slow` 写入；改用例实现的去向（提速、改纯、删除）不在命令内动手，整理成清单交 `/opsx-propose` 另立 change；不改被测代码、不改断言、不代 commit。`README.md` 与 `install.sh` 的命令计数 SHALL 从 17 改为 18 并列出 `/test-audit`。契约文档的类别与去向 MUST 与脚本常量 `AUDIT_RULES`、`ACTIONS` 一致。
Feature: 一条命令从体检走到复核
Rule: 能机械做的命令内做完；要判断怎么改用例的交给正式的 change

#### Scenario: test-audit-command-doc-covers-flow
- **GIVEN** 模板仓库的 `template/.claude/commands/test-audit.md`
- **WHEN** 读它的全文
- **THEN** 文件以带 `description:` 的 frontmatter 开头
- **AND** 正文含 `test-tiers.py audit`、`--out`、`test-audit.py render`、`test-audit.py verify`、`--compare`、`--plan`、`test-tiers.py probe`、`allow-slow`、`/opsx-mini`、`/opsx-propose`
- **AND** 正文含「等人类批准」「不改断言」「不代 commit」「无同名 skill」

#### Scenario: readme-and-install-count-test-audit
- **GIVEN** `README.md` 与 `install.sh`
- **WHEN** 查找命令计数与命令清单
- **THEN** `README.md` 含「18 个 slash 命令」且命令表有 `/test-audit` 一行，`install.sh` 含「18 个 slash command」与 `/test-audit`
- **AND** 两个文件都不再出现「17 个 slash」

#### Scenario: standard-doc-matches-script-constants
- **GIVEN** `test-tiers.py` 的 `AUDIT_RULES` 与 `test-audit.py` 的 `ACTIONS`
- **WHEN** 与契约文档「测试套件合规标准」一节对照
- **THEN** `AUDIT_RULES` 的每个类别名、规则号都出现在该节
- **AND** `ACTIONS` 的每个去向名都出现在该节，`AUDIT_RULES` 里每个 `fix` 项都是 `ACTIONS` 的键
