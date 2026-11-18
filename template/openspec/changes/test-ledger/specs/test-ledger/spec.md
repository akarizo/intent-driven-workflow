## ADDED Requirements

### Requirement: 门禁的每次测试运行留下逐用例结局与耗时的观测
`slice-gate.py` SHALL 在门禁进程内维护一张观测表，`ledger_observations()` 返回它的副本；每条观测形如 `{"form": "nodeid" | "junit", "outcomes": {用例 id: 结局}, "secs": {用例 id: 秒}}`，另可带 `"tier": 层名`（上报方已经知道这批用例属于哪一层时）。三个入口各上报一次本次实测：`run_test_gate`（依赖图测到时 `form` 为 `nodeid`，用例 id 为仓库相对 nodeid，耗时为该用例 setup + call + teardown 之和；依赖图没测到而 junit 可解析时 `form` 为 `junit`，用例 id 为 `classname::name`，结局与耗时取自 junit）、`_pytest_outcomes`（`form` 为 `nodeid`，无论调用方是否传了 `durations` 都带耗时）、`run_part`（pytest 部件与适配器部件都报：`form` 为 `nodeid`，用例 id 与耗时取自它返回的 `secs`，`outcomes` 为空，`tier` 为 `unit`；`secs` 为 `None` 时不报）。`run_test_gate` 返回的依赖图 SHALL 多一个 `secs = {nodeid: 秒}`，其余键与含义不变。`run_test_gate` 带 `cwd` 运行时 MUST NOT 上报。上报与采集 MUST NOT 改变任何入口的既有返回值含义，也 MUST NOT 让测试运行失败。
Feature: 门禁看得到每条用例跑了多久
Rule: 依赖图测到用 nodeid，没测到用 junit；采集只追加，不改判定

#### Scenario: deps-run-records-case-seconds
- **GIVEN** 被测仓库的 `gate.test` 是直接的 pytest 调用，其中一条用例睡 0.3 秒
- **WHEN** 以 `deps=True` 调用 `run_test_gate`
- **THEN** 返回的 `deps["secs"]` 的键集合等于 `deps["nodes"]` 的键集合，睡 0.3 秒的那条不小于 0.3
- **AND** `deps["nodes"]` 的内容与改动前相同
- **AND** 观测表新增一条 `form` 为 `nodeid` 的观测，`outcomes` 与 `secs` 覆盖这些用例

#### Scenario: junit-fallback-when-deps-unmeasured
- **GIVEN** `gate.test` 是只把 `--junitxml` 传给 pytest、丢掉 `-p` 插件参数的包装脚本
- **WHEN** 以 `deps=True` 调用 `run_test_gate`
- **THEN** 返回的 `deps` 为 `None`，`deps_kind` 为 `plugins-dropped`
- **AND** 观测表新增一条 `form` 为 `junit` 的观测，用例 id 形如 `classname::name`，每条都有结局与耗时

#### Scenario: incremental-rerun-records-seconds
- **GIVEN** 被测仓库有两个测试文件
- **WHEN** 不传 `durations` 调用 `_pytest_outcomes` 重跑其中一个文件
- **THEN** 返回的四元组与改动前相同
- **AND** 观测表新增一条 `form` 为 `nodeid` 的观测，只含被重跑文件的用例，每条都有耗时
- **AND** 传了 `durations` 字典时该字典照旧被填上同样的耗时

#### Scenario: part-adapter-run-is-observed
- **GIVEN** 部件形态的被测仓库，其中一个部件的单元命令是往 `$FLIGHT_JUNIT` 写报告的脚本
- **WHEN** 对该部件调用 `run_part`
- **THEN** 观测表新增一条 `form` 为 `nodeid` 的观测，`secs` 等于返回值的 `secs`，`outcomes` 为空，`tier` 为 `unit`
- **AND** `run_part` 的返回值与改动前相同

