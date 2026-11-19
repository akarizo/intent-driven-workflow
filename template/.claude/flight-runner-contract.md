# 飞行门禁 · 运行器契约

> 项目侧接入飞行门禁测试运行的唯一依据。门禁实现在 `.claude/hooks/slice-gate.py`，体检在 `.claude/hooks/flight-doctor.py`。

门禁跑 `gate.test` 时往环境里注入一组变量；项目的包装脚本按本文转发，增量 final、锚点复用与检查读结果才能工作。直接调 pytest 的项目零改动（`PYTEST_ADDOPTS` / `PYTHONPATH` 注入照旧），本文只约束会重建子进程环境的包装脚本。

## 1. 包装脚本要转发的两个变量

| 变量 | 内容 | 转发方法 |
|---|---|---|
| `FLIGHT_PLUGIN_PATH` | flight 插件与 `sitecustomize.py` 所在目录 | 被测进程的 `PYTHONPATH` 以它开头 |
| `FLIGHT_PYTEST_ARGS` | 本次要传给 pytest 的 `-p` 插件参数与 `--junitxml=<path>`，按 shell 规则引号 | 按 shell 拆词后原样传给 pytest |

- **两者都为空**（去插件重跑）→ 什么也不加，与不转发一致。
- **其余 `FLIGHT_*` 变量**（插件靠它们定位输出）须留在被测进程环境里；按白名单重建环境时，白名单要放行 `FLIGHT_` 前缀。

```bash
#!/usr/bin/env bash
# 包装脚本示例：清掉项目自己不要的 PYTEST_ADDOPTS / PYTHONPATH，仍让依赖图测到
set -eo pipefail
unset PYTEST_ADDOPTS
eval "args=($FLIGHT_PYTEST_ARGS)"            # 为空时 args=()
export PYTHONPATH="${FLIGHT_PLUGIN_PATH:+$FLIGHT_PLUGIN_PATH:}src"
exec python3 -m pytest -q tests "${args[@]}"
```

## 2. `GATE_PHASE` / `GATE_CHANGE`

- **注入范围**：baseline 与 final 运行 `gate.test`、`gate.impacted` 与增量重跑时都设。
- **`GATE_PHASE`**：`baseline` 或 `final`。全局守护（检查的 `slice` 命令）与 wave 集成检查另有 `slice`、`wave` 两个取值，见第 11 节。
- **`GATE_CHANGE`**：change 目录名。包装脚本用 `$GATE_CHANGE` 取 change 名，不写死；`cmd_key` 会把脚本里的本 change 名归一成 `<change>`，两个只差 change 名的脚本指纹相同，跨 change 复用才成立。

## 3. 检查可读的 `GATE_TEST_RESULT`

- **何时有**：只在 final 运行 `gate.checks` 的 `final` 命令时设，值为结果文件绝对路径 `<git common dir>/flight-gate-checks/<change>/.gate-test-result.json`；baseline 阶段为空。同树沿用的 final 不跑检查，也不写结果文件。
- **字段**：

| 字段 | 含义 |
|---|---|
| `change` / `commit` / `at` | 本次 final 的 change、commit、时间 |
| `mode` | `full` / `incremental` / `impacted` / `tests-only` |
| `cmd` / `cmd_key` | gate.test 命令与它的指纹 |
| `nodes` | `{仓库相对 nodeid: outcome}`，outcome 取 `passed` / `failed` / `error` / `skipped` / `xfailed` / `xpassed`；`impacted` 或依赖图未测时为 `null` |
| `inherited` | 沿用锚点结论的用例数；全量为 0；`impacted` 为 `null` |
| `failed_nodes` | 本次判为失败（`failed` / `error`）的 nodeid，排序 |
| `junit` | 本次 junit 副本（同目录 `.gate-test-junit.xml`）绝对路径；增量时只含重跑部分；取不到为 `null` |
| `complete` | `nodes` 覆盖锚点与本次重跑的全部用例时为真 |

