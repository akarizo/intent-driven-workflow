---
name: openspec-subagent-apply-change
description: legacy 逐 task 守门 apply 模式。默认流程已改为飞行模式（slices.json + slice-gate 机械门禁 + 评审离路径），本 skill 仅在用户对 /opsx-apply 显式传 --gate=per-task 时按路径读取。当用户在 /opsx-apply --gate=per-task 时使用。
license: MIT
compatibility: Requires git, OpenSpec CLI, and Claude Code subagents (Agent tool).
metadata:
  author: intent-driven-claude-code
  version: "1.0"
---

> **legacy**：默认流程已改为飞行模式（见 `openspec-git-discipline` 与 `slice-gate.py`），本 skill 仅在 `/opsx-apply --gate=per-task` 时按路径读取，不再是推荐路径。实测逐 task 链路每 task 22–106 min，等 review/fix 子 agent 占 64–80% 时间。

# OpenSpec Subagent Apply（逐 task 守门，legacy）

用 fresh subagent 逐个 task 实现一个 OpenSpec change：**每个 task 由一个干净的实现 subagent 走完整 TDD 写出来，紧接着由一个干净的 `code-reviewer` subagent 守门**，CRITICAL/HIGH 级问题不修复不许勾选 checkbox。全部 task 完成后做一次整体 full review + `/opsx-verify`，最后收口报告，**不 merge 不 archive**。

这是"tdd → subagent 开发 → subagent-review，每个功能有守门员"的落地。

**REQUIRED SUB-SKILL：** 任何 apply / 实现动作前先用 `openspec-git-discipline`。
**实现纪律：** 每个实现 subagent 必须走 `test-driven-development` skill（RED→验红→GREEN→验绿→REFACTOR + GWT 三段中文注释）。

## 何时使用

- 用户在 `/opsx-apply` 的确认问询里选了"**subagent 逐 task 守门**"。
- 中级+ 变更（新 capability / 改公共契约 / 跨模块 / 引入新抽象 / 架构决策），希望每个 task 都有独立守门员。

**何时不要用：**
- `--no-confirm` 调用（来自 `/opsx-bulk-apply` 的子 agent）→ 走串行 `openspec-apply-change`。**subagent 不能嵌套**，子 agent 内不能再派逐 task subagent。
- 纯文档 / 纯配置 / 一次性 prototype 的 mini 任务 → 串行或直接改。

## 与其他 apply 路径的边界

| Skill | 粒度 | 隔离 | 守门 |
| --- | --- | --- | --- |
| `openspec-apply-change`（串行） | 单 change，主会话逐 task 串行写 | 本 change 的 worktree | 无（靠 /pr-ship 末尾） |
| **本 skill** | 单 change，**逐 task 派 subagent** | 本 change 的 worktree（不为每 task 各开） | **每 task 一个守门员** + 末尾 full review |
| `openspec-bulk-apply-change` | **多 change**，各派 subagent 跑整个 apply | 每 change 一个 worktree | 各自 apply 内的纪律 |

**worktree 粒度 = 每 change 一间，不是每 task 一间**：本 change 从 propose 起就在自己的 `.worktrees/<name>/` worktree 内（见 `openspec-git-discipline` 的 Worktree Isolation），apply 也在**这一间**里进行。逐 task 是**串行累积**（task2 依赖 task1 的产出），所有 task 必须在**同一间** worktree 里累积 —— 因此**不要为每个 task 各开 worktree、也不要在本 change worktree 内再嵌套子 worktree**。Claude Code 原生 `isolation: worktree` 每次派发都新建独立 worktree、看不到前序 task 产出，正是这里要避免的。在本 change worktree 内累积还让分级门禁（`intent-gate.py`，相对路径判断）零改动生效。

## Review 水位线（`review-log.md`）

