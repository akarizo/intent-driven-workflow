## Context

本 change 命中两条触发器：
- **数据模型**：锚点池条目新增字段 `full_suite_sec`；
- **跨模块**：baseline 与 final 写锚点，baseline、final、preflight 读全量耗时。

**全量耗时的现状**（`slice-gate.py`）：

- 读取只经 `suite_sec(change_dir, data)`。取值顺序是 `gate-baseline.json` 顶层的 `full_suite_sec`，再到计划里旧的 `gate.full_suite_sec`（`DRAFT-measurements-stay-out-of-plan-files` 决策 2、3）。
- final 的超时上限是 `_g7_timeout`：有全量耗时时取 `max(120, 3 × 全量耗时)`，没有时取 600 秒。
- baseline 结束时按下面的顺序写 `full_suite_sec`（`_run_baseline` 结尾，约 5207–5214 行）：

| 情形 | 取值顺序（现状） |
|---|---|
| 全量运行 | 本次墙钟 |
| 增量（复用旧基线 / 锚点 / 基线池） | `last_sec`（开跑前 `suite_sec`）→ `src.full_suite_sec` → `src.test.sec` |

**缺陷链**：C2 实测，各 change 的 `gate-baseline.json` 与 `timeline.md` 可查。

```
baseline #1（经锚点）   last_sec=None · 锚点包装没有 full_suite_sec / test
                        → full_suite_sec = None；test.sec = 补跑 131.6s
baseline #2（复用 #1）  last_sec=None · src=#1：full_suite_sec=None → 取 src.test.sec = 131.6
                        → full_suite_sec = 131.6（真实全量约 470s）
final                   超时上限 3 × 131.6 = 394.8s；增量重跑 394.9s → 「G2 test：增量重跑超时」×2
```

**预热来源的现状**：`_warm_source` 在 changes 根下按 `slices.json` 的 `os.path.getmtime` 取最新的那个，比较用严格的 `>`。新 worktree 是一次检出的，32 个 `slices.json` 的 mtime 完全相同（实测），结果取决于 `os.listdir` 的顺序。

## Goals / Non-Goals

**Goals:**
- 增量 baseline 的 `full_suite_sec` 只来自真实的全量测量（本次全量、预热、来源锚点沿链继承下来的全量）；取不到时留空，不拿补跑秒数充当全量。
- 锚点条目带上全量耗时，并随增量 baseline 与增量 final 写出的新锚点传下去。
- 预热来源的选择只取决于 git 历史与 change 名，和检出时刻、文件系统顺序都无关。

**Non-Goals:**
- 不改 `_g7_timeout` 的公式与 600 秒缺省。
- 不回填旧锚点：没有字段就按未知处理（用户 2026-11-20 选定）。
- 不改基线池：池只收全绿的全量，它的 `test.sec` 就是全量耗时，`tests/test_baseline_pool.py` 钉住的行为保持。
- 不改预热的其它规则：分层仓库跳过、`--cmd` 显式命令、包装脚本沿用都不动。

## Decisions

### D1 锚点条目记 `full_suite_sec`

| 写锚点的地方 | `full_suite_sec` 取值 |
|---|---|
| 全量 baseline（`hit is None`，非部件形态） | 本次全量墙钟（就是写进基线的那个 `full_sec`） |
| 全量 final（`anchor_part` 的 `source: final-full`） | 本次 `run_test_gate` 的墙钟，一位小数 |
| 增量 baseline / 增量 final（`_anchor_forward`） | 来源锚点的 `full_suite_sec`，经 `_num` 过滤，不是数值就为 `None` |

`_anchor_forward` 是两条增量路径共用的构造函数，在它的返回值里加这一个键，就同时覆盖增量 baseline 与增量 final。

**备选**：只在 baseline 写锚点时带。被否：final 写出的锚点同样会成为下一个 change 的来源，漏掉 final，链会在 final 处断开。

### D2 增量 baseline 的取值顺序

| 来源 | 取值顺序（修复后） |
|---|---|
| 锚点 | `last_sec` → 来源锚点（`cand["pick"][0]`）的 `full_suite_sec` → `None` |
| 本 change 旧基线 | `last_sec` → `src.full_suite_sec` → `src.mode == "full"` 时取 `src.test.sec` → `None` |
| 基线池 | `last_sec` → `src.full_suite_sec` → `src.test.sec`（池条目都是全量） |