- **用法**：
  - 只要实跑结果的检查（例如统计真实耗时、只信本次执行的结局）看 `mode == "full"`，否则跳过或降级；
  - 要逐用例结局的检查读 `nodes`，先看 `complete` 为真；`inherited > 0` 表示其中有沿用锚点的结论；
  - `tests-only` 表示没有依赖图、只重跑了上次绿 final 之后改动的测试文件：`nodes` 与 `inherited` 为 `null`，`complete` 为假；
  - 不要再从项目缓存或 junit 自行拼结局——增量时 junit 不完整。

## 4. 易变变量与项目缓存键

- ⚠ **`FLIGHT_` 与 `GATE_` 前缀的变量每次运行都变，项目侧任何按环境做键的缓存都必须从缓存键剔除它们，建议直接改用白名单（只列真正影响结果的变量）。**
- 黑名单挡不住新变量：实测还见过 `CLAUDE_EFFORT` 混进缓存键，白名单才是根治。

## 5. 依赖图未测的四类原因与修法

基线写 `deps_unmeasured: {kind, why}`，warning 为 `依赖图未测（<kind>）：<why>`；锚点写 `deps_kind`。

| 类别 | 判定 | 修法 |
|---|---|---|
| `not-pytest` | 既没有 junit 输出，也没有 pytest 汇总行 | 依赖图只认 pytest：改用 pytest，或配 `gate.impacted` 由仓库自己选测 |
| `plugins-dropped` | pytest 跑了，但外层防护标记没写、也没有插件导入错误——包装脚本没把 `-p` 参数传给 pytest | 按第 1 节转发 `$FLIGHT_PYTEST_ARGS`（连同 `$FLIGHT_PLUGIN_PATH`） |
| `plugin-import-failed` | 输出里有 flight 插件导入错误（门禁随即去插件重跑） | 包装脚本覆写了 `PYTHONPATH`：让它以 `$FLIGHT_PLUGIN_PATH` 开头 |
| `incomplete` | 依赖图记录有开始、没有结束，或已损坏 | 被测进程中途退出或记录写入被中断；查清后重跑 baseline |

体检：`python3 .claude/hooks/flight-doctor.py doctor` 的 `[runner]` 节按类别统计在途 change 的基线。

**未测须表态**：本 change 的基线带 `deps_unmeasured` 时，选测复核多一个伪触发项 `runner:deps-unmeasured`。
- 出路三条：按上表修好后重跑 baseline；配 `gate.impacted`；或在计划的 `gate.scope_full_reason` 为它写理由（显示在 spec.html，以 approve 提交为准）。
- 不写理由：lint / preflight 判红，final 开跑前复核判 `G2 scope` 红。
- 基线跑出来之前可以预写；内建声明下的非 pytest 运行器与部件形态不要求。

## 6. `gate-scope.json` 的可选字段

`<openspec 根>/gate-scope.json` 恰含 `cmd` 或 `builtin` 之一，另可选：

| 字段 | 形状 | 作用 |
|---|---|---|
| `global` | 仓库相对路径 glob 的字符串数组 | Δ 中有路径匹配 → final 与经锚点的基线都自动全量，原因点名该 glob；内建选测把它当全选触发项 |
| `blind` | 测试文件 glob 的字符串数组 | 匹配的现存测试文件每次增量都重跑（依赖图看不见的依赖） |
| `anchor_max_hops` | 正整数，缺省 5 | 锚点链上限：由增量推出的锚点 `hops` 逐代 +1，`hops` ≥ 上限的锚点不再作候选，下一次回到全量 |
| `inert` | 仓库相对路径 glob 的字符串数组，无缺省 | 这些路径的改动不影响测试结论——ship 的新鲜度、final 的同树沿用与 Δ、baseline 的复用判定都不计它们；依赖图测到时与它对账，矛盾即判红 |

形状不合法时 lint 与 preflight 判红并点名字段。

