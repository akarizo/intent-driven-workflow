## Context

**现状**（读 `template/.claude/hooks/` 现行代码，main `b1be3db`，已含 plan-hygiene、machine-test-lock 与 ship-rerun-hardening）：

- 门禁里跑测试的入口有三个，各自留下的逐用例信息不同：
  - `run_test_gate(cmd, …)`：跑任意 `gate.test` / 区域命令 / `gate.impacted`。恒注入 `--junitxml`（经 `PYTEST_ADDOPTS` 与 `FLIGHT_PYTEST_ARGS`）；`deps=True` 时另加载依赖图插件，返回 `deps.nodes = {nodeid: PASSED|…}`；`probe=True`（有分层文件）时另有探针的逐用例 `sec`。junit 在临时目录里，函数返回前就删了，只在有 `gate.checks` 的 final 里留一份副本。
  - `_pytest_outcomes(root, targets, …)`：G7 实跑、增量重跑、基线补跑、final 无图退路的重跑。用 G7 插件记逐用例结局；逐用例耗时（`FLIGHT_G7_SEC`）只在调用方传了 `durations` 时才取。
  - `run_part(top, name, part)`：部件形态的单元层。适配器部件直接 `subprocess.run`，返回 `secs = {顶层 id: 秒}`；pytest 部件转给 `run_test_gate`（带 `cwd`）。
- 逐用例**结局**已经随锚点保存（`nodes`），增量运行靠 `_anchor_forward` 把没重跑文件的旧结局带到新锚点。逐用例**耗时**哪里都不保存。
- baseline 有四条路：全量、经锚点增量（`_try_anchor`）、复用旧基线或基线池（`_try_reuse`）、部件形态。final 有七种结局：全量、内建增量、`gate.impacted`、无图退路（ship-rerun-hardening：没有可用锚点、上次绿 final 之后只改了测试文件时，经 `_pytest_outcomes` 只重跑这些文件，不写锚点）、部件形态、同树沿用（不跑）、G7 红或选测复核未过（不跑套件）。
- final 时间线备注的现行格式（machine-test-lock design D8）：`[全量（原因）|增量（…）] [单元 Xs · 集成 Ys ·] 测试 Xs · 检查 a Xs / b Ys · 排队 Xs · 负载 a→b/N ok|red`，片段以 ` · ` 相连，结论词在末尾。解析方：`timeline.py`（按末尾取结论）、`flight-doctor.py`（`parse_note` 认「全量（」「增量」；`TEST_RE` / `WAIT_RE` / `CHECKS_RE` 取秒数，`CHECKS_RE` 到下一个 ` · ` 为止）。
- `ship --markdown` 只在有 reasons 或 blocked 时有输出；`tests/test_ship_verdict.py` 钉住「ready 时输出为空」。
- `tests/test_gate_checks_baseline.py::test_no_checks_behavior_unchanged` 钉住 final 输出 JSON 的键集合。

**已定决策**（2026-11-18，方案页第 04 节与主会话的拆分）：C5 拆成 C5a（本 change：留账 + 归因 + 可见，不判红）与 C5b（预算、豁免扩展、棘轮）。

**在役 ADR 与本设计的关系**：

- `DRAFT-baseline-reuse-via-dependency-anchor` / `DRAFT-final-incremental-by-dependency-anchor`：锚点是「可沿用的测试结论」。本设计给锚点条目加一个可选字段 `secs`，不改任何选锚点、判全量的规则。
- `DRAFT-gate-test-result-handoff-and-runner-contract`：`GATE_TEST_RESULT` 结果文件的字段与含义不变，本设计不加字段。
- `DRAFT-measurements-stay-out-of-plan-files`：度量不进计划文件。账本在 git common dir，`gate-baseline.json` 只加摘要，`slices.json` 不动。
- `DRAFT-machine-wide-test-lock`：baseline / final 的测量在独占锁内。账本记下本次的锁状态，供以后判断这份耗时可不可信。
- `DRAFT-gate-evidence-not-self-reported`：账本与对账由脚本写，不经模型。
- 没有需要 supersede 的 ADR。

