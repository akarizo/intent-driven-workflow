## Context

**现状**（行号指 `template/.claude/hooks/`，main `ef52807`，即 C1 `plan-hygiene` 合入之后）：

- **`ship` 的新鲜度只容忍记账文件**：`_final_fresh`（`slice-gate.py:5766`）取 final 行的 commit 与 HEAD 的文件名之差，全部是 `changes/<任一 change>/` 下的记账文件才算新鲜。
- **同树沿用同样只容忍记账文件**：`_final_reusable`（`:5246`）按严格 Δ 判，去掉记账文件后必须为空。
- **final 走增量的唯一入口是测到依赖图的锚点**：`_pick_anchor`（`:5295`）只取 `measured` 为真的锚点；取不到时 `_full_triggers` 给出 `final:no-anchor`，`_full_why` 说「没有可用锚点」（`:5398`），全量。
- **baseline 有一条不靠依赖图的复用路**，final 没有：`_try_reuse`（`:5650`）在 Δ 只含 `test_*.py` 时复用上次全量结论、只补跑这些文件；Δ 里有别的文件就报「有非测试文件改动」。
- **每次实跑的 final 都留一份记录**：`<git common dir>/flight-final/<change>.json`（`_final_rec_write`，`:5237`），含 commit、快照、指纹与结果；红的记录带着最近一次绿的树（`_last_green`，`:5257`）。`gate.impacted` 已经拿它当锚点用（`_impacted_anchor`，`:5267`）。
- **可选声明已有三项**：`gate-scope.json` 的 `global` / `blind` / `anchor_max_hops`（`SCOPE_EXTRAS`，`:1527`；`_scope_extras`，`:1588`），形状由 `_scope_decl` 校验。
- **预告函数只有一个**：`final_forecast`（`:5777`），`flight-doctor.py forecast` 与 `ship` 的「final 过期」理由都调它。
- **`/pr-ship` 无条件重跑**：step 2b 写的是「沉淀 commit 之后重跑 final」（`commands/pr-ship.md:50`）。

**实测**（2026-11-18，各 change 时间线里 apply-done 之后的 final 行）：afa 收口阶段全量 49 次，原因全部是「没有可用锚点」；本仓 2 次，都在增量功能自己的那个 change。

**用户决策**（2026-11-18，方案页 `docs/flight-fixes-and-test-governance.html` 第 02b 节与对话）：收口全量属于需要加固的结构性问题；`inert` 不做缺省、与依赖图对账；final 补一条无图退路；`/pr-ship` 先裁决再重跑。

**在役 ADR 的约束**：

- `DRAFT-final-incremental-by-dependency-anchor` 决策 4「没有可用锚点即全量」、决策 5「`ship` 按两棵树的差判 final 是否过期」：D5 给前者加一个例外，D2 给后者的「差」加一类不计的路径。新立 ADR 记录，原文不改。
- `DRAFT-baseline-reuse-by-content-fingerprint`（只改测试文件才复用）与 `DRAFT-baseline-reuse-via-dependency-anchor`：D2 在两条路上各去掉 `inert` 路径，判据本身不变。
- `DRAFT-gate-test-result-handoff-and-runner-contract` 决策 1（结果文件写明 `mode` / `inherited` / `complete`，由检查自己决定）：D6 在它之内加一个 `mode` 取值。
- `DRAFT-unmeasured-deps-need-plan-statement`（C1）：依赖图未测须表态。本 change 不改它；无图退路只在已经表态（或配了 `gate.pytest` 的可复现运行器）的前提下生效。
- `DRAFT-repo-selector-reports-scope-at-plan-time`、`DRAFT-scope-provider-mandatory-with-runtime-guard`：`gate-scope.json` 的形状校验与开跑前复核，D3 的核对挂在同一处。