**`inert` 的边界**：
- **永不按 `inert` 处理的五类路径**：测试路径、全局文件、`global` 命中的路径、`changes/` 下的路径、`gate-scope.json` / `gate-checks.json` / `test-tiers.json`——即使匹配 glob 也照常计入改动；glob 匹配到已跟踪的测试路径、全局文件或 `global` 路径时 lint 判红。
- **依赖图测到时对账**：有测试文件依赖了匹配 `inert` 的路径 → lint / preflight 判红并点名路径与测试文件；final 运行时仍按依赖图重跑依赖它的测试并警告。
- **依赖图没测到时无法对账**：声明只能靠人在 PR 里审；起飞前的「基线过期」判定与 lint / typecheck 结论的沿用不看 `inert`。

## 7. 接入步骤

1. **改包装脚本**：按第 1 节转发两个变量，用 `$GATE_CHANGE` 代替写死的 change 名；项目缓存键按第 4 节剔除 `FLIGHT_` / `GATE_`。
2. **跑 baseline，确认依赖图测到**：`slice-gate.py baseline --full` 后基线 warnings 没有「依赖图未测」，或 `flight-doctor.py doctor` 的 `[runner]` 为 0；未测且暂不接入的，须按第 5 节写理由才能起飞。
3. **对账**：baseline 之后提交一处改动，跑 `slice-gate.py final`（增量）留下结果文件副本，再在同一棵树上跑 `slice-gate.py final --full`，两份结果文件的 `nodes` 逐条一致才算接通。
4. **声明 global / blind / inert**：对账不一致的来源（依赖图看不见的配置、数据、插件目录）写进 `gate-scope.json` 的 `global`；只能靠每次重跑兜住的测试写进 `blind`；与测试无关、却会让 final 过期或退回全量的路径（记忆文件、文档、迁移脚本）写进 `inert`；必要时调 `anchor_max_hops`。
5. **检查改读结果文件**：`gate.checks` 的 `final` 命令改读 `$GATE_TEST_RESULT`，不再自己重跑测试或拼 junit。

## 8. 全机测试锁

同一台机器同一时刻只让一套全量测试在跑：门禁的测试运行先取锁再开跑，取不到就排队。

- **是什么**：用户级目录（缺省 `~/.claude/flight-lock/`）下的一把读写锁，跨仓库、跨 worktree 共用；持有进程退出即释放。
- **谁用哪种**：

  | 方式 | 命令 |
  |---|---|
  | **独占** | `slice-gate.py baseline` · `slice-gate.py final` · `test-tiers.py run` / `probe` |
  | **共享** | 切片 `slice-gate.py gate`（verify 到 G7） |

  共享方之间可同时持有；独占方排队时，后来的共享方不插队。
- **环境变量**：

  | 变量 | 作用 |
  |---|---|
  | `FLIGHT_LOCK=off` | 关闭锁，门禁直接开跑 |
  | `FLIGHT_LOCK_DIR` | 锁目录；主目录在网络盘时指到本机路径 |
  | `FLIGHT_LOCK_MAX_HOLD_SEC` | 持有上限：某次运行持锁超过它，排队方不再等；缺省为上次全量耗时的 3 倍、不低于 300 秒，没有记录时 1800 秒 |
  | `FLIGHT_LOCK_HELD` | 重入标记，门禁自己设，持锁期间的子进程不再排队；包装脚本按白名单重建环境时须随 `FLIGHT_` 前缀放行（第 1、4 节），否则被测进程里再调门禁会排到持有上限 |

- **CI**：容器已经隔离时设 `FLIGHT_LOCK=off`。
- **门禁之外的测试运行**想一起排队：`python3 .claude/hooks/flight-lock.py run exclusive -- <命令>`；看谁在占：`python3 .claude/hooks/flight-lock.py status`。
- **放弃等待**：排队方发现持有者超过持有上限即放弃（状态 `timeout`），这一次不加锁继续跑，G10 慢单测、G13 集成层单条超线、G14 层总量超预算都降为警告（原文保留并注明原因）；`off` 与平台不支持（`unavailable`）时同样不加锁，但 G10 / G13 / G14 照常判。
- **留痕**：输出 JSON 的 `lock` 字段；时间线备注里的「排队 Ns · 负载 起→止/核数」；final 备注里的「测试 Ns · 检查 <名> Ns」；`flight-doctor.py cost` 归因排队与收口秒数，`doctor` 的 `[checks]` `[lock]` 两段体检。排队期间 stderr 打印「排队中」与在等谁，不是卡死。
- **已知限制**：共享方之间不限流；不保证先来先到；多用户之间互不可见（锁目录在各自主目录下）。

