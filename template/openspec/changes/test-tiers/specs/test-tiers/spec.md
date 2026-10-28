## ADDED Requirements

### Requirement: 分层文件与计划里的区域选择由 lint 校验
仓库级分层文件 `test-tiers.json` SHALL 从 openspec 根目录读取，openspec 根目录 = change 目录的上两级（`<change_dir>/../..`，与 `gate-checks.json` 同一解析）。

文件存在时，`slice-gate.py lint`（preflight 内的同一份计划校验也一样）SHALL 在下面任一条不满足时退出非 0，stderr 每条违规以 `tiers:` 开头并点名对象：

- 文件可读、是合法 JSON、顶层是对象，否则只报一行并点名该文件；
- 顶层只含 `unit`、`regions`、`slow_allow`，且必有 `unit`；
- `unit` 只含 `paths` 与 `cmd`：`paths` 是非空数组、每项去掉首尾空白后非空；`cmd` 是非空字符串；
- `regions` 是对象；区域名匹配 `^[a-z0-9-]+$`；每个区域只含 `paths`、`covers`、`cmd`，`paths` 同上，`covers` 是数组（可以为空）、每项非空，`cmd` 是非空字符串；
- `slow_allow` 是对象；每项只含 `reason` 与 `approved`，都是非空字符串；
- `gate.test` 去掉首尾空白后等于 `unit.cmd` 去掉首尾空白后（基线就是单元层）；
- `gate.integration` 缺省，或是数组、每项是 `regions` 里的区域名、不重复；
- `gate.integration_skip` 缺省，或是对象、每个键是 `regions` 里的区域名、理由去掉首尾空白后非空、键不同时出现在 `gate.integration`；
- 区域的 `covers` 里任一 glob 与任一切片 `owns` 里任一 glob 相交（与同 wave owns 重叠同一判定）时，该区域 SHALL 出现在 `gate.integration` 或 `gate.integration_skip`；
- `scenario_tests` 指向的每个测试文件路径 SHALL 匹配 `unit.paths`，或匹配某个已选区域（`gate.integration` 里的区域）的 `paths`。

文件不存在时上面各条都不触发；但计划里出现 `gate.integration` 或 `gate.integration_skip` 时，lint SHALL 报一行以 `tiers:` 开头、指出缺少分层文件。

`plan_sha` SHALL 只在 `gate.integration` 是非空数组时把它追加进哈希内容；其余情况结果与本 change 之前相同。

#### Scenario: lint-rejects-unreadable-tiers-file
- **GIVEN** `openspec/test-tiers.json` 的内容不是合法 JSON；本 change 的计划其余部分合法
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头并含 `test-tiers.json`

#### Scenario: lint-rejects-malformed-tiers-file
- **GIVEN** 分层文件的 `unit` 缺 `cmd`；区域 `Bad` 的名字不合法；区域 `typo` 带未知字段 `cover`；`slow_allow` 里 `tests/unit/test_a.py::test_x` 的 `reason` 是空白
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `tiers:` 开头的行分别点名 `unit`、`Bad`、`typo`、`tests/unit/test_a.py::test_x`

#### Scenario: lint-requires-gate-test-to-be-unit-cmd
- **GIVEN** 分层文件的 `unit.cmd` 是 `python3 -m pytest -q tests/unit`；计划的 `gate.test` 是 `python3 -m pytest -q tests`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头并含 `gate.test`

#### Scenario: lint-rejects-bad-region-selection
- **GIVEN** 分层文件只有区域 `hooks` 与 `docs`；计划的 `gate.integration` 是 `["hooks", "ghost", "hooks"]`，`gate.integration_skip` 是 `{"docs": "  ", "hooks": "不碰"}`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `tiers:` 开头的行分别点名 `ghost`、重复的 `hooks`、理由空白的 `docs`、同时出现在两处的 `hooks`

#### Scenario: lint-rejects-integration-without-tiers-file
- **GIVEN** openspec 根目录下没有 `test-tiers.json`；计划的 `gate.integration` 是 `["hooks"]`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头并含 `test-tiers.json`

