## ADDED Requirements

### Requirement: 分层文件的部件形态由 lint 校验
分层文件 `<openspec 根>/test-tiers.json` 顶层含 `parts` 时为**部件形态**，否则为**简写形态**。简写形态的字段、校验与门禁行为 SHALL 与本 change 之前相同；简写形态里出现 `root` / `test_files` / `list` / `junit` / `probe` SHALL 按现有「未知字段」报错。

部件形态下，`slice-gate.py lint`（preflight 内同一份校验也一样）SHALL 在下面任一条不满足时退出非 0，stderr 每条违规以 `tiers:` 开头并点名对象：

- 顶层只含 `parts` 与 `slow_allow`；`parts` 不得与 `unit` / `regions` 同时出现；`parts` 是非空对象，部件名匹配 `^[a-z0-9-]+$`；
- 部件只含 `root`、`test_files`（可选）、`unit`、`regions`（可选）；
- `root` 是非空字符串、不以 `/` 开头、不含 `..` 段，且是 git 顶层下存在的目录（`.` 表示顶层）；
- `test_files` 缺省，或是非空数组、每项非空；
- `unit` 与每个区域恰有 `paths`、`list` 之一：`paths` 是非空数组、每项非空；`list` 是非空字符串；`cmd` 是非空字符串；`unit` 另可有 `junit`（非空字符串）与 `probe`；区域另须有 `covers`（数组，可为空）；
- 区域名匹配 `^[a-z0-9-]+$`，且在全部部件之间唯一；
- `probe` 只含 `cmd`、`canary`、`canary_files`、`sha`、`checked`；`cmd`、`canary` 非空，`canary_files` 是非空数组；没有 `sha` 或 `checked` 时报「未自检」；`sha` 里每个路径的文件 sha256 与记录不符或文件不存在时，报该路径并提示重跑 `test-tiers.py canary`；
- 在部件 `root` 下运行每个 `list` 命令（超时 60 秒），退出非 0 或超时 → 点名部件与层；输出每行一个相对 `root` 的路径，库补上 `root` 前缀后作为该层的文件集合；
- `gate.test` 去掉首尾空白后逐字等于 `python3 .claude/hooks/test-tiers.py run unit`；
- 计划不得有 `gate.impacted`；
- `gate.integration` / `gate.integration_skip` 与 `covers` 表态规则同简写形态，区域按全仓唯一的名字查找；
- `scenario_tests` 指向的每个测试文件 SHALL 落在某个部件的单元层，或某个已选区域。

`plan_sha` 的算法 SHALL 不变。

#### Scenario: parts-lint-rejects-mixed-shapes
- **GIVEN** 分层文件顶层同时有 `parts` 与 `unit`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头、同时含 `parts` 与 `unit`

#### Scenario: parts-lint-rejects-malformed-parts
- **GIVEN** 部件形态的分层文件里：部件名 `Api` 不合法；部件 `up` 的 root 是 `../out`；部件 `ghost` 的 root 是不存在的目录 `nope`；部件 `both` 的 `unit` 同时写了 `paths` 与 `list`；区域 `dup` 同时出现在部件 `both` 与 `odd` 里；部件 `odd` 带未知字段 `extra`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `tiers:` 开头的行分别点名 `Api`、`../out`、`nope`、`both`、`dup`、`extra`

#### Scenario: parts-lint-requires-driver-gate-test
- **GIVEN** 合法的部件形态分层文件；计划的 `gate.test` 是某个部件的 `unit.cmd`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头、含 `gate.test` 与 `test-tiers.py run unit`

#### Scenario: parts-lint-rejects-impacted
- **GIVEN** 合法的部件形态分层文件；计划的 `gate.test` 是驱动命令，另有 `gate.impacted`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `tiers:` 开头并含 `gate.impacted`