```
C4 · 容器图（轻量 C4 风格；◆ 修改，＋ 新增）

 [仓库维护者] ──声明──▶ ◆ <openspec 根>/gate-scope.json
                           ├ global（一改就全量）
                           ├ blind（每次都重跑）
                           └ ＋ inert（改了不影响测试结论）
                                   │ 读（_scope_extras）
        ┌──────────────────────────┼───────────────────────────────┐
        ▼                          ▼                               ▼
 ◆ 选测复核                 ◆ 测试结论的三处复用               ◆ flight-doctor.py doctor
 lint / preflight /         ├ ship 新鲜度（_final_fresh）         [declare] 列出声明与矛盾
 baseline 开跑前            ├ final 同树沿用 + 取锚点的 Δ
 ＋ 静态核对                └ baseline 复用（旧基线 / 池 / 锚点）
 ＋ 与依赖图对账 ◀── 读 ── <git common dir>/flight-anchors/（测到依赖图的锚点）
        │ 矛盾 → 判红                 │ 运行时矛盾 → 依赖图优先 + 警告
        ▼                             ▼
 [人类] 修声明                 ◆ slice-gate.py final
                                 ├ 有锚点 → 按依赖图增量（不变）
                                 ├ ＋ 没有锚点，上次绿 final 之后只改了测试文件 → 只重跑它们（tests-only）
                                 │        读 <git common dir>/flight-final/<change>.json
                                 └ 其余 → 全量；因非测试文件而不适用时点名文件
                                          │
                 ◆ final_forecast ◀───────┘ 同一个判定
                   ├─▶ flight-doctor.py forecast
                   └─▶ ship 的「final 过期」理由 ──▶ ◆ /pr-ship：先看 ship，再决定是否重跑 final
```

- **边界**：`inert` 只影响「测试结论能不能沿用」这一件事；计划、门禁声明、lint / typecheck 结论、起飞前的基线过期判定都不看它。
- **强制点**：声明对不对，在选测复核里机械核对；运行时再以依赖图为准兜一次。
- **假设**：仓库维护者会在 PR 里审 `gate-scope.json` 的改动；依赖图测不到的仓库里，对账做不了，这一层只剩人审。

## Goals / Non-Goals

**Goals**：

- 只改了与测试无关的路径（记忆文件、文档等）时，`ship` 不判 final 过期，final 与 baseline 不因它重跑。
- 声明写错时，能机械发现的在起飞前发现；运行时不因声明跳过依赖图认定该重跑的测试。
- 没有依赖图的仓库，上次绿 final 之后只改了测试文件时，final 只重跑这些文件。
- 仍然要全量时，事先说清原因，点名文件。
- `/pr-ship` 的重跑由 `ship` 的输出决定。

**Non-Goals**：

- 不给 `inert` 缺省值，不按扩展名推断。
- 不放宽起飞前检查的「基线过期」与 lint / typecheck 结论的沿用条件。
- 不改 `gate.impacted` 路径。
- 不为无图退路写锚点、不让它支持测试分层。
- 不改 C1 的表态制与它的豁免范围。
- 不动全机测试闸与时间线耗时格式（C2）。

## Decisions

### D1 · `inert` 是 `gate-scope.json` 的第四个可选字段

- **形状**：仓库相对路径 glob 的字符串数组，匹配方式与 `global` / `blind` 相同（`fnmatch.fnmatchcase`，`*` 可跨目录）。并入 `SCOPE_EXTRAS` / `SCOPE_EXTRAS_SHAPE` / `_scope_extras`，形状错误沿用现有通道由 lint、preflight 点名。
- **不做缺省**：本仓就有读 `CLAUDE.md`、README 与命令文档的测试；哪条路径与测试无关只有仓库自己知道。
- **否决**：
  - 按扩展名把 `.md` / 配置当无关：正是本仓会漏测的做法。
  - 写在每个 change 的计划里：它是仓库的事实，不是某个 change 的决定；放计划里还要进批准与 `plan_sha` 的讨论。
  - 复用 `global` 取反之类的写法：两个字段各说一件事更好审。

### D2 · 生效范围：三处测试结论的复用；五类路径永不生效

- **一个判定函数**，三处共用：给定一组路径，返回其中按 `inert` 生效的子集。
- **生效处**：

  | 位置 | 现在 | 改后 |
  |---|---|---|
  | `ship` 的新鲜度（`_final_fresh`） | 差集全是记账文件才新鲜 | 去掉记账文件后，其余全部按 `inert` 生效也算新鲜 |
  | final 同树沿用（`_final_reusable`） | 严格 Δ 去掉记账文件须为空 | 再去掉生效的 `inert` 路径 |
  | final / baseline 取锚点（`_pick_anchor`） | Δ 原样参与选测与全量触发项 | 逐个候选先去掉生效的 `inert` 路径，再比 Δ 大小 |
  | baseline 旧基线 / 基线池（`_try_reuse`） | Δ 有非 `test_*.py` 即不复用 | 判定前去掉生效的 `inert` 路径；返回的 `files`（供 verify 判重跑）仍是完整 Δ |
  | 无图退路（D5） | — | Δ 去掉生效的 `inert` 路径 |