#### Scenario: lint-requires-decision-for-covered-region
- **GIVEN** 区域 `hooks` 的 `covers` 是 `["src/hooks/**"]`；切片 S1 的 `owns` 含 `src/hooks/gate.py`；计划的 `gate.integration` 与 `gate.integration_skip` 都没有 `hooks`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头并点名 `hooks`

#### Scenario: lint-requires-scenario-test-in-tier
- **GIVEN** `unit.paths` 是 `["tests/unit/**"]`；区域 `hooks` 的 `paths` 是 `["tests/integration/hooks/**"]` 但没被选上；`scenario_tests` 把一条 scenario 映射到 `tests/integration/hooks/test_g.py::test_g`，另一条映射到 `tests/test_loose.py::test_loose`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `tiers:` 开头的行分别点名 `tests/integration/hooks/test_g.py` 与 `tests/test_loose.py`

#### Scenario: lint-accepts-valid-tiers-plan
- **GIVEN** 分层文件合法，`unit.cmd` 与 `gate.test` 相同；区域 `hooks` 的 `covers` 与 S1 的 `owns` 相交且在 `gate.integration` 里；区域 `docs` 的 `covers` 也相交，在 `gate.integration_skip` 里写了理由；scenario 测试分别在 `tests/unit/` 与 `tests/integration/hooks/` 下
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0，stdout 打印 waves

#### Scenario: no-tiers-file-lint-unchanged
- **GIVEN** openspec 根目录下没有 `test-tiers.json`；计划没有 `gate.integration` 与 `gate.integration_skip`
- **WHEN** 运行 `slice-gate.py lint`，并对同一份计划计算 `plan_sha`
- **THEN** lint 退出 0，stderr 没有以 `tiers:` 开头的行
- **AND** `plan_sha` 与按本 change 之前的算法（`[test, lint, typecheck, [[id, verify]]]`，有 `gate.checks` 时追加检查）算出的相同

### Requirement: 切片改动的测试文件必须归层（G12）
分层文件存在时，`slice-gate.py gate` SHALL 检查本切片区间（`base..HEAD` 加未提交改动）里改动过、当前仍存在、文件名符合测试文件命名（`test_*.py`、`*_test.py`、`*.test.*`、`*.spec.*`）的每个文件：路径匹配 `unit.paths` 或某个已选区域的 `paths`；否则 `failed` 加一条 `G12 tiers: <路径> …`。分层文件不存在时不做这项检查。

#### Scenario: gate-flags-test-file-outside-tiers
- **GIVEN** `unit.paths` 是 `["tests/unit/**"]`，已选区域 `hooks` 的 `paths` 是 `["tests/integration/hooks/**"]`；切片区间里新增了 `tests/integration/hooks/test_ok.py` 与 `tests/test_stray.py`
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** `failed` 里有一条以 `G12` 开头并点名 `tests/test_stray.py`
- **AND** 没有任何 `G12` 项点名 `tests/integration/hooks/test_ok.py`

### Requirement: 单元层运行时用探针逐用例记录触碰与耗时
slice-gate 以探针方式运行单元层（`gate.test`）时 SHALL：

- 经 `PYTEST_ADDOPTS` 追加 `-p flight_tier_probe`；插件文件写进临时目录并把该目录加进 `PYTHONPATH`，不写进被测仓库；
- 对每个用例记录耗时 = setup、call、teardown 三个阶段耗时之和；
- 对每个用例记录在这三个阶段内发生的审计事件，归为三类，每类保留第一条样例：
  - 文件：`open`、`os.mkdir`、`os.remove`、`os.rename`、`os.rmdir`、`os.chmod`、`os.truncate`、`os.utime`、`os.symlink`、`os.link`、`os.listdir`、`os.scandir`、`os.walk`、`glob.glob`、`shutil.copyfile`、`shutil.copytree`、`shutil.move`、`shutil.rmtree`、`shutil.copymode`、`shutil.copystat`；
  - 子进程：`subprocess.Popen`、`os.system`、`os.exec`、`os.spawn`、`os.posix_spawn`、`os.fork`；
  - 网络：`socket.connect`、`socket.bind`、`urllib.Request`；