逐 task 守门产生的审查状态**必须落盘**，供后续 review 点（本 skill 的整合审、`/pr-ship` 的 PR 评审、`/opsx-verify` 的测试纪律检查）判断「哪段范围已经审过、哪些 finding 已经处理」，避免同一份代码被反复全量重审。

**路径**：`openspec/changes/<change>/review-log.md`。落在 `openspec/` 内 → `intent-gate.py` 天然豁免、随 change 一起归档、人类可读、可进 PR。

**格式**：

````markdown
# Review Log · <change>

BASE_REF: <apply 开始前的 HEAD>
REVIEWED_UPTO: <已被守门审过并通过的最新 commit>

| # | scope | range | verdict | 阻断并修复 | date |
|---|-------|-------|---------|-----------|------|
| 1 | task 1.1 | a1b2c3d..4e5f6a | pass | 2 (HIGH) | 2026-08-25 |
| 2 | task 1.2 | 4e5f6a..9f8e7d6 | pass | 0 | 2026-08-25 |

## Deferred（未阻断，留给整合审与 PR 一并呈现）
- MEDIUM `src/export.py:88` — 重复的日期解析，建议抽公共函数
- LOW `src/api.py:12` — 命名 `tmp2` 不表意
````

**唯一写入方 = 本 skill 的主会话**：在 4d 勾选 checkbox 时追加一行并推进 `REVIEWED_UPTO`。`code-reviewer` subagent **不读**这个文件——它拿到的「已审范围 / 已处理 finding」由主会话摘进 prompt，保持 reviewer 干净、不带本地状态。

**兜底原则**：任何读取方**读不到 `review-log.md` → 一切回退全量审**。水位线只能缩小「已被守门覆盖」那部分的范围，**永远不能**让未审代码蒙混过关——`REVIEWED_UPTO` 之后的任何 commit 一律按全量标准审。

## Steps

### 1. 选 change 并跑 git discipline

- 确定 change 名（命令给了就用；否则从上下文推断 / 唯一 active 自动选 / 歧义则 `openspec list --json` + AskUserQuestion）。宣布："Using change: <name>"。
- 用 `openspec-git-discipline`：① 确认 CWD 已在本 change 的 `.worktrees/<name>/` worktree 内（见 Worktree Isolation）——不在则进入已存在的 worktree，缺失则停下报告；② 确认 proposal 工件已在一个单独 commit（只含工件、无实现代码，无需先合 `main`）；③ `git status --short` 看工作树状态。未满足则停下报告，不强行开工。

### 2. 取 apply 上下文

```bash
openspec status --change "<name>" --json
openspec instructions apply --change "<name>" --json
```

- 解析 `schemaName`、`contextFiles`、进度、task 列表。
- **Read 所有 `contextFiles`**（proposal / specs / design / adr / tasks，按 schema）。
- 读 `tasks.md`，列出所有未勾选 `- [ ]` task。
- 状态处理：`blocked`（缺工件）→ 提示 `/opsx-continue`；`all_done` → 提示 archive，结束。

### 3. 记录起点 + 确认工作区干净（commit 锚点是逐 task 圈 diff 的基础）

```bash
git rev-parse HEAD          # 记为 BASE_REF（apply 开始前的 HEAD）
git status --short          # 工作区必须干净
```

**关键机制：每个 task 由实现 subagent 产生一个本地 commit**（见 4a），这样：

- 每个 task 的"净 diff" = `git diff HEAD~1` 或 `git diff <task前一个commit>..HEAD`（精确、无歧义）；
- 整个 change 的累计 diff = `git diff <BASE_REF>..HEAD`（两点，比 BASE_REF 与当前 HEAD 之间的全部 commit）。

**前置硬要求**：开工前 `git status --short` 必须**干净**（无未提交改动）。若工作区脏，停下让用户先 commit / stash——否则首个 task 的 commit 会把无关改动一起裹进去，污染该 task 的净 diff。