- **永不生效的五类**（即使匹配 glob）：
  - 测试路径（`is_test_path`：`tests/` 等目录下的任何文件，或按文件名认出的测试文件）；
  - 全局文件（`_global_file`：`conftest.py`、`pyproject.toml`、`pytest.ini` 等）；
  - `global` 命中的路径——同一路径同时匹配 `inert` 与 `global` 时 `global` 赢；
  - `changes/` 下的路径（计划变了 final 必须过期；记账文件另有规则）；
  - 三份声明文件（改了声明本身就该重新判一次）。
- **不在范围内的判定**：
  - preflight 的「基线过期：自基线以来有改动」不看 `inert`：基线还管 lint / typecheck / 检查的结论，重跑一次 baseline 走增量、代价很小。
  - lint / typecheck 结论的沿用条件（严格 Δ 为空）不看 `inert`：文档格式检查这类 lint 正是被这些路径影响的。
  - `gate.impacted`：Δ 原样交给仓库的选测命令。
- **否决**：把 `inert` 做进 `_delta` 本身——它的调用方里有上面三处不该放宽的判定，逐个调用点显式选用更不容易放错。

### D3 · 核对分两层：起飞前判红，运行时依赖图优先

- **静态核对**（选测复核：lint、preflight、baseline 开跑前；在按提供方核对之前）：`git ls-files` 里匹配某条 `inert` glob 的路径，若属于测试路径、全局文件、`global` 命中 → 判红，点名 glob、至多 5 个路径与类别。
  - `changes/` 下的路径与声明文件不判红，只是不生效：`openspec/**` 这种写法很自然，判红会逼人把 glob 拆碎。
- **依赖图对账**（同一处）：取锚点池里与本计划同命令指纹、同分层指纹、测到依赖图的最新一条锚点；任一测试文件的依赖（含 shell 静态闭包，与 `_final_select` 同口径）里有按 D2 生效的 `inert` 路径 → 判红，点名路径、测试文件与锚点。没有这样的锚点 → 不对账、不判红。
  - 用「最新一条」而不是 final 实际会选的那条：lint 阶段还没有本 change 的基线，能拿到的证据就是池里最新的测量；它不是 HEAD 的祖先也不妨碍它证明「有用例读这个文件」。
- **运行时**（final 与 baseline 的锚点路径）：对选中的那条锚点再判一次，被依赖的路径不生效、留在 Δ 里，依赖它的测试文件照常被选中；final 另给一条警告。`ship` 与同树沿用没有选中的锚点，用对账那一条。
- **`doctor`**：`[declare]` 多列一项 `inert`；声明了的话，对锚点池里每条测到依赖图的锚点对账，矛盾逐条列出（同一路径只列一次）；没有这样的锚点列一行「无法对账」。
- **否决**：
  - 只在运行时兜，不判红：声明错了没人知道，下次没有依赖图时就真的漏测。
  - 对账不过就让 final 判红：final 的职责是判代码，声明的错在起飞前拦；运行时按依赖图处理已经不会漏测。

### D4 · `/pr-ship` 先跑 `ship`，按 reasons 决定是否重跑

- step 2b 改为：沉淀提交之后运行 `slice-gate.py ship`；reasons 里没有 `final 过期` → 不重跑；有 → 重跑 final，理由后面的补跑预告已经说明这次是增量还是全量。
- `ship` 每次调用都会往时间线记一行，属于记账文件，不影响新鲜度。
- 评审修复之后的「有修复 commit 时先重跑 final 再 ship」不改：修复改的是代码。
- **否决**：把沉淀挪到 apply 的 final 之前——沉淀要读评审结论与整段对话，属于收口之后的主会话工作；挪动牵涉 `/opsx-apply` 与工作流脚本。

### D5 · final 的无图退路：上次绿 final 之后只改了测试文件 → 只重跑它们