- 不计入：发生在 import 机制（`importlib._bootstrap*`、`zipimport`）或 pytest 断言重写读源文件期间的事件；三个阶段之外（如失败报告生成）的事件；
- 插件加载失败（输出含 `Error importing plugin "flight_tier_probe"`）时，去掉探针把单元层重跑一次；本次结果判「不可度量」并写明原因，失败用例差分照常用重跑的结果；
- 输出里没有探针的开跑记录（如 `gate.test` 不是 pytest）时判「不可度量」。

#### Scenario: probe-classifies-each-test
- **GIVEN** 单元层有四个用例：只做算术的；在 `tmp_path` 里写文件的；用子进程运行当前解释器的；在测试函数里首次 import 测试目录下另一个模块的
- **WHEN** slice-gate 以探针方式运行单元层
- **THEN** 写文件的用例被记为碰了「文件」，用子进程的被记为碰了「子进程」
- **AND** 只做算术的与首次 import 模块的都没有任何触碰记录

#### Scenario: probe-counts-setup-and-teardown
- **GIVEN** 单元层有一个用例，它的 fixture 在准备阶段与清理阶段各睡 0.4 秒，测试函数本身不睡
- **WHEN** slice-gate 以探针方式运行单元层
- **THEN** 该用例记录的耗时不少于 0.8 秒

#### Scenario: probe-falls-back-when-plugin-cannot-load
- **GIVEN** `gate.test` 是 `env PYTHONPATH= python3 -m pytest -q tests/unit`（包装命令清空了 `PYTHONPATH`），单元层用例全绿
- **WHEN** slice-gate 以探针方式运行单元层
- **THEN** 结果的退出码为 0，判为不可度量，原因含「探针」
- **AND** 没有任何用例被记为触碰或超时

#### Scenario: probe-unmeasurable-for-non-pytest
- **GIVEN** `gate.test` 是 `true`
- **WHEN** slice-gate 以探针方式运行单元层
- **THEN** 结果判为不可度量，没有逐用例记录

### Requirement: 单元层的慢单测（G10）与不纯（G11）判定
对一次单元层运行的逐用例记录，slice-gate SHALL：

- 把耗时 ≥ 3 秒的用例当作候选，在同一次 pytest 调用里单独重跑这些候选一次；重跑耗时仍 ≥ 3 秒，或重跑没有取得它的耗时，即确认超线；
- 确认超线且不在 `slow_allow` 里的用例，各给一条失败 `G10 slow unit test: <nodeid> …`，写明首跑与重跑耗时及处理方式（提速、移入集成区域、或经 `test-tiers.py allow-slow` 由人类放行）；
- 确认超线但在 `slow_allow` 里的用例，各给一条警告，带放行记录；
- 有任何触碰记录的用例，各给一条失败 `G11 impure unit test: <nodeid> …`，写明触碰类别与样例；
- 本次运行不可度量时，只给一条警告 `G10/G11 不可度量：<原因>`，不判红。

#### Scenario: slow-unit-test-confirmed-is-red
- **GIVEN** 单元层记录里 `tests/unit/test_a.py::test_big` 首跑 3.4 秒，单独重跑 3.3 秒，`slow_allow` 为空
- **WHEN** slice-gate 判定单元层
- **THEN** 失败里有一条以 `G10` 开头、点名 `tests/unit/test_a.py::test_big`，含 3.4 与 3.3

#### Scenario: slow-unit-test-not-confirmed-on-rerun-passes
- **GIVEN** 单元层记录里 `tests/unit/test_a.py::test_jitter` 首跑 3.1 秒，单独重跑 0.2 秒
- **WHEN** slice-gate 判定单元层
- **THEN** 没有任何 `G10` 失败

#### Scenario: allowed-slow-unit-test-is-warning
- **GIVEN** `tests/unit/test_a.py::test_big` 首跑 3.4 秒、重跑 3.3 秒；`slow_allow` 里有它，`approved` 是 `2026-10-28T08:00:00Z · 放行 test_big`
- **WHEN** slice-gate 判定单元层
- **THEN** 没有任何 `G10` 失败
- **AND** 警告里有一条点名 `tests/unit/test_a.py::test_big` 并含 `2026-10-28T08:00:00Z`

