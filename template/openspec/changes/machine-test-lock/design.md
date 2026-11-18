## Context

**现状**（读 `template/.claude/hooks/` 现行代码，main `b7be9ed`）：

- `slice-gate.py` 的三个测量命令各自直接开跑，没有任何互斥，也不读负载：
  - `cmd_baseline`：复用判定里的补跑 → `run_test_gate(gate.test)` → lint / typecheck → 每片 verify → 已选区域 → 检查；
  - `cmd_final`：G7 实跑 scenario → lint / typecheck → gate.test（全量 / 增量 / `gate.impacted`）→ 区域 → 检查；
  - `cmd_gate`：该片 verify → lint / typecheck → G7。
- `test-tiers.py run` / `probe` 同样直接跑单元层。
- 时间线备注的现行格式与解析方：
  - baseline：`exit 0, 529.9s ok；全量：<原因>；verify 推导 N 片`，或 `增量（…） ok`；
  - final：`[全量（原因）|增量（…）] [单元 Xs · 集成 Ys] ok|red`，结论词在末尾；
  - gate：`S1 [单元 Xs · 集成 Ys] ok|red`；
  - `timeline.py report` 取 gate 备注的第一个词作切片 id、按 `endswith(" ok")` / `endswith("red")` 取结论；
  - `flight-doctor.py` 的 `parse_note` 按「全量：」「全量（」「增量」「同树沿用」分类，秒数只认 baseline 的 `exit N, Xs`（`SEC_RE`）；final 没有秒数，`cost` 里恒为 0；
  - `tests/test_flight_doctor.py` 断言 `cost --json` 的 `baseline` 对象**整体相等**，所以这两个对象不能加键。
- `_final_checks` 调 `_run_check` 拿到每项检查的秒数后丢弃（`rc, out, _, timed_out`）；baseline 的检查秒数已记在 `gate-baseline.json`。
- 本仓测试套件大量以子进程运行 `slice-gate.py baseline / final / gate`（`tests/conftest.py` 的 `run_hook` 把 `os.environ` 原样传下去）。门禁一旦取用户级目录里的锁，本仓的测试就会去排真实飞行的队。
- 门禁给子进程的环境来自 `dict(os.environ)`；`_drop_inherited` 只清 `FLIGHT_ENV` 名单里的变量。Python 打开的文件描述符缺省不被子进程继承。

**已定决策**（2026-11-18，方案页 `docs/flight-fixes-and-test-governance.html` Q1、Q2，用户回复「按推荐」）：

- **Q1**：读写锁——全量类运行独占，切片 verify 共享。
- **Q2**：排队超时后不加锁继续跑，标记争抢，时间类判定降为警告。

**在役 ADR**：

- `DRAFT-gate-test-result-handoff-and-runner-contract`：`FLIGHT_` / `GATE_` 前缀是每次运行都变的变量，项目缓存键须剔除，白名单重建环境时须放行 `FLIGHT_` 前缀。本设计新增的 `FLIGHT_LOCK_*` 沿用这条约定，不偏离。
- `DRAFT-test-tiers-unit-baseline-by-audit-probe`：G10 慢候选单独重跑确认。本设计不改这套判定，只在确知争抢的那一次把结论降级。
- `DRAFT-gate-evidence-not-self-reported`：留痕由脚本写。排队与耗时同样由脚本写进时间线。
- 没有需要 supersede 的 ADR。

```
C4 · 组件图（轻量 C4 风格；★ 新增，◆ 修改）

 飞行 A（仓库 X）            飞行 B（仓库 Y）          人 / CI
 ◆ slice-gate.py            ◆ slice-gate.py           flight-lock.py run … -- pytest
   baseline / final ─独占─┐    gate S3 ─共享─┐                │独占 / 共享
 ◆ test-tiers.py run ─独占┤                  │                │
                          ▼                  ▼                ▼
                 ★ flight-lock.py（acquire / release / holders / note）
                          │ flock                         │ 读写
                          ▼                               ▼
      ~/.claude/flight-lock/gate.lock · main.lock      holders/<pid>.json
                          │
          lock 信息 ──────┴──▶ ◆ 输出 JSON 的 lock / sec ──▶ ◆ timeline.md 备注
                                                               │ 读
                                                               ▼
                                     ◆ flight-doctor.py  cost（排队、final 秒数）· doctor [checks] [lock]
```