**水位线初始化**：若 `openspec/changes/<name>/review-log.md` 不存在，用刚记下的 `BASE_REF` 初始化它（格式见上面的 **Review 水位线** 节）；已存在（续做场景）则读出 `REVIEWED_UPTO`，从它之后的 task 继续。

> 这些是**本地实现 commit**，落在当前 feature 分支 / worktree，绝不 push / merge / archive；用户已在 `/opsx-apply` step 6 选「subagent 逐 task 守门」时知情同意（见 `openspec-git-discipline` 的 carve-out）。

### 4. 逐 task 循环（核心）

对每个未勾选的 task，按顺序依次执行（**串行，不并行**——后一个 task 依赖前一个的产出）：

#### 4a. 派 fresh 实现 subagent

用 **Agent 工具**（`subagent_type: general-purpose`——它有 Write/Edit/Bash，能写代码、跑测试、commit；**不要**用只读的 `code-reviewer`）派发。

派发前主会话先准备好要塞进 prompt 的**运行上下文**（subagent 是 cold 的，这些它无从自知）：repo 根绝对路径、本 change 目录路径、相关源文件位置（从 contextFiles / 既有代码定位）、项目测试命令（探测：有 `package.json` 看 `scripts.test`、有 `pytest.ini`/`pyproject.toml` 用 `pytest`、有 `go.mod` 用 `go test`，等等）。

prompt 必须**自包含**（subagent 不带主会话上下文）：

```
背景：你在为 OpenSpec change `<name>` 实现单个 task。在本 change 的 worktree 内直接操作（主会话已进入它；不要再新建/嵌套 worktree、不要切分支、不要 push）。

运行环境（已为你查好）：
- repo 根：<绝对路径>
- 本 change 目录：<绝对路径>/openspec/changes/<name>/
- 与本 task 相关的源文件：<路径清单；新建文件给目标路径>
- 跑测试的命令：<如 `pytest tests/`、`npm test`、`go test ./...`>
- 你有 Write / Edit / Bash 权限，可直接改文件、跑测试、git commit。

本 task：<task 编号 + 完整描述>

相关规格（节选自 contextFiles）：
<贴出与本 task 相关的 spec scenario / design 决策 / adr 约束片段——尽量完整，reviewer 之后会按这些 spec 核对你的实现>

强制要求：
1. 必须走 test-driven-development skill：先写失败测试 → 用上面的测试命令亲眼验证它失败（RED）→ 写最小实现让它通过（GREEN）→ 再跑验证通过 → REFACTOR。报告里要贴 RED 和 GREEN 两次测试运行的关键输出，证明你确实先红后绿。
2. 每个单测函数体首行是 `// Given:`（Python 用 `#`）三段中文注释，When 只触发一个被测动作，Then 注释与断言一一对应。详见 .claude/skills/test-driven-development/SKILL.md 与 testing-anti-patterns.md。
3. 只做这一个 task，不要顺手改无关代码、不要引入未要求的抽象。
4. 保持最小改动，清理自己造的 orphan（未引用的 import / 变量）。
5. **完成后，把本 task 的全部改动作为一个本地 commit 提交**（只 add 与本 task 相关的文件，不用 `git add -A`）：
   `git add <本 task 相关文件>` → `git commit -m "<type>(<scope>): <task 编号 简述>"`
   不要 push、不要 merge、不要碰别的分支。

完成后报告：本 task commit 的 SHA、改了哪些文件（路径）、新增/修改了哪些测试、RED→GREEN 的测试输出摘要、有没有遗留问题。
```

> 主会话在派发前记下 `git rev-parse HEAD`（本 task 起点 = 上一个 commit），用于 4b 圈定 diff。

#### 4b. 派 code-reviewer subagent 守门

实现 subagent 返回后（它已 commit 本 task），先跑 `python3 .claude/hooks/session-model.py` 判定 `<main>`（stdout 即别名；exit 3 = 判不出 → 停下交人工给出别名，禁模型自述），再用 **Agent 工具**（`subagent_type: code-reviewer`、`model: "<main>"`，写法同 `/pr-ship` 第 8 步）派发。**本 task 净 diff 就是那个 commit**——用两点 diff 精确圈定，不再有歧义：

```
背景：review 一个 OpenSpec change 里单个 task 的实现。这是 intent-driven 工作流的逐 task 守门。

