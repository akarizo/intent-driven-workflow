## Context

飞行模式里，「合在一起还对不对」只在 final 才第一次被检查。现状（读 main `2cc6167` 的代码，已含 plan-hygiene、machine-test-lock、ship-rerun-hardening、test-ledger、slice-resume-deterministic）：

| 环节 | 现状 | 出过的事 |
|---|---|---|
| 切片门禁 `cmd_gate` | 跑本片 `verify`、`gate.lint` / `gate.typecheck`、G3–G8、G12；`gate.checks` 只在 baseline 与 final 运行（`CHECK_FIELDS = name / baseline / final / timeout_sec`） | 引入未声明跨包依赖的切片门禁照绿（F5） |
| wave 合回 | integrator 运行 `merge`、逐片 `record`、刷新接口摘要、记 `integrate` 事件；`integrator.md` 明文禁止此时跑 final | 合回后的树没人检查，下一个 wave 的切片被上一个 wave 拖红（F4） |
| 修复通道 | `opsx-apply.js` 的 Fix 阶段只收评审的 CRITICAL / HIGH，排在全部 wave 之后 | 只能人工手写前置 fix 工作流（F4） |
| owns 条数 | `MAX_OWNS = 12`，不分大小 | 写满 12 条的切片改用宽通配（F7） |
| owns 漏列 | 门禁 `G6 ownership` / 下游 `G1 verify` 红了才知道；改计划后重新批准、重新起飞，工作流从头跑 | 每漏一个文件一次停飞（F6） |

约束：

- Workflow 脚本不碰文件系统，状态只能经 args 进、经 agent 的返回值出；`agent()` 的并发位与缓存按调用顺序定位。
- 自举飞行（本仓自己飞）时，工作流脚本用 `scriptPath` 指向 change worktree 里的 `template/.claude/workflows/opsx-apply.js`，在起飞那一刻载入，整趟飞行用的是起飞时的版本（等于拉分支时 main 的版本）；agent 定义与 hooks 由各 agent 在运行时从所在工作树读，随合回逐步变新（查实：记忆 `self-hosting-workflow-args`、`self-hosting-slice-deps`，`slice-resume-deterministic` design D9）。
- 现行 ADR：`DRAFT-measurements-stay-out-of-plan-files`（脚本不写计划文件）、`DRAFT-gate-evidence-not-self-reported`（判据不由被门禁方提供）、`DRAFT-final-incremental-by-dependency-anchor`（锚点是可沿用的测试结论）、`DRAFT-executor-turn-tiers-by-owned-files`（档位按现存文件数、由脚本现算）、`DRAFT-test-ledger-outside-repo-follows-anchors`（锚点带逐用例耗时 `secs`）。
- 方案页第 07 节 Q6 已定：不放宽所有权，只把发现提前、把重新批准做便宜。

### 调查一：owns 上限与宽通配的数据

脚本 `calibration/replay-owns.py`（借用 `slice-resume-deterministic/calibration/replay-turns.py` 定位计划与展开 owns 的方法），结果存 `calibration/replay-owns-20261118.txt`。样本：本机 6 个仓库、188 个 change、805 个切片（能找到计划的），「现存文件数」在计划入库的那个 commit 上数。

- **12 条上限只压大片档**：标准档（现存文件 ≤ 8）624 片，owns 条数 P99 = 9，最多 11 条，没有一片写满；大片档 181 片，28.7% 恰为 12 条，59.1% 在 10–12 条。
- **写满的切片用通配顶替**：恰为 12 条的 52 片里 48% 含通配，其余各组是 7%（1–4 条）、17%（5–8 条）、17%（9–11 条）。
- **写满的切片更容易越权写**：门禁报过 `G6 ownership … 不在 owns 内` 的切片占比，12 条组是 19.2%（10/52），其余各组 2.3%–4.2%。
- **放到多少条**：恰为 12 条的 52 片里，现存文件数不超过 16 / 20 / 30 / 40 的各占 65% / 69% / 75% / 77%。30 之后几乎不再增加（剩下的是几十到几百个文件的机械迁移，本来就该用通配）。取 **30**，与方案页草案一致；上限被 12 截断，看不到「不设限时人会写多少条」，所以仍标草案。
- **宽通配的线**：259 条带通配的 owns，展开数 P50 = 10、P90 = 123；展开超过 20 的占 30.9%，涉及 5.7% 的切片。最宽通配超过 20 的切片报过 G6 的占 14.3%（6/42），不超过的占 3.2%（24/745）。这个差异混着规模的影响，不能说明宽通配导致越权，只能说明这些切片值得审批的人多看一眼。取 **20**，草案。