#### Scenario: impure-unit-test-is-red
- **GIVEN** 单元层记录里 `tests/unit/test_a.py::test_io` 碰了「文件」，样例是 `open /tmp/x`
- **WHEN** slice-gate 判定单元层
- **THEN** 失败里有一条以 `G11` 开头、点名 `tests/unit/test_a.py::test_io`，含 `open /tmp/x`

#### Scenario: unmeasurable-unit-run-only-warns
- **GIVEN** 单元层运行不可度量，原因是「没有探针输出」
- **WHEN** slice-gate 判定单元层
- **THEN** 没有任何 `G10` 或 `G11` 失败
- **AND** 恰有一条警告以 `G10/G11 不可度量` 开头并含「没有探针输出」

### Requirement: baseline、final、preflight 按分层运行
分层文件存在时，baseline、final、preflight SHALL 按下面的方式运行：

- **baseline** SHALL：
  - 分层文件或区域选择不合法时停下，不写运行标记、不碰现有 `gate-baseline.json`；
  - 不走增量复用（与 `--full` 相同）；
  - 以探针方式运行 `gate.test`（即单元层），按上一条 Requirement 判 G10 / G11，任一失败即基线红；在 `gate-baseline.json` 记 `tiers`：`{"measured": true}`，或 `{"measured": false, "why": <原因>}`；
  - 在每片 verify 之后、`gate.checks` 之前，逐个运行 `gate.integration` 里区域的 `cmd`，按 junit 记 `regions.<区域名> = {exit, sec, cmd[, failed]}`：可度量的红记预存红并警告，不可度量的红即基线红；
  - 不运行未选区域。
- **final** SHALL 在 G7 绿时：单元层按基线差分并判 G10 / G11；再逐个已选区域——基线没有它的记录、或记录的 `cmd` 与分层文件当前命令不同时，失败 `G2 region <区域名>：基线缺记录或命令已变，重跑 baseline`；否则按它的基线失败逐条差分，新增失败记 `G2 region <区域名>: …`。G7 红时不跑单元层与区域并给警告（与现状一致）。
- **preflight** SHALL 在已选区域缺基线记录、或记录的 `cmd` 与分层文件当前命令不同时报「基线过期」。

分层文件不存在时，baseline / final / preflight / gate 的行为与输出不变：不注入探针，`gate-baseline.json` 没有 `tiers` 与 `regions` 键。

#### Scenario: baseline-red-when-unit-test-impure
- **GIVEN** 分层文件合法；单元层里有一个在 `tmp_path` 写文件的用例 `tests/unit/test_u.py::test_writes`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0
- **AND** `gate-baseline.json` 的 `reasons` 里有一条以 `G11` 开头并点名 `tests/unit/test_u.py::test_writes`

#### Scenario: baseline-red-when-unit-test-slow
- **GIVEN** 分层文件合法、`slow_allow` 为空；单元层里有一个每次都睡 3.1 秒的纯函数用例 `tests/unit/test_u.py::test_sleepy`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0
- **AND** `gate-baseline.json` 的 `reasons` 里有一条以 `G10` 开头并点名 `tests/unit/test_u.py::test_sleepy`

#### Scenario: baseline-records-selected-regions-only
- **GIVEN** 分层文件有区域 `hooks` 与 `docs`，计划只选了 `hooks`；`hooks` 里有一个预存失败的用例；单元层全绿且纯
- **WHEN** 运行两次 `slice-gate.py baseline`
- **THEN** 两次都退出 0，`gate-baseline.json` 的 `mode` 都是 `full`
- **AND** `regions` 只有 `hooks`，它的 `failed` 含那个预存失败用例；`docs` 的命令一次都没有运行

#### Scenario: final-diffs-regions-against-baseline
- **GIVEN** 基线已记录区域 `hooks` 的预存失败 `test_old`；之后的提交让 `hooks` 里另一个用例 `test_new` 也失败
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出非 0
- **AND** `failed` 里有一条以 `G2 region hooks` 开头并点名 `test_new`，没有任何失败项点名 `test_old`

