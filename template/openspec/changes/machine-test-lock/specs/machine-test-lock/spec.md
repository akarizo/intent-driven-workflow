## ADDED Requirements

### Requirement: 全机测试锁区分独占与共享
`flight-lock.py` SHALL 在锁目录（缺省 `~/.claude/flight-lock/`，环境变量 `FLIGHT_LOCK_DIR` 可改）下提供一把跨仓库、跨 worktree 共用的读写锁：独占持有与任何其他持有互斥，共享持有之间可以并存。有独占方在排队时，后来的共享方 MUST NOT 先于它拿到锁。持有者 SHALL 把方式、change、命令标签、pid 与起始时间写在锁目录里；排队方 SHALL 在第一次没拿到锁时立刻往 stderr 打印一行含「排队中」与持有者标签的提示，之后每 30 秒一行。持有进程退出（含被杀）后锁 MUST 自动释放。`flight-lock.py run <exclusive|shared> -- <命令>` SHALL 取锁后运行命令、以命令的退出码退出，并在 stderr 末尾打印一行 `flight-lock: <JSON>` 给出本次的方式、状态与排队秒数；`flight-lock.py status --json` SHALL 列出在世的持有者。
Feature: 一台机器同一时刻只有一套满核并行的测试
Rule: 独占排队、共享并存；锁跟着门禁进程走，进程没了锁就没了

#### Scenario: exclusive-holders-mutually-exclude
- **GIVEN** 进程 A 经 `flight-lock.py run exclusive` 持有锁，命令尚未结束
- **WHEN** 进程 B 以同一锁目录运行 `flight-lock.py run exclusive -- <命令>`
- **THEN** B 的 stderr 出现含「排队中」与 A 的标签的一行，B 的命令没有开始
- **AND** A 结束后 B 的命令才运行，B 以命令的退出码退出
- **AND** B 的 `flight-lock:` 行里状态为 `held`、排队秒数大于 0

#### Scenario: shared-holders-run-together
- **GIVEN** 进程 A 经 `flight-lock.py run shared` 持有锁，命令尚未结束
- **WHEN** 进程 B 以同一锁目录运行 `flight-lock.py run shared -- <命令>`
- **THEN** A 还没结束时 B 的命令已经开始运行

#### Scenario: exclusive-waiter-blocks-new-shared
- **GIVEN** 进程 A 持有共享锁；进程 X 请求独占并已在排队
- **WHEN** 进程 C 请求共享
- **THEN** C 的命令没有开始，C 的 stderr 出现「排队中」
- **AND** A 结束后 X 的命令先运行；X 结束后 C 的命令才运行

#### Scenario: killed-holder-releases-lock
- **GIVEN** 进程 A 持有独占锁，进程 B 请求独占并在排队
- **WHEN** A 的 `flight-lock.py` 进程被 SIGKILL 杀掉
- **THEN** B 的命令随即运行
- **AND** `flight-lock.py status --json` 不再列出 A

#### Scenario: status-lists-live-holders
- **GIVEN** 进程 A 以 `--change demo --label "final gate"` 持有独占锁
- **WHEN** 运行 `flight-lock.py status --json`
- **THEN** 输出的持有者列表恰有一项，方式为 `exclusive`，change 为 `demo`，标签为 `final gate`，pid 为 A 的 pid

### Requirement: 持锁期间的子进程不再排队
持有锁的进程 SHALL 给它启动的子进程带上重入标记（环境变量 `FLIGHT_LOCK_HELD`，含锁目录）；带着同一锁目录的重入标记请求锁的进程 MUST NOT 等待，状态记为 `nested`。标记里的锁目录与当前锁目录不同 → 不算重入，照常取锁。本仓测试套件 SHALL 经 `tests/conftest.py` 把 `FLIGHT_LOCK_DIR` 指到本次会话的临时目录，使测试里启动的门禁不去排用户级目录里的锁。
Feature: 被测进程里再调门禁不会自己等自己
Rule: 重入只认同一把锁；测试套件用自己的锁目录

#### Scenario: nested-run-does-not-wait
- **GIVEN** 外层 `flight-lock.py run exclusive -- <命令>`，其命令是以同一锁目录再次运行 `flight-lock.py run exclusive -- <内层命令>`
- **WHEN** 外层运行
- **THEN** 内层命令运行完成，外层以 0 退出
- **AND** 内层的 `flight-lock:` 行里状态为 `nested`、排队秒数为 0