### 调查二：wave 里重跑受影响测试要花多少

同一份脚本的 D 段统计各仓时间线里「增量」运行的测试秒数（wave 集成检查的测试那一半与增量 final 用同一选法）。43 次增量运行：74% 不超过 60 秒，77% 不超过 120 秒，其余全部在 500 秒以上，120–300 秒之间一次都没有。分布是两头的：要么只动了几个叶子文件，要么动到被几乎所有测试依赖的文件（本仓的 `slice-gate.py`：512–571 秒）。预算取 **120 秒**，落在两头之间的空档里。样本小（本仓带秒数的增量 final 只有 7 次，其他仓库的增量运行都不超过 37 秒），草案。

### 调查三：补 owns 之后「回一句起飞加续跑」现在通不通

结论：**起飞通，续跑没有**。

- 通的部分（C1 `plan-hygiene` 修掉的）：改 `slices.json` 让批准过期，人类回一句「起飞」重新批准；`plan_sha` 只含 gate 命令与各片 `verify`，只改 owns 不会让基线过期；已有 approve 事件的 change，preflight 不再按内容判基线过期。
- 差的部分：`/opsx-apply` 每次都用完整的 waves 重新启动工作流，没有任何「已落地」的概念。已合回的切片会再派一遍执行体：新开的临时 worktree 里实现已经在了，执行体读切片包、跑 verify、过门禁、交回一个与分支相同的 commit，`merge` 是空操作。结果是对的，但每个已落地的切片白花一个主模型 high 的执行体。Workflow 运行时的 `resumeFromRunId` 帮不上：它按调用顺序回放缓存，上次交回红结论的那一片会原样回放成红。
- 本 change 补上这一截（D8）。

## Goals / Non-Goals

**Goals:**

- 仓库声明的全局守护在每片门禁里运行，引入问题的那一片自己就红。
- 每个 wave 合回后有一次集成检查，红了能在下一个 wave 之前修。
- 集成检查的成本有上限、进时间线、进成本归因。
- owns 条数不再逼大切片放宽通配；宽通配有理由可审。
- 补计划后的重新起飞只花没落地那几片的钱。

**Non-Goals:**

- 不做 owns 的静态预测（按接口扫描替身与桩）。Q6 已定：不靠预测更准。
- 不放宽所有权：跨片修复是集成检查红了之后的专用通道，切片执行体写 owns 之外的文件仍然是 `G6`。
- 集成检查的测试那一半不支持配了分层文件的仓库（两种形态都不支持），也不支持 `gate.impacted`：前者要处理探针与区域，部件形态的 final 本来就恒全量；后者的选测只有仓库自己的命令知道。这些仓库的集成检查只跑守护。
- 集成检查不写锚点、不落测试账本（D5）。
- final 红之后的修复通道不在本 change 里（final 之后仍是评审修复与人工）。
- 不改 `MAX_SLICES` / `MAX_DEPTH`。
- 跨片修复执行体仍用标准档定义，不走 `start` / `gate`（与现有 Fix 阶段相同）。

## Decisions

长期决策另立三份 ADR 草案：`DRAFT-wave-integration-check-and-cross-slice-fix`（D1–D5）、`DRAFT-owns-cap-follows-turn-tier`（D6、D7）、`DRAFT-retakeoff-skips-landed-slices`（D8）。

### D1 守护是检查的第三条命令 `slice`

`gate.checks` 每项多一个可选字段 `slice`（非空字符串；缺省或 `null` 表示这个检查不是守护）。`final` 仍然必填。沿用检查已有的全部机制：`timeout_sec`、`gate.checks_skip`（整个检查跳过，须写理由）、共用目录、日志、环境变量。

