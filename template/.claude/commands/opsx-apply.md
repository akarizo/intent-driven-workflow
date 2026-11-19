---
description: 飞行模式 apply：批准后从门禁 lint 直跑到 PR，中途不问；模型按角色显式路由
---

飞行模式跑完一次 apply：批准自检（`takeoff-gate.py`；非 0 → 停下报告并交出 `spec.html` 路径，不派发）→ 选 change → git 纪律检查 → 切片规划 lint → 记录并提交批准事件 → 启动切片工作流（模型按角色显式路由；不可用则回退并行 Agent 派发）→ 收工作流 JSON → 收口分解（打印各角色实际模型）→ 直接进入 `/pr-ship`。除四种暂停例外，全程不问询。

**Input**：可选指定 change 名（如 `/opsx-apply add-auth`）。留空则从会话上下文推断，仍歧义才列候选。`--gate=per-task` → 跳过飞行模式，转读 `.claude/skills/legacy/openspec-subagent-apply-change/SKILL.md` 并按它逐 task 守门执行（legacy 路径，本命令 step 3–7 不适用）。
**模型路由（铁律：按角色显式声明，不得留空让 `CLAUDE_CODE_SUBAGENT_MODEL` 默认兜底）**

每个角色的 model 与 effort 都取自 `slices.json.routing`：规划期由 `/opsx-propose` 用 `model-routing.py pin` 钉住，人类批准时在 spec.html 里看到的就是这份。起飞时由 step 3 的 `model-routing.py resolve` 读出，本命令不写死任何模型名。

| 角色 | 路由键 | 依据 |
|---|---|---|
| slice-executor（实现） | `flight.executor` | 必须一次做对；实测 Sonnet 执行体的 fix 子 agent 数 ≥ impl 数 |
| slice-executor-large（大片档实现） | `flight.executor-large` | 同上；轮次上限 80 |
| 批量修复与 wave 跨片修复 | `flight.fixer` | 修复要一次闭环 |
| code-reviewer（切片评审 / 复核） | `flight.reviewer` | 门禁判完机械项后剩下的全是难判断；离关键路径 |
| integrator（合回 / 抽接口 / final） | `flight.integrator` | 纯机械，指令明确 |

**Steps**

0. **批准自检（起飞判据；批准由脚本校验，禁模型自证）**
   先按 step 1 的规则定出 `<name>`（有参数直接用参数），再跑：
   ```bash
   python3 .claude/hooks/takeoff-gate.py --change-dir openspec/changes/<name>   # exit 3 = 没有人类批准 / 批准过期
   ```
   - `exit 0` → stdout 是批准证据：人类消息（含中途插话），或会话 `/goal` 生效（人类持续授权，豁免新鲜度，摘要以 `/goal` 开头）。原样留着给 step 4 的 approve 事件。
   - `exit ≠ 0` → **停下报告**：打印 `openspec/changes/<name>/spec.html` 的绝对路径，说明「起飞需要你自己发出 `/opsx-apply <change>`」，**不进入任何后续步骤、不派发任何 agent**。

1. **选 change**
   - 有参数用参数；否则从会话上下文推断；只有一个活跃 change 自动选；歧义 → `openspec list --json` + **AskUserQuestion** 让用户选。
   - 宣告：`Using change: <name>`，以及如何覆盖（`/opsx-apply <other>`）。

2. **git 纪律检查**（`openspec-git-discipline` skill）
   - CWD 必须在本 change 的 `.worktrees/<name>/`；不在则进入（该 worktree 缺失 → 停下报告，不在主仓库工作区写实现代码）。
   - `git status --short` 确认工件已单独 commit、工作树干净；不满足 → 停下报告，不进入下一步。