#### Scenario: test-suite-uses-isolated-lock-dir
- **GIVEN** 本仓的 pytest 会话
- **WHEN** 测试读取环境变量 `FLIGHT_LOCK_DIR`
- **THEN** 它指向一个存在的目录，且不在用户主目录的 `.claude` 之下

### Requirement: 锁不可用或持有者停滞时不加锁继续
排队方 SHALL 在最早的在世持有者持锁时间超过该持有者声明的上限时放弃等待，状态记为 `timeout`，随后不加锁运行。上限由持有者在取锁时声明：设了 `FLIGHT_LOCK_MAX_HOLD_SEC` 取它；否则为持有者上次全量耗时的 3 倍且不低于 300 秒；没有耗时记录时为 1800 秒。`FLIGHT_LOCK=off` 时 MUST NOT 取锁，状态记为 `off`。平台没有 `flock`、锁目录不可创建或不可写时状态记为 `unavailable` 并带原因。这三种状态下命令 MUST 照常运行，退出码 MUST 只取决于命令本身。
Feature: 锁坏了或有人占着不放，门禁照样能跑
Rule: 锁自身的任何问题都不让命令失败；没拿到锁要留下原因

#### Scenario: waiter-gives-up-on-stalled-holder
- **GIVEN** 进程 A 以 `FLIGHT_LOCK_MAX_HOLD_SEC=0.3` 持有独占锁且一直不结束
- **WHEN** 进程 B 以同一锁目录运行 `flight-lock.py run exclusive -- <以 7 退出的命令>`
- **THEN** B 在 A 仍持有时运行了它的命令，并以 7 退出
- **AND** B 的 `flight-lock:` 行里状态为 `timeout`，原因点名 A 的标签

#### Scenario: lock-off-or-unavailable-runs-unlocked
- **GIVEN** 进程 A 持有独占锁
- **WHEN** 进程 B 带 `FLIGHT_LOCK=off` 运行 `flight-lock.py run exclusive -- <命令>`；另一次把 `FLIGHT_LOCK_DIR` 指到一个普通文件之下的路径再运行
- **THEN** 两次的命令都立即运行、以命令的退出码退出
- **AND** 第一次状态为 `off`；第二次状态为 `unavailable` 且原因非空

### Requirement: 门禁各命令按方式持锁
`slice-gate.py baseline` 与 `final` SHALL 在运行第一条测试命令之前取**独占**锁、在最后一项检查结束之后释放（同树沿用的 final 不运行任何测试，不取锁）；`slice-gate.py gate` SHALL 从运行 verify 之前到 G7 结束之后持**共享**锁；`test-tiers.py run` 与 `probe` SHALL 整个运行期间持**独占**锁。这些命令的输出 JSON（`baseline` 另写进 `gate-baseline.json`）SHALL 带 `lock` 字段：`mode`、`state`、`waited`（排队秒数）、`why`、`load`（起止负载，取不到为 null）、`cores`。`flight-lock.py` 缺失或加载失败时门禁 MUST 照常运行，`lock.state` 为 `unavailable`。
Feature: 全量类运行排队，切片 verify 并行
Rule: 整段测量只排一次队；锁只加在调用点，判定逻辑不动

#### Scenario: baseline-and-final-hold-exclusive-lock
- **GIVEN** 一个有计划、测试全绿的仓库，锁目录里没有其他持有者
- **WHEN** 依次运行 `slice-gate.py baseline` 与 `slice-gate.py final`
- **THEN** 两次输出 JSON 的 `lock.mode` 都是 `exclusive`、`lock.state` 都是 `held`、`lock.waited` 是数字
- **AND** `gate-baseline.json` 里有同样的 `lock` 字段

#### Scenario: slice-gate-holds-shared-lock
- **GIVEN** 同一个仓库，切片 S1 已 `start`
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 输出 JSON 的 `lock.mode` 是 `shared`、`lock.state` 是 `held`

#### Scenario: final-queues-behind-exclusive-holder
- **GIVEN** 另一个进程在同一锁目录持有独占锁
- **WHEN** 运行 `slice-gate.py final`
- **THEN** final 的 stderr 出现「排队中」，持有者结束之前 final 不结束
- **AND** 持有者结束后 final 以 0 退出，`lock.waited` 大于 0

#### Scenario: gate-runs-when-lock-module-missing
- **GIVEN** 一份不含 `flight-lock.py` 的 hooks 目录副本
- **WHEN** 用副本里的 `slice-gate.py` 运行 baseline
- **THEN** baseline 以 0 退出，`lock.state` 是 `unavailable`