### Requirement: 账本由实测与沿用合成，存在 git common dir
`test-ledger.py` SHALL 提供 `build(meta, observations, universe=None, source=None, rerun_files=None, root=None, tier_of=None)`，把观测合成账本：顶层带 `v`、`id_form`、`tiered`、`complete` 与 `meta` 里的字段，`cases` 为 `{用例 id: {"o": 结局, "s": 秒 | null, "t": 层 | null, "m": 1 | 0}}`。规则：给了 `universe`（`{nodeid: 结局}`）时只用 `nodeid` 形式的观测，账本的用例恰为 `universe` 的键；没给时，观测里有 `junit` 形式或来源的 `id_form` 为 `junit` 就用 `junit` 形式（此时 `nodeid` 形式的观测按 pytest 写 junit 的规则换算后并入：文件路径去掉 `.py`、`/` 换成 `.`，中间的类名以 `.` 相连，得 `classname`，最后一段为 `name`），否则用 `nodeid` 形式（`junit` 形式的观测丢弃）；账本的用例为实测到的用例，`rerun_files` 给了时再并上来源里「文件仍存在且不在 `rerun_files` 里」的用例。实测到的用例 `m` 为 1；其余 `m` 为 0，耗时取自来源，来源没有该用例或没有耗时时 `s` MUST 为 `null`，不得填 0 或估算值。同一用例有多条观测时以后来的为准。结局统一成小写的 `passed / failed / error / skipped / xfailed / xpassed`，未知为 `null`。`complete` 为真当且仅当每条 `m` 为 0 的用例都在来源里。层的归属：观测带 `tier` 时该观测里的用例取它；否则 `tier_of` 给了时 `t` 为 `tier_of(用例所在文件)`，`junit` 形式的文件由 `classname` 从长到短试出 `root` 下存在的 `.py`；两者都没有时 `t` 为 `null`。`tiered` 为真当且仅当给了 `tier_of` 或有观测带 `tier`。`from_anchor(锚点)` SHALL 把带 `nodes` 的锚点条目转成来源（`secs` 缺失时耗时全为 `null`）。`save(root, change, name, obj)` SHALL 原子写 `<git common dir>/flight-ledger/<change>/<name>.json` 并只保留最近 30 个 change 的目录；`load` 读不到返回 `None`。`summary(账本)` SHALL 给出 `{cases, measured, inherited, no_sec, id_form, complete, tiers: {层: {cases, sec}}}`，没有层的用例归在 `-` 下。子命令 `show --change-dir DIR [--phase baseline|final] [--tier 层] [--top N] [--json]` SHALL 按耗时由大到小列出账本里的用例，退出码 0 有账本 / 1 没有 / 2 参数不可用。
Feature: 一份账本说清每条用例的结局、耗时、所属层与来源
Rule: 取不到的耗时记空，沿用的标沿用

#### Scenario: build-marks-measured-and-inherited
- **GIVEN** 用例全集有 `tests/test_a.py::test_a`、`tests/test_b.py::test_b`、`tests/test_b.py::test_c` 三条；本次观测只实测到后两条；来源有前两条的耗时
- **WHEN** 调用 `build` 并传入全集与来源
- **THEN** 后两条 `m` 为 1、耗时取自观测；第一条 `m` 为 0、耗时取自来源
- **AND** `complete` 为真，`id_form` 为 `nodeid`
- **AND** 把来源里第一条的耗时去掉后重做，第一条的 `s` 为 `null`，`summary` 的 `no_sec` 为 1

#### Scenario: build-keeps-unrerun-cases-from-source-ledger
- **GIVEN** 没有用例全集；观测是 `junit` 形式，实测到 `tests.test_b::test_b`；来源账本有 `tests.test_a::test_a` 与 `tests.test_b::test_old`；`rerun_files` 为 `["tests/test_b.py"]`，两个文件都存在
- **WHEN** 调用 `build`
- **THEN** 账本恰有 `tests.test_a::test_a`（`m` 为 0）与 `tests.test_b::test_b`（`m` 为 1），没有 `tests.test_b::test_old`
- **AND** `id_form` 为 `junit`，`complete` 为真
- **AND** 同样的输入不给来源时 `complete` 为假
- **AND** 观测只有 `nodeid` 形式的 `tests/test_b.py::test_b`、来源的 `id_form` 为 `junit` 时，得到的账本与上面相同

#### Scenario: build-attributes-tiers-per-case
- **GIVEN** 观测里有 `tests/unit/test_u.py::test_u` 与 `tests/integration/hooks/test_h.py::test_h`；`tier_of` 把前者的文件判为 `unit`、后者判为 `hooks`
- **WHEN** 调用 `build` 再取 `summary`
- **THEN** 两条用例的 `t` 分别为 `unit` 与 `hooks`，`tiered` 为真
- **AND** `summary["tiers"]` 里 `unit` 与 `hooks` 各 1 条，秒数等于各自用例的耗时
- **AND** 不给 `tier_of` 时两条的 `t` 都是 `null`，`summary["tiers"]` 只有 `-`
- **AND** 一条带 `"tier": "unit"` 的观测里的用例，即使 id 里没有文件路径，`t` 也是 `unit`