- **边界**：锁逻辑只在 `flight-lock.py`；`slice-gate.py` 与 `test-tiers.py` 只有「取锁 / 放锁 / 把 info 写进输出」三类调用点。
- **强制力**：锁是协作式的，只约束经门禁或 `flight-lock.py run` 启动的运行；人直接敲 `pytest` 不受约束。
- **假设**：同一个用户在一台机器上跑多条飞行（体检取证的情形）；多用户共用机器不在范围。

## Goals / Non-Goals

**Goals**：

- 同一用户、同一台机器上，同一时刻至多一套全量类测试在跑；同一 wave 的切片 verify 仍然并行。
- 每次门禁运行留下排队秒数、起止负载；final 留下 gate.test 与每项检查的秒数；`cost` 据此归因。
- 锁出任何问题门禁照跑，并留下「这次没拿到锁」的原因。
- 确知争抢的那一次，时间类判定不再判红。

**Non-Goals**：

- 共享方之间的并行度配额。
- 先来先到的严格公平。
- 多用户、多机、网络文件系统上的互斥。
- 逐用例耗时账本、分层预算（另一个 change）；baseline 回写 `slices.json`（另一个 change）。
- 给 gate.test 加运行超时。

## Decisions

### D1 · 一把读写锁，两把 `flock` 文件实现

锁目录里两个文件：`gate.lock`（闸口）与 `main.lock`（主锁）。

- 共享方：取闸口（独占）→ 取主锁（共享）→ 放闸口。
- 独占方：取闸口（独占）并**一直拿着**→ 取主锁（独占）→ 放闸口。
- 独占方在等主锁时握着闸口，后来的共享方过不了闸口，所以不会被源源不断的共享方饿死。

- **为什么用 `flock`**：进程退出（含 SIGKILL）时内核放锁，没有「死锁文件」要清；标准库 `fcntl` 就有，零依赖。
- **否决**：
  - pid 文件 + 轮询存活：进程崩溃后要靠别人判死，判错就双持或永久占用；
  - 单把 `flock` 直接用 `LOCK_SH` / `LOCK_EX`：BSD 语义不保证写方不饿死；
  - 信号量文件（N 个槽位）：能做配额，但「全量独占」要一次拿满 N 个槽，死锁与部分持有的处理都更复杂；配额本身是 Non-Goal。
- **描述符不外泄**：两个锁文件用 `os.open` 打开，Python 缺省不可继承，被测子进程拿不到这把锁。门禁进程一退出锁就释放，哪怕它起的测试进程还活着。

### D2 · 轮询取锁，不用阻塞式 `flock`

`LOCK_NB` 尝试，失败后睡 0.2 秒起、逐步加到 1 秒再试。

- **为什么**：排队期间要做三件事——第一次失败立刻打印在等谁、每 30 秒再打印、判断持有者是否停滞（D5）。阻塞调用做不了。
- **代价**：不保证先来先到（谁先轮询到谁拿）。写进 ADR 的已知天花板。

### D3 · 持锁范围是「整段测量」，不是逐条命令

- `baseline`：写完运行标记之后取锁，到检查全部结束、结束快照之前放锁。
- `final`：同树沿用判定之后（沿用就不取锁）、G7 实跑之前取锁，到检查全部结束放锁。
- `gate`：verify 之前取锁，G7 之后放锁。
- `test-tiers.py run` / `probe`：整个子命令。

- **为什么不逐条命令**：
  - 一次 final 有 G7、gate.test、若干区域、若干检查，逐条取锁要重新排 5–8 次队，总等待不可预期，时间线也没法用一个数字说明；
  - baseline 有「运行期间的改动」检测（开跑快照与结束快照之差），拉长墙钟只会增加误报；
  - 整段持有时，一次测量内部的各步骤彼此不受别的飞行干扰，秒数才可比。
- **代价**：lint / typecheck 夹在中间也占着独占锁。它们通常远短于测试；真成问题再拆。
- **baseline 的取锁点为什么在运行标记之后**：preflight 靠运行标记分辨「还在跑」与「缺基线」，排队期间也应该报「还在跑」。开跑快照仍在运行标记之前取（保持 unified-test-result-reuse design D12：快照失败不碰现有基线）；排队期间的改动会被结束快照比出来、判基线无效，这是对的。