#### Scenario: parts-lint-resolves-list-selector
- **GIVEN** 部件 `go` 的 root 是 `svc/go`，单元层 `list` 命令在 root 下只输出 `a_test.go`；`scenario_tests` 一条映射到 `svc/go/a_test.go::TestA`，另一条映射到 `svc/go/b_test.go::TestB`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** 以 `tiers:` 开头的行恰有一行点名 `svc/go/b_test.go`，没有一行点名 `svc/go/a_test.go`
- **WHEN** 把该 `list` 命令改成退出 1，再运行 `slice-gate.py lint`
- **THEN** stderr 有一行以 `tiers:` 开头、含 `go` 与 `list`

#### Scenario: parts-lint-requires-self-checked-adapter
- **GIVEN** 部件 `py` 的 `unit.probe` 写了 `cmd`（运行仓库内脚本 `svc/py/probe.py`）、`canary`、`canary_files`，没有 `sha` 与 `checked`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** stderr 有一行以 `tiers:` 开头、含 `py` 与「未自检」
- **WHEN** 补上 `checked` 与正确的 `sha`（`{"svc/py/probe.py": <该文件 sha256>}`）后运行 lint
- **THEN** 退出 0
- **WHEN** 再改动 `svc/py/probe.py` 的内容后运行 lint
- **THEN** stderr 有一行以 `tiers:` 开头、含 `svc/py/probe.py` 与 `canary`

#### Scenario: parts-lint-accepts-valid-parts-plan
- **GIVEN** 合法的部件形态分层文件（部件 `go` 用 `list`、带区域 `go-db`；部件 `py` 用 `paths` 与 `test_files`）；`gate.test` 是驱动命令；`gate.integration` 是 `["go-db"]`；`scenario_tests` 指向两个部件的单元层与区域 `go-db` 里的文件
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0

#### Scenario: shorthand-tiers-unchanged
- **GIVEN** 简写形态的合法分层文件，`gate.test` 等于 `unit.cmd`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0
- **WHEN** 在简写形态的 `unit` 里加上 `list`
- **THEN** lint 退出非 0，stderr 有一行以 `tiers:` 开头、含 `未知字段`

### Requirement: 部件形态下测试文件恰属一个部件、恰落一层（G12）
部件形态下，部件 P 的测试文件集合 SHALL 是：P 写了 `test_files` 时为匹配它的文件；否则为 P 的 `root` 下匹配内置命名的文件。内置命名 SHALL 在 `TEST_FILE_RE` 之外另认：

- Go：`*_test.go`；
- JVM：`*Test.java`、`*Tests.java`、`*IT.java`（`.kt` 同）；
- C#：`*Tests.cs`、`*Test.cs`；
- Ruby：`*_spec.rb`、`test_*.rb`、`*_test.rb`；
- Rust：部件 root 下 `tests/` 目录里的 `*.rs`。

匹配任一部件 `probe.canary_files` 的文件 SHALL 被排除在外。

`slice-gate.py gate` 的 G12 在部件形态下 SHALL 对本切片区间改动且仍存在、且属于全仓测试文件（匹配内置命名或任一部件的 `test_files`）的文件逐个判定，下面任一情况报一条 `G12 tiers:` 失败并点名文件：

- 不属于任何部件；
- 属于某部件，但不在该部件单元层，也不在任何已选区域内。

#### Scenario: gate-flags-file-outside-parts
- **GIVEN** 部件形态：部件 `py`（root `svc/py`，`test_files` 是 `svc/py/tests/**/test_*.py`，单元层 `svc/py/tests/unit/**`）；计划没选区域；切片区间里新增了 `svc/py/tests/unit/test_ok.py`、`svc/py/tests/integration/test_i.py` 与 `tools/x_test.go`
- **WHEN** 对该切片运行 `slice-gate.py gate`
- **THEN** `failed` 里有一条 `G12 tiers:` 点名 `svc/py/tests/integration/test_i.py`，一条 `G12 tiers:` 点名 `tools/x_test.go`
- **AND** 没有 `G12` 条目点名 `svc/py/tests/unit/test_ok.py`

### Requirement: 部件运行器在 root 下运行并把结果换成顶层坐标
slice-gate SHALL 提供部件运行器，在 `<git 顶层>/<root>` 下运行部件的单元层，并：