#### Scenario: ledger-stored-per-change-in-git-common-dir
- **GIVEN** 一个 git 仓库和它的一间 worktree
- **WHEN** 在主工作区 `save(root, "c", "baseline", 账本)`，再在 worktree 里 `load(worktree, "c", "baseline")`
- **THEN** 读回的内容与写入的相同，文件位于 `<git common dir>/flight-ledger/c/baseline.json`
- **AND** `load` 一个不存在的 change 返回 `None`
- **AND** 已有 30 个 change 目录时再给一个新 change 存一份，最旧的那个目录被清掉，剩 30 个

#### Scenario: show-lists-cases-by-tier-and-seconds
- **GIVEN** change `c` 存有一份 final 账本，含单元层两条（0.1 秒、2.0 秒）与区域 `hooks` 一条（5.0 秒）
- **WHEN** 运行 `test-ledger.py show --change-dir <c> --json`，再运行 `show --change-dir <c> --tier unit --top 1`
- **THEN** 第一次退出 0，JSON 里的用例按耗时由大到小排列，摘要的各层条数与秒数正确
- **AND** 第二次只列出单元层最慢的那一条
- **AND** 对没有账本的 change 运行 `show` 退出 1，并说明没有账本

### Requirement: final 账本与基线账本对账得出测试变更
`test-ledger.py` SHALL 提供 `delta(base, final, rerun_files=None, root=None)`，返回 `(对账结果 | None, 原因 | None)`。`base` 为 `None` 或 `base` 的 `complete` 为假时结果为 `None` 并给出原因（不完整的基线缺了没补跑的用例，对账会把它们编成新增）。两份账本的 `id_form` 不同时，SHALL 先把 `nodeid` 形式的那份按合成账本时的同一规则换算成 `junit` 形式再对账。随后：新增 = 在 final 不在 base；删除 = 在 base 不在 final 且（final 的 `mode` 为 `full` 或 `parts`，或该用例的文件在 `root` 下已不存在，或该文件在 `rerun_files` 里）；其余在 base 不在 final 的计入 `unknown`；变慢 = 两边都有、final 里 `m` 为 1、两边耗时都不为 `null`、且 final 耗时不小于 base 的 2 倍并且多出不少于 0.5 秒。结果 SHALL 含 `commit`、`base_commit`、`added`、`removed`、`unknown`、`slower_n`、`slower`（至多 5 条 `[id, 前, 后]`）、`added_sec`、`top_added`（至多 5 条 `[id, 秒, 层]`，按耗时由大到小）、`inherited`、`no_sec`、`complete`、`tiers`（`{层: {"before": [条数, 秒], "after": [条数, 秒]}}`）与 `advice`。`segment(结果)` SHALL 返回 `用例 +A/-R（新增 X.Xs）`，`parse_segment(备注)` SHALL 从时间线备注里取回这三个数（没有该片段返回 `None`）；片段 MUST NOT 含 ` · `、「测试」「检查」「排队」。`render(结果)` SHALL 返回以 `## 测试变更` 开头的 Markdown。`advice(结果)` SHALL 按固定规则给出建议行：新增用例里非 `unit` 层的耗时之和大于 `unit` 层时点名最慢的新增集成用例；某层耗时较基线上涨不少于 20% 且不少于 5 秒时点名该层；无耗时用例占比超过 10% 时提示跑一次全量。子命令 `delta --change-dir DIR [--markdown|--json]` SHALL 打印已存的对账结果，退出码 0 有 / 1 没有 / 2 参数不可用。对账与建议 MUST NOT 产生任何判红。
Feature: 每个 change 收口时知道测试多了什么、慢了什么
Rule: 只报告；分不清的不算删除

#### Scenario: delta-counts-added-removed-slower
- **GIVEN** 基线账本有 a（0.1 秒）、b（0.2 秒）、c（1.0 秒）；final 账本是全量，有 a（0.1 秒）、c（2.6 秒，实测）、d（0.4 秒）、e（3.0 秒）
- **WHEN** 调用 `delta`
- **THEN** `added` 为 2、`added_sec` 为 3.4、`removed` 为 1、`unknown` 为 0
- **AND** `slower_n` 为 1，`slower` 里是 c 的前后耗时
- **AND** `top_added` 的第一条是 e