#### Scenario: final-red-on-new-impure-unit-test
- **GIVEN** 基线绿；之后的提交在单元层新增一个起子进程的用例 `tests/unit/test_u.py::test_spawns`
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出非 0
- **AND** `failed` 里有一条以 `G11` 开头并点名 `tests/unit/test_u.py::test_spawns`

#### Scenario: final-red-when-region-record-stale
- **GIVEN** 基线记录了区域 `hooks` 的结果；之后分层文件里 `hooks` 的 `cmd` 被改成另一条命令
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 退出非 0
- **AND** `failed` 里有一条以 `G2 region hooks` 开头并含「重跑 baseline」

#### Scenario: preflight-stale-when-region-cmd-changed
- **GIVEN** 基线绿且记录了区域 `hooks`；之后分层文件里 `hooks` 的 `cmd` 被改成另一条命令
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0
- **AND** stderr 含「基线过期」并点名 `hooks`

#### Scenario: no-tiers-file-gate-unchanged
- **GIVEN** openspec 根目录下没有 `test-tiers.json`；计划没有 `gate.integration`
- **WHEN** 运行 `slice-gate.py baseline`，再运行 `slice-gate.py final`
- **THEN** 两者都退出 0
- **AND** `gate-baseline.json` 没有 `tiers` 与 `regions` 键，final 的 `failed` 与 `warnings` 里都没有 `G10`、`G11`、`G12` 或 `G2 region` 项

### Requirement: 每次门禁分层报告耗时
分层文件存在时，跑测试的门禁子命令（`gate`、`baseline`、`final`）SHALL 在输出 JSON 里给出 `tier_sec`，并写进 `summary` 与 timeline 备注，让每次门禁都能看出单元层与集成层各花了多少秒：

- 形状 `{"unit": 秒, "integration": 秒, "regions": {区域名: 秒}}`，秒数保留 1 位小数；`integration` = `regions` 各项之和；有未归层用例的耗时时另加 `"unclassified": 秒`；
- 归层：按用例文件（nodeid 里 `::` 之前的部分）匹配分层文件的 `paths`；匹配到多层时取第一个（单元层优先，区域按名字排序）；
- 计入：
  - G7 实跑 scenario 测试时，每个用例的 setup + call + teardown 耗时，按归层累加；
  - baseline / final 里单元层运行（`gate.test`，含探针加载失败后的重跑与 G10 候选重跑）的墙钟，计入 `unit`；
  - 每个已选区域 `cmd` 运行的墙钟，计入该区域；
- 不计入：lint、typecheck、每片 verify、`gate.checks`；
- `summary` 末尾追加 `；单元 X.Xs · 集成 Y.Ys`；timeline 备注在结论词（`ok` / `red`）之前插入 `单元 X.Xs · 集成 Y.Ys`，结论词仍在末尾，飞行记录照常逐行打印；
- `preflight` 不跑测试，不报告。

分层文件不存在时，输出、`summary` 与 timeline 备注都不变（没有 `tier_sec` 键）。

#### Scenario: tier-seconds-split-by-file
- **GIVEN** 逐用例耗时为：单元层两个用例 0.5 秒与 0.3 秒（其中一个带参数后缀）、区域 `hooks` 一个 2.0 秒、区域 `docs` 一个 1.0 秒、不在任何层的 `tests/test_loose.py` 一个 0.1 秒
- **WHEN** 按分层文件归层累加
- **THEN** 单元 0.8 秒；集成 3.0 秒，其中 `hooks` 2.0、`docs` 1.0；未归层 0.1 秒

#### Scenario: slice-gate-reports-tier-seconds
- **GIVEN** 分层文件合法、计划选了区域 `hooks`；切片 S1 起跑后提交两个 scenario 测试：单元层用例睡 0.3 秒，`hooks` 的用例睡 0.6 秒
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** `tier_sec` 的单元不少于 0.25 秒且少于 0.6 秒，集成与 `regions.hooks` 都不少于 0.55 秒
- **AND** `summary` 含「单元」与「集成」；timeline 里 gate 那行的备注以 `S1` 开头、含「单元」与「集成」，仍以 `ok` 或 `red` 结尾