3. **切片规划 lint**
   ```bash
   python3 .claude/hooks/slice-gate.py lint --change-dir openspec/changes/<name>
   python3 .claude/hooks/slice-gate.py preflight --change-dir openspec/changes/<name>
   ```
   `lint` 拿到 stdout 的 waves JSON。**exit 非 0（规划红）→ 停下把 stderr 点名的规则原样报告，不进入实现**。
   随后运行 `python3 .claude/hooks/slice-gate.py turns --change-dir openspec/changes/<name>`，stdout 的 JSON（每片档位 `standard` / `large`）原样作为 `turns` 传给工作流；模型不自己判断档位。
   再运行 `python3 .claude/hooks/slice-gate.py landed --change-dir openspec/changes/<name>`，stdout 的 JSON（已落地的切片 → 门禁行里的 commit）原样作为 `landed` 传给工作流；首次起飞是 `{}`；报 `invalid choice`（hooks 未升级）就不传。用途：补计划后重新起飞时，已落地的切片不再派执行体，评审与集成检查照做。
   `preflight` 校验 `gate-baseline.json`：**exit 非 0（缺基线 / 基线红 / 基线过期）→ 停下把 stderr 原样报告，不进入实现**；基线由 `/opsx-propose` 的 `baseline` 步骤生成，缺了回去补，不在这里手工造。
   `preflight` 同时复核选测范围（与 lint 同一口径：按提供方重算，未声明判红、全选须逐项有理由；内建提供方在此给出 final 的精确预测）；baseline 开跑前也做同一复核，未过不写运行标记、不运行。
   **final 开跑前复核**：final 在跑任何测试之前按提供方重算全选触发项（builtin 用内建规则，cmd 重跑命令），与 approve 提交时的 `gate.scope_full_reason` 对账——有未表态的全选触发项、提供方失败、或理由在批准后被改 → `G2 scope` 红、不跑测试，按「门禁红不收口」处理（回 propose 补理由并重新批准）；`final --full` 豁免（显式全量只会多跑）。

   preflight 绿后运行：
   ```bash
   python3 .claude/hooks/flight-doctor.py forecast --change-dir openspec/changes/<name>
   ```
   把它的输出（测试成本预告：baseline / final 各走全量还是增量、原因与约耗秒数）原样打印。只预告，不阻断：结论不影响是否起飞。
   baseline、final 与切片门禁会排队等全机测试锁（同一台机器同一时刻只有一套全量在跑）；stderr 里的「排队中」不是卡死，时间线会记下排队秒数，详见 `.claude/flight-runner-contract.md` 第 8 节。

   **读出钉住的路由**（lint / preflight 之后）：
   ```bash
   python3 .claude/hooks/model-routing.py resolve --change-dir openspec/changes/<name>   # stdout: {"models": {...}, "efforts": {...}}；exit 3 = 停飞
   ```
   - exit 非 0 → **停下报告**，把 stderr 原样报告，不起飞。未 pin：给出 `python3 .claude/hooks/model-routing.py pin --change-dir openspec/changes/<name>`，并说明 pin 会改计划工件，pin 后要人类重新批准；环境覆盖：说明要先 unset 哪个变量（stderr 已点名）。
   - 绿 → 运行 `python3 .claude/hooks/model-routing.py show --change-dir openspec/changes/<name>`，把路由表原样打印（起飞只打印，不问询）。resolve 的 `models` / `efforts` 原样留给 step 4 的 `.flight` 与 step 5 的派发。

4. **记录批准事件并提交飞行记录**
   ```bash
   python3 .claude/hooks/timeline.py record approve --change-dir openspec/changes/<name> --note "<批准证据>"
   git add openspec/changes/<name>/timeline.md && git commit -m "chore(flight): approve"
   ```
   `<批准证据>` 用 step 0 `takeoff-gate.py` stdout 的原文，不自己编。飞行记录文件（timeline.md / gate-report.md / evidence.log）由 hook 自动追加，**起飞前必须已提交**，否则 integrator 合回并行切片时会因工作区脏被 `git merge` 拒绝。写 `openspec/changes/<name>/.flight`（JSON，字段 `{"started","approval","models","efforts","source"}`：启动时间 · step 0 的批准证据 · step 3 resolve 输出的 `models` / `efforts` · `slices.json.routing.source`）。