#### Scenario: delta-keeps-unrerun-cases-out-of-removed
- **GIVEN** 基线账本有 `tests/test_a.py::test_a`、`tests/test_b.py::test_b`、`tests/test_gone.py::test_g`；final 账本的 `mode` 为 `impacted`，只有 `tests/test_b.py::test_b2`；`rerun_files` 为 `["tests/test_b.py"]`；`root` 下 `tests/test_a.py` 存在、`tests/test_gone.py` 不存在
- **WHEN** 调用 `delta`
- **THEN** `removed` 为 2（`test_b` 因文件被重跑、`test_g` 因文件已不存在）
- **AND** `unknown` 为 1（`test_a` 没被重测，不算删除）

#### Scenario: delta-handles-missing-or-junit-baseline
- **GIVEN** 一份 `id_form` 为 `nodeid` 的 final 账本，含 `tests/test_a.py::test_a` 与 `tests/test_a.py::TestC::test_m`
- **WHEN** 以 `base=None` 调用 `delta`；再以一份 `id_form` 为 `junit`、含 `tests.test_a::test_a` 与 `tests.test_a::test_old` 的基线账本调用
- **THEN** 第一次的对账结果是 `None`，原因说明「基线账本不在本机」
- **AND** 第二次对账成功：新增 1 条（`tests.test_a.TestC::test_m`）、删除 1 条，`test_a` 两边算同一条

#### Scenario: segment-and-markdown-are-bounded
- **GIVEN** 一份新增 14 条（8.4 秒）、删除 1 条、变慢 7 条、新增里有 12 条带耗时的对账结果
- **WHEN** 取 `segment`、`render`，并把片段放进一条 final 时间线备注的「检查」片段之后、锁片段之前
- **THEN** 片段为 `用例 +14/-1（新增 8.4s）`，`parse_segment` 从整条备注里取回 14、1、8.4
- **AND** `flight-doctor.py` 的 `note_costs` 对这条备注取到的测试秒数、排队秒数、各项检查秒数与不插片段时相同
- **AND** `render` 的第一行是 `## 测试变更`，列出的新增用例与变慢用例各不超过 5 条

#### Scenario: advice-lines-follow-fixed-rules
- **GIVEN** 对账结果一：新增用例里 `hooks` 层 7.5 秒、`unit` 层 0.9 秒；对账结果二：`unit` 层耗时从 20 秒涨到 26 秒；对账结果三：100 条用例里 30 条无耗时；对账结果四：以上都不满足
- **WHEN** 分别调用 `advice`
- **THEN** 结果一有一行点名最慢的新增 `hooks` 用例
- **AND** 结果二有一行点名 `unit` 层
- **AND** 结果三有一行提示跑一次全量
- **AND** 结果四返回空列表

### Requirement: baseline 写基线账本，锚点带上逐用例耗时
`slice-gate.py baseline` SHALL 在写锚点之前落账，写出 `<git common dir>/flight-ledger/<change>/baseline.json`（`phase` 为 `baseline`，`mode` 为 `full` / `incremental` / `parts`，`lock` 为本次的锁状态）：全量且依赖图测到时用例全集取依赖图的用例；经锚点的增量基线以来源锚点为来源、以新锚点的用例为全集、以补跑的测试文件为 `rerun_files`；复用旧基线或基线池时来源是被复用基线所属 change 的基线账本（其 `commit` 与被复用基线相同才算）。`gate-baseline.json` SHALL 多一段 `ledger`（`summary` 的结果），MUST NOT 含逐用例数据。本次写出的锚点 SHALL 带 `secs = {nodeid: 秒}`（只含有耗时的用例；依赖图没测到时为 `null`）。配了分层文件时用例的层按分层文件归属。落账失败（`test-ledger.py` 缺失、加载失败、抛错、目录不可写）时 baseline 的 `ok`、`reasons`、退出码 MUST 与没有账本功能时相同，只在 `warnings` 里多一条以「测试账本未写」开头的说明。
Feature: 基线留下一份可对账的逐用例账本
Rule: 账本在仓库之外；账本出错不影响基线