#### Scenario: baseline-and-final-report-tier-seconds
- **GIVEN** 分层文件合法、计划只选了区域 `hooks`；单元层用例睡 0.3 秒，`hooks` 的用例睡 0.6 秒，两者都是已去标记的 scenario 测试
- **WHEN** 运行 `slice-gate.py baseline`，再运行 `slice-gate.py final`
- **THEN** baseline 退出 0，`gate-baseline.json` 的 `tier_sec` 单元不少于 0.25 秒，`regions` 只有 `hooks` 且不少于 0.55 秒，集成等于 `regions` 之和
- **AND** final 输出的 `tier_sec` 单元不少于 0.25 秒、集成不少于 0.55 秒，`summary` 含「单元」与「集成」
- **AND** timeline 里 baseline 与 final 那两行的备注都含「单元」与「集成」

#### Scenario: no-tiers-file-no-tier-seconds
- **GIVEN** openspec 根目录下没有 `test-tiers.json`；计划没有 `gate.integration`；两个 scenario 测试已去标记
- **WHEN** 运行 `slice-gate.py baseline`，再运行 `slice-gate.py final`
- **THEN** `gate-baseline.json` 与 final 输出都没有 `tier_sec` 键
- **AND** final 的 `summary` 与 timeline 备注都不含「单元」

### Requirement: /test-tiers 的重划分脚本
`.claude/hooks/test-tiers.py` SHALL 提供：

- `probe [--cmd CMD] [--json PATH]`：在 git toplevel 以探针方式运行 `CMD`（缺省 `<当前解释器> -m pytest -q`）；stdout 每个测试文件一行：层级（单元 / 集成 / 混合）、单元与集成用例数、最慢耗时、一条触碰样例；末行写合计与耗时 ≥ 3 秒且无触碰的用例数；`--json` 写逐用例记录与按文件汇总；不可度量时退出 2。
- `check [--openspec-root DIR]`：在 git 跟踪的文件与未被忽略的未跟踪文件里，取文件名符合测试文件命名的；每个 SHALL 恰好匹配一层（`unit` 或某个区域）；有未归层或匹配多层的文件时逐个点名并退出 1；全部恰好一层时退出 0；分层文件缺失或不合法时退出 2。
- `allow-slow NODEID --reason TEXT [--openspec-root DIR] [--session PATH]`：按 takeoff-gate 的方式定位会话转录，取时间最新的一条人类消息（人类消息判据同 takeoff-gate）；它 SHALL 同时含 NODEID 的函数名（最后一个 `::` 之后、去掉参数化后缀 `[...]`）与放行词（放行、允许、allow、approve，不分大小写）。成立时写入 `slow_allow[NODEID] = {"reason": TEXT, "approved": "<ISO 时间> · <原话摘要>"}`，保留文件其余内容，退出 0；不成立或定位不到转录时退出 3，不改文件，stderr 写明原因。
- `render --probe PATH --plan PATH --out PATH`：plan 是 `{"tiers": <拟写入的分层文件内容>, "moves": {<源文件或 nodeid>: <目标文件>}}`；输出单文件 HTML：每个源、目标、目标所属层、探针证据；每层的用例数与耗时合计；问题清单（落点不属于恰好一层的用例、落进单元层却有触碰或耗时 ≥ 3 秒的用例）；导出按钮。有问题时 stderr 逐条列出并退出 1，否则退出 0。

#### Scenario: probe-cli-reports-file-tiers
- **GIVEN** 一个仓库有 `tests/test_pure.py`（只有纯函数用例）、`tests/test_io.py`（用例都写临时文件）、`tests/test_mixed.py`（一个纯函数、一个起子进程）
- **WHEN** 运行 `test-tiers.py probe --json out.json`
- **THEN** 退出 0；stdout 把三个文件分别标为「单元」「集成」「混合」
- **AND** `out.json` 的逐用例记录里 `tests/test_mixed.py` 的子进程用例带「子进程」样例，纯函数用例没有触碰