### D4 · 重入标记带锁目录

持锁期间往 `os.environ` 写 `FLIGHT_LOCK_HELD=<方式>:<pid>:<锁目录真实路径>`，放锁时恢复。子进程请求锁时：标记里的锁目录等于当前锁目录 → 不取锁，状态 `nested`；不等 → 照常取锁。

- **为什么带目录**：本仓的测试套件会把 `FLIGHT_LOCK_DIR` 指到会话临时目录（D9）。外层门禁（真实锁目录）下跑的测试再起门禁时，应该在临时目录里真正取锁并判定，而不是被外层标记短路。
- **不做祖先进程检查**：包装脚本若按白名单重建环境又没放行 `FLIGHT_` 前缀，被测进程里再调门禁会排到持有上限后不加锁继续。契约第 1 节已要求放行 `FLIGHT_` 前缀；文档再点名一次。

### D5 · 放弃等待按「持有者停滞」判，不按排队方自己的耗时判 ⚠ 与方案页不同

方案页的草案是「排队上限 = 本仓上次全量耗时的 3 倍」。读代码后改成：

- 持有者取锁时在 `holders/<pid>.json` 里声明自己的持有上限 `cap_sec`：
  - 设了 `FLIGHT_LOCK_MAX_HOLD_SEC` → 取它；
  - 否则有上次全量耗时 → `max(300, 3 × 耗时)`；
  - 否则 1800。
- 排队方每次轮询读在世的持有者：最早的那个已持有超过它的 `cap_sec` → 放弃，状态 `timeout`，`why` 写「<change> · <标签> 已持有 N 秒，超过上限 M 秒」。
- 读不到任何持有者信息（刚取到锁还没写文件的瞬间）→ 按排队方自己的同一公式兜底。

- **为什么改**：
  - 按排队方算，小仓库排在大仓库后面必然超时：本仓全量约 5 分钟，afa 约 10 分钟，再排两条 afa 的飞行就是 20 分钟——正常排队被当成超时，一超时就并跑，等于没锁；
  - 方案页 Q2 的前提写的是「超时只对应持有者真的跑了很久」，按持有者判才是这句话的字面意思；
  - 队伍里每换一个持有者，时钟自然重置，排多久都不算超时，只有某一个持有者卡住才算。
- **上次全量耗时从哪来**：本 change `gate-baseline.json` 的 `test.sec`（baseline 命令读覆盖前的旧基线）；读不到再退 `slices.json` 的 `gate.full_suite_sec`。另一个 change 要把后者挪走，先读基线使两边都成立。
- **数字都是草案**：3 倍、300 秒、1800 秒没有数据支撑，上线后看时间线里的排队秒数再调。

### D6 · 只有 `timeout` 降级；`off` 与 `unavailable` 照常判 G10 ⚠ 与方案页不同

方案页写的是「没拿到锁的那次（排队超时 / 未加锁），时间类判定一律降为警告」。本设计只在 `timeout` 时降级。

- **为什么**：
  - `timeout` 是**确知**有别的运行同时在跑，秒数必然不可信；
  - `unavailable`（没有 `flock` 的平台、锁目录不可写）下如果也降级，这些环境里 G10 就永远不会红——相对今天是放宽，违背「门禁只能加严」；今天的行为（带单独重跑确认的判定）应当保持；
  - `off` 是人显式声明「这里已经隔离」（CI 容器），正是最该照常判的地方；如果 `off` 就降级，CI 里 G10 永不判红。
- **降级的形状**：把以 `G10 slow unit test` 开头的失败项挪进警告，原文保留，末尾加「（排队放弃后未持锁，时间类判定降为警告：<why>）」。G11（纯度）与差分判定不动。
- **实现位置**：`slice-gate.py` 一个纯函数处理 `(failed, warnings, lock_info)`，在 baseline 与 final 取得 G10 / G11 结论的各处调用（简写形态的全量与增量、部件形态的 `_baseline_parts` / `_final_parts`）。

### D7 · `flight-lock.py` 的接口（S3 / S4 / S5 按它写）

模块（经 `importlib` 按路径加载，与 `flight-doctor.py` 加载 `slice-gate.py` 同法），**任何函数都不抛异常**：