#### Scenario: full-baseline-writes-ledger-and-summary
- **GIVEN** 被测仓库的 `gate.test` 是直接的 pytest 调用，共 3 条用例
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 基线账本存在，`mode` 为 `full`、`id_form` 为 `nodeid`，3 条用例都是 `m` 为 1 且有耗时
- **AND** `gate-baseline.json` 的 `ledger.cases` 为 3、`ledger.no_sec` 为 0，整个文件里没有 `"cases": {`
- **AND** 最新锚点的 `secs` 恰有这 3 条用例

#### Scenario: anchor-baseline-inherits-seconds
- **GIVEN** change `c` 有一次测到依赖图的全量基线；之后提交了 `src/a.py` 的改动
- **WHEN** 再运行 baseline（经锚点增量，只补跑 `tests/test_a.py`）
- **THEN** 基线账本的 `mode` 为 `incremental`，`tests/test_a.py` 的用例 `m` 为 1，其余用例 `m` 为 0 且耗时不为 `null`
- **AND** 新写出的锚点的 `secs` 覆盖全部用例
- **AND** 把来源锚点的 `secs` 删掉后重做同样的步骤，没补跑的用例耗时为 `null`，`gate-baseline.json` 的 `ledger.no_sec` 大于 0，baseline 仍然 `ok`

#### Scenario: reused-baseline-keeps-source-ledger
- **GIVEN** `gate.test` 是丢掉插件参数的包装脚本（依赖图未测），change `c` 已有一次全量基线与对应的基线账本（`id_form` 为 `junit`）；之后只改了一个测试文件并提交
- **WHEN** 再运行 baseline（复用旧基线，只补跑该测试文件）
- **THEN** 新的基线账本里被改文件的用例 `m` 为 1，其余用例 `m` 为 0 且耗时沿用旧账本
- **AND** `complete` 为真

#### Scenario: tiered-baseline-attributes-tiers
- **GIVEN** 配了分层文件的被测仓库：单元层一条用例，已选区域 `hooks` 两条用例
- **WHEN** 运行 baseline
- **THEN** 基线账本的 `tiered` 为真，单元层用例的 `t` 为 `unit`，区域用例的 `t` 为 `hooks`
- **AND** `gate-baseline.json` 的 `ledger.tiers` 里 `unit` 为 1 条、`hooks` 为 2 条

#### Scenario: ledger-failure-does-not-fail-baseline
- **GIVEN** 一份不含 `test-ledger.py` 的 hooks 目录副本
- **WHEN** 用这份副本里的 `slice-gate.py` 运行 baseline
- **THEN** 退出码为 0，`ok` 为真，`reasons` 为空
- **AND** `warnings` 里有一条以「测试账本未写」开头
- **AND** `gate-baseline.json` 没有 `ledger`，写出的锚点 `secs` 为 `null`

### Requirement: final 写收口账本并报告测试变更
`slice-gate.py final` 在实际跑了测试套件时 SHALL 落账（`phase` 为 `final`，`mode` 为 `full` / `incremental` / `impacted` / `tests-only` / `parts`），写出 `final.json`：内建增量以所选锚点为来源、以新锚点的用例为全集、以本次重跑的文件为 `rerun_files`；全量且依赖图测到时全集取依赖图的用例；无图退路（输出 JSON 的 `incremental.source` 为 `tests-only`）以本 change 上一份 `final.json` 为来源（它的 `commit` 等于上次绿 final 的 commit 时才算数，否则没有来源）、以本次重跑的文件为 `rerun_files`，`mode` 记 `tests-only`。随后 SHALL 与本 change 的基线账本对账，把 `summary` 加 `delta`（对账结果或 `null`）与 `why` 作为输出 JSON 的 `tests`，把对账结果存成 `delta.json`，并在 final 时间线备注的「检查」片段之后、锁片段之前插入 `segment` 的片段（没有对账结果时不插）。本次写出的锚点 SHALL 带 `secs`。G7 红、选测复核未过、同树沿用这三种没有跑套件的 final MUST NOT 落账，输出 JSON 没有 `tests`。`slice-gate.py ship --markdown` SHALL 在 `gate-report.md` 最后一条 final 行的 commit 等于 `delta.json` 的 `commit` 前 10 位时，在现有输出之后附上 `render` 的文本；对不上或没有 `delta.json` 时输出与没有账本功能时相同。`ship` 的 JSON 输出、退出码与时间线记录 MUST 不变。落账或对账失败时 final 的 `ok`、`failed`、退出码 MUST 与没有账本功能时相同，只在 `warnings` 里多一条以「测试账本未写」开头的说明。部件形态的 baseline 与 final SHALL 同样落账（`mode` 为 `parts`），用例来自各部件单元层的上报。
Feature: 收口时看得到这个 change 给测试套件带来了什么
Rule: 只在真的跑了套件时落账；报告进时间线与 PR 正文，不改结论