- **仓库默认清单**：`<openspec 根>/gate-checks.json` 的某项是对象且带非空 `slice` 时，计划里的同名检查必须也带非空 `slice`，否则 lint 红（`checks: 仓库默认检查 <名> 是全局守护（声明了 slice），计划里的同名检查须带 slice`）。只核对「有没有」，不核对命令文本是否相同（与现有对 `baseline` / `final` 的做法一致）。写进 `gate.checks_skip` 的仍按跳过处理。
- **`plan_sha`**：任一检查带 `slice` 时，在现有键之后追加 `["slice", [[name, slice], …]]`。没有检查带 `slice` 的计划，`plan_sha` 与今天逐字节相同（在途 change 的基线不过期）。
- **baseline**：每个带 `slice` 的检查，在它的 `baseline` 命令之后运行 `slice` 命令（`GATE_PHASE=slice`），结果记在 `gate-baseline.json` 的 `checks.<名>.slice = {exit, sec, cmd[, reused][, timed_out]}`；红或超时 → 基线红（`check <名> 的 slice 命令在基线上红（exit N）`）。沿用条件与该检查的 `baseline` 命令相同。只有 `slice`、没有 `baseline` 的检查，`checks.<名>` 只有 `slice` 一段。
- **切片门禁**：`cmd_gate` 在 `gate.lint` / `gate.typecheck` 之后、仍持共享锁时，按 `gate.checks` 的顺序运行每个带 `slice` 的检查：
  - 基线没有该检查的 `slice` 记录、记录不绿、或记录的 `cmd` 与计划不同 → `G15 guard <名>：基线缺记录或与计划不符，重跑 baseline`，不运行；
  - 运行：环境 `GATE_PHASE=slice`、`GATE_CHANGE`、`GATE_BASE_COMMIT`（基线 commit）、`GATE_CHECK_DIR`（与 baseline / final 同一个共用目录）；日志写 `<共用目录>/.gate-slice-<切片 id>.log`（同一 wave 的切片并行过门禁，不能共用一个日志名）；
  - 非 0 → `G15 guard <名>：exit N；日志 …` 加输出末尾 20 行；超时 → `G15 guard <名>：超时 N 秒`。
  - 门禁 JSON 在计划里有守护时多一个 `guards: {名: {exit, sec}}`，时间线的 gate 备注多一段 `守护 a 1.2s / b 0.4s`；没有守护时两处都不出现。
- **运行契约的新增条款**：`slice` 命令会被同一 wave 的多个切片同时调用，而且它们共用 `GATE_CHECK_DIR`，所以 `slice` 命令对共用目录只读（或自己保证并发安全）；它应当是秒级的。

为什么不新开一个字段（交接文档建议的 `gate.always_verify`）：守护要的仓库默认清单、跳过须写理由、超时、日志、环境变量，检查已经全有；另开一套就是两份配置、两处 lint。

为什么要基线先跑一遍：守护在起点就是红的话，每一片的门禁都会红，而且红得与本片无关。

否决「把守护命令拼到每片 `verify` 后面」：`verify` 是计划文件里的字符串，拼接等于脚本改计划；`G1` 与守护的红也分不开。

### D2 wave 集成检查是一个子命令

`slice-gate.py wave-check --change-dir DIR [--wave N] [--of M] [--fix-base SHA]`，在所在工作树的 git 顶层运行，退出码按 `ok`。分两半：

**守护那一半**：与 D1 的门禁相同，区别只有 `GATE_PHASE=wave`、日志名 `.gate-wave.log`。

**测试那一半**（受影响的测试）：

1. 以下任一成立 → 不跑，`tests.mode = "skipped"`，`tests.why` 写原因，**不算红**：
   - openspec 根有 `test-tiers.json`（`分层仓库：受影响测试留给 final`）；
   - 计划配了 `gate.impacted`（`gate.impacted 选测留给 final`）；
   - 取不到可用锚点或命中全量触发项：用 `final_forecast` 同一套步骤（内容快照 → `_pick_anchor` → `_full_why`），它给出全量原因时原样作为 `why`（如 `没有可用锚点`、`依赖图未测（…）`、全局文件触发项）；
   - 估算耗时超过预算（下一条）。
2. 选中集合 = `_final_select(锚点, Δ, 声明的 blind)`，与增量 final 完全相同（Δ 是锚点到当前树的全部改动，不是只算本 wave 的：只算本 wave 会漏掉「上一个 wave 改了中间模块的 import、本 wave 改了它新依赖的文件」这种情况，因为依赖图是锚点那一刻测的）。
3. **预算**：锚点带 `secs`（`test-ledger` 之后的全量会写）时，估算 = 选中文件里各用例 `secs` 之和；估算 > 预算 → 跳过，`why` 写 `受影响测试约 X 秒（N 个文件），超过预算 Y 秒，留给 final`。预算 = 计划的 `gate.wave_test_budget_sec`（正数，lint 校验），缺省 `WAVE_TEST_BUDGET_SEC = 120`。锚点没有 `secs` → 估算为 `null`，照常运行。
4. 运行：`_pytest_outcomes(root, 选中文件, gate, extra_env={GATE_PHASE: "wave", GATE_CHANGE})`，不加载依赖图插件与探针。
5. 判定：FAILED / ERROR 的用例里，去掉基线预存红（`gate-baseline.json` 的 `test.failed_nodes`）与所选锚点的失败清单，剩下的 → `G16 wave test：新增失败 N 条：…`；超时 → `G16 wave test：重跑受影响测试超时`；退出码不在 0 / 1 / 5 或有收集错误 → `G16 wave test：exit N` 加输出末尾。选中集合为空 → `tests.mode = "none"`。
6. strict xfail 的骨架（后面的 wave 才解锁）结局是 XFAIL，不算失败；所以「每个 wave 合回后，除骨架外整套测试该是绿的」是这一半要守的不变量。