- 设 `FLIGHT_JUNIT` 为一个临时文件路径；
- 部件写了 `probe` 时，改为运行 `probe.cmd`，传 `FLIGHT_UNIT_CMD` = 要跑的测试命令与 `FLIGHT_TIER_OUT`；适配器的退出码作为本次运行的退出码；
- 部件没写 `probe` 时，注入内置 pytest 探针，探针记录相对 git 顶层的用例 id；
- 返回结果中的逐用例耗时 `secs` 依次取自：探针记录的 `sec`、`$FLIGHT_JUNIT`、`unit.junit` 匹配且修改时间不早于本次运行开始的文件；
- junit 的 testcase 带 `file` 属性时 id 为 `<root>/<file>::<name>`，否则为 `<部件名>::<classname>::<name>`；
- 适配器记录的 nodeid（相对 root）SHALL 被补上 `root` 前缀；
- pytest 部件的可度量判定与失败用例集 SHALL 与 `run_test_gate` 相同。

#### Scenario: part-runs-in-root-with-junit
- **GIVEN** 部件 `sh`（root `svc/sh`）的单元命令把当前目录写进标记文件，并往 `$FLIGHT_JUNIT` 写两个 testcase：`classname="pkg" name="TestA" time="0.5"`，以及 `file="a_test.go" name="TestB" time="0.25"`
- **WHEN** 部件运行器运行该部件
- **THEN** 退出码为 0，标记文件记录的目录是 `svc/sh`
- **AND** `secs` 恰为 `{"sh::pkg::TestA": 0.5, "svc/sh/a_test.go::TestB": 0.25}`

#### Scenario: part-reads-fresh-junit-glob-only
- **GIVEN** 部件 `sh` 的 `unit.junit` 是 `reports/*.xml`；`svc/sh/reports/old.xml` 是一天前的报告，含 `TestOld`；单元命令写出 `reports/new.xml`，含 `TestNew`，且不写 `$FLIGHT_JUNIT`
- **WHEN** 部件运行器运行该部件
- **THEN** `secs` 含 `TestNew` 的 id，不含 `TestOld` 的 id

#### Scenario: adapter-wraps-unit-cmd
- **GIVEN** 部件 `sh`（root `svc/sh`）写了 `probe.cmd`；适配器执行 `$FLIGHT_UNIT_CMD`（单元命令以 3 退出），并往 `$FLIGHT_TIER_OUT` 写开跑记录、`a_test.go::TestA`（无触碰，0.1 秒）、`b_test.go::TestB`（文件触碰，0.2 秒）
- **WHEN** 部件运行器运行该部件
- **THEN** 退出码为 3
- **AND** 探针结果的 id 恰为 `svc/sh/a_test.go::TestA` 与 `svc/sh/b_test.go::TestB`，后者带「文件」触碰
- **AND** `secs` 取自探针记录

#### Scenario: builtin-probe-ids-from-toplevel
- **GIVEN** 部件 `py`（root `svc/py`，`pytest.ini` 在 `svc/py`，没写 `probe`）；单元层 `tests/unit/test_p.py` 有纯函数用例 `test_pure` 与读文件的用例 `test_touch`
- **WHEN** 部件运行器带探针运行该部件
- **THEN** 探针结果的 id 恰为 `svc/py/tests/unit/test_p.py::test_pure` 与 `svc/py/tests/unit/test_p.py::test_touch`
- **AND** 只有后者带「文件」触碰

### Requirement: 逐部件判定 G10 与 G11
部件形态下，每个部件的单元层运行后 SHALL 按下面的规则判定，所有文本都带「部件 <名字>」：

- **G11**：探针可度量时，带触碰的用例各报一条 `G11 impure unit test` 失败；不可度量时给一条警告 `G11 不可度量：部件 <P>：<原因>`。
- **G10**：有逐用例耗时时，耗时 ≥ 3 秒的为候选；有候选时整部件单元层重跑一次，重跑耗时仍 ≥ 3 秒或重跑没有该 id 才确认。确认的候选在 `slow_allow` 里时给警告（带 `approved`），否则报一条 `G10 slow unit test` 失败。没有逐用例耗时时给警告 `G10 不可度量：部件 <P>：<原因>`。
- G10 与 G11 都不可度量时，SHALL 合成一条警告 `G10/G11 不可度量：部件 <P>：<原因>`。