#### Scenario: test-tiers-run-and-probe-hold-exclusive-lock
- **GIVEN** 一个有分层文件的仓库，另一个进程在同一锁目录持有独占锁
- **WHEN** 分别运行 `test-tiers.py run unit` 与 `test-tiers.py probe`
- **THEN** 两次的 stderr 都出现「排队中」，持有者结束之前都不结束
- **AND** 持有者结束后两次都以 0 退出

### Requirement: 争抢时时间类判定降为警告
`lock.state` 为 `timeout` 的 baseline 或 final 里，G10 慢单测 SHALL 由失败降为警告，警告文字 SHALL 保留原判定内容并写明因放弃等待而降级；G11 及其他判定 MUST 不变。`lock.state` 为 `held`、`nested`、`off` 或 `unavailable` 时 G10 MUST 照常判定。
Feature: 只有确知有人同时在跑的那一次，秒数才不作数
Rule: 降级只针对时间；关掉锁或平台不支持不等于放宽

#### Scenario: contended-run-downgrades-slow-unit-verdict
- **GIVEN** 分层文件合法、单元层有一个每次睡 3.1 秒的纯函数用例；另一个进程以 `FLIGHT_LOCK_MAX_HOLD_SEC=0.3` 持有独占锁且不结束
- **WHEN** 以同一锁目录运行 `slice-gate.py baseline`
- **THEN** baseline 以 0 退出，`lock.state` 是 `timeout`
- **AND** `reasons` 里没有 G10；`warnings` 里有一条同时含 `G10`、该用例的 id 与「降为警告」

#### Scenario: lock-off-keeps-slow-unit-verdict
- **GIVEN** 同样的仓库
- **WHEN** 带 `FLIGHT_LOCK=off` 运行 `slice-gate.py baseline`
- **THEN** `lock.state` 是 `off`，baseline 以非 0 退出，`reasons` 里有一条以 G10 开头并点名该用例

### Requirement: 时间线记录排队、负载与收口各项耗时
baseline、final、gate 的时间线备注 SHALL 带锁片段：持锁时为「排队 <秒>s」，放弃等待时为「排队 <秒>s 后放弃（<原因>）」，未加锁时为「未加锁（<原因>）」，重入时为「重入」；取得到负载时其后接「 · 负载 <起>→<止>/<核数>」。final 实际运行了 gate.test（全量、增量或 `gate.impacted`）时，输出 JSON SHALL 带 `sec.test`，备注 SHALL 带「测试 <秒>s」；运行了检查时 JSON SHALL 带 `sec.checks`（`{检查名: 秒}`），备注 SHALL 带「检查 <名> <秒>s」，多项以「 / 」分隔。final 与 gate 备注的结论词（`ok` / `red`）MUST 仍在末尾，gate 备注 MUST 仍以切片 id 开头，已有的「全量（…）」「增量（…）」「单元 …s · 集成 …s」文字 MUST 不变。
Feature: 慢了能看出慢在排队、测试还是检查
Rule: 备注只增不改；旧的解析方照常工作

#### Scenario: timeline-records-wait-and-load
- **GIVEN** 一个有计划、测试全绿的仓库，切片 S1 已 `start`
- **WHEN** 依次运行 baseline、`gate S1`、final
- **THEN** 三条时间线备注都匹配「排队 <数字>s」
- **AND** final 的备注以 ` ok` 结尾；gate 的备注以 `S1 ` 开头、以 ` ok` 或 ` red` 结尾
- **AND** 平台取得到负载时，三条备注都含「负载 」

#### Scenario: final-note-records-test-and-check-seconds
- **GIVEN** 计划配了一项检查 `probe-check`，baseline 已绿，之后有一处代码改动
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 输出 JSON 的 `sec.test` 是数字，`sec.checks` 恰含 `probe-check` 且值是数字
- **AND** final 的时间线备注匹配「测试 <数字>s」与「检查 probe-check <数字>s」，并以 ` ok` 结尾