**全机测试锁**：整个子命令取一把锁，守护与测试都在锁内。测试那一半会运行且选中集合非空 → 独占（与增量 final 同类：它跑的是一批不限于本片的测试，耗时不可预先封顶到秒级）；否则 → 共享（与切片门禁同类）。`expect_sec` 取估算值，取不到退 `_lock_expect_sec`。排队放弃后不加锁照跑，结论不降级（这里没有时间类判定）。

**输出 JSON**：

```json
{"slice": "wave", "ok": true, "commit": "<HEAD>", "failed": [], "warnings": [],
 "summary": "wave 2/3 通过：守护 2 项 · 测试 3 个文件 12.3s",
 "wave": 2, "of": 3,
 "guards": {"layering": {"exit": 0, "sec": 1.2}},
 "tests": {"mode": "impacted | skipped | none", "why": null, "files": ["tests/test_a.py"],
           "rerun_tests": 7, "est_sec": 9.8, "sec": 12.3, "budget_sec": 120},
 "lock": {…}}
```

`slice` 固定为 `"wave"`：这样它符合工作流的门禁 JSON 形状，`record --json` 不用改就能写回；`gate-report.md` 里所有 wave 共用一行名，`report_latest` 取到的是最近一次集成检查。`--wave` / `--of` 只用于文案与时间线，不给时写 `wave ?`。

**飞行记录**：`gate-report.md` 追加一行（切片列 `wave`）；时间线记事件 `wave-check`，备注 `wave 2/3 · 守护 layering 1.2s · 测试 12.3s（3 个文件） · <锁片段> ok`，跳过时测试段写 `测试跳过（<原因>）`，没有守护时省掉守护段，结论词在末尾。

**`--fix-base SHA`**（跨片修复执行体收尾时给，SHA 是它开工时的 HEAD）：

- 取 `SHA..HEAD` 的改动文件；其中有本 change 的飞行记录文件 → `G6 flight-record`（与切片门禁同一条规则，修复执行体不得提交飞行记录）；
- 输出多一个 `fix: {"base": SHA, "files": […], "outside_owns": […]}`，`outside_owns` = 不被计划里任何切片的 owns 匹配的文件；时间线备注多一段 `跨片修复 N 个文件（owns 外 K 个）`；
- SHA 不在对象库或不是 HEAD 的祖先 → `G0 base`，不运行检查。

**`record`**：收到 `slice == "wave"` 的 JSON 时，时间线事件记 `wave-check`（备注由 JSON 的 `wave` / `of` / `guards` / `tests` / `fix` 重拼，拼不出的段省略），其余（幂等、写 `gate-report.md`）不变。

**`ship`**：`report_latest` 里有 `wave` 行且是红的 → reasons 加一条 `wave 集成检查红：<failed 摘要>（修复后重跑 slice-gate.py wave-check）`。没有 `wave` 行不产生任何理由。`ship` 的输出键不变。

为什么 `ship` 要管：铁律 5「门禁红不收口」。守护的 `slice` 命令不保证被该检查的 `final` 命令覆盖，只靠 final 兜不住「守护一直红、final 却绿」。

否决：

- **wave 集成检查直接跑一次 final**：后面的 wave 还没解锁骨架，G7 必红；写锚点、落账、同树沿用这些 final 的副作用也都不该在半成品上发生。
- **没有锚点时跑全量**：每个 wave 一次全量，正是方案页点名要避免的退化；afa 一次全量 20 分钟以上。
- **只按本 wave 的改动选测**：见上面第 2 条，不成立。

### D3 工作流：合回的同一次派发里做集成检查

integrator 的 wave 合回派发在原有步骤（提交飞行记录 → `merge` → 逐片 `record` → 接口摘要 → `integrate` 事件 → 提交飞行记录）的最后多一步：运行 `slice-gate.py wave-check --change-dir … --wave <i> --of <n>`，把它打印的 JSON 原样放进返回 JSON 的 `check` 字段，再提交一次飞行记录。