## 9. 测试账本

baseline 与 final 每次跑测试都留一份逐用例账本，收口时与基线对账，打印「测试变更」。只报告，不判红。

- **在哪**：`<git common dir>/flight-ledger/<change>/` 下三份文件 `baseline.json` / `final.json` / `delta.json`（对账结果，带 final 的 commit），各自覆盖写；不进仓库，跨 worktree 共用；写入时只保留最近 30 个 change 的目录。入库的只有摘要：`gate-baseline.json` 的 `ledger` 段（不含逐用例数据）。
- **每条用例四个字段**：

  | 字段 | 含义 |
  |---|---|
  | `o` | 结局：`passed` / `failed` / `error` / `skipped` / `xfailed` / `xpassed`，未知为 `null` |
  | `s` | 秒（setup + call + teardown，保留 3 位小数）；取不到为 `null`，不估算 |
  | `t` | 层：`unit` 或区域名（按分层文件归层）；没有分层文件或文件不在任何层为 `null` |
  | `m` | 1 = 本次实测，0 = 沿用 |

- **耗时的来源**：依赖图测到 → 依赖图插件记的耗时，用例 id 为 nodeid；依赖图没测到 → junit 的 `time`，用例 id 为 `classname::name`。一份账本只用一种 id 形式。包装脚本只要按第 1 节转发 `$FLIGHT_PYTEST_ARGS`（其中的 `--junitxml`）就有耗时。
- **沿用**：增量运行里没重跑的用例沿用锚点（或来源账本）的结局与耗时，记 `m=0`；升级前写的锚点没有耗时，沿用的用例耗时记 `null`，跑一次全量后补齐。
- **看账本**：
  - `python3 .claude/hooks/test-ledger.py show --change-dir <dir> [--phase baseline|final] [--tier <层>] [--top N] [--json]`：按耗时由大到小列用例；
  - `python3 .claude/hooks/test-ledger.py delta --change-dir <dir> [--markdown|--json]`：打印已存的对账结果；
  - 两者只读，退出码 0 有账本 / 1 没有 / 2 参数不可用；`flight-doctor.py doctor` 的 `[tests]` 段打印最新账本摘要与最近 5 个 change 的测试变更。
- **测试变更**（final 对基线账本对账）：新增、删除、变慢、各层前后的用例数与耗时；增量运行没覆盖到的用例记「未重测」，不算删除。出现在三处：final 输出 JSON 的 `tests`、时间线 final 备注里的 `用例 +A/-R（新增 Xs）`、PR 正文的「## 测试变更」（`ship --markdown` 在 `delta.json` 的 commit 与最后一条 final 对得上时附出）。
- **只报告**：账本与对账不判红，阈值（变慢、建议行）只决定打印什么；账本写不成只留一条「测试账本未写：<原因>」警告，不影响门禁结论。
- **不落账**：切片 `gate`、final 的 G7 红 / 选测复核未过、同树沿用的 final。
- **已知限制**：切片门禁不留账；部件形态只有单元层、没有部件维度；账本只在产生它的机器上（基线账本不在本机时对账为空并给出原因）。

## 10. 时间预算与放行

分层文件可给每层写时间预算，放行慢用例可带上限与期限。不写就是现状。

- **预算写在哪**：`unit` 与区域条目里可选的 `"budget": {"case_sec": 秒, "total_sec": 秒}`；部件形态写在 `parts.<部件>.unit` 与 `parts.<部件>.regions.<区域>` 里。两个字段都可选。
  - `case_sec`：单条用例的线；
  - `total_sec`：整层（或整个区域）的总量预算。
  - 不写：单元层单条仍是 3 秒，区域不判。