```
C4 · 组件图（轻量 C4 风格；★ 新增，◆ 修改）

  被测进程（pytest）
  ◆ 依赖图插件：逐用例结局 + 耗时 ─┐        junit（依赖图没测到时）─┐
  G7 插件：逐用例结局 + 耗时 ──────┤                              │
                                   ▼                              ▼
 ◆ slice-gate.py   run_test_gate · _pytest_outcomes · run_part ──▶ 进程内观测表（本次实测）
        │ cmd_baseline / cmd_final 各一个落账点
        ▼
 ★ test-ledger.py  build（实测 + 沿用）· save / load · delta · render · advice · show
        │ 写                                  │ 读来源
        ▼                                    ▼
 <git common dir>/flight-ledger/<change>/    锚点池（◆ 条目带 secs）
   baseline.json · final.json · delta.json
        │
        ├──▶ ◆ gate-baseline.json 的 ledger 摘要
        ├──▶ ◆ final 输出 JSON 的 tests · 时间线片段「用例 +A/-R（新增 Xs）」
        ├──▶ ◆ ship --markdown 的「## 测试变更」
        └──▶ ◆ flight-doctor.py doctor 的 [tests]
```

- **边界**：采集留在 `slice-gate.py`（它才看得到测试进程）；账本的合成、存取、对账、渲染全在 `test-ledger.py`。`slice-gate.py` 对账本模块只有「上报观测 / 落账 / 读对账结果」三类调用。
- **强制力**：无。本 change 的所有输出都是报告。

## Goals / Non-Goals

**Goals**：

- 每次 baseline / final 的测试运行留下逐用例账本：结局、耗时、所属层、实测还是沿用。
- final 与基线对账，得出本 change 的「测试变更」，在时间线、PR 正文、体检里看得见。
- 耗时取不到就记 `null`，沿用的就标沿用，不把猜测混进数字。
- 账本出任何问题都不影响门禁结论。

**Non-Goals**：

- 不判红：预算、单条上限、棘轮、豁免扩展属于 C5b。G10 / G11 / G12 不动。
- 切片门禁不落账。
- 部件形态：区域运行不采集，账本不带部件维度。
- 不改 `GATE_TEST_RESULT`、不改锚点的选取规则、不改 `plan_sha`。
- 不做跨机器同步：账本只在产生它的机器上。

## Decisions

### D1 · 账本逻辑落新文件，`slice-gate.py` 只加调用点

- `test-ledger.py` 按 `flight-lock.py` 的方式由 `slice-gate.py` 按路径加载（`importlib`），加载失败或调用抛错 → 落账函数返回一条警告，门禁照常。
- `flight-doctor.py` 同法加载它来读账本。
- `test-ledger.py` 不反向加载 `slice-gate.py`：层的归属由调用方传一个 `tier_of(文件) -> 层名 | None` 进来。
- **为什么**：`slice-gate.py` 已 6075 行，五个在途 change 都要改它；新逻辑独立成文件，冲突面只剩调用点。
- **备选**：写进 `slice-gate.py`——被否，理由同上。

### D2 · 耗时从哪来：依赖图插件优先，junit 兜底，两种 id 不混用

| 运行方式 | 用例 id | 结局 | 耗时 |
|---|---|---|---|
| `run_test_gate`，依赖图测到 | nodeid（仓库相对） | 依赖图插件（现有） | 依赖图插件新记的 setup + call + teardown 之和 |
| `run_test_gate`，依赖图没测到、junit 可解析 | `classname::name`（与基线 `test.failed` 同一形式） | junit（failure / error / skipped / 其余 passed） | junit 的 `time` |
| `_pytest_outcomes` | nodeid | G7 插件（现有） | G7 插件的耗时文件（改为恒取） |
| `run_part`（pytest 部件与适配器部件） | `run_part` 返回的顶层 id | 未知（`null`） | `run_part` 返回的 `secs`；观测另带 `tier = unit`（它跑的就是该部件的单元层，适配器部件的 id 里没有文件路径，靠这个归层） |

- 依赖图插件多写一种记录 `{"sec_node": nodeid, "sec": 秒}`；`_read_deps` 把它读成 `secs`（同一用例多条取最大值——xdist 的主进程与 worker 各写一份）。旧的读取逻辑遇到不认识的记录本来就跳过。
- 一份账本只用一种 id 形式：有依赖图全集时用 nodeid；否则观测里有 junit 形式、或来源账本是 junit 形式，就用 junit；否则 nodeid。
- junit 形式的账本里，nodeid 形式的观测按 pytest 写 junit 的规则**正向**换算成 `classname::name` 再并入（文件路径去掉 `.py`、`/` 换成 `.`，类名以 `.` 相连）。正向换算是确定的；反向（从 `classname` 猜文件）才有损，所以 nodeid 形式的账本直接丢弃 junit 形式的观测。典型情形：依赖图没测到的仓库里，G7 实跑与补跑（经 `_pytest_outcomes`，恒是 nodeid）要与套件的 junit 观测、junit 形式的来源账本并到一起。
- **为什么不统一用 junit**：junit 的 `classname::name` 映射回 nodeid 是有损的；而依赖图没测到的仓库（afa 现状）恰恰只有 junit。两头各用原生的。
- **为什么不用探针的 `sec`**：只有配了分层文件才有。
- `run_test_gate` 带 `cwd`（部件或部件区域）时不上报：id 相对部件目录，与顶层 id 混不到一起；部件单元层由 `run_part` 统一上报。
- 观测可带可选的 `tier`：上报方已经知道这批用例属于哪一层时直接给出，账本优先用它；否则按用例所在文件查分层文件。