#### Scenario: check-flags-unclassified-and-ambiguous-files
- **GIVEN** `unit.paths` 是 `["tests/unit/**"]`，区域 `hooks` 的 `paths` 是 `["tests/integration/**", "tests/unit/test_both.py"]`；仓库里有 `tests/unit/test_a.py`、`tests/unit/test_both.py`、`tests/test_loose.py`
- **WHEN** 运行 `test-tiers.py check`
- **THEN** 退出 1
- **AND** 输出点名 `tests/test_loose.py`（未归层）与 `tests/unit/test_both.py`（匹配多层），不点名 `tests/unit/test_a.py`

#### Scenario: allow-slow-requires-latest-human-message
- **GIVEN** 会话转录里较早的一条人类消息是「放行 test_big，fixture 要读大样本」，最新的一条人类消息是「继续」
- **WHEN** 运行 `test-tiers.py allow-slow tests/unit/test_a.py::test_big --reason 读大样本`
- **THEN** 退出 3，分层文件不变
- **AND** 当最新一条人类消息改成「放行 test_big，fixture 要读大样本」后再运行同一命令，退出 0，`slow_allow` 里 `tests/unit/test_a.py::test_big` 的 `approved` 含该消息的时间与「放行 test_big」

#### Scenario: render-writes-approval-page
- **GIVEN** 一份探针结果含 `tests/test_mixed.py` 的纯函数用例与子进程用例；划分稿把纯函数用例移到 `tests/unit/test_mixed.py`、把子进程用例移到 `tests/integration/hooks/test_mixed.py`，`tiers` 里 `unit.paths` 是 `["tests/unit/**"]`、区域 `hooks` 的 `paths` 是 `["tests/integration/hooks/**"]`
- **WHEN** 运行 `test-tiers.py render --probe … --plan … --out page.html`
- **THEN** 退出 0；`page.html` 含两个目标路径与「导出」按钮
- **AND** 把子进程用例的目标改成 `tests/unit/test_mixed.py` 后再运行，退出 1，stderr 点名该用例

### Requirement: 文档写明分层规则与命令
文档 SHALL 写明：

- `template/.claude/commands/test-tiers.md`：`/test-tiers` 的步骤（probe → 起草划分 → render 审批页并等人类批准 → 搬文件与拆混合文件 → check 与用例数复核）、mini 留痕、放行慢单测的方式、门禁的分层耗时报告（`tier_sec`）；
- schema 的 tasks instruction：`gate.integration` / `gate.integration_skip`、分层文件存在时 `gate.test` 必须等于 `unit.cmd`、写 scenario 骨架前先定层；
- `opsx-propose` 命令与同名 skill：写骨架前先定层；配置了分层时 baseline 只跑单元层（带探针）与已选区域、不走增量；
- `opsx-verify` 命令与同名 skill：final 的区域差分、G10、G11；
- TDD skill：写测试前先定层，单元层 = 不碰真实文件 / 子进程 / 网络、每个用例含准备与清理 <3 秒；
- slice-executor：新测试先定层，G12；
- README：命令数 16 并列出 `/test-tiers`，测试分层一节；`install.sh` 的命令数提示同步；
- `CLAUDE.md.snippet`：一行指向分层规则。

#### Scenario: docs-describe-test-tiers
- **GIVEN** 本 change 的文档改动已完成
- **WHEN** 检查上述各文件
- **THEN** `test-tiers.md` 含 `test-tiers.py probe`、`render`、`check`、`allow-slow`、`/opsx-mini` 与 `tier_sec`
- **AND** schema 的 tasks instruction 含 `gate.integration`、`gate.integration_skip` 与 `unit.cmd`；propose 命令与同名 skill 都含「先定层」；verify 命令与同名 skill 都含 `G10` 与 `G11`
- **AND** TDD skill 含「先定层」与「3 秒」；slice-executor 含 `G12`；README 含 `/test-tiers` 与「16 个 slash 命令」；`install.sh` 含 `16 个 slash command`；`CLAUDE.md.snippet` 含 `test-tiers.json`