- **各层的处置**：

  | 判定 | 对象 | 处置 |
  |---|---|---|
  | `G10` | 单元层单条超过 `case_sec`（缺省 3 秒） | 判红；候选单独重跑确认、放行规则不变 |
  | `G13` | 集成层单条超过区域的 `case_sec`，本 change 新增的用例 | 判红（`G13 slow integration test: …`） |
  | `G13` | 集成层单条超线，基线账本里已有、基线时已超线 | 警告，计「老债」 |
  | `G13` | 集成层单条超线，基线账本里已有、基线时未超线 | 警告，计「本次量到超线」（单次测量分不出噪声） |
  | `G14` | 单元层合计超过 `total_sec` | 判红（`G14 tier budget: …`），baseline 与 final 都判 |
  | — | 区域合计超过 `total_sec` | 警告，列最慢 3 条与本 change 新增的秒数 |

  - 集成层单条只判本次实测、有耗时的用例；baseline 阶段的超线全部计老债，只警告。
- **放行的上限与期限**：`slow_allow` 条目可带 `limit_sec` 与 `expires`（`YYYY-MM-DD`），由 `test-tiers.py allow-slow` 的 `--limit-sec` / `--expires` 写入。
  - 用例耗时超过 `limit_sec` → 判红；放行了但没写上限 → 该用例不设线；
  - 今天（UTC）晚于 `expires` → 这条放行不再算数，按没放行判红；到期日当天仍有效；
  - 到期前 14 天起，警告里带「放行将于 <日期> 到期」；
  - 两个字段都没有的旧条目与现在完全一样。
- **依赖测试账本（第 9 节）**：G13 / G14 读账本判。
  - 账本不可用 → G13 / G14 不判，只留一条以「预算未判」开头的警告；
  - 基线账本不在本机或不完整 → 分不出新增与已有，集成层单条一条都不判红，警告里写原因；
  - 账本不完整、或某范围无耗时的用例超过一成 → 该范围的总量不判（「G14 未判」警告）。
- **排队放弃**：锁状态 `timeout`（第 8 节）的那次运行，G10 / G13 / G14 都降为警告；`off`、`unavailable` 照常判。
- **预算变更**：final 用基线 commit 上的分层文件与当前版本逐项比——预算数值变了（标放宽 / 收紧，取消算放宽）、放行条目增删或 `limit_sec` / `expires` 变了——有变动即给出以「预算变更」开头的警告，并随「## 测试变更」写进 PR 正文。只报告，不判红。基线 commit 上没有分层文件、取不到或解析不了时不比。
- **总量的口径**：账本里整层逐用例耗时（实测 + 沿用）之和，不是墙钟；增量与全量之间是同一个量。
- **留余量**：总量预算建议不低于当前合计的 2 倍——两次运行之间的合计本身会波动。
- **升级与回退**：旧版 hooks 读到带 `budget` 的分层文件会报未知字段，先升级 hooks 再写预算；删掉 `budget` 与放行的两个新字段即回到现状。

## 11. 全局守护与 wave 集成检查

`gate.checks` 里带 `slice` 命令的检查是全局守护：除了 baseline / final 的成对命令，它还在每片门禁与每个 wave 合回后运行，尽早发现切片把全局不变量弄红。

- **`slice` 字段**：`gate.checks` 的检查可多带一条 `slice` 命令（非空字符串）。`gate-checks.json` 里声明了 `slice` 的默认检查，计划里的同名检查必须连同 `slice` 一起带上（lint 校验）。`slice` 进 `plan_sha`，改了要重跑 baseline。
- **在哪跑**：
  - baseline：证明起点是绿的，结果记在 `gate-baseline.json` 的 `checks.<名>.slice`，红或超时即基线红；
  - 每片门禁：红记 `G15 guard <名>`；
  - 每个 wave 合回后的集成检查：`python3 .claude/hooks/slice-gate.py wave-check`；
  - final 不跑它，final 跑的是该检查的 `final` 命令。
- **环境变量**：`GATE_CHANGE` / `GATE_BASE_COMMIT` / `GATE_CHECK_DIR` 与 baseline / final 相同；`GATE_PHASE` 多两个取值：

  | `GATE_PHASE` | 时机 |
  |---|---|
  | `baseline` | baseline 运行 `gate.test` 与检查的 `baseline` 命令 |
  | `slice` | baseline 与每片门禁运行检查的 `slice` 命令 |
  | `wave` | wave 合回后的集成检查（守护与受影响测试两半） |
  | `final` | final 运行 `gate.test` 与检查的 `final` 命令 |