#### Scenario: part-g10-confirmed-by-rerun
- **GIVEN** 部件 `go` 没有探针结果，junit 耗时：`TestSlow` 3.4 秒、`TestFast` 0.1 秒、`TestFlaky` 3.1 秒、`TestOk` 3.2 秒；整部件重跑耗时：`TestSlow` 3.5 秒、`TestFlaky` 0.4 秒、`TestOk` 3.3 秒；`slow_allow` 含 `TestOk` 的 id
- **WHEN** 判定该部件的 G10 / G11
- **THEN** 失败恰有一条，是点名 `TestSlow`、含「部件 go」的 `G10 slow unit test`
- **AND** 警告含一条点名 `TestOk` 的已放行 G10，以及一条 `G11 不可度量：部件 go`
- **AND** 失败与警告都不提 `TestFlaky`

#### Scenario: part-g11-and-unmeasurable-warnings
- **GIVEN** 部件 `py` 的探针结果里 `svc/py/x_test.py::test_net` 有「网络」触碰；部件 `go` 既没有探针结果也没有逐用例耗时
- **WHEN** 分别判定两个部件
- **THEN** `py` 的失败有一条 `G11 impure unit test`，含「部件 py」与「网络」
- **AND** `go` 没有失败，警告恰有一条，以 `G10/G11 不可度量：部件 go` 开头

### Requirement: baseline / final / preflight 逐部件运行
部件形态下，baseline / final / preflight SHALL 逐部件运行与对账，规则如下：

- baseline 与 final SHALL 不执行 `gate.test`，改为逐部件运行单元层。
- **baseline** SHALL：
  - 记 `test.parts.<P> = {exit, sec, cmd[, failed]}`：可度量的 pytest 红记 `failed` 并警告；不可度量的红进 `reasons`，文本含「部件 <P>」；
  - 逐部件判 G10 / G11，失败进 `reasons`；
  - 在区域所属部件的 root 下运行已选区域；
  - 输出与 `gate-baseline.json` 的 `tier_sec` 增加 `parts.<P>.unit` 与 `parts.<P>.integration`。
- **final** SHALL：
  - 在 G7 绿时逐部件运行；
  - 基线缺 `test.parts.<P>` 或记录的 `cmd` 与当前 `unit.cmd` 不同 → `G2 part <P>：基线缺记录或命令已变，重跑 baseline`；
  - 否则按基线 `failed` 差分（标签 `part <P>`），再判 G10 / G11；
  - `incremental.mode` 恒为 `full`，`full_why` 含「多部件」。
- **preflight** SHALL 在基线各部件记录的 `cmd` 与当前 `unit.cmd` 不一致、或部件集合不一致时，报「基线过期」并点名部件。
- 简写形态与没有分层文件时，三者行为与输出 SHALL 不变。

#### Scenario: baseline-runs-each-part-and-reports-part-seconds
- **GIVEN** 部件 `py`（root `svc/py`，pytest，单元层全绿且纯）与部件 `sh`（root `svc/sh`，脚本写 junit 并记录当前目录）；`gate.test` 是驱动命令（被测仓库里没有 `test-tiers.py`）
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 基线 `ok` 为真
- **AND** `test.parts` 恰有 `py` 与 `sh`，各自的 `cmd` 等于分层文件里的 `unit.cmd`、`exit` 为 0
- **AND** `sh` 的命令在 `svc/sh` 下运行
- **AND** `tier_sec.parts` 有 `py` 与 `sh`，各含 `unit`

#### Scenario: baseline-records-part-preexisting-red
- **GIVEN** 同上的两个部件，`py` 单元层有一个失败用例 `test_old`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 基线 `ok` 为真，`test.parts.py.failed` 含 `test_old`
- **WHEN** 让 `sh` 的单元命令以 1 退出后重跑 baseline
- **THEN** 基线 `ok` 为假，`reasons` 有一条含「部件 sh」