评审模式：full —— 本 task 净 diff 就是全量范围，没有已审前置，按你的全部 checklist 维度审。

审查范围（仅这个范围）：本 task 的净 diff = 实现 subagent 刚产生的那个 commit。
取 diff：`git diff <本 task 起点 SHA>..HEAD`（两点；<本 task 起点 SHA> = 派实现 subagent 前主会话记下的 HEAD）。
  等价写法：`git show <本 task commit SHA>`。
  注意用两点 `..` 不是三点 `...`——逐 task 是线性累积，两点比的是"起点到 HEAD 的实际改动"。
本 task 要求（请逐条核对实现是否满足）：<task 描述 + 相关 spec scenario 全文>
RED→GREEN 证据：<实现 subagent 报告里的测试输出摘要——据此判断是否真先写了失败测试>

阻断阈值：CRITICAL 与 HIGH 都阻断。测试缺失 / TDD 纪律被破坏（含拿不出 RED 证据、GWT 注释缺失）按 HIGH 起评。
除通用代码质量外，**务必核对 spec compliance**：实现有没有覆盖上面每条 spec scenario、有没有偏离 spec 约束。
按你的分级格式输出报告，结论行明确"通过 / 阻断"，末尾签名。
不要修代码。
```

#### 4c. 阻断判定与回灌

- reviewer 报告**有 CRITICAL 或 HIGH** → **不勾 checkbox**。派一个 fresh 修复 subagent（`subagent_type: general-purpose`）。它也是 cold 的，prompt 必须把"修什么、在哪、问题是什么"讲全：

  ```
  背景：修复一个 OpenSpec change 里某 task 实现被 code-reviewer 挡下的问题。在本 change 的 worktree 内直接操作（主会话已进入它），不要 push / 切分支 / 新建 worktree。

  运行环境：<同 4a：repo 根 / change 目录 / 相关源文件 / 测试命令 / 有 Write·Edit·Bash 权限>
  本 task：<task 编号 + 描述>
  本 task 已有的实现 commit：<SHA>，改动文件：<清单>（用 `git show <SHA>` 查看现状）

  reviewer 挡下的问题（逐条修）：
  <把 reviewer 报告里每条 CRITICAL/HIGH 原样贴出：文件:行号 + 问题 + 修法建议>

  强制要求：
  1. 只修上面列出的问题，不要顺手改别的。
  2. 修复也走 TDD：每个被挡的 bug，先写一个能复现它的失败测试（亲眼验证它红）→ 再改实现让它绿。不允许直接改实现不补测试。
  3. 修完把改动提交为**一个独立的 `fix:` commit**：`git commit -m "fix(<scope>): <task 编号> <finding 摘要>"`。**不要用 `git commit --amend`**——amend 会改写 commit SHA，导致「修复增量」这个区间无法稳定圈定，而下一步的聚焦复核正依赖这个区间。不要 push。（一个 task 因此可能对应多个 commit，整洁性让位于区间可圈定；PR 阶段可 squash 找回。）

  完成后报告：改了什么、新增哪些复现测试、RED→GREEN 输出、最终 commit SHA。
  ```

  修完派一个 fresh `code-reviewer`（`model: "<main>"`，`<main>` 同 4b 由 `python3 .claude/hooks/session-model.py` 判定，exit 3 则停下交人工）做**聚焦复核**——**不重审整个 task**，只看修复增量与原 finding 是否闭环：

  ```
  背景：复核一个 OpenSpec change 里某 task 的修复补丁，判断上一轮 code review 挡下的问题是否已闭环。

  评审模式：follow-up —— 只审下面这个修复 commit，**不要**重审本 task 的其余代码（那部分上一轮已审过）。

  审查范围（仅这个范围）：修复 commit `<fix commit SHA>`。
  取 diff：`git show <fix commit SHA>`。

  上一轮挡下的 finding（逐条核对是否已闭环）：
  <把上一轮报告里每条 CRITICAL/HIGH 原样贴出：文件:行号 + 问题 + 当时给的修法建议>

  你的任务只有两条：
  1. 逐条判定上面每个 finding 是「已闭环 / 未闭环 / 修得不对（引入新问题）」，各给一句依据。
  2. 判断这个修复 commit 本身有没有新引入的 CRITICAL/HIGH 问题。

  阻断阈值不变：CRITICAL 与 HIGH 都阻断。结论行明确"通过 / 阻断"，末尾签名。不要修代码。
  ```

  → **循环直到无 CRITICAL/HIGH**（每轮都只审当轮新增的 `fix:` commit）。
- MEDIUM / LOW → 记录进收口报告，**不阻断**（除非用户另行要求）。
- **回灌硬上限：3 轮**。第 3 轮复审仍有 CRITICAL/HIGH → **停下，不再自动回灌、不勾 checkbox、不向用户问"要不要继续修"**。把现状（剩余阻断项 + 已试 3 轮）报告给用户，由用户决定（往往意味着 task 描述/spec/设计本身有问题，需回 `/opsx-continue` 改工件，而非继续蛮修）。绝不蒙混勾选。

#### 4d. 勾选 checkbox

仅在本 task 守门通过（无 CRITICAL/HIGH）后，**由主会话**（不是 subagent）把 `tasks.md` 里该 task 的 `- [ ]` 改成 `- [x]`（`tasks.md` 在 `openspec/`，门禁豁免，主会话 Edit 直接放行）。然后进入下一个 task。

紧接着**由主会话**追加水位线记录（格式见 **Review 水位线** 节）：

- 在区间表追加一行：`scope` = 本 task 编号、`range` = `<本 task 起点 SHA>..<当前 HEAD>`、`verdict` = `pass`、`阻断并修复` = 本 task 回灌修掉的 CRITICAL/HIGH 条数；
- 把 `REVIEWED_UPTO` 推进到当前 HEAD；
- 把本 task 守门报告里**未阻断**的 MEDIUM / LOW 逐条登记到 `## Deferred` 清单（带 `文件:行号` + 一句摘要）——它们后续会随 `/pr-ship` 的 PR 评论上浮给人类 reviewer，不要只留在会话里。