- 不另开一个 agent：少一次派发；`label` 仍是 `integrate:w<i>`，模型对账与既有测试的 mock 都不用改。
- `slice-gate.py wave-check` 报 `invalid choice`（hooks 未升级）→ `check` 写 `null`。工作流见到 `check` 缺失或为 `null`：不派修复、不记 blocked，只在返回值的 `waves` 里记一条 `{wave, skipped: "integrator 未带回集成检查结果"}`。final 仍然兜底。
- `merge` 失败（`ok: false`）时不运行集成检查（现有的 blocked 逻辑不变）。
- 返回形状 `MERGE` 加可选的 `check`（对象或 `null`）。

### D4 跨片修复通道

`check.ok === false` 时，工作流在进入下一个 wave 之前：

1. **派修复执行体**（`label: fix:w<i>`，`isolation: worktree`，执行体模型与 effort，`slice-executor` 定义，阶段记 `Fix`）。prompt 要点：
   - 这是跨片修复，不是切片：不运行 `start` / `gate`，不受任何切片的 owns 限制，但只改让下列失败项变绿所必需的文件；
   - 第一步基点校验（`git merge-base --is-ancestor $(git rev-parse <branch>) HEAD`）与 `sub-sync`，与现有 Fix 阶段逐字相同；失败 → 原样返回 `G0` JSON；
   - 记下开工时的 `git rev-parse HEAD` 作为 `<base>`；
   - 失败项清单 = `check.failed`；红的集成检查本身就是「先失败的测试」，不必再造一条；需要新测试才能钉住的缺陷照 TDD 写；
   - 逐条 commit（`fix:` 前缀），不 push，不提交飞行记录；
   - 收尾运行 `slice-gate.py wave-check --change-dir … --wave <i> --of <n> --fix-base <base>`，把 JSON 原样返回。
   - 未返回 / 抛错 / `G0` 拒绝 → 重派一次（从头来，与 Fix 阶段相同）。
2. **绿了才合回**：修复返回 `ok: true` 且有 commit → 派 integrator（`label: integrate:w<i>:fix`）：提交飞行记录 → `merge wavefix<i>=<commit>` → `record --json <修复返回的 JSON 原文>` → `timeline.py record wave-fix --note "wave <i>"` → 提交飞行记录。合回失败 → 按下面的「仍红」处理，理由用合回的 failed。
3. **评审**：合回成功后照切片的做法 push 一个评审（`label: review:wavefix<i>`，审 `git show <commit>`，门禁 JSON 给修复返回的那份）。它的 finding 与切片评审一起进后面的 Fix 阶段。
4. **仍红**（修复返回 `ok: false`、两次都没返回、或合回失败）→ 不合回修复提交，记 `blocked: {slice: "wave<i>", kind: "gate" | "infra", reason}`，理由带修复的 commit（有的话），然后定停飞范围：
   - 最后一次检查的 `failed` 里有 `G15` 开头的项（守护红）→ 后面所有 wave 的切片全部记 blocked（infra，`wave <i> 集成检查红（守护）`）。守护是全局的，分支红着，后面每一片的门禁都会被它拖红，派了也是白跑。
   - 只有 `G16`（测试红）→ 只停依赖本 wave 任一已合回切片的下游切片（把这些切片加进依赖判断用的 blocked 集合，沿用现有「依赖已 blocked 就跳过」的逻辑）；与本 wave 无依赖的切片照常派。
5. 返回值多一个 `waves: [{wave, ok, failed, tests, fix: {commit, ok, files, outside_owns} | null, skipped}]`；`/opsx-apply` 收口时把它原样写进 `review-findings.json` 的 `waves`，`/pr-ship` 起草正文时把其中带 `fix` 的条目列成「跨片修复」（commit、文件清单、owns 外的文件）。

与铁律的关系：

- **先意图后代码**：修复通道只在一次已批准的飞行内、由一条红的机械检查触发，修的是让这条检查变绿，不是新需求；计划工件不变。
- **所有权**：切片执行体的 `G6` 不放宽。修复执行体不受 owns 限制，但它改了什么由脚本算（`--fix-base`），`outside_owns` 单列，进时间线、`gate-report.md`、`review-findings.json` 与 PR 正文。
- **TDD 与留痕**：红在先（home 里那次红的 `wave` 行与 `wave-check` 事件）、绿在后（修复的 `wave` 行经 `record` 写回），两行都是脚本写的。
- **独立评审**：修复提交有自己的一次评审；PR 评审兜底。