#### Scenario: baseline-red-on-impure-part-unit
- **GIVEN** 同上的两个部件，`py` 单元层有一个读文件的用例
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 基线 `ok` 为假，`reasons` 有一条 `G11 impure unit test`，含「部件 py」

#### Scenario: final-diffs-each-part
- **GIVEN** 基线记录了 `py` 的预存红 `test_old`；之后 `py` 单元层新增失败用例 `test_new` 并提交
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `failed` 有一条 `G2 part py`，点名 `test_new`、不点名 `test_old`
- **AND** `incremental.mode` 是 `full`，`full_why` 含「多部件」

#### Scenario: final-red-when-part-record-stale
- **GIVEN** 基线建立后，分层文件里部件 `sh` 的 `unit.cmd` 被改动并提交
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `failed` 有一条 `G2 part sh`，含「重跑 baseline」

#### Scenario: preflight-stale-when-part-cmd-changed
- **GIVEN** 基线建立后，分层文件里部件 `sh` 的 `unit.cmd` 被改动并提交
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0，stderr 含「基线过期」与「部件 sh」

### Requirement: test-tiers.py 的驱动、检查与金丝雀自检
`test-tiers.py` SHALL 提供：

- **`run unit [--part P]`**：在每个部件的 root 下依次运行其 `unit.cmd`（简写形态视作 root 为 `.` 的单个部件），每个部件打印一行「部件 <P>：exit <N> · <秒>s」；全部为 0 时退出 0，否则退出 1；分层文件缺失或不合法时退出 2。
- **`check`**：部件形态下逐个点名问题文件，有问题时退出 1：
  - 「不属于任何部件：<文件>」；
  - 「属于多个部件：<文件>（<部件…>）」；
  - 「未归层：<文件>」与「匹配多层：<文件>」（在所属部件内判）；
  - 金丝雀文件不参与。
- **`canary (--part P | --root DIR --adapter CMD --canary CMD)`**：
  - 生成随机令牌 T 与临时目录 D，在 root 下运行适配器；`FLIGHT_UNIT_CMD` = 金丝雀命令，另设 `FLIGHT_CANARY_TOKEN` = T、`FLIGHT_CANARY_DIR` = D、`FLIGHT_TIER_OUT`、`FLIGHT_JUNIT`。
  - 通过条件（全部满足）：
    - 有开跑记录；
    - 名字（去掉非字母数字、转小写）分别含 `flightcanarypure` / `flightcanaryfile` / `flightcanaryproc` / `flightcanarynet` 的四个用例都有记录；
    - pure 无触碰；
    - file 有「文件」触碰且样例含 T，并且 `D/T` 存在；
    - proc 有「子进程」触碰；
    - net 有「网络」触碰。
  - 通过时：`--part` 模式把 `probe.sha`（`probe.cmd` 里每个解析为仓库内文件的词 → sha256）与 `probe.checked` 写回分层文件，其余内容原样保留，退出 0。
  - 不通过时：逐条打印未满足的条件，不改文件，退出 1。
  - `probe.cmd` 里没有仓库内文件时退出 2。
- **`probe --root DIR --cmd CMD [--adapter CMD]`**：在 DIR 下运行；有 `--adapter` 时按适配器契约运行；输出与 `--json` 里的用例与文件路径都相对 git 顶层。

#### Scenario: driver-runs-every-part
- **GIVEN** 部件形态：部件 `a`（root `a`）的单元命令在当前目录写标记文件并退出 0；部件 `b`（root `b`）的单元命令退出 1
- **WHEN** 在仓库里运行 `test-tiers.py run unit`
- **THEN** 退出 1
- **AND** stdout 有一行含「部件 a」与「exit 0」，一行含「部件 b」与「exit 1」
- **AND** 标记文件出现在 `a/` 下