### D3 · 进程内观测表，而不是沿返回值层层传

- 三个采集点各调一次 `_ledger_observe(form, outcomes, secs)`，往模块级列表追加一条；`ledger_observations()` 返回它的副本。
- 落账时把整张表交给 `test-ledger.py` 合并：同一用例后来的观测覆盖先前的。
- **为什么**：一次 baseline 可能先后试几个复用候选、补跑、再全量、再跑区域；一次 final 先跑 G7 再跑套件。这些都是「本次在这棵树上实测到的」，都该进账本。若沿返回值传，要改 `_try_reuse`、`_try_anchor`、`scenario_status` 等一串函数的签名。
- **代价**：模块级可变状态。它只在门禁进程内存在、只增不删、落账只读，测试里通过 `ledger_observations()` 观察。

### D4 · 放哪：逐用例数据在 git common dir，入库的只有摘要

- `<git common dir>/flight-ledger/<change>/baseline.json`、`final.json`、`delta.json`，各自覆盖写（原子写）。
- 写入时清理：只保留最近 30 个 change 的目录（按目录内最新文件的修改时间；**30 是草案**）。
- `gate-baseline.json` 多一段 `ledger`：`{cases, measured, inherited, no_sec, id_form, complete, tiers: {层: {cases, sec}}}`，不含逐用例数据。
- 入库可追溯的载体只有两个：final 时间线里的一小段、PR 正文里的「## 测试变更」。
- **为什么不入库**：万级用例的账本每份约 1 MB，每个 change 两三份。
- **为什么不写进 `gate-report.md`**：它靠 `append_report` 往文件尾追加表格行、靠 `report_latest` / `report_has_row` 按列解析；在里面插一节要处理与「天花板」表的相对位置，收益只是多一个入库副本。
- **为什么不新增一个入库的报告文件**：记账文件清单（`BOOKKEEPING`）被 ship 新鲜度、脏检查、integrator 的提交步骤共用，加一个文件要同改 agent 定义与工作流提示。
- 跨 worktree：common dir 是共用的，临时 worktree 与 change worktree 看到同一份。

### D5 · 账本形状（v1）

```json
{
  "v": 1, "change": "…", "commit": "…", "at": "…",
  "phase": "baseline | final", "mode": "full | incremental | impacted | tests-only | parts",
  "lock": "held | nested | timeout | off | unavailable | null",
  "id_form": "nodeid | junit", "tiered": true, "complete": true,
  "cases": {"<用例 id>": {"o": "passed", "s": 0.123, "t": "unit", "m": 1}}
}
```

- `o` 结局：`passed / failed / error / skipped / xfailed / xpassed`，未知为 `null`。
- `s` 秒，保留 3 位小数；取不到为 `null`。
- `t` 层：`unit` 或区域名（`tiers_matching` 的第一个）；没有分层文件或文件不在任何层为 `null`。
- `m`：1 = 本次实测，0 = 沿用。
- `lock` 取自本次运行的锁状态，C5b 判时间类规则时用得上；本 change 只记不用。

### D6 · 用例全集与「沿用」

- **有依赖图全集**（落账时调用方把新锚点的 `nodes` 传进来）：账本的用例就是这些。实测到的记 `m=1`；其余记 `m=0`，耗时取来源锚点的 `secs`。来源锚点没有 `secs`（升级前写的锚点）→ 耗时 `null`。
- **没有全集**（依赖图没测到、`gate.impacted`、部件形态）：
  - 全量 → 账本 = 实测到的用例；
  - 复用旧基线 / 基线池（只补跑了若干测试文件）→ 实测 ∪ 来源账本里「文件仍在、且不在补跑清单里」的用例；来源账本是那个 change 的 `baseline.json`，且它的 commit 必须等于被复用基线的 commit，否则当作没有来源；
  - final 的无图退路（只重跑了改动的测试文件）→ 同一条规则，来源账本换成本 change 上一份 `final.json`，且它的 commit 必须等于「上次绿 final」的 commit，否则当作没有来源。来源要在覆盖写 `final.json` 之前读出。无图退路不写锚点，所以不涉及 `secs`。