### Requirement: 成本归因与体检读得到排队和收口耗时
`flight-doctor.py cost` SHALL 从 final 备注的「测试 <秒>s」取该次运行的秒数、从 baseline 与 final 备注的「排队 <秒>s」取排队秒数：全量 final 的秒数计入 `final.full_sec` 与对应 `full_runs` 项的 `sec`；`--json` 另给顶层 `wait_sec`（`{"baseline": 秒, "final": 秒}`），文本输出在各事件行写出排队秒数。`baseline` 与 `final` 两个对象已有的键 MUST 不增不减；没有这些片段的旧时间线 MUST 得到与改动前相同的结果。`flight-doctor.py doctor` SHALL 新增两节：`[checks]` 逐个在途 change 读最近一条 final 备注，某项检查的秒数不低于 10 秒且不低于「测试」秒数的一半时点名该 change 与检查并写明疑似在重跑测试；`[lock]` 列出当前在世的持有者（方式、change、标签、已持有秒数），没有时写「空闲」，`FLIGHT_LOCK=off` 时写明已关闭。两个子命令仍恒以 0 退出。
Feature: 收口的成本不再是 0，重跑测试的检查会被点名
Rule: 只读、只报告、不阻断

#### Scenario: cost-reads-final-seconds-and-wait
- **GIVEN** 一份时间线：一条旧格式的全量 baseline、一条带「排队 12.5s」的全量 baseline、一条带「测试 524.3s」与「排队 212.0s」的全量 final、一条带「测试 8.0s」的增量 final
- **WHEN** 运行 `flight-doctor.py cost --json` 与不带 `--json` 的 `cost`
- **THEN** `final.full_sec` 等于 524.3，对应 `full_runs` 项的 `sec` 等于 524.3
- **AND** `wait_sec` 等于 `{"baseline": 12.5, "final": 212.0}`
- **AND** `baseline` 与 `final` 两个对象的键集合都恰为 `full`、`incremental`、`full_sec`
- **AND** 文本输出的 final 一行含「排队 212.0 秒」

#### Scenario: doctor-flags-check-as-slow-as-tests
- **GIVEN** 在途 change `c1` 的最近一条 final 备注含「测试 100.0s · 检查 ratchet 95.0s / style 1.0s」
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** `[checks]` 一节点名 `c1` 与 `ratchet` 并含「重跑」
- **AND** 该节不出现 `style`

#### Scenario: doctor-reports-lock-holders
- **GIVEN** 一个进程以 `--change demo --label "final gate"` 在锁目录持有独占锁
- **WHEN** 以同一锁目录运行 `flight-doctor.py doctor`；持有者结束后再运行一次
- **THEN** 第一次的 `[lock]` 一节含 `demo` 与 `final gate`
- **AND** 第二次的 `[lock]` 一节含「空闲」

### Requirement: 随模板下发全机测试锁的说明
`template/.claude/flight-runner-contract.md` SHALL 新增一节说明全机测试锁：独占与共享各用在哪些命令、`FLIGHT_LOCK=off`、`FLIGHT_LOCK_DIR`、`FLIGHT_LOCK_MAX_HOLD_SEC`、重入标记 `FLIGHT_LOCK_HELD` 须随 `FLIGHT_` 前缀留在被测进程环境里、CI 容器里怎么关、门禁之外的测试运行用 `flight-lock.py run` 排队、放弃等待后时间类判定降级。`opsx-apply` 与 `opsx-propose` 的命令及同名 skill、`test-tiers.md`、`README.md` SHALL 各写明门禁运行会排队等全机测试锁，并指向契约文档或 `flight-lock.py`。
Feature: 项目侧知道门禁为什么在等、怎么关
Rule: 命令与同名 skill 同改

#### Scenario: contract-documents-machine-test-lock
- **GIVEN** `template/.claude/flight-runner-contract.md`
- **WHEN** 阅读其中标题含「全机测试锁」的一节
- **THEN** 该节提到 `FLIGHT_LOCK=off`、`FLIGHT_LOCK_DIR`、`FLIGHT_LOCK_MAX_HOLD_SEC`、`FLIGHT_LOCK_HELD`、`flight-lock.py run`
- **AND** 写明独占与共享、CI、降为警告
- **AND** 原有的第 1–7 节标题都还在

#### Scenario: commands-and-skills-mention-queueing
- **GIVEN** `opsx-apply.md`、`opsx-propose.md`、`openspec-apply-change/SKILL.md`、`openspec-propose/SKILL.md`、`test-tiers.md`、`README.md`
- **WHEN** 逐个查找含「全机测试锁」的行
- **THEN** 六个文件都有这样的行，且该行含「排队」
- **AND** 六个文件都提到 `flight-lock.py` 或 `flight-runner-contract.md`