| 接口 | 说明 |
|---|---|
| `acquire(mode, change="", label="", expect_sec=None)` | `mode` 为 `"exclusive"` / `"shared"`；阻塞到拿到、放弃或判定不取；返回持有对象 |
| 持有对象 `.info` | `{"mode", "state", "waited", "why", "load", "cores"}`；`state` ∈ `held` / `nested` / `off` / `unavailable` / `timeout`；`waited` 保留 1 位小数；`load` 为 `[起, 止]`（止在 `release` 时填）或 `None`；`cores` 为整数或 `None` |
| 持有对象 `.release()` | 幂等；删自己的持有者文件、放锁、恢复重入标记、填 `load[1]` |
| `holders()` | 在世持有者列表：`{"pid", "mode", "change", "label", "started"（ISO）, "held_sec", "cap_sec"}`；pid 已不在的文件顺手删掉 |
| `note(info)` | 时间线锁片段（D8） |
| `lock_dir()` | 当前生效的锁目录 |

CLI：

- `flight-lock.py run <exclusive|shared> [--change NAME] [--label TEXT] [--expect-sec N] -- CMD [ARG…]`：取锁 → 不经 shell 运行 CMD → 放锁 → stderr 末行 `flight-lock: <info 的 JSON>` → 以 CMD 的退出码退出（CMD 起不来为 127）。
- `flight-lock.py status [--json]`：`holders()` 的内容，另带 `dir` 与 `enabled`；恒退出 0。

排队提示（stderr）：`flight-lock: 排队中（<方式>），等 <change> · <标签> · pid <pid> · 已持有 <N>s`。

`slice-gate.py` 一侧只有一个加载函数：加载失败、文件缺失、`acquire` 意外抛错都返回一个 `state = unavailable` 的替身对象（带 `info` 与空的 `release()`），调用点不写 `try`。

### D8 · 留痕格式（只增不改）

锁片段 `note(info)`：

| 状态 | 片段 |
|---|---|
| `held` | `排队 12.3s` |
| `timeout` | `排队 600.0s 后放弃（<why>）` |
| `nested` | `重入` |
| `off` | `未加锁（FLIGHT_LOCK=off）` |
| `unavailable` | `未加锁（<why>）` |

`load` 非空时其后接 ` · 负载 2.9→17.8/18`（各保留 1 位小数）。

各事件的备注：

- **final**：`[全量（…）|增量（…）] [单元 Xs · 集成 Ys] [测试 Xs] [检查 a Xs / b Ys] <锁片段> ok|red`。新片段之间、以及与前面的分层片段之间用 ` · ` 连接；与「全量（…）」「增量（…）」之间仍是一个空格；结论词前一个空格。同树沿用的备注不变。
- **gate**：`S1 [单元 Xs · 集成 Ys] <锁片段> ok|red`，连接规则同上。integrator 的 `record` 写回分支的那一行不变（见 Risks）。
- **baseline**：现有三种备注末尾各接 `；<锁片段>`。
- 例：`全量（没有可用锚点） 测试 524.3s · 检查 ratchet 3.1s / linkage 2.4s · 排队 212.0s · 负载 2.9→17.8/18 ok`。

输出 JSON：

- 三个命令都加 `lock`（即 `info`）；baseline 同时写进 `gate-baseline.json`（入池与锚点只挑固定键，不带它）。
- final 加 `sec`：`{"test": 秒 | null, "checks": {名: 秒}}`。`test` 是 gate.test 这一步的墙钟（全量、增量重跑或 `gate.impacted`，不含区域）；没跑到（G7 红、scope 复核未过、部件形态）为 `null`，此时备注没有「测试」片段。`checks` 只含本次实际运行的检查。

解析（`flight-doctor.py`）：

- `测试 ([\d.]+)s` → 该 final 的秒数；全量时计入 `final.full_sec` 与 `full_runs[].sec`；
- `排队 ([\d.]+)s` → 排队秒数，按事件累加到新的顶层键 `wait_sec`；
- `检查 (.+?)(?= · | ok$| red$)` 再按 ` / ` 拆成「名 秒」；
- 没有这些片段的行按旧逻辑，结果与改动前相同；`baseline` / `final` 两个对象不加键（现有测试整体断言）。

### D9 · 测试套件用自己的锁目录

