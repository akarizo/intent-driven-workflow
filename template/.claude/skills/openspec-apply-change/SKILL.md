---
name: openspec-apply-change
description: Implement tasks from an OpenSpec change using flight mode — 批准后从门禁 lint 一路跑到 PR，中途不问，模型按角色显式路由。Use when the user wants to start implementing, continue implementation, or work through tasks.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "2.0"
  generatedBy: "1.3.1"
---

飞行模式跑完一次 apply：批准自检（`takeoff-gate.py`；非 0 → 停下报告并交出 `spec.html` 路径，不派发）→ 选 change → git 纪律检查 → 切片规划 lint → 记录并提交批准事件 → 启动切片工作流（模型按角色显式路由；不可用则回退并行 Agent 派发）→ 收工作流 JSON → 收口分解（打印各角色实际模型）→ 直接进入 `/pr-ship`。除四种暂停例外，全程不问询。

**REQUIRED SUB-SKILL：** 用 `openspec-git-discipline`（含 **Worktree Isolation**）—— apply 必须在本 change 的 `.worktrees/<name>/` worktree 内进行，实现代码落在那里。

**Input**：可选指定 change 名。留空则从会话上下文推断，仍歧义才列候选。`--gate=per-task` → 转读 `.claude/skills/legacy/openspec-subagent-apply-change/SKILL.md` 并按它逐 task 守门执行；本 skill 其余步骤不适用于该分支。
`--model=<alias>`（可选）→ 人工指定会话主模型别名 `<main>`，**优先于 `session-model.py` 的判定**；仅用于脚本判定不出、或主模型是第三方 / 自定义 id 的场合。

**模型路由（铁律：按角色显式声明，不得留空让 `CLAUDE_CODE_SUBAGENT_MODEL` 默认兜底）**

| 角色 | 模型 | effort |
|---|---|---|
| slice-executor（实现 / 批量修复） | 会话主模型别名 `<main>`（由 `session-model.py` 判定，见 step 4） | high |
| code-reviewer（切片评审 / 复核） | 会话主模型别名 `<main>`（由 `session-model.py` 判定，见 step 4） | high |
| integrator（合回 / 抽接口 / final） | `sonnet` | low |

**Steps**

0. **批准自检（起飞判据；批准由脚本校验，禁模型自证）**
   先按 step 1 的规则定出 `<name>`（有参数直接用参数），再跑：
   ```bash
   python3 .claude/hooks/takeoff-gate.py --change-dir openspec/changes/<name>   # exit 3 = 没有人类批准 / 批准过期
   ```
   `exit 0` → stdout 是人类批准证据，留给 step 3 的 approve 事件。`exit ≠ 0` → **停下报告**：打印 `openspec/changes/<name>/spec.html` 的绝对路径，说明「起飞需要你自己发出 `/opsx-apply <change>`」，不进入后续步骤、不派发任何 agent。

1. **选 change**
   - 有参数用参数；否则从会话上下文推断；只有一个活跃 change 自动选；歧义 → `openspec list --json` + **AskUserQuestion** 让用户选。
   - 宣告：`Using change: <name>`。

1.5 **确认已在本 change 的 worktree 内**（见 `openspec-git-discipline` 的 Worktree Isolation）
   CWD 必须是 `.worktrees/<name>/`；不在则进入已存在的 worktree；worktree 缺失 → 停下报告，不在主仓库工作区写实现代码。
   `git status --short` 确认工件已单独 commit、工作树干净；不满足 → 停下报告。

2. **切片规划 lint**
   ```bash
   python3 .claude/hooks/slice-gate.py lint --change-dir openspec/changes/<name>
   python3 .claude/hooks/slice-gate.py preflight --change-dir openspec/changes/<name>
   ```
   `lint` 拿到 stdout 的 waves JSON。exit 非 0（规划红）→ 停下报告规划问题，不进入实现。
   `preflight` 校验 `gate-baseline.json`：exit 非 0（缺基线 / 基线红 / 基线过期）→ 停下把 stderr 原样报告，不进入实现；基线由 propose 的 `baseline` 步骤生成，缺了回去补。

3. **记录批准事件并提交飞行记录**
   ```bash
   python3 .claude/hooks/timeline.py record approve --change-dir openspec/changes/<name> --note "<批准证据>"
   git add openspec/changes/<name>/timeline.md && git commit -m "chore(flight): approve"
   ```
   `<批准证据>` 用 step 0 `takeoff-gate.py` stdout 的原文，不自己编。飞行记录文件由 hook 自动追加，起飞前必须已提交，否则 integrator 合回并行切片时会被 `git merge` 拒绝。写 `openspec/changes/<name>/.flight`（JSON，字段 `{"started","approval","models","efforts","raw","source"}`）。

