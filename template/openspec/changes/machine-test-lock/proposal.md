## Why

门禁把机器当成自己独占的：每条飞行的 baseline、final、切片 verify 都直接开跑，彼此不知道对方存在。afa 的测试分层体检（2026-11-18）取证时，18 核机器上另一条飞行正在收口，负载 37–45。后果有三个：

- 墙钟被拉长，而且拉长了多少没有记录；
- 时间类判定失真——项目侧的单条 3 秒预算在负载高于核数时只能退化成告警，模板的 G10 慢单测判定在同样条件下会不会误判，没有运行样本；
- 时序敏感的用例偶发红，把 MR 打成 draft。

模板里没有任何并发闸：`slice-gate.py` 全文没有文件锁，也不读负载。

同一份体检还指出收口的成本在留痕里是 0：final 的时间线备注没有秒数，各项检查的耗时算出来又丢了（`slice-gate.py` 的 `_final_checks` 丢弃 `_run_check` 返回的秒数），`flight-doctor.py cost` 因此报「final：全量 3 次（0.0 秒）」。最贵的一步无法归因，违背铁律 8（度量必打印）。

2026-11-18 的方案页（`docs/flight-fixes-and-test-governance.html`）定了两点：

- **Q1 粒度**：读写锁——全量类运行独占，切片 verify 之间共享。
- **Q2 排队超时**：放弃等待后不加锁继续跑，标记争抢，时间类判定降为警告，对错判定不变。

## What Changes

- **新增全机测试锁** `template/.claude/hooks/flight-lock.py`（锁逻辑全在这一个文件）：
  - 用户级目录（缺省 `~/.claude/flight-lock/`，`FLIGHT_LOCK_DIR` 可改）下的一把读写文件锁，跨仓库、跨 worktree 共用；用系统的 `flock`，持有进程退出时内核自动放锁。
  - **独占**与**共享**两种持有方式；独占方排队时后来的共享方进不来（不饿死）。
  - 持有期间给子进程带重入标记：被测进程里再调门禁不会自己等自己。
  - 持有者把自己是谁（change、命令、pid、起始时间、持有上限）写在锁目录里；排队方立刻打印在等谁，之后每 30 秒打印一次。
  - **放弃等待**：最早的在世持有者持锁超过它声明的上限（缺省为它上次全量耗时的 3 倍、不低于 300 秒；没有耗时记录时 1800 秒；`FLIGHT_LOCK_MAX_HOLD_SEC` 可改）→ 排队方不再等，不加锁继续跑。
  - **回退**：平台没有 `flock`、锁目录不可用、`flight-lock.py` 缺失或抛错 → 不加锁照跑并记「未加锁」；`FLIGHT_LOCK=off` 显式关闭（给已经隔离的 CI 容器用）。锁自身的任何问题都不让门禁失败。
  - CLI：`flight-lock.py run <exclusive|shared> -- <命令>`（门禁之外的测试运行也能排队）与 `flight-lock.py status`。
- **门禁持锁**（`slice-gate.py` 只加调用点）：
  - `baseline`、`final` 从第一条测试命令到最后一项检查整段**独占**；
  - 切片 `gate` 的 verify 到 G7 整段**共享**；
  - `test-tiers.py run` / `probe` **独占**。
- **争抢时降级**：放弃等待后跑出来的那一次，G10 慢单测由判红降为警告并写明原因；G11 及所有对错判定不变。
- **留痕**：
  - baseline / final / gate 的输出 JSON 带 `lock`（方式、状态、排队秒数、起止负载、核数），时间线备注带「排队 N 秒 · 负载 起→止/核数」；
  - final 的 JSON 带 `sec`（gate.test 秒数与每项检查秒数），时间线备注带「测试 N 秒 · 检查 <名> N 秒」；
  - 结论词仍在备注末尾，旧时间线照常能读。
- **成本归因与体检**（`flight-doctor.py`）：
  - `cost` 认新备注：final 的秒数不再是 0，另列排队秒数；
  - `doctor` 新增 `[checks]`（某项检查耗时接近 gate.test → 疑似检查在重跑测试）与 `[lock]`（当前持有者）。
- **文档**：`flight-runner-contract.md` 新增一节；`opsx-apply` / `opsx-propose` 命令与同名 skill、`test-tiers.md`、`README.md` 各补一句排队说明。
- **不做**：
  - 共享方之间的并行度配额（已知天花板，先看上线后的负载数字）；
  - 逐用例耗时账本、分层预算与豁免（另一个 change）；
  - baseline 回写 `slices.json`、契约未接的表态（另一个 change）；
  - 多用户共用一台机器时跨用户排队（锁在用户级目录）。

## Capabilities

### New Capabilities

- `machine-test-lock`：全机测试锁的语义（独占 / 共享 / 不饿死 / 重入 / 放弃等待 / 回退）、门禁各命令的持锁方式、争抢时时间类判定降级、排队与耗时的留痕、`flight-doctor.py` 的归因与体检、随模板下发的说明。

### Modified Capabilities

- 无。`openspec/specs/` 不存在；门禁的对错判定不变，本 change 的增量以 ADDED 写在新 capability 里。

## Impact

- **代码**：新增 `template/.claude/hooks/flight-lock.py`；改 `template/.claude/hooks/slice-gate.py`（调用点、输出字段、备注、G10 降级）、`test-tiers.py`（`run` / `probe` 持锁）、`flight-doctor.py`（`cost` 解析、`doctor` 两节）。
- **测试**：新增 `tests/test_flight_lock.py`、`tests/lock_helpers.py`、`tests/test_gate_lock.py`、`tests/test_gate_cost_note.py`、`tests/test_flight_doctor_lock.py`、`tests/test_lock_docs.py`；`tests/conftest.py` 给整个套件指定临时锁目录（本仓测试会在子进程里跑门禁，不能去排真实的全机锁）。
- **文档**：`template/.claude/flight-runner-contract.md`、`template/.claude/commands/{opsx-apply,opsx-propose,test-tiers}.md`、`template/.claude/skills/{openspec-apply-change,openspec-propose}/SKILL.md`、`README.md`。
- **ADR**：新增 `template/openspec/adr/DRAFT-machine-wide-test-lock.md`。
- **行为变化**：同一用户在同一台机器上的多条飞行，全量类运行改为排队；`FLIGHT_LOCK=off` 恢复原行为。输出 JSON 与时间线只增不改；`flight-doctor.py cost --json` 的新数据放在新的顶层键里，已有键的形状不变。
- **下游**：已安装的仓库跑 `./install.sh --upgrade` 拿到新 hook；项目侧缓存键按契约第 4 节已须剔除 `FLIGHT_` 前缀，新增的 `FLIGHT_LOCK_*` 变量不需要额外处理。
- **与方案页的两处出入**（详见 design D5、D6）：放弃等待的上限按**持有者**算而不是按排队方自己算；`FLIGHT_LOCK=off` 与平台不支持时 G10 **不**降级。