- **并行与只读**：同一 wave 的多个切片会并行过门禁、并行调用 `slice` 命令，并且共用 `GATE_CHECK_DIR`；`slice` 命令对共用目录只读（或自己保证并发安全）。日志按场合分名：切片门禁 `<GATE_CHECK_DIR>/.gate-slice-<切片 id>.log`，baseline `.gate-slice.log`，集成检查 `.gate-wave.log`。
- **要快**：它在每片门禁里跑，应当是秒级的；`timeout_sec` 照常生效，超时即红。
- **wave 集成检查的测试那一半**：按依赖图只重跑受影响的测试（与增量 final 同一选法），新增失败记 `G16 wave test`。以下情况跳过并在时间线写明原因，不退化成全量：没有可用锚点；估算耗时超过 `gate.wave_test_budget_sec`（缺省 120 秒，留给 final）；配了分层文件或 `gate.impacted`。运行 `gate.test` 时 `GATE_PHASE` 同样是 `wave`。
- **不做什么**：集成检查不写锚点、不写测试账本。

## 12. 测试套件合规标准

测试套件「合规」的明文判据。`test-tiers.py audit` 按它体检，`/test-audit` 按它整改；类别、规则号、去向与脚本常量 `AUDIT_RULES`（`test-tiers.py`）、`ACTIONS`（`test-audit.py`）一字不差，由测试对账。

- **规则**：

  | 规则 | 合规判据 | 数据来源 |
  |---|---|---|
  | R1 | openspec 根有合法的分层文件 | 文件 |
  | R2 | 每个测试文件恰属一层（部件形态：恰属一个部件、在该部件内恰落一层） | 测试文件清单 |
  | R3 | 单元层用例不碰真实文件、子进程、网络 | 探针记录 |
  | R4 | 单元层用例不超线（缺省 3 秒；有效放行按放行上限） | 测量 |
  | R5 | 每个集成区域写了单条上限 `budget.case_sec` | 分层文件 |
  | R6 | 集成区域用例不超线（有效放行按放行上限） | 测量 |
  | R7 | 写了总量预算的范围，合计不超预算 | 测量 |
  | R8 | 放行条目有效且有边界：所指文件还在、未过期、有 `limit_sec` 与 `expires` | 分层文件 |

- **体检**：`python3 .claude/hooks/test-tiers.py audit` 只读、**不跑测试**、不改文件（`--out` 除外）。
  - 读：分层文件、测试文件清单（git 跟踪与未忽略）、最近一次测量——测试账本（第 9 节），可叠加 `test-tiers.py probe --json` 的结果（`--probe`，覆盖账本里同一用例的耗时并带触碰记录）；
  - 账本的选取：`--ledger` > `--change-dir` 的收口账本（没有则基线账本）> 本机 `at` 最新的一份；`--no-ledger` 不读；
  - 每条用例按当前分层文件由所在文件重新归层；所在文件已不存在的丢弃，计入 `source.dropped`；
  - 参数：`--change-dir` / `--ledger` / `--no-ledger` / `--probe` / `--scope` / `--category` / `--top` / `--json` / `--out` / `--compare` / `--plan`。