5. **启动切片工作流**
   - 优先用 **Workflow** 工具：`name: "opsx-apply"`，`args: {change: "<name>", changeDir: "openspec/changes/<name>", hooksDir: ".claude/hooks", agentsDir: ".claude/agents", waves: <step3 的 waves>, useAgentTypes: true, branch: "<git branch --show-current>", models: <step 3 resolve 的 models>, efforts: <step 3 resolve 的 efforts>}`。`models` / `efforts` 原样传 resolve 的输出（5 个角色：executor / executor-large / fixer / reviewer / integrator），不手改；`models` 缺任一角色脚本会拒绝起飞。
   - 同时传 `deps: <slices.json 里每片的 deps 映射>`，依赖已 blocked 的切片脚本不再派发。
   - 同时传 `turns: <上一步 turns 的输出>`：值为 `large` 的片派 `slice-executor-large`（80 轮），其余派 `slice-executor`（40 轮）。
   - 同时传 `landed: <上一步 landed 的输出>`：其中的切片不再派执行体（返回值 `slices` 里标 `landed`），评审照派；整个 wave 都已落地时只做集成检查、不合回。
   - Workflow 不可用（工具缺失 / `disableWorkflows`）→ **回退**，语义与脚本逐项一致：按 waves 逐 wave 用 **Agent** 工具在同一条消息里并行派发 `subagent_type: slice-executor`（`turns` 里为 `large` 的片派 `subagent_type: slice-executor-large`），每个派发都显式传 `model` 与 `effort`，取 resolve 的值（执行体取 `models.executor` / `efforts.executor`，大片档取 `executor-large`）（每个执行体（含单片 wave 与 fix）都带 `isolation: worktree`，每个 wave 都派 integrator 合回；Agent 派发带 `effort`（取自 model-routing resolve）；Agent 工具不支持 effort 参数的旧版本由 agent frontmatter 决定，回退路径收口不对账 effort；执行体 `slice-gate.py start` 带 `--expect-branch <branch>`，由 `slice-gate.py` 校验 worktree 是否从 change 分支最新 commit 分叉，start 非 0 则执行体把它打印的 JSON 原样返回），回报只收其原样 JSON；**门禁红则以其 `failed` 重派同一切片一次**——重派 prompt 带上一轮的 `commit`，`slice-gate.py start <S> --continue <commit> --expect-branch <branch>` 由脚本接上一轮的全部提交（接不上以 `G0 base` 非 0 退出，执行体原样返回；start 幂等）；**执行体未返回门禁 JSON（Agent 工具回报 partial 或无 JSON）也重派一次**（Agent 调用抛错与未返回同样处理：重派一次）——prompt 说明上一轮未返回，`slice-gate.py start <S> --resume-checkpoint` 从快照恢复半成品后继续；重派仍无 JSON 记 blocked（infra），理由写明档位与该档上限、半成品快照位置：`执行体未返回（已重派一次）：<档位>上限 <N> 轮；半成品快照在 refs/flight/<change>/<S>，重新起飞的首轮会清掉它，要保留先在新 worktree 里 start <S> --resume-checkpoint`；仍红记 blocked，依赖它的切片直接记 blocked；每个 wave 跑完派一个 `integrator`（`model` / `effort` 取 `models.integrator` / `efforts.integrator`）先提交飞行记录、用 `slice-gate.py merge <S>=<sha> ...` 合回（脚本逐片 `git merge --no-ff` 并处理 submodule gitlink，退出非 0 则原样返回其 failed；只合回、不跑 final）、逐片 `slice-gate.py record --json '<该切片门禁 JSON 原文>'` 写回门禁结论与天花板行；评审用 `code-reviewer`（`model` / `effort` 取 `models.reviewer` / `efforts.reviewer`）并行派发（`run_in_background` 语义：不等它完成再继续）；全部 wave 跑完后对阻断 finding 做一次批量修复（fix 的 `model` / `effort` 取 `models.fixer` / `efforts.fixer`，同样 `isolation: worktree`；fix 第一步先做基点校验 `git merge-base --is-ancestor $(git rev-parse <branch>) HEAD`，不成立则不做改动、返回 `G0 base`，再跑 `slice-gate.py sub-sync --change-dir <dir> --expect-branch <branch>` 按 gitlink 填充子仓（非 0 则不做改动、原样返回其 `G0 submodule` failed），`start fix` 也带 `--expect-branch <branch>`；fix 未返回、Agent 调用抛错或 G0 拒绝都重派一次，仍无可合回结果记 blocked（infra）、不合回且照常跑 final），integrator 先用 `slice-gate.py merge fix=<sha>` 合回 fix 的 commit、再跑一次 final。integrator 与 final 抛错或未返回时重派一次，仍失败记 blocked（infra）；评审未返回只记录（blocked，infra），不重派——切片级评审缺失由 pr-ship 的整 PR 评审兜住。
   - 回退路径的已落地切片与 wave 集成检查（同样与脚本逐项一致）：`landed` 里的切片不派执行体，评审照派。每个 wave 合回并 `record` 之后，integrator 运行 `python3 .claude/hooks/slice-gate.py wave-check --change-dir <dir> --wave <i> --of <n>`（整个 wave 都已落地时只运行它、不合回），把它的 JSON 作为合回返回值的 `check` 带回（退出 1 = 红，是正常结论，照样带回）；子命令不存在（`invalid choice`）→ `check` 写 null，跳过，照常往下。`check` 红 → 当场派一次**跨片修复**：`subagent_type: slice-executor`、`model` / `effort` 取 `models.fixer` / `efforts.fixer`、`isolation: worktree`，不运行 `start` / `gate`、不受切片 owns 限制（只改让失败项变绿所必需的文件），先做与批量修复相同的基点校验与 `sub-sync`，记下开工时的 HEAD，收尾运行带 `--fix-base <开工时的 HEAD>` 的 `wave-check` 并原样返回其 JSON；未返回、抛错或 G0 拒绝重派一次。修复绿了 → integrator 用 `slice-gate.py merge wavefix<i>=<commit>` 合回、`slice-gate.py record --json '<修复 JSON 原文>'` 写回、`timeline.py record wave-fix` 记 `wave-fix` 事件，并为该 commit 派一个 `code-reviewer` 评审（`wavefix<i>`）。仍红（或修复未返回、合回失败）→ 不合回，记 blocked（`wave<i>`；交回红结论或合回失败为 `gate`，未返回为 `infra`）；最后一次集成检查的失败项里有 `G15`（守护红）→ 后面的 wave 全部停下并记 blocked（infra）；只有 `G16`（测试红）→ 只停依赖本 wave 切片的下游切片，其余照常派发。评审汇总、批量修复与 final 照常进行。
   - 两条路径最终都产出同一份 JSON：`{change, models, efforts, slices: [...], blocked: [...], blocking: [...], deferred: [...], fix, final, waves: [...]}`（完整字段见 `.claude/workflows/opsx-apply.js` 的 `return`）。