> 勾选这个动作本身的改动会落进**下一个** task 的 commit 里（或由用户在 pr-ship 前单独 commit），无所谓——它不影响逐 task 净 diff 的圈定（diff 比的是实现 subagent 的代码 commit）。`review-log.md` 的改动同理。
> 输出建议：每个 task 实时显示 `Working on task N/M: <desc>` → `实现 subagent 返回（commit <SHA>）` → `守门：<通过 / 阻断 X 项，回灌第 K 轮>` → `✓ task complete`。

### 5. 整合审位置判定（全部 task 完成后）

整合审（跨 task 交互 / 整体一致性 / 端到端完整性）在一次变更里**只跑一次**。它跑在本地还是跑在 `/pr-ship`，由**用户明确选择**决定——**不要靠推断**「用户是不是打算立刻 ship」。

**硬跳过条件（先判，命中就不问）**：change 只有 **1 个 task** → 整合审**恒跳过**，理由是逐 task 守门已覆盖它的全部 diff，再审一次就是重复审同一份。在收口报告里注明跳过与理由。

否则用 **AskUserQuestion** 问一次：

- question：`<name> 的全部 task 已通过守门。整合审（跨 task 交互 / 整体一致性 / 端到端完整性）跑在哪一步？`
- header：`整合审`
- options：
  - `立即 /pr-ship（推荐）` — **跳过本地整合审**，整合审在 PR 阶段做。`/pr-ship` 本来就必须产出一份贴 PR 的报告，整合审搭在那里零额外成本，且结论对人类 reviewer 可见。
  - `暂不 ship，先在本地整合审` — 现在跑一次本地整合审（见下），之后再决定是否 ship。
  - `都跳过` — 直接收口（用户自负其责，收口报告里注明整合审未执行）。