- **入口**：`_full_why` 给出的原因是「没有可用锚点」（不是链长上限）、不是 `--full`、没配 `gate.impacted`。
- **条件**（全部成立才走，一个共用函数给 `cmd_final` 与 `final_forecast`）：
  1. 没有测试分层文件；
  2. 增量重跑能等价复现 `gate.test`（`_unreproducible_why` 为空：直接的 pytest 调用，或配了 `gate.pytest`）；
  3. final 记录里有最近一次绿的树（`_last_green`），它的 `gate.test` / `gate.pytest` 指纹与分层指纹同当前；
  4. 它到当前树的 Δ（`_delta`，计划工件与其他 change 的目录本来就不计）去掉生效的 `inert` 路径后，只含文件名匹配 `test_*.py` 的路径，且都不命中 `global`；
  5. 这些测试文件不含基线的预存红（按行式 `failed` 的模块名、按 `failed_nodes` 的文件，两种都查，与 `_try_reuse` 相同）。
- **重跑集合**：Δ 里现存的测试文件 ∪ `blind` 命中的已跟踪测试文件。
- **判定**：
  - 有失败或错误 → `G2 test：新增失败 N 条：…`（改动的文件里没有预存红，所以失败都是新的）；
  - 超时、异常退出码、收集错误 → `G2 test` 红；
  - 都没有 → 测试部分绿。G7、lint、typecheck、检查照常运行。
- **与 `_try_reuse` 的两处差别**：
  - baseline 补跑红时放弃复用、改跑全量（它要的是一份完整的基线）；final 补跑红就是红，不必再跑一遍全量去确认。
  - 多一条「增量可等价复现」（条件 2）。`_try_reuse` 没有它，包装脚本类仓库的补跑实际用的是门禁自己的解释器；final 是最后一道，从严。代价：包装脚本类仓库要配 `gate.pytest` 才用得上这条路。
- **不写锚点**：锚点的用途是带着依赖图给后来的运行选测，这条路没有依赖图。final 记录照常写，下一次仍可同树沿用或再走这条路。
- **不设链长上限**：沿用的集合每次只会因为重跑而缩小，不涉及依赖图的漂移；与 baseline 的旧基线复用相同。
- **不适用时的说明**：条件 4 因为有非测试文件而不成立时，全量原因在「没有可用锚点」之后追加「上次绿 final <10 位> 后有非测试文件改动：<至多 8 个>」；条件 5 不成立时追加「…后改动的测试文件有预存红：<用例>」。其余条件不成立不追加。
  - 「有非测试文件改动」是 `flight-doctor.py cost` 现有的归类关键词（可避免），时间线里这种全量自动归到「可避免」，不改归类表。
- **否决**：
  - 没有绿 final 时拿基线当起点：基线到当前树的 Δ 是整个 change 的改动，本来就不只有测试文件。
  - 让这条路也覆盖「只改了文档」：那是 `inert` 的事，要仓库声明。

### D6 · 新模式在各处的名字

| 位置 | 取值 |
|---|---|
| final 结果 JSON | `incremental.mode` = `incremental`，`incremental.source` = `tests-only`，`anchor` = `{change, commit}`（上次绿 final），`rerun` = 文件清单，`rerun_tests` = 用例数，`inherited_tests` = `null` |
| 摘要 | `；增量：无依赖图，只重跑改动的 N 个测试文件（M 个用例），其余沿用上次绿 final <10 位>` |
| 时间线备注 | `增量（无图：上次绿 final <10 位>，只重跑 N 个测试文件） ok` |
| `GATE_TEST_RESULT` | `mode` = `tests-only`，`nodes` = `null`，`inherited` = `null`，`complete` = 假，`failed_nodes` = 本次重跑的失败 |
| 检查环境 | `GATE_FINAL_MODE` = `incremental`，`GATE_DELTA_FILE` = Δ，`GATE_ANCHOR_COMMIT` = 上次绿 final 的 commit |
| `final_forecast` | `("incremental", "无图：上次绿 final <10 位>，只重跑 N 个测试文件")` |

- 结果 JSON 的顶层键不变；`incremental.source` 已有 `builtin` / `impacted` 两个取值，这里加第三个。
- 时间线备注以「增量」开头，`flight-doctor.py cost` 的解析不用改；全量原因里不出现「增量」二字，免得被认错。
- `GATE_TEST_RESULT.mode` 新增取值属于契约扩展：契约给检查的用法是「只认 `mode == "full"`，否则跳过或降级」，按它写的检查不受影响。

### D7 · 预告与实际用同一个判定

- `final_forecast` 在「没有可用锚点」时调用 D5 的同一个函数：适用 → 预告增量；因非测试文件不适用 → 在原因后追加同一句。C1 给它加的「依赖图未测（类别）：修法」那句照旧在前。
- `ship` 的「final 过期」理由自然带上这句；`/pr-ship` 的人与模型不用另跑预告。