6. **收口分解**
   收到工作流 JSON 后：
   ```bash
   python3 .claude/hooks/timeline.py record apply-done --change-dir openspec/changes/<name>
   python3 .claude/hooks/session-decompose.py --session <当前会话 jsonl，取 ~/.claude/projects/<slug>/ 下最新> --workflow <Workflow 返回的 Transcript dir> --expect-models '<.flight 里的 models>' --expect-efforts '<.flight 里的 efforts>' --turns '<step 3 turns 的输出>'
   python3 .claude/hooks/timeline.py report --change-dir openspec/changes/<name>
   python3 .claude/hooks/flight-doctor.py cost --change-dir openspec/changes/<name>
   python3 .claude/hooks/slice-gate.py reap --change-dir openspec/changes/<name>
   ```
   `cost` 在 timeline report 之后运行，原样打印本 change 的全量 / 增量次数与每次全量的原因归因（必要 / 可避免），恒 exit 0。
   `reap` 回收本次飞行的临时 worktree：已落地的直接删，作废尝试先归档到 `refs/flight/<change>/attic/<目录名>` 再删（可用 `git worktree add <路径> <ref>` 找回），锁定的不碰；原样打印它在 timeline 里记下的那一行「回收 N 个 · 释放 X MB · 归档 M 个」。恒 exit 0，不影响收口结论；报 `invalid choice`（hooks 未升级）时跳过，照常往下。
   `--expect-models` / `--expect-efforts` 是机械对账（`--turns` 让大片档按 `executor-large` 对账）：任一不符（非 0）→ **铁律 11 违规**，在收口报告点名与路由表不符的 agent（角色 / 期望 / 实际），并把它作为一条 `{"severity": "HIGH", "summary": "路由不符 …"}` 追加进 `review-findings.json.blocking`——`ship` 据此自动判 draft，主会话不自行判断。打印 session-decompose 与 timeline report 输出的飞行记录（含**各 agent 实际模型**）；把工作流返回的 `{blocked, blocking, deferred, fix}` 与 `waves`（每个 wave 的集成检查结论与跨片修复）原样写入 `openspec/changes/<name>/review-findings.json`（`blocked` 条目带 `kind: gate | infra`，供 `/pr-ship` 进 PR 正文作说明；`blocking` 是 `ship` 裁决依据之一）；删除 `openspec/changes/<name>/.flight`；然后跑机械裁决：
   ```bash
   python3 .claude/hooks/slice-gate.py ship --change-dir openspec/changes/<name>    # 退出 0 ready / 1 draft；reasons 列出为何不 ready
   ```
   `ship` 只读 `gate-report.md`（每切片最新行 + final 行是否 ok 且对齐 HEAD）与 `review-findings.json.blocking`，不看工作流的 blocked 列表。reasons 里出现 `final 过期` → 重跑 `slice-gate.py final` 再 `ship`（同树会秒回：代码树、计划、命令都没变且上次绿就沿用结论；内容变了走增量，只重跑受影响的测试）。reasons 里出现「wave 集成检查红」→ 修复后重跑 `slice-gate.py wave-check` 再 `ship`。把门禁绿的切片在 `tasks.md` 里对应 `- [ ]` 勾成 `- [x]`（红的切片不勾）；飞行记录文件单独 `chore(flight)` commit。