选「暂不 ship」时，派一个 `code-reviewer` subagent（`model: "<main>"`，`<main>` 同 4b 由 `python3 .claude/hooks/session-model.py` 判定，exit 3 则停下交人工）审**整个 change 的累计 diff**（`git diff <BASE_REF>..HEAD`，**两点**——比 apply 开始到现在的全部 commit）：

```
背景：对一个 OpenSpec change 做整合审——全部 task 已逐个通过守门，现在只看它们拼起来有没有问题。

评审模式：integration —— 下面这段范围**每个 task 的单 task 质量已被逐 task 守门审过并修过**，不要重复审。
已审范围：<BASE_REF>..<REVIEWED_UPTO>（<N> 个 task，守门期间已阻断并修复 <X> 项）
已登记为 deferred 的 finding（**不要重复上报**）：
<把 review-log.md 的 Deferred 清单原样贴出>

审查范围：`git diff <BASE_REF>..HEAD`（两点）。

**只报这四类**：
1. 跨 task 的交互问题（task A 改的接口 / 数据结构被 task B 误用）
2. 整体一致性（命名、错误处理、分层风格跨 task 是否统一）
3. 端到端完整性（各 task 拼起来是否真满足 change proposal 的整体目标、有无遗漏的 capability）
4. 工件与实现是否一致（实现有没有偏离 spec / design 的约束）

**不要报**：上面「已审范围」内的单 task 级质量问题、已登记为 deferred 的条目。
例外——若你确认某条上游 finding 实际没修好，可以报，但必须标注「上游 review 未闭环」。

按你的分级格式输出报告，结论行明确"通过 / 阻断"，末尾签名。不要修代码。
```

无论走哪条分支，都把**整合审位置**（本地 / 交给 pr-ship / 跳过及理由）记进收口报告，让下一步的人知道整合审有没有做、做在哪。

### 6. Verify

跑 `/opsx-verify <name>`（复用 `openspec-verify-change`）做三维一致性 + TDD/BDD 纪律检查。有 blocking 问题 → 回到对应 task 修 → 重跑，直到无 blocking。

### 7. 收口（不 merge 不 archive）

报告：

- change 名 + schema
- 每个 task：commit SHA、守门轮数、阻挡过的 CRITICAL/HIGH（摘要）、最终状态
- **整合审位置**：本地已跑 / 交给 `/pr-ship` / 跳过（含理由）——以及跑了的话，结论是什么
- **水位线区间**：`BASE_REF` → `REVIEWED_UPTO`，覆盖 N 个 task
- `/opsx-verify` 结论
- 改动文件汇总 + 本次产生的 commit 列表（`git log <BASE_REF>..HEAD --oneline`）
- 遗留的 MEDIUM/LOW（供后续处理）

结尾固定提示：

> 本次做了实现 + 逐 task 守门 + 验证，产生了 N 个本地 commit（在当前分支，**未 push、未 merge、未 archive**）。下一步：`/claudemd-commit`（预算中性沉淀知识）→ `/pr-ship`（送出 + 合并前守门；逐 task commit 可在 PR 时选 squash 合并）。合回 main 后再 `/opsx-archive <name>`。

## Guardrails