- `complete`：每条 `m=0` 的用例都在来源里找得到 → 真。有补跑清单却没有来源 → 假。
- 锚点带 `secs`：baseline 的两处写锚点与 final 的一处，写之前先落账，把账本里有耗时的用例写成 `secs = {nodeid: 秒}`。依赖图没测到时写 `null`。锚点的其余字段与选取规则不变。
- **为什么耗时跟着锚点走**：增量运行沿用谁的结局，就该沿用谁的耗时；锚点的保留与清理（最多 20 条）已经有了，不用再造一套对应关系。
- **备选**：账本另存一份按锚点命名的快照——被否：要与锚点池的清理保持同步。

### D7 · 对账规则（final 账本 F 对基线账本 B）

- **前提**：B 在本机；否则对账结果为空并给出原因（「基线账本不在本机」）。
- **两边 id 形式不同**（典型：直接 pytest 的基线是 nodeid，`gate.impacted` 的 final 只有 junit；或仓库中途把依赖图接通了）：把 nodeid 那一份正向换算成 junit 形式再对（规则同 D2）。
- **新增**：在 F 不在 B。
- **删除**：在 B 不在 F，且满足其一——F 是全量或部件形态；该用例的文件已不存在；该用例的文件在本次重跑清单里。
- **未重测**：在 B 不在 F 而又不满足上面任何一条（典型：`gate.impacted` 只跑了选测）。单独计数，不算删除。
- **变慢**：两边都有，F 里是本次实测，两边耗时都不是 `null`，且 `F ≥ B × 2` 并且 `F − B ≥ 0.5 秒`（**两个阈值都是草案**）。只报告。
- **各层前后**：按层汇总 B 与 F 的用例数与耗时之和（`null` 不计入和）。
- **最慢新增**：新增用例按耗时取前 5。
- 另报：F 里沿用的条数、无耗时的条数、F 是否 `complete`。
- **建议行**（固定规则，零 token，只打印；阈值为草案）：
  1. 本次新增用例里，集成层（非 `unit` 的层）耗时之和大于单元层 → 提示「新增耗时主要在集成层」并点名最慢的新增集成用例；
  2. 某层耗时较基线上涨 ≥ 20% 且 ≥ 5 秒 → 点名该层最慢的 3 条新增或变慢用例；
  3. 无耗时用例占比 > 10% → 说明来源（沿用自没有账本的锚点 / junit 缺 `time`），提示跑一次全量。

### D8 · 输出到哪

- **final 输出 JSON**：新增 `tests = {…摘要…, "delta": {…} | null, "why": 原因 | null}`。`delta` 里的清单都有上限（各 5 条），不会随用例数膨胀。
- **时间线**：final 备注在「检查」片段之后、锁片段之前插一段 `用例 +A/-R（新增 X.Xs）`。片段内不含 ` · `，不含「测试」「检查」「排队」字样，现有三个正则与结论词的取法都不受影响。没有对账结果时不插。
- **`delta.json`**：对账结果原样存一份，带 final 的 commit。
- **`ship --markdown`**：`gate-report.md` 里最后一条 final 行的 commit（10 位）等于 `delta.json` 的 commit 前 10 位 → 在现有输出之后附 `render(delta)`（标题「## 测试变更」）。对不上或没有 → 不附。`ship` 的 JSON 输出、退出码、时间线记录都不变。
- **同树沿用的 final** 不跑测试，不产生新账本，时间线里也没有这一段；`delta.json` 仍是上一次实跑留下的那份，commit 对不上时 ship 不会贴。
- **`gate-baseline.json`**：`ledger` 摘要（D4）。baseline 的时间线备注不动。

### D9 · 哪些运行不落账

| 情形 | 处理 | 理由 |
|---|---|---|
| 切片 `gate` | 不落账 | 只跑该片 verify（不经采集点）与 scenario 用例，覆盖不到整套；观测照常累积但没人读 |
| final 的 G7 红 / 选测复核未过 | 不落账 | 套件没跑 |
| 同树沿用 | 不落账 | 没有运行 |
| final 无图退路 | 落账，`mode = tests-only` | 重跑经 `_pytest_outcomes` 上报；其余用例沿用上一份收口账本（D6）。收口阶段沉淀或评审修复只动了测试文件时走的就是这条路，不落账的话 PR 正文的「测试变更」会对不上最后一条 final |
| 部件形态 | 落账，`mode = parts` | 单元层各部件经 `run_part` 上报；区域运行不采集（见 D2） |
| baseline 红 | 照常落账 | 账本记的是实测事实；起飞前本来就要重跑 baseline |