#### Scenario: final-full-reports-test-delta
- **GIVEN** change `c` 有一次全量基线（3 条用例）；之后提交了一个新测试文件（一条睡 0.3 秒的用例）
- **WHEN** 运行 `slice-gate.py final --full`
- **THEN** 输出 JSON 的 `tests.cases` 为 4，`tests.delta.added` 为 1、`removed` 为 0，`added_sec` 不小于 0.3
- **AND** final 时间线备注含 `用例 +1/-0（新增 `，且结论词仍在末尾
- **AND** `flight-doctor.py cost` 对该时间线的输出里 final 的全量次数为 1、秒数等于备注里的「测试」秒数
- **AND** `<git common dir>/flight-ledger/c/delta.json` 存在，`commit` 为当前 HEAD

#### Scenario: incremental-final-marks-inherited-cases
- **GIVEN** change `c` 有一次测到依赖图的全量基线；之后提交了一个新测试文件
- **WHEN** 运行 `slice-gate.py final`（内建增量）
- **THEN** 收口账本的 `mode` 为 `incremental`，新文件的用例 `m` 为 1，没重跑文件的用例 `m` 为 0 且耗时不为 `null`
- **AND** `tests.inherited` 大于 0，`tests.complete` 为真
- **AND** 本次写出的锚点 `secs` 覆盖全部用例

#### Scenario: tests-only-final-inherits-previous-final-ledger
- **GIVEN** 依赖图测不到的被测仓库（`gate.test` 是只转发 `--junitxml` 的包装脚本），change `c` 的 final 已绿并留下收口账本；之后只提交了 `tests/test_a.py` 的改动（多一条用例）
- **WHEN** 运行 `slice-gate.py final`（无图退路，只重跑 `tests/test_a.py`）
- **THEN** 收口账本的 `mode` 为 `tests-only`，`id_form` 为 `junit`，`complete` 为真
- **AND** `tests/test_a.py` 的两条用例 `m` 为 1，其余用例与上一份收口账本相同、`m` 为 0
- **AND** 输出 JSON 的 `tests.delta.added` 为 1、`removed` 为 0

#### Scenario: ship-markdown-appends-test-delta-when-fresh
- **GIVEN** change `c` 的 final 刚跑完且通过，留下了与该 final 同一 commit 的 `delta.json`
- **WHEN** 运行 `slice-gate.py ship --change-dir <c> --markdown`
- **THEN** 输出里有以 `## 测试变更` 开头的一节
- **AND** 把 `delta.json` 的 `commit` 改成别的值后再运行，输出里没有这一节
- **AND** 两次的退出码相同，不带 `--markdown` 的 JSON 输出没有新增键

#### Scenario: ledger-failure-does-not-fail-final
- **GIVEN** 一份不含 `test-ledger.py` 的 hooks 目录副本，change `c` 已用它跑过 baseline
- **WHEN** 用这份副本里的 `slice-gate.py` 运行 final
- **THEN** 退出码为 0，`ok` 为真，`failed` 为空
- **AND** `warnings` 里有一条以「测试账本未写」开头，输出 JSON 没有 `tests`
- **AND** final 时间线备注里没有「用例 +」片段

#### Scenario: parts-runs-write-ledger
- **GIVEN** 部件形态的被测仓库：部件 `py`（pytest）与部件 `sh`（脚本往 `$FLIGHT_JUNIT` 写报告）
- **WHEN** 依次运行 baseline 与 final
- **THEN** 基线账本与收口账本的 `mode` 都是 `parts`
- **AND** 账本里有部件 `sh` 的用例，带耗时、`t` 为 `unit`
- **AND** final 输出 JSON 的 `tests.delta.added` 为 0、`removed` 为 0