否决：

- **修复在 change 家里直接改**：与正在合回的 integrator、与下一个 wave 的派发抢工作树；现有的隔离 + 合回机制白白不用。
- **红了就把修复提交也合回、让后面接着修**：没证明过的修复进分支，下一个 wave 在更不确定的树上开工。
- **修复重试到绿为止**：没有上限的循环；方案页定的是「复查一次，仍红才 blocked」。
- **让 `start` 认一个保留的修复 id，从而复用 `--continue` 与快照恢复**（方案页写的是「复用 C3 的接续逻辑」）：`start` 的接续、快照、留痕都以「计划里有这一片、有它的 owns」为前提（快照只存 owns 内的改动，标记驱动所有权拦截），给一个没有 owns 的保留 id 要在这三处各开一个口子。修复只尝试一次、未交回就从头重派一次，用不上接续；现有的批量修复阶段也是这样做的。真出现修复执行体经常撞轮次上限时再做。

### D5 集成检查不写锚点、不落账

- **锚点**：锚点是「这棵树上整套测试的结论」，半成品树（骨架还是 xfail、后面的 wave 没合回）不是一个该被别的 change 沿用的结论；写了还要处理逐用例结局前移、依赖图合并，等于在 wave 里做一遍增量 final。
- **测试账本**：`test-ledger` 的账本只有 `baseline` 与 `final` 两份，对账回答「这个 change 给测试套件带来了什么」。wave 里落账会覆盖 `final.json`，而无图退路正拿它当来源。`_pytest_outcomes` 照常往进程内观测表上报，没有人读（与切片门禁相同，`test-ledger` design D9）。
- 集成检查花的秒数在时间线与 `flight-doctor.py cost` 里（D9）。

### D6 owns 上限随轮次档

- `OWNS_CAP = {"standard": 12, "large": 30}`。切片的档位与 `slice_turns` 同一算法：计划写 `"turns": "large"` → 大片档；否则现存文件数（基线 commit 的树，取不到用 HEAD）多于 `TURN_LARGE_FILES` → 大片档；不在 git 仓库里 → 只认计划里的 `turns`。
- 超限的报错写明两档的数字与出路：`owns: S3 的 owns 有 14 条，标准档须在 1–12 内（大片档 1–30；这一片要更多条目先写 "turns": "large"）`。
- 只有 owns 多于 12 条的切片才需要数文件，其余切片不增加 git 调用。

为什么挂在轮次档上而不另设一个量：两者要回答的是同一个问题「这是不是一个大切片」，`DRAFT-executor-turn-tiers-by-owned-files` 已经定了答案怎么算。小切片想要更多 owns 条目时写 `"turns": "large"`，等于明说「这一片比看上去大」，同时拿到更多轮次，两件事是一致的。

否决（交接文档的两个方向）：

- **列表语法（花括号、一行多文件）**：owns 的匹配函数被门禁、选测、hook 共用，加语法要同改四处，还要定义与重叠检查的交互。
- **`owns_amend` 不占上限**：等于没有上限。

### D7 宽通配要写理由

- 带通配符（`*` `?` `[`）的 owns 条目，在与 D6 同一棵树上展开出的现存文件数多于 `OWNS_WIDE_FILES = 20` 时，该片须有 `owns_wide: {"<该条目原文>": "<理由>"}`，否则 lint 红：`owns: S3 的 src/abc/* 展开出 37 个现存文件（> 20），须在该片的 owns_wide 里为它写理由`。
- `owns_wide` 形状：对象，键必须是该片 owns 里的条目，值是非空字符串；多余的键、空理由都红。
- lint 通过时在 stderr 为每个带通配的条目打一行 `owns: S3 src/abc/* → 37 个文件`（与现有的范围摘要一样只在没有错误时打印）。
- **已批准的 change 不追溯**：change 的时间线已有 approve 事件时，缺理由只打印不判红（它是在旧规则下批准的；`waves` / `turns` / `preflight` 在飞行中都会调 lint，追溯会把在途飞行拦死）。超出条数上限不受这条豁免影响（上限只放宽、没有收紧）。
- 不在 git 仓库里时不做这项检查。

### D8 重新起飞不重做已落地的切片

`slice-gate.py landed --change-dir DIR` 打印 `{切片 id: 门禁行里的 commit}`，退出 0；计划不合法时与 lint 一样退出 2。一片「已落地」须同时满足：