#### Scenario: check-parts-membership
- **GIVEN** 部件形态：
  - 部件 `py`：root `svc/py`，`test_files` 是 `svc/py/**/test_*.py`，单元层 `svc/py/tests/unit/**`；
  - 部件 `go`：root `svc/go`，单元层 `svc/go/**`，`probe.canary_files` 是 `svc/go/canary/**`；
  - 部件 `js` 与 `js2`：root 都是 `web`，都没写 `test_files`。
  - 仓库里有 `svc/py/tests/unit/test_a.py`、`svc/py/tests/it/test_b.py`、`svc/go/x_test.go`、`svc/go/canary/canary_test.go`、`tools/y_test.go`、`web/a.test.ts`。
- **WHEN** 运行 `test-tiers.py check`
- **THEN** 退出 1
- **AND** stdout 含「不属于任何部件：tools/y_test.go」「属于多个部件：web/a.test.ts」「未归层：svc/py/tests/it/test_b.py」
- **AND** 没有一行提到 `canary_test.go`、`x_test.go` 或 `test_a.py`

#### Scenario: canary-accepts-adapter-and-records-sha
- **GIVEN** 部件 `go`（root `svc/go`）的 `probe.cmd` 运行仓库内脚本 `svc/go/adapter.py`；该适配器执行 `$FLIGHT_UNIT_CMD`（金丝雀命令写出 `$FLIGHT_CANARY_DIR/$FLIGHT_CANARY_TOKEN`），并如实报出四个金丝雀用例的触碰（file 的样例含令牌）
- **WHEN** 运行 `test-tiers.py canary --part go`
- **THEN** 退出 0
- **AND** 分层文件里该部件的 `probe.sha` 恰为 `{"svc/go/adapter.py": <该文件 sha256>}`，`probe.checked` 非空，其余键不变

#### Scenario: canary-rejects-incomplete-adapter
- **GIVEN** 同上，但适配器不执行 `$FLIGHT_UNIT_CMD`，并且不报 net 用例的「网络」触碰
- **WHEN** 运行 `test-tiers.py canary --part go`
- **THEN** 退出 1
- **AND** stdout 含「网络」与「落盘」
- **AND** 分层文件内容与运行前逐字节相同

#### Scenario: probe-cli-adapter-prefixes-root
- **GIVEN** 目录 `svc/go` 下有适配器脚本，它为 `a_test.go::TestA` 写一条无触碰记录
- **WHEN** 运行 `test-tiers.py probe --root svc/go --cmd <命令> --adapter <适配器命令> --json <路径>`
- **THEN** 退出 0
- **AND** stdout 有一行以「单元」开头并含 `svc/go/a_test.go`
- **AND** JSON 的 `tests` 恰有键 `svc/go/a_test.go::TestA`

### Requirement: 文档写明部件形态与两种契约
`/test-tiers` 命令文档 SHALL 写明：

- 部件形态：`parts` / `root` / `test_files` / `paths` / `list`；
- 驱动命令 `test-tiers.py run unit`；
- JUnit 契约 `FLIGHT_JUNIT` / `unit.junit`；
- 探针适配器契约 `FLIGHT_UNIT_CMD` / `FLIGHT_TIER_OUT`；
- 金丝雀自检（`canary`、四个用例的命名、`FLIGHT_CANARY_TOKEN` / `FLIGHT_CANARY_DIR`）与 sha 锁定；
- 多部件发现步骤与「未覆盖」清单。

schema tasks instruction、`opsx-propose` 命令与同名 skill SHALL 写明「部件形态下 `gate.test` 写驱动命令」。README 与 `CLAUDE.md.snippet` SHALL 提到部件形态。

#### Scenario: docs-describe-parts
- **GIVEN** 本 change 的文档改动已完成
- **WHEN** 检查各文档
- **THEN** `test-tiers.md` 含 `parts`、`root`、`test_files`、`list`、`FLIGHT_JUNIT`、`FLIGHT_UNIT_CMD`、`FLIGHT_CANARY_TOKEN`、`canary`、`run unit`、「金丝雀」、「未覆盖」
- **AND** `schema.yaml`、`opsx-propose.md`、`openspec-propose/SKILL.md` 都含 `test-tiers.py run unit`
- **AND** `README.md` 含「部件」与 `canary`；`CLAUDE.md.snippet` 含 `parts`