### D10 · 账本永不让门禁失败

- 落账函数整体包在 `try` 里：模块缺失、common dir 不可写、观测形状意外 → 返回 `(None, "测试账本未写：<原因>")`，警告进 `warnings`，baseline / final 的 `ok` 不变（铁律 10）。
- 采集点只做追加；依赖图插件里新加的那几行不得抛错（取不到 `duration` 记 0）。
- 对账失败 → `tests.delta = null`，`tests.why` 写原因；时间线不插片段。

### D11 · `flight-doctor.py doctor` 的 `[tests]` 与 `test-ledger.py` 的子命令

- `[tests]`：
  - 取在途 change 里最新的一份账本（先 final 后 baseline，按账本的 `at`）；
  - 打印：来源（change、阶段、commit 前 10 位、模式）、各层用例数与耗时、最慢 10 条、无耗时条数；
  - 再列最近 5 个 change 的测试变更：读各 change 时间线里最后一条带 `用例 +A/-R（新增 Xs）` 的 final 行；
  - 没有账本：一行原因（本机还没有带账本的 baseline / final）；openspec 根没有 `test-tiers.json` 时再提示可跑 `/test-tiers` 才有分层。
- `test-ledger.py show --change-dir DIR [--phase baseline|final] [--tier 层] [--top N] [--json]`：按耗时由大到小列用例；退出码 0 有账本 / 1 没有 / 2 参数不可用。
- `test-ledger.py delta --change-dir DIR [--markdown|--json]`：打印已存的对账结果；退出码同上。
- 两者只读，给人和后面的体检命令（C6）用。

## Risks / Trade-offs

- [依赖图插件改动影响每一次测试运行] → 新增逻辑只有「按 nodeid 累加一个浮点数、会话结束多写几行」；在一次性原型上跑全量（579 条）没有新增失败。
- [锚点文件变大，选锚点时要读全部锚点] → 每条用例多一个数；万级用例的锚点从约 0.5 MB 到约 1 MB，最多 20 条。读取变慢时把 `secs` 挪到旁路文件（ceiling，实现时标注）。
- [耗时有噪声，「变慢」会误报] → 只报告不判红；阈值取「翻倍且多 0.5 秒」；测量在独占锁内。阈值是草案，C5b 用实测数据再定。
- [升级后头几次飞行对账不完整] → 来源锚点没有 `secs` 时如实记「无耗时」；建议行第 3 条会提示跑一次全量。锚点链上限（缺省 5 代）也会周期性带来全量。
- [换机器 / 清了 common dir 后没有基线账本] → 对账为空并说明原因；重跑 baseline 即恢复。
- [模块级观测表] → 见 D3 的代价。
- [`ship --markdown` 在 ready 时也可能有输出] → `pr-ship.md` 同步说明；本机没有对账结果时与现状一致，`tests/test_ship_verdict.py` 钉的「ready 时为空」仍成立。
- [部件形态的账本不完整（没有区域、没有部件维度、适配器部件没有结局）] → 文档写明；C5b 设计部件维度时补。

## Migration Plan

- 随 `install.sh --upgrade` 分发：`test-ledger.py` 是新文件，其余是既有文件的增量改动。
- 不需要人工迁移。升级后：
  1. 下一次 baseline 开始写基线账本；经旧锚点的增量基线里，沿用的用例没有耗时；
  2. 第一次全量（baseline 或 final）之后锚点带上 `secs`，此后的增量运行沿用得到耗时。
- 回退：删掉 `test-ledger.py` 即可——落账点返回警告，门禁其余行为不变；`<git common dir>/flight-ledger/` 可直接删除。

## Open Questions

- **变慢阈值、建议行阈值、保留的 change 目录数**都是草案，没有数据支撑；C5b 设计预算时一起定。
- **切片门禁要不要留账**：现在不留。C3 把留痕改到 common dir 之后，可以重新考虑让每片的 scenario 用例耗时也可见。
- **部件维度**：账本现在只有层。C5b 若按部件给预算，需要给用例加部件归属，并补上部件区域运行的采集。
- **跨机器**：PR 是在另一台机器上开的时候，「## 测试变更」不会出现。是否值得把对账摘要入库，等实际出现这种用法再定。
- **换算的重名**：两条不同的 nodeid 换算后可能得到同一个 `classname::name`（如 `a/x.py::C::t` 与 `a/x/C.py::t`），对账时会并成一条。没见过实例，先不处理。
- **`GATE_TEST_RESULT` 要不要带账本路径**：本 change 不加。仓库自己的检查若要读逐用例耗时，C5b 再议。
- 没有需要 supersede 的在役 ADR。