### D8 · 切片顺序

`slice-gate.py` 被三片先后修改，同一文件不能同 wave：S1（声明与生效）→ S2（核对与 `doctor`）→ S3（无图退路与预告），深度 3；文档片 S4 与 S1 同 wave，它不引用任何新的子命令（`ship` 早已存在）。

## Risks / Trade-offs

- [`inert` 声明错了、仓库又没有依赖图 → 改动不触发重跑，漏测] → 不做缺省；五类路径永不生效；契约文档写明这种仓库里声明只能靠人审；`final --full` 随时可用。
- [对账用池里最新的锚点，它可能来自别的分支，依赖略有出入] → 只会多报矛盾（偏严），不会少跑；矛盾的修法是改声明或改测试，两者都是显式动作。
- [无图退路沿用的结论来自更早的 final，中间如果有人绕过门禁改了环境] → 与 baseline 旧基线复用同一假设；指纹（命令、`gate.pytest`、分层）变了就不沿用；`--full` 可用。
- [被别的测试文件 import 的 `test_*.py` 改了，只重跑它自己] → baseline 的旧基线复用已有同样的盲区并被接受；`conftest.py` 是全局文件，不走这条路。
- [`GATE_TEST_RESULT.mode` 多一个取值，枚举了全部取值的检查会走到缺省分支] → 契约文档列出新取值；proposal 标明。
- [C2 `machine-test-lock` 未合入，也改 `cmd_final` 的备注与 `flight-doctor.py`] → 本 change 对备注只加一个分支；后合入的一方在预合并时解冲突，两边的测试各自钉着自己的格式。
- [`/pr-ship` 文档改成有条件重跑，模型看漏条件直接跳过重跑] → `ship` 之后建 PR 前还会再裁一次（step 6），final 过期必然被判 draft，不会带着过期的 final 开出 ready 的 PR。

## Migration Plan

- 模板合入后，下游 `./install.sh --upgrade`。不需要数据迁移：
  - 没写 `inert` 的仓库，三处判定与今天逐字节相同；
  - 无图退路只在「上次绿 final 之后只改了测试文件」时改变行为，条件不成立即今天的全量。
- afa 侧（不在本 change）：在 `gate-scope.json` 声明与测试无关的路径；包装脚本类的 change 配 `gate.pytest` 才能用上无图退路。
- 回退：还原 `slice-gate.py` 与 `flight-doctor.py`；旧脚本遇到 `inert` 字段会报「未知字段」，回退时要同时从 `gate-scope.json` 里删掉它。

## Open Questions

- **与方案页 / 派发指令不一致的三处**（都已按上面的决策写进规格，请在审批时确认）：
  - D5：无图退路多了一条「增量可等价复现」，比 `_try_reuse` 严。没配 `gate.pytest` 的包装脚本仓库（afa 现状）用不上它，要先配这一项。
  - D5：补跑红时 final 直接判红，不像 baseline 那样退回全量。
  - D2：起飞前检查的「基线过期」不看 `inert`。方案页只说了「baseline 的复用判定」，这里把它限定为复用，不含过期判定。
- **对账用哪条锚点**：现在取池里同指纹最新的一条。若实际使用中多报矛盾成了噪声，可改成「final 会选的那条」，代价是 lint 阶段常常没有可用的。
- **C1 遗留、仍未决**：内建声明下的非 pytest 运行器与部件形态不要求为「依赖图未测」表态（在役 ADR `DRAFT-builtin-scope-provider-and-shell-closure`）。本 change 不动它。
- **审批页会把带可选字段的声明显示成「未声明」**（既有问题，不在本 change 范围）：`spec_html.py` 的 `scope_provider`（`:583`）用 `len(decl) != 1` 判声明形状，`gate-scope.json` 只要多一个 `global` / `blind` / `inert` 就落到「未声明选测范围」。门禁自己的判定不受影响，但写了 `inert` 的仓库在 `spec.html` 上会看到错误的说明。建议在下游开始写 `inert` 之前修掉（一行判断加一条测试），是并进本 change 还是单开 mini，请审批时定。
- **无图退路与测试分层**：配了 `test-tiers.json` 的仓库不走这条路（探针与区域的处理都在锚点路径里）。有需要时再单独设计。