`tests/conftest.py` 在导入时建一个会话临时目录、写进 `os.environ["FLIGHT_LOCK_DIR"]`，进程退出时删除。

- **为什么不用 `FLIGHT_LOCK=off`**：关掉之后门禁输出里就没有 `held` 状态可测；而且套件应当走真实的取锁路径。
- **为什么够用**：套件里的门禁子进程在临时目录取锁，串行执行、互不等待；外层若有真实门禁持锁，重入标记里的目录不同（D4），不会短路。
- 专测并发的用例各自再建锁目录，经环境显式传给每个子进程。

### D10 · `doctor` 的两节

- `[checks]`：每个在途 change 取时间线里最近一条带「测试」片段的 final 备注；某项检查 ≥ 10 秒且 ≥ 测试秒数的一半 → 一行点名 change、检查、两个秒数，写「疑似检查在重跑测试，改读 `$GATE_TEST_RESULT`（契约第 3 节）」。没有命中写「无」。阈值是草案。
- `[lock]`：锁目录、是否启用、`holders()`；没有持有者写「空闲」；`FLIGHT_LOCK=off` 写「已关闭（FLIGHT_LOCK=off）」。`flight-lock.py` 加载失败写原因。

## Risks / Trade-offs

- **[共享方之间仍可能超订]** 五个切片同时 verify 且各自满核并行 → 不做配额；时间线里有负载数字，上线后据此决定。
- **[不保证先来先到]** 轮询取锁，后到的可能先拿 → 独占方握着闸口，最多被一个后到的独占方插队；写进 ADR。
- **[锁只在用户级目录]** 多用户共用机器互不可见；主目录在网络文件系统上时 `flock` 可能不可靠 → 文档写明可用 `FLIGHT_LOCK_DIR` 指到本机路径。
- **[包装脚本剥掉 `FLIGHT_LOCK_HELD` 且被测进程里再调门禁]** → 内层排到持有上限后不加锁继续；契约文档点名这个变量须放行。
- **[baseline 排队期间运行标记显示「仍在跑」]** 起始时间早于实际开跑 → 排队提示打在 baseline 的 stderr 里；preflight 的文案不改。
- **[切片 gate 的排队秒数到不了分支的时间线]** gate 在临时 worktree 里跑，integrator 用 `record --json` 写回的只有固定字段 → 本 change 不改工作流脚本与 `record`：切片 gate 的排队信息只在它的输出 JSON（`lock`）与临时 worktree 的时间线里，分支上的 `cost` 只统计 baseline 与 final 的排队。要带回分支得给工作流的门禁结构加字段，留给后续 change。
- **[并发测试的时序]** 用「开始文件 / 放行文件 / stderr 里的排队提示」作同步点，只有「持有者超过上限」一条依赖真实时间（0.3 秒上限，轮询 0.2 秒）→ 断言留足余量（等待上限 10 秒）。
- **[gate.test 挂死会占着锁]** 本 change 不给 gate.test 加超时 → 排队方按 D5 放弃并留痕，不会被永久卡住。
- **[与并行中的 plan-hygiene change 冲突]** 两边都改 `slice-gate.py` 的 baseline 段与 `flight-doctor.py` → 后合的那个 PR 预合并 main 时解冲突；本设计不依赖 `gate.full_suite_sec` 的去留（D5）。

## Migration Plan

1. 合入后各仓库 `./install.sh --upgrade`，新 hook 随 `.claude/hooks/` 下发；无配置、无数据迁移。
2. 第一次运行自动建锁目录。
3. 观察一周 `flight-doctor.py cost` 的排队秒数与时间线里的负载，回头定 D5 的数字和要不要做共享配额。
4. **回退**：环境里设 `FLIGHT_LOCK=off` 即恢复改动前的行为（不排队、G10 照常判）；删掉 `flight-lock.py` 效果相同（状态 `unavailable`）。时间线与 JSON 的新片段不影响旧版解析。

## Open Questions

- **D5 与 D6 两处偏离方案页**，请在 `spec.html` 审批时确认：按持有者判停滞；`off` / `unavailable` 不降级。
- D5 的三个数字（3 倍、300 秒下限、1800 秒缺省）与 D10 的阈值（10 秒、一半）都是草案。
- lint / typecheck 是否该留在独占段内（D3）：现在留着，等时间线数据。
- 没有需要 supersede 的在役 ADR。