### Requirement: 体检列出测试账本
`flight-doctor.py doctor` SHALL 在现有各节之后输出 `[tests]` 一节：取在途 change 里 `at` 最新的一份账本（final 先于 baseline），打印它的来源（change、阶段、commit 前 10 位、模式）、各层的用例数与秒数、耗时最大的至多 10 条用例、无耗时的条数；再列出至多 5 个 change 最近一次带「用例 +A/-R（新增 Xs）」片段的 final 行里的这三个数。没有任何账本时 SHALL 打印一行以「没有账本数据」开头的原因；openspec 根没有 `test-tiers.json` 时另打印一行提到 `/test-tiers` 的提示。`test-ledger.py` 缺失或读账本出错时该节只打印一行说明。`doctor` 恒以 0 退出的约定不变，其余各节的输出不变。
Feature: 随时能看一眼测试套件现在多大、多慢、最近怎么变的
Rule: 体检只读，不阻断

#### Scenario: doctor-tests-lists-tiers-and-slowest
- **GIVEN** 在途 change `c` 存有一份 final 账本：单元层 12 条共 3.0 秒，区域 `hooks` 2 条共 9.0 秒，其中一条无耗时
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** 退出码为 0，输出有 `[tests]` 一节
- **AND** 该节写出来源 `c`、`final`，写出 `unit` 12 条与 `hooks` 2 条及各自秒数
- **AND** 列出的最慢用例不超过 10 条，第一条是耗时最大的那条
- **AND** 写出无耗时 1 条

#### Scenario: doctor-tests-lists-recent-change-deltas
- **GIVEN** 两个在途 change 的时间线各有一条带「用例 +3/-1（新增 2.5s）」与「用例 +0/-0（新增 0.0s）」片段的 final 行，第三个 change 的 final 行没有片段
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** `[tests]` 一节按 change 列出前两个的新增、删除与新增耗时
- **AND** 第三个 change 不出现在这份清单里

#### Scenario: doctor-tests-explains-missing-ledger
- **GIVEN** 本机没有任何账本，openspec 根没有 `test-tiers.json`
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** 退出码为 0，`[tests]` 一节有一行以「没有账本数据」开头
- **AND** 另有一行提到 `/test-tiers`
- **AND** 其余各节（`[runner]`、`[anchors]`、`[gate.test]`、`[declare]`、`[checks]`、`[lock]`）照常输出

### Requirement: 文档说明测试账本与测试变更
`template/.claude/flight-runner-contract.md` SHALL 新增第 9 节「测试账本」，写明：账本的位置（`<git common dir>/flight-ledger/<change>/`）与三份文件、用例记录的四个字段（`o` / `s` / `t` / `m`）、耗时的两种来源（依赖图插件与 junit）及「取不到记 `null`」、「沿用」的含义、`test-ledger.py show` 与 `delta` 两个子命令、账本只报告不判红且失败不影响门禁；原有第 1–8 节的标题 MUST 保留。`template/.claude/commands/test-tiers.md` SHALL 在「门禁的分层耗时」之后说明账本按分层文件给每条用例归层、没有分层文件时不分层。`template/.claude/commands/pr-ship.md` 在贴 `ship --markdown` 输出的那一步 SHALL 说明输出可能含「## 测试变更」一节且须原样贴入。`README.md` SHALL 有一条说明测试账本与 `flight-doctor.py doctor` 的 `[tests]`。
Feature: 接入方与 reviewer 读得懂账本
Rule: 文档与行为同一个 change 落地

#### Scenario: docs-describe-test-ledger
- **GIVEN** 本 change 落地后的模板文档
- **WHEN** 读 `flight-runner-contract.md`、`commands/test-tiers.md` 与 `README.md`
- **THEN** 契约文档有以 `## 9.` 开头且含「测试账本」的标题，该节提到 `flight-ledger`、`test-ledger.py show`、`test-ledger.py delta`、`null`、沿用、不判红
- **AND** 契约文档原有第 1–8 节的标题都还在
- **AND** `test-tiers.md` 提到测试账本按分层文件归层
- **AND** `README.md` 有一行同时提到测试账本与 `[tests]`

#### Scenario: pr-ship-doc-mentions-test-delta-section
- **GIVEN** 本 change 落地后的 `commands/pr-ship.md`
- **WHEN** 读贴 `slice-gate.py ship … --markdown` 输出的那一步
- **THEN** 该步写明输出可能含「## 测试变更」
- **AND** 写明不要改写或删减这一节
