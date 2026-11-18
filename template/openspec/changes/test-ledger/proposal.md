## Why

门禁现在只回答测试「对不对」，不回答「多贵」：

- **没有逐用例耗时**。baseline 与 final 只留整套秒数（`gate-baseline.json` 的 `test.sec`、final 时间线里的「测试 Xs」）；有分层文件时多一行层合计（`tier_sec`）。哪条用例慢、慢在哪一层，只能事后手工解析 junit（afa 2026-11-18 的测试分层体检就是这么做的）。
- **变更与测试成本对不上账**。一次 change 新增了几条用例、加了多少秒、有没有把别的用例拖慢，飞行记录和 PR 正文里都没有。afa 的集成用例两周从 1383 条涨到 1956 条（+41%），是体检时才发现的。
- **后面两件事都要以它为前提**：分层预算与豁免（C5b `tier-budgets`）要有逐用例耗时才能判线；体检与整改命令（C6）要有一份可列出的账本。

2026-11-18 用户在方案页 `docs/flight-fixes-and-test-governance.html` 第 04 节提出「每次变更要知道新增了哪些用例、速度如何、要不要优化」，并回复「按推荐」。本 change 是该页 C5 的前半（C5a）：只做留账、归因、可见，**不改任何判红规则**。范围与取舍来自方案页与主会话的拆分指令，没有另开 `grill-me` 访谈。

## What Changes

- **逐用例采集**（`template/.claude/hooks/slice-gate.py`，只加采集点）：
  - 依赖图插件在记逐用例结局的同时累计该用例 setup + call + teardown 的耗时；`_read_deps` 的返回值多一个 `secs`。
  - 依赖图没测到（包装脚本丢了插件、非 pytest）时退用 junit：按 `classname::name` 取结局与耗时。
  - 增量重跑（`_pytest_outcomes`）恒取逐用例耗时，不再只在调用方要分层耗时时才取。
  - 部件形态的适配器部件按 `run_part` 已有的逐用例秒数上报。
  - 门禁进程把每次测试运行的「本次实测」记进进程内观测表，供落账时合并；不改任何函数的既有返回值含义。
- **账本**（新文件 `template/.claude/hooks/test-ledger.py`）：
  - 把观测合成一份账本：每条用例记结局、秒、所属层、是本次实测还是沿用；耗时取不到记 `null`，不编数。
  - 存在 `<git common dir>/flight-ledger/<change>/` 下（`baseline.json` / `final.json` / `delta.json`），不进仓库；只保留最近若干个 change 的目录。
  - 子命令 `show`（按层、按耗时列账本）与 `delta`（打印对账结果）。
- **baseline 与 final 落账**（`slice-gate.py`，各一个落账点）：
  - baseline：写基线账本；`gate-baseline.json` 只多一段十来个数的 `ledger` 摘要；写出的锚点带上逐用例耗时 `secs`，增量运行里没重跑的用例靠它沿用耗时。
  - final：写收口账本，与基线账本对账，结果进输出 JSON 的 `tests`、时间线的一小段摘要（`用例 +A/-R（新增 Xs）`）与 `delta.json`。
  - 账本的任何失败都只留一条警告，不改 baseline / final 的结论。
- **对账与「测试变更」**（`test-ledger.py`）：新增、删除、变慢、各层用例数与耗时的前后对比、最慢的新增用例、沿用未实测与无耗时的条数；几条固定规则的建议行。只报告，不判红。
- **PR 正文**（`slice-gate.py ship --markdown`）：本机有与 final 对应的对账结果时，末尾附「## 测试变更」一节。
- **体检**（`template/.claude/hooks/flight-doctor.py doctor`）：新增 `[tests]` 一节——最近一份账本的各层用例数与耗时、最慢用例、最近几个 change 的新增用例与新增耗时；没有账本时说明原因。
- **文档**：`flight-runner-contract.md` 新增「测试账本」一节；`commands/test-tiers.md`、`commands/pr-ship.md`、`README.md` 各补相应说明。
- **不做**（留给 C5b / C6）：
  - 分层文件里的 `budget`、`slow_allow` 的 `limit_sec` / `expires`、集成层单条上限与棘轮、层总量预算判定、任何新的判红。现有 G10 / G11 / G12 的判定与文本不动。
  - 体检与整改命令。
  - 切片门禁（`gate`）不落账：它只跑该片 verify 与 scenario 用例，覆盖不到整套。
  - 部件形态下区域运行不采集、账本不带部件维度（只有层）。
  - `GATE_TEST_RESULT` 结果文件不加字段。

## Capabilities

### New Capabilities

- `test-ledger`: 门禁每次 baseline / final 留下逐用例账本（结局、耗时、所属层、实测或沿用），final 与基线对账得出「测试变更」，并在时间线、PR 正文与体检里可见；全程只报告、不判红，账本失败不影响门禁结论。

### Modified Capabilities

（无。`openspec/specs/` 下还没有已归档的 capability。）

## Impact

- **代码**：
  - 新增 `template/.claude/hooks/test-ledger.py`。
  - `template/.claude/hooks/slice-gate.py`：依赖图插件文本、`_read_deps`、`run_test_gate`、`_pytest_outcomes`、`run_part` 各一处采集；`cmd_baseline`、`cmd_final`、`cmd_ship` 各一处调用；三处写锚点带 `secs`。
  - `template/.claude/hooks/flight-doctor.py`：`doctor` 多一节。
- **输出形状**（只增不改）：
  - `_read_deps` / `run_test_gate` 的依赖图多 `secs`；锚点条目多 `secs`；
  - `gate-baseline.json` 多 `ledger`；final 输出 JSON 多 `tests`；
  - final 时间线备注在「检查」片段之后、锁片段之前多一段 `用例 +A/-R（新增 Xs）`；
  - `ship --markdown` 可能多一节「## 测试变更」（ready 且本机没有对账结果时输出仍为空）。
- **受波及的旧测试**（在一次性原型上跑全量量出）：只有 `tests/test_gate_checks_baseline.py::test_no_checks_behavior_unchanged`（它钉住 final 输出 JSON 的键集合），已并入 S5 的 owns。
- **磁盘**：`<git common dir>/flight-ledger/` 每个 change 至多三份 JSON；锚点文件因 `secs` 变大（每条用例约几十字节）。
- **已安装仓库**：升级后第一次全量运行之前，沿用自旧锚点的用例没有耗时，对账里计入「无耗时」；不需要人工迁移。
- **依赖**：只用标准库。ship-rerun-hardening（C1b）已合入：它的 final 无图退路同样落账（`mode = tests-only`，沿用上一份收口账本）；`inert` 不影响账本。