- **`last_sec` 仍然排第一**：沿用 `DRAFT-measurements-stay-out-of-plan-files` 决策 2「增量基线沿用上一份的值」。预热写的就是真实全量，排第一能让 /opsx-propose 的常规流程拿到最新测量。
- **判定「是不是增量」**：旧基线看自己的 `mode` 字段。基线池条目没有 `mode`，但按 `_pool_write` 的入池条件（`hit is None`）全是全量，所以按全量处理。
- **备选**：锚点值优先于 `last_sec`。被否：`last_sec` 来自本 change 自己的测量，比跨 change 的锚点更贴近当前代码树；两者都是真实的全量测量。

### D3 预热来源：git 最后提交时间

- **排序键**：每个候选 change（除 `archive` 与本 change 外，`slices.json` 存在且 `gate.test` 非空）记作 `(提交时间, 名字)`，取最大的那个。
  - **提交时间**：git 里最后一次改动该 `slices.json` 的提交的 committer 时间（`%ct`）。
  - **从没提交过的**：提交时间记为 `-1`，所以排在所有已提交的之后。
  - **时间相同**：取名字字典序最大的。
- **取时间的方式**：一次 `git log --format=%ct --name-only -- <changes 根>/*/slices.json`，逐行解析，每个路径取第一次出现时的时间（`git log` 从新到旧排，第一次出现的就是最新提交）。git 调用失败时，全部按 `-1` 处理，退化为按名字排序。
- **备选**：
  - **最近一条锚点所属的 change**：锚点池为空、或那个 change 已经归档时还得再退一步，规则更长。被否（用户 2026-11-20 选定 git 提交时间）。
  - **只按名字排序**：确定，但名字和新旧无关。被否。

### 动态图（C4 dynamic，ASCII）

```
 /opsx-propose                    slice-gate.py                         锚点池（git common dir）
 ─────────────                    ─────────────                         ────────────────────────
 warm ──────────────────────────▶ _warm_source：按 (git %ct, 名字) 选来源
                                  全量运行 ─────────── 写锚点 {full_suite_sec: 墙钟} ──▶ A1
                                  gate-baseline.json.full_suite_sec = 墙钟
 baseline（经锚点）─────────────▶ last_sec ?? A1.full_suite_sec ─────────────────────── 读 A1
                                  写锚点 _anchor_forward(A1) {full_suite_sec: A1 的} ──▶ A2
 baseline（复用旧基线）─────────▶ last_sec ?? old.full_suite_sec ?? (old 是全量 ? old.test.sec : None)
 final（增量）──────────────────▶ _g7_timeout(suite_sec) · 写 A3 = _anchor_forward(A2) ──▶ A3
 final（全量）──────────────────▶ 写锚点 {full_suite_sec: 本次墙钟} ──────────────────▶ A4
```

- **边界**：`slice-gate.py` 是唯一的写方；锚点池是跨 change 共享的测量存储；`gate-baseline.json` 是本 change 的测量归宿。
- **假设**：锚点池里的旧条目没有 `full_suite_sec`，按未知处理。

## Risks / Trade-offs

- **[风险] 过渡期旧锚点没有字段**：经旧锚点、本 change 又没有预热时，`full_suite_sec` 为空，final 超时上限退到 600 秒。本仓库 C2 的增量 final 跑过 609.6 秒，可能超时。→ **缓解**：
  - /opsx-propose 的常规流程先预热，`last_sec` 排第一；
  - 锚点池只留最新 20 条，每次 baseline / final 都写新锚点，旧条目很快被挤出；
  - 必要时可设 `FLIGHT_G7_TIMEOUT` 临时覆盖超时上限（现有行为）。
- **[风险] git 调用失败**：比如不在 git 仓库内。→ 全部按 `-1` 退化为按名字排序，结果仍然确定，预热照常进行。
- **[权衡] 已提交的旧 change 会胜过没提交的新 change**：同一 worktree 里正在规划、还没提交的另一个 change，排在已提交的后面。这种布局本来就少见（每个 change 有自己的 worktree），换来的是结果不依赖检出时刻。

## Migration Plan

- 不迁移数据：旧锚点没有字段按未知处理，旧 `gate-baseline.json` 不改。
- 回滚：revert 本 change 的代码 commit 即可。新锚点多出的字段旧代码不读，不影响回滚。

## Open Questions

- 无。两项决策已在 grill-me 定下（2026-11-20）：预热来源按 git 最后提交时间；旧锚点留空、退到 600 秒。
- 与在役 ADR 一致：`DRAFT-measurements-stay-out-of-plan-files` 规定增量基线沿用上一份的值、读取经 `suite_sec`，本 change 两条都沿用，不需要 supersede。