7. **不问，直接进入 `/pr-ship`**
   无论 `ship` 结果如何都调用 `/pr-ship`；它会自己再跑一次 `ship` 决定以 draft 还是 ready 建 PR，并把 `ship --markdown` 的段落贴进正文。主会话不自行判断 draft。

**暂停例外（仅这四种，其余一律直接往下走，不问）**
- spec 自相矛盾
- 需要破坏性操作（如需要用户显式授权的 merge / push / delete）
- 测试环境本身坏（verify 在改动前就不可运行）
- 同一门禁项连续 2 次红

**Guardrails**
- 启动到 `/pr-ship` 之间不出现 AskUserQuestion（四种暂停例外走「停下报告」，不是问询）。
- 模型按角色显式路由；派发时不得省略 `model`；收口报告必须打印各角色实际模型。
- 起飞前的人类批准由 `.claude/hooks/takeoff-gate.py` 校验（PreToolUse hook + step 0 自检），**禁模型自证**；脚本非 0 就不起飞。
- 路由取自 `slices.json.routing`，经 `model-routing.py resolve` 读取，**禁模型自述**；未 pin 或环境覆盖即停飞。
- `--gate=per-task` 是唯一非飞行路径，转给 legacy skill 承载，本命令步骤 3–7 不适用于该分支。
- 不自动 merge / push / 删 worktree。