1. `gate-report.md` 里它的最新一行是绿的；
2. 那一行的 commit 能解析，且是 HEAD 的祖先；
3. 从那个 commit 到当前工作树，`<change>/slices/<S>.md` 与 `<change>/specs/` 没有改动；`slices.json` 里该片的条目除 `owns` 与 `owns_wide` 外与那个 commit 上的相同（那个 commit 上读不到计划或没有该片 → 不算落地）。

第 3 条是为了：人类补的是别的片的 owns 时，已落地的片不受影响；人类改了某片的 scenario 或切片包时，这一片要重做。

工作流的新参数 `args.landed`（可选，上面的输出原样）：

- 每个 wave 里已落地的切片不派执行体，`results` 里记 `{slice, ok: true, commit, landed: true}`；
- 评审照派（门禁 JSON 给 `{slice, ok: true, commit, failed: []}`）：上一次飞行的评审结论在重新起飞时会被新的 `review-findings.json` 覆盖，不重审就丢了；
- 一个 wave 只要有已落地或本次合回的切片，就做集成检查。整个 wave 都已落地时 integrator 的派发不含 `merge` / `record`，只跑 `wave-check` 并返回 `{ok: true, merged: [], failed: [], warnings: [], check}`。这保证了上一次飞行停在「集成检查红」时，重新起飞不会在红的分支上接着派。
- `/opsx-apply` 在取 `turns` 之后运行 `landed`，把输出作为 `args.landed`；报 `invalid choice` 时不传。

否决 Workflow 的 `resumeFromRunId`：见调查三；另外它只在同一会话内有效。

### D9 看得见：审批页与成本归因

- **审批页**（`spec_html.py`）：测试成本那一块列出带 `slice` 的检查（名字与命令，标题点明「全局守护：每片门禁与每个 wave 合回后都运行」）与 `gate.wave_test_budget_sec`（写了才显示）；切片表里写了 `owns_wide` 的切片，把通配与理由显示出来。两处都直接读 `slices.json`，不调 `slice-gate.py`。
- **成本归因**（`flight-doctor.py cost`）：从时间线的 `wave-check` 事件汇总，文本多一行 `wave 集成检查 N 次：守护 Xs · 测试 Ys · 跳过测试 K 次`，JSON 多一个 `wave: {count, guard_sec, test_sec, skipped}`；没有 `wave-check` 事件时文本不多这一行，JSON 的 `wave.count` 为 0。

### D10 落地顺序、兼容与本 change 自己的飞行

| 组合 | 行为 |
|---|---|
| 旧工作流脚本 + 新 hooks | 没人调用 `wave-check`；写了 `slice` 的检查仍在 baseline 与每片门禁里运行（G15）；没有跨片修复 |
| 新工作流脚本 + 旧 hooks | integrator 报 `invalid choice` → `check: null` → 工作流跳过；`landed` 不可用 → 不传 |
| 旧计划（没有 `slice`、`owns_wide`、预算） | `plan_sha` 不变；门禁输出与时间线不多任何段；集成检查只有测试那一半 |

回退路径（铁律 10）：Workflow 不可用、改用 Agent 工具逐 wave 派发时，`opsx-apply.md` 与同名 skill 的回退段逐项镜像脚本的语义——已落地的切片不派执行体、每个 wave 合回后由 integrator 运行 `wave-check`、红了派一次带 `isolation: worktree` 的跨片修复（收尾带 `--fix-base`）、绿了用 `merge wavefix<i>=<commit>` 合回并评审、仍红时按 `G15` / `G16` 定停飞范围、结果里带 `waves`。两条路径调用的是同一个子命令，判定都在脚本里；文档的镜像由 scenario `apply-docs-mirror-wave-check-and-fix` 钉住。

本 change 自己的飞行：

- 工作流脚本是起飞时载入的旧版，整趟飞行没有集成检查与跨片修复；本 change 的计划也不使用任何新字段（起飞时的 lint 不认识它们）。
- `integrator.md` 随 S4 合回立刻被后续 wave 的 integrator 读到。新加的一项写成「仅当 prompt 点名时才运行 `wave-check`；子命令不存在就在返回里给 `check: null`」，旧 prompt 不点名，所以不受影响。
- 切片依赖按「引用新子命令的片依赖提供它的片」排，或在定义里写明子命令不存在时的回退：S4（工作流与 agent 定义）不依赖 S2（`wave-check`），靠上一条的回退句；S5（命令文档）依赖 S2、S4；S7（成本归因解析 `wave-check` 事件的备注格式）依赖 S2。
- 三个改 `slice-gate.py` 的片（S1 → S2 → S3）各占一个 wave。