- 始终先 `openspec-git-discipline`：确认已在本 change 的 worktree 内、proposal 工件已单独成 commit，否则不开工。
- **worktree 每 change 一间**：在本 change 的 `.worktrees/<name>/` worktree 内逐 task 累积；不为每个 task 各开、不嵌套子 worktree。
- 每个 task **先实现 subagent、再 reviewer subagent**，CRITICAL/HIGH 不修不勾 checkbox。
- 实现 subagent **必须**走 TDD（RED→GREEN→REFACTOR + GWT 中文注释）；reviewer 把"测试缺失 / TDD 被破坏"按 HIGH 阻断。
- reviewer 是**干净、只读**的（prompt 自包含、不带主会话上下文、只 review 不改码）。
- task 之间**串行**（依赖累积），不要并行派发。
- **每个 task 一个本地 commit**（实现 subagent 产生，落当前分支）——这是逐 task 圈 diff 的锚点，且已被 `openspec-git-discipline` 的 carve-out 允许（用户在 step 6 已知情同意）。
- **不 push、不 merge、不 archive、不碰 main、不擅自建分支**——除非用户明确指示。逐 task 本地 commit ≠ 上述任一项。
- 回灌**硬上限 3 轮**；到顶仍阻断就停下交用户，不再问"要不要继续"、不蒙混勾选。
- **守门通过必须写水位线**（4d）：不写 `review-log.md`，后续 `/pr-ship` 与 `/opsx-verify` 就读不到已审范围，会退回全量重审——重复就是这么来的。
- **修复用独立 `fix:` commit，禁 `--amend`**：amend 改写 SHA 会让修复增量区间不可圈定，聚焦复核只能退回重审整个 task。
- **整合审只跑一次**，位置由用户在 step 5 明确选，不靠推断；1 个 task 的 change 恒跳过。
- 子 agent 不能再嵌套 subagent；`--no-confirm`（bulk-apply）一律走串行 `openspec-apply-change`。

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| 给每个 task 开独立 worktree | 逐 task 是串行累积，全在本 change 的**同一间** worktree 里；每 change 一间、不是每 task 一间 |
| 实现 subagent 跳过 TDD | prompt 强制走 test-driven-development；reviewer 按 HIGH 阻断缺测试 |
| reviewer 带了主会话上下文 | prompt 自包含、不传对话历史，保独立性 |
| CRITICAL 没修就勾 checkbox | 阻断阈值 = CRITICAL + HIGH，回灌修复过才勾 |
| 并行派多个 task subagent | 后一个 task 依赖前一个产出，必须串行 |
| apply 完顺手 archive | 本 skill 只到 verify，archive 要先合 main、由用户触发 |
| bulk-apply 子 agent 里再调本 skill | subagent 不能嵌套；子 agent 走串行 |
| 取 diff 用三点 `A...HEAD` | 逐 task 线性累积用**两点** `A..HEAD`；三点比的是 merge-base 之后，分支场景会取错 |
| 工作区脏就开工 | 首个 task commit 会裹进无关改动；step 3 先 `git status --short` 验干净 |
| 实现 subagent 不 commit / 主会话替它 commit | 由实现 subagent 自己在 task 末尾 commit（它最清楚改了什么）；主会话只记起点 SHA |
| 实现 subagent 用了只读的 code-reviewer 类型 | 实现要 Write/Edit/Bash，用 `general-purpose`；`code-reviewer` 只给守门 |
| 修复用 `git commit --amend` | SHA 被改写 → 修复增量区间不可圈定 → 聚焦复核退化成重审整个 task。统一新增独立 `fix:` commit |
| 守门通过了却不写 `review-log.md` | 后续 review 点读不到已审范围，全量重审，本 skill 的去重设计当场失效。4d 勾 checkbox 与写水位线是同一步 |
| 靠推断「用户是不是要立刻 ship」决定跑不跑整合审 | 模型读不了心。step 5 用 AskUserQuestion 明确问，按答案硬判定 |