- **类别**：

  | 类别 | 级别 | 规则 | 判据 | 可选去向 |
  |---|---|---|---|---|
  | `no-tiers` | 不合规 | R1 | 没有分层文件 | 无（先跑 `/test-tiers`） |
  | `layering` | 不合规 | R2 | 测试文件未归层、匹配多层、不属于任何部件或属于多个部件 | `move` / `retier` |
  | `unit-impure` | 不合规 | R3 | 探针记录里单元层用例有触碰 | `purify` / `move` / `split` |
  | `unit-slow` | 不合规 | R4 | 单元层用例超线 | `speedup` / `move` / `allow` |
  | `no-case-limit` | 不合规 | R5 | 集成区域没写 `budget.case_sec` | `budget` |
  | `region-slow` | 不合规 | R6 | 集成区域用例超线 | `speedup` / `allow` / `delete` |
  | `total-over` | 不合规 | R7 | 写了 `total_sec` 的范围合计超预算 | `speedup` / `delete` / `budget` |
  | `allow-stale` | 不合规 | R8 | 放行所指的测试文件已不存在 | `drop-allow` |
  | `allow-expired` | 不合规 | R8 | 放行已过期 | `allow` / `speedup` / `move` / `drop-allow` |
  | `allow-unbounded` | 不合规 | R8 | 未过期的放行缺 `limit_sec` 或缺 `expires` | `allow` / `drop-allow` |
  | `allow-soon` | 提示 | — | 放行 14 天内到期 | 无 |
  | `allow-unneeded` | 提示 | — | 有测量且耗时已回到线内的有效放行 | `drop-allow` |
  | `pure-in-region` | 提示 | — | 探针显示区域文件里有无触碰且低于单元层线的用例 | `move` / `split` |
  | `purity-unchecked` | 提示 | — | 没有探针结果，纯度未在体检里核对 | 无 |
  | `gwt-missing` | 提示 | — | Python 用例缺 Given / When / Then 注释的条数（只计数） | 无 |
  | `unjudged` | 未判 | — | 没有测量、来源账本不完整或来自选测、某范围有测试文件没有测量或无耗时的用例超过一成 | 无 |

  - 条目 id = `<类别>:<键>`，跨两次体检稳定；一条放行只归入最靠前的一个放行类别；
  - 未判的范围不出 `total-over`，已量到的单条超线照常列出；提示不影响结论。
- **退出码**：

  | 码 | 含义 |
  |---|---|
  | `0` | 合规 |
  | `1` | 有不合规项 |
  | `2` | 输入不可用（分层文件不合法、账本 / 探针 / change 目录读不了） |
  | `3` | 没有不合规项，但有未判项 |

  - 带 `--compare`（再加 `--plan` 取本轮目标）：有新增不合规项或目标未解决 → `1`；否则有未判项 → `3`（未能确认）；否则 `0`。没排进本轮的老债不算失败。
- **体检与门禁的区别**：门禁回答「这次变更有没有变坏」，体检回答「离标准多远」。集成层**老债**（G13）与区域总量超预算，门禁只警告（第 10 节），体检计为不合规。
- **去向与轨道**：

  | 去向 | 做什么 | 轨道 |
  |---|---|---|
  | `move` | 整文件搬到另一层的目录 | 命令内执行 |
  | `split` | 把一条用例原样拆到另一个文件 | 命令内执行 |
  | `retier` | 改分层文件的 `paths` / 部件归属 | 命令内执行 |
  | `budget` | 写或调预算 | 命令内执行 |
  | `drop-allow` | 删掉失效的放行条目 | 命令内执行 |
  | `allow` | 放行，或给放行补上限与期限 | 交人放行（人类原话 + `test-tiers.py allow-slow`） |
  | `speedup` / `purify` / `delete` | 提速、改纯、删用例 | 转 change（清单交 `/opsx-propose`） |
  | `keep` | 本轮不处理 | 须写理由 |

- **整改护栏**（`python3 .claude/hooks/test-audit.py verify`，对着相对 `--base` 的 git 改动核对）：
  1. **改动范围**：只许测试文件、分层文件、openspec 根之下的文件与稿里 `support`；命中区域 `covers` 判「改了被测代码」，`support` 不能豁免；
  2. **用例与断言不变**：按 `类名.函数名` 比较两边的用例集合、断言与参数化，跨文件移动不算改动；
  3. **分层文件的改动与稿一致**：放行增改 ↔ `allow`、放行删除 ↔ `drop-allow`、预算放宽 ↔ `budget`，对不上判稿外；
  4. **核对不了的如实列出**：非 Python 测试文件、解析失败的文件进「未核对」，不判失败。
- 体检与整改的完整流程见 `.claude/commands/test-audit.md`（`/test-audit`）。