4. **启动切片工作流**
   - 先定出会话主模型别名 `<main>`：
     ```bash
     python3 .claude/hooks/session-model.py   # stdout: opus|sonnet|haiku|fable；exit 3 = 判定不出
     ```
     `exit ≠ 0` → **停下报告**，提示用 `--model=<alias>` 显式指定后重跑；有 `--model=` 旗标时以旗标为准。禁模型自述主模型。
   - 优先用 **Workflow** 工具：`name: "opsx-apply"`，`args: {change, changeDir, hooksDir: ".claude/hooks", agentsDir: ".claude/agents", waves, useAgentTypes: true, branch: "<git branch --show-current>", models: {executor: "<main>", reviewer: "<main>", integrator: "sonnet"}, efforts: {executor: "high", reviewer: "high", integrator: "low"}}`。`models` 缺任一角色脚本会拒绝起飞。
   - 同时传 `deps: <slices.json 里每片的 deps 映射>`，依赖已 blocked 的切片脚本不再派发。
   - Workflow 不可用（工具缺失 / `disableWorkflows`）→ **回退**，语义与脚本逐项一致：按 waves 逐 wave 用 **Agent** 工具在同一条消息里并行派发 `subagent_type: slice-executor`、`model: "<main>"`（每个执行体（含单片 wave 与 fix）都带 `isolation: worktree`，每个 wave 都派 integrator 合回；Agent 工具没有 effort 参数，effort 由 agent frontmatter 决定：执行体 / 评审员 high，integrator low；执行体 `slice-gate.py start` 带 `--expect-branch <branch>`，由 `slice-gate.py` 校验 worktree 是否从 change 分支最新 commit 分叉，start 非 0 则执行体把它打印的 JSON 原样返回），回报只收其原样 JSON；门禁红则以其 `failed` 重派同一切片一次——重派 prompt 带上一轮的 `commit` 与 `base`：第零步 HEAD 不是该 commit 则 `git cherry-pick <commit>`（冲突 abort 并记 `G0 base`），再 `slice-gate.py start <S> --base <base>` 接续同一基准（start 幂等）；执行体未返回门禁 JSON（Agent 工具回报 partial 或无 JSON）也重派一次（Agent 调用抛错与未返回同样处理：重派一次）——prompt 说明上一轮未返回，`slice-gate.py start <S> --resume-checkpoint` 从快照恢复半成品后继续；重派仍无 JSON 记 blocked（infra）；仍红记 blocked，依赖它的切片直接记 blocked；wave 后派 `integrator`（`model: "sonnet"`）先提交飞行记录、合回（只合回、不跑 final）、逐片 `slice-gate.py record --json '<该切片门禁 JSON 原文>'` 写回门禁结论与天花板行；评审用 `code-reviewer`（`model: "<main>"`）并行派发（`run_in_background` 语义：不等）；最后一次批量修复（fix 同样 `isolation: worktree`；fix 第一步先做基点校验 `git merge-base --is-ancestor $(git rev-parse <branch>) HEAD`，不成立则不做改动、返回 `G0 base`，`start fix` 也带 `--expect-branch <branch>`；fix 未返回、Agent 调用抛错或 G0 拒绝都重派一次，仍无可合回结果记 blocked（infra）、不合回且照常跑 final），integrator 先合回 fix 的 commit、再跑 final。integrator 与 final 抛错或未返回时重派一次，仍失败记 blocked（infra）；评审未返回只记录（blocked，infra），不重派——切片级评审缺失由 pr-ship 的整 PR 评审兜住。
   - 两条路径最终都产出同一份 JSON：`{change, models, efforts, slices, blocked, blocking, deferred, fix, final}`。

5. **收口分解**
   ```bash
   python3 .claude/hooks/timeline.py record apply-done --change-dir openspec/changes/<name>
   python3 .claude/hooks/session-decompose.py --session <当前会话 jsonl，取 ~/.claude/projects/<slug>/ 下最新> --workflow <Workflow 返回的 Transcript dir> --expect-models '<.flight 里的 models>'
   python3 .claude/hooks/timeline.py report --change-dir openspec/changes/<name>
   ```
   `--expect-models` 机械对账：非 0 → 铁律 11 违规，收口报告点名不符的 agent，并把它作为一条 `severity: HIGH` 追加进 `review-findings.json.blocking`，由 `ship` 机械判 draft。打印飞行记录（含各 agent 实际模型）；把 `{blocked, blocking, deferred, fix}` 原样写入 `openspec/changes/<name>/review-findings.json`（`blocked` 带 `kind: gate | infra`）；删除 `.flight`；跑 `python3 .claude/hooks/slice-gate.py ship --change-dir openspec/changes/<name>`（只读 gate-report.md 每切片最新行 + final 对齐 HEAD + blocking；退出 0 ready / 1 draft；`final 过期` → 重跑 final 再 ship）；把门禁绿的切片在 `tasks.md` 里勾选；飞行记录文件单独 `chore(flight)` commit。

6. **不问，直接进入 `/pr-ship`**
   无论 `ship` 结果如何都调用；`/pr-ship` 自己再跑 `ship` 决定 draft / ready 并把 `ship --markdown` 段落贴进正文。主会话不自判 draft。

**暂停例外（仅这四种）**：spec 自相矛盾 · 需要破坏性操作 · 测试环境本身坏 · 同一门禁项连续 2 次红。

**Guardrails**
- 启动到 `/pr-ship` 之间不出现 AskUserQuestion。
- 模型按角色显式路由；派发时不得省略 `model`；收口报告必须打印各角色实际模型。
- 起飞前的人类批准由 `.claude/hooks/takeoff-gate.py` 校验，**禁模型自证**；脚本非 0 就不起飞。
- `<main>` 由 `.claude/hooks/session-model.py` 判定，**禁模型自述**；判定不出停飞，人工 `--model=<alias>` 覆盖。
- `--gate=per-task` 转 legacy skill，不与本流程混用。
- 不自动 merge / push / 删 worktree。

**Fluid Workflow Integration**

- 可随时调用；不锁相位（Before all artifacts are done、部分实现之后都能跑）。
- 实现中若发现设计问题，允许建议更新工件，不是硬性阻断。