## Risks / Trade-offs

- [每个 wave 多一次集成检查的墙钟] → 守护是仓库声明的快检查；测试那一半有 120 秒预算、没有锚点时不跑；耗时进时间线与 `cost`。本仓实测：改到 `slice-gate.py` 的增量要 512–571 秒，会被预算挡下。
- [预算挡下之后，集成检查在本仓基本只剩守护] → 如实写进 README；本仓的守护目前只有 `schema-validate` 可以声明 `slice`（另一个 change 的事）。调高预算是计划里一个字段。
- [`slice` 命令并行运行时互相踩共用目录] → 契约写明对共用目录只读；日志按切片分名。
- [守护不够快，每片门禁都被拖慢] → `timeout_sec` 照常生效；`cost` 里能看到守护秒数；整个检查可用 `checks_skip` 带理由跳过。
- [跨片修复改了大量 owns 外的文件] → 不拦（修复本来就是 owns 之外的事），但 `outside_owns` 单列进 PR 正文，修复提交单独评审。
- [integrator（低档模型）转写 `check` JSON 出错] → 工作流只用 `ok` 与 `failed` 两个字段做决定；真值在分支上的 `gate-report.md` 与时间线里，`ship` 读的是那里。
- [`landed` 误判一片已落地] → 条件 3 把计划里与该片相关的改动都算上了；final 的 G7 仍然验全部 scenario，真漏了会红在 final。
- [`ship` 因为一条旧的红 `wave` 行一直判 draft] → 理由里写了做法：修复后重跑 `slice-gate.py wave-check`，新的一行会盖过旧的。
- [门禁编号] → `tier-budgets`（C5b，已起飞）占用 G13（集成层新增用例超线）与 G14（层总量超预算）；本 change 的守护红与 wave 测试红因此取 G15 / G16。
- [与在飞的 `tier-budgets`（C5b）同改 `slice-gate.py`、`flight-doctor.py`、`flight-runner-contract.md`、`README.md`] → 它动分层耗时判定（G10 / G11 / G12 一带）、`test-tiers.py`、`test-ledger.py`；本 change 动检查（`CHECK_FIELDS` 一带）、`cmd_gate` 里 lint 之后的一段、lint 的 owns 循环、`cmd_record` / `cmd_ship` 各一处与三个新函数。`cmd_gate` 与 `flight-doctor.py` 的 `cost` 是两边都可能碰的地方，后合的那个预合并 main。契约文档两边都可能新增一节，节号以后合的为准（本 change 的测试按节标题断言，不按节号）。
- [集成检查的测试那一半不支持分层仓库] → afa 是部件形态，final 本来就恒全量，选不出「受影响的测试」；它从本 change 得到的是守护与跨片修复通道，这正是 F4 / F5 的现场。

## Migration Plan

无数据迁移。升级后：

- 在途 change 的计划不用改；已批准的 change 不因宽通配规则变红。
- 仓库想启用守护：在 `gate-checks.json` 的检查上加 `slice`，之后新建的计划照抄；已有计划加了 `slice` 要重跑 baseline（`plan_sha` 变了）。
- 回滚：还原本 change 的提交；`gate-report.md` 里的 `wave` 行与时间线里的 `wave-check` 事件对旧脚本无害（按切片名与事件名被忽略）。

## Open Questions

1. **测试那一半的预算缺省 120 秒是否合适？** 依据见调查二，样本小。它决定本仓的集成检查几乎只跑守护。
2. **修不好时的停飞范围**：本设计按红的种类分（守护红全停，测试红只停下游）。方案页写的是「让依赖它的下游切片停下」一种。守护红时不全停的话，后面每片的门禁都会因 G15 白跑一轮再红。
3. **`ship` 是否该因为红的 `wave` 行判 draft？** 本设计判（铁律 5）。代价是多一种要人处理的 draft 原因。
4. **已落地的切片重新起飞时是否重审？** 本设计重审（不重审会丢上一次飞行的评审结论）。更省的做法是把上一次的 `review-findings.json` 合并进来，那要改收口步骤，留作后续。
5. **大片档 owns 上限 30、宽通配 20** 都是草案，依据见调查一。
6. **本仓要不要给 `schema-validate` 加 `slice`？** 不在本 change 里做（它要改 `template/openspec/` 下的仓库声明并重跑所有在途基线）。
