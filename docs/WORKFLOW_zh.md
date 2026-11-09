# Intent-Driven 工作流详解

> 把 _为什么_、_做什么_、_怎么做_、_长期决策_、_实现步骤_ 这五件事，**强制按顺序**写下来，让代码上线时仍然能解释自己。

```
proposal → specs → design → adr → tasks
```

每一步都依赖前一步。`/opsx-apply` 在 `tasks` 完成前会拒绝运行。
schema 把这套规则编码在 `openspec/schemas/intent-driven/schema.yaml` 里。

---

## 阶段总览

| 阶段 | 文件 | 关键问题 | 配套 skill |
| --- | --- | --- | --- |
| 1. proposal | `proposal.md` | 为什么现在做？影响什么 capability？ | `grill-me` |
| 2. specs | `specs/<capability>/spec.md` | 系统外部可观测的行为是什么？ | `gherkin-authoring` |
| 3. design | `design.md` | 怎么实现？权衡了什么？ | `c4-diagrams` |
| 4. adr | `<repo>/openspec/adr/DRAFT-*.md`（合并时定号为 `NNNN-*.md`） | 哪些是长期不可逆的架构决策？ | `architectural-decision-records` |
| 5. tasks | `tasks.md` | 怎么落到逐条可勾选的步骤？ | —— |

---

## 1. proposal — 写"为什么"

**目标**：让一个完全没上下文的同事/未来的自己，仅凭这份 proposal 就能判断这件事值不值得做。

**模板**（来自 schema）：

```markdown
## Why
<!-- 1-2 句话点明问题 / 机会 -->

## What Changes
<!-- bullet 列出新增 / 修改 / 删除；BREAKING 显式标注 -->

## Capabilities
### New Capabilities
- `user-auth`: 简述这个能力的范围
### Modified Capabilities
- `data-export`: 行为级的改动是什么

## Impact
<!-- 影响的代码、API、依赖、运维系统 -->
```

**`Capabilities` 是 proposal → specs 的契约**：每一个列出的 capability 都会在 specs 阶段
对应一个 `specs/<capability>/spec.md` 文件。

---

## 2. specs — 写"做什么"

**目标**：用 Gherkin 句式描述行为，避免泄漏 UI/数据库/HTTP 细节。

```markdown
## ADDED Requirements

### Requirement: User data export
Feature: User data export
Rule: Users can export their own data

#### Scenario: Successful CSV export
- **GIVEN** a user has saved data
- **WHEN**  the user exports their data as CSV
- **THEN** the system provides a CSV file containing the user's data
```

四种 delta header：

| Header | 用途 | 注意事项 |
| --- | --- | --- |
| `## ADDED Requirements` | 新增 requirement | 直接写 |
| `## MODIFIED Requirements` | 修改已有 requirement | **必须粘贴完整的修改后内容**，不能只贴 diff |
| `## REMOVED Requirements` | 删除 requirement | 必须含 `**Reason**` 和 `**Migration**` |
| `## RENAMED Requirements` | 仅改名 | `FROM: / TO:` 格式 |

`### Requirement: <name>` 和 `#### Scenario: <name>` 的标题层级是 OpenSpec archive 用来合并的契约，**不能改**。

---

## 3. design — 写"怎么做"

**目标**：把会被后续 review 的关键决策（why X over Y）固化下来；预防"半年后看代码不知道为什么这么写"。

`design.md` 包含：

- **Context**：现状、约束、相关人
- **Goals / Non-Goals**：明确做什么 + **明确不做什么**
- **Decisions**：每个决策都附 _备选方案_ 和 _选择理由_
- **Risks / Trade-offs**：`[Risk] → Mitigation`
- **Migration Plan**：上线 / 回滚步骤
- **Open Questions**：尚未解决的问题；如果建议变更某个 in-force ADR，写在这里，由 adr 阶段处理

**铁律**：写 design 前先读 `openspec/adr/`，构建 supersession 图，识别**当前生效**的 ADR 集合。
新 design 必须跟现行 ADR 一致；要推翻某个现行 ADR，只能在 Open Questions 提议并让 adr 阶段新建一个 supersede。

---

## 4. adr — 写"长期不可逆决策"

**铁律**：**ADR 一经 accepted 就不可改**。任何字段都不可改：Status、Date、Decision、Consequences 全部冻结。

要变更一个旧决策？新建一个 ADR：

```markdown
# 0042. 改用 Postgres 替代 MySQL 做目录服务

- Status: accepted, supersedes ADR-0017
- Date: 2026-05-13
- Supersedes: ADR-0017

## Context
...为什么要重新讨论 ADR-0017...
```

文件名：分支上先用 `DRAFT-kebab-title.md`（**不取顺序号**），合并入 main 前才定号成 `NNNN-kebab-title.md`。NNNN 是仓库范围全局递增，**永不复用**。

> **为什么分支上不取号**：`NNNN` 是仓库范围的全局计数器。并行分支若各自扫 main 取「最大号 +1」，会撞到同一个号，合并第二条时文件名与 `Supersedes:` / CLAUDE.md 指针双双冲突。所以号推迟到「分支 → main」这一刻才由落地分支的人分配。
>
> **合并前定号 6 步**（详见 `openspec-git-discipline` skill）：
> 1. 切到最新 main，`ls openspec/adr/` 取当前最大 `NNNN`
> 2. 给本 change 的每个 `DRAFT-*` 顺次分配 `max+1、max+2…`
> 3. `git mv DRAFT-kebab-title.md NNNN-kebab-title.md`（保留历史）
> 4. 改文件内首行 `# DRAFT.` → `# NNNN.`
> 5. 回填本 change 内对该 draft 的引用（兄弟 ADR 的 `Supersedes:`、design 指针、CLAUDE.md 占位）
> 6. 提交定号后再合并
>
> 每条分支合并前**各自**重扫 main 的当前 max，后合并的分支看到的已是前一条定好的号，顺序天然错开、无缝无撞。`Supersedes:` 指向的旧 ADR 保留其**真实旧号**（它已在 main、号稳定），只有本分支自己的新 ADR 号被推迟。

何时建 ADR？满足三个条件全部：

1. 是**长期架构承诺**（pattern / 技术选型 / 模块边界 / 契约），不是战术实现细节
2. 会影响**当前变更之外**的未来工作
3. 当前没有 in-force ADR 已经覆盖，或者**有意推翻**某个 in-force ADR

不满足就别建 ADR，写在 design 里即可。

---

## 5. tasks — 写"怎么逐步实现"

```markdown
## 1. 数据层

- [ ] 1.1 新建 user_exports 表（migration）
- [ ] 1.2 增加 ExportJob 模型

## 2. API 层

- [ ] 2.1 POST /v1/exports 创建任务
- [ ] 2.2 GET  /v1/exports/:id 查询状态
```

**强制**：必须用 `- [ ]` checkbox 格式，否则 `/opsx-apply` 解析不到进度。

---

## apply · 飞行模式

`/opsx-apply <name>` 默认走**飞行模式**：tasks 阶段已经把实现拆成 `slices.json`（每片声明 `owns` / `deps` / `verify` / `scenarios`）与配套切片包 `slices/<S>.md`；apply 零问询，直接把这份计划跑起来：

```
slice-gate.py lint（校验 slices.json：片数 1–9 / DAG 深度 ≤ 3 / 同 wave owns 不相交 / verify 必填）
  → 算 wave → 起命名 Workflow .claude/workflows/opsx-apply.js（useAgentTypes 按 wave 并行）
    Workflow 不可用（未开通 / disableWorkflows）→ 回退：主会话按同一 waves 用 Agent 工具并行派发，语义一致
  同 wave 内每个切片派 slice-executor（model: inherit，maxTurns 40，acceptEdits）：
    走 test-driven-development（RED→验红→GREEN→验绿→REFACTOR + GWT 中文注释），只写 owns 内文件
    → 收尾跑 slice-gate.py gate（G1 verify / G2 lint·typecheck / G3 源码配对测试 / G4 GWT / G5 RED 先于 GREEN 留痕 / G6 所有权 / G7 scenario 已转 pass）
    → 门禁红重试一次，仍红则该切片 blocked、其余切片继续；门禁绿立即离路径起 code-reviewer（不阻塞下一 wave）
  全部 wave 完成 → integrator 合回并跑一次批量修复（汇总 CRITICAL/HIGH）→ slice-gate.py final（全量 test/lint/typecheck + 全部 scenario 状态）
  → session-decompose.py 收口分解（各 agent 实际模型）→ timeline.py report 打印飞行记录 → 转 /pr-ship
```

**含 submodule 的仓库**同样走飞行模式，机制见 `openspec-git-discipline` skill 的 Submodule 小节。

**Workflow 前置条件**：需要付费计划（Pro 要在 `/config` 里手动打开 Workflow）；把 `slice-gate.py` 与测试命令加进项目 `.claude/settings.json` 的 allow 规则，否则每个切片起步都会被权限提示打断并行。

**模型路由（铁律，按角色显式声明）**：slice-executor 与 code-reviewer 用会话主模型 `<main>`（effort high），integrator / final-gate 用 sonnet（effort low），渲染 / 分解 / 时间线是零 token 脚本。`<main>` 由 `.claude/hooks/session-model.py` 读会话转录判定（stdout `opus|sonnet|haiku|fable`，exit 3 = 判定不出），**禁模型自述**；判定不出不起飞（需 `--model=<alias>` 显式指定）。`/opsx-apply` 以 `args.models` 显式传入，脚本缺参拒绝起飞；收口 `session-decompose.py --expect-models` 机械对账各 agent 实际模型，不符即非 0（按 draft PR 处置）。解析顺序自 v2.1.251 起为「调用参数 > frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > 主会话」，派发时留空 `model` 就会落到 env 默认值。

**两处人类审批不可省**：起飞批准由 `.claude/hooks/takeoff-gate.py` 校验会话转录里的人类消息证据与新鲜度（PreToolUse hook 注册在 `Workflow|Agent|Task` 上拦未获批准的飞行派发；它对 `Workflow` 工具是否触发尚未实测，未触发时由 `/opsx-apply` step 0 的显式自检兜底），模型自证无效；PR review 是第二处。

**关键约束**：

- **所有权即隔离**：同一 wave 内各切片 `owns` 不相交（lint 校验），并行零冲突；门禁 G6 对 `owns` 之外的写入 DENY，执行体撞上不绕过，记入 `failed` 继续做能做的部分。
- **评审离关键路径**：门禁绿的切片立即起 `code-reviewer`（不 await），不拖慢下一 wave；不重跑测试套件，只读 `gate-report.md` + `evidence.log`。
- **subagent 不能嵌套**：`--no-confirm`（`/opsx-bulk-apply` 子 agent）一律走串行（`openspec-apply-change`）。
- **回退路径语义一致**：Workflow 不可用时主会话用 `Agent` 工具按同一 wave 并行派发，收到的仍是同样的门禁 JSON；不因回退而降低纪律。

详见 `.claude/agents/slice-executor.md`、`.claude/agents/integrator.md`、`.claude/agents/code-reviewer.md`、`.claude/hooks/slice-gate.py`。想用旧的逐 task 阻断式守门见下文「Legacy 模式」。

---

## Git 纪律

| 时机 | 规则 |
| --- | --- |
| propose 前 | 优先在 `main` 上；不在则警告并询问 |
| propose 后 | 提示用户把工件**单独提交为一个 commit**（只含 openspec 工件，不混实现代码）；可选建 PR 分支 |
| apply 前 | **工件必须已单独成一个 commit**（无需先合 `main`）；之后可在 main / 分支 / worktree 实现 |
| archive 前 | **必须从 `main` 运行**；implementation 必须已合回 |
| archive 后 | 提示 commit archive 与 spec sync 改动 |

**合并后清理：`/clean-after-merged [target-branch]`**——PR 被人类合并后在主仓库根运行：先 `--ff-only` 同步 target，再由 `merged-cleanup.py` 判定每个 worktree / 分支 / 飞行快照的档位。**safe 档**（已合并的 worktree、`branch -d`、已落地 change 的 `refs/flight/*`）自动执行；**manual 档**（squash 合并需 `-D`、有未提交改动、被锁定、远端分支 `push --delete`）只打印命令交你。**子仓提交保护**：含子仓的 worktree 若有只存在于它的子仓提交（未推送），删除会连子仓库本体一起丢失，脚本一律判为 manual，先推送子仓再删。

完整规则见 `.claude/skills/openspec-git-discipline/SKILL.md`。

---

## 端到端示例

```bash
# 在某项目根
cd ~/my-app

# 1. 启动 Claude Code，输入：
/opsx-propose add-user-export

# Claude 会：
#   - openspec new change add-user-export
#   - 生成 proposal.md, specs/user-export/spec.md, design.md, openspec/adr/DRAFT-*.md, tasks.md

# 2. 用户审阅，把工件单独提交为一个 commit（只含 openspec 工件；无需先合 main）
git add openspec
git commit -m "propose: add-user-export"

# 3. 实现（飞行模式，零问询）
git checkout -b feat/add-user-export
/opsx-apply add-user-export
#   lint slices.json → 算 wave → Workflow 并行派 slice-executor（门禁绿即离路径起 code-reviewer）
#   → 全部 wave 完成后批量修复 → final gate → 打印飞行记录
#   （想要旧的逐 task 阻断式守门：/opsx-apply add-user-export --gate=per-task）

# 4. 实现合回 main 后归档
git checkout main && git pull
/opsx-verify  add-user-export   # 一致性检查
/opsx-archive add-user-export   # 移到 openspec/changes/archive/YYYY-MM-DD-*
```

---

## Legacy 模式：逐 task 守门（`--gate=per-task`）

飞行模式是默认。`--gate=per-task` 仍可选回旧的**逐 task 阻断式守门**（吸收自 sdd-plus-superpowers 的 subagent-development 玩法，中文化自研、不依赖外部插件）：

```
对每个 task：
  派 fresh 实现 subagent（走 test-driven-development：RED→验红→GREEN→验绿→REFACTOR + GWT 中文注释）
    → 派 code-reviewer subagent 审本 task 净 diff（mode=full，CRITICAL/HIGH 阻断）
    → 有阻断项 → 回灌修（独立 fix: commit）→ 聚焦复核（mode=follow-up，只审那个 commit）→ 循环到清零
    → 勾选 checkbox - [ ] → - [x] + 写 review-log.md（推进 REVIEWED_UPTO、登记未阻断的 MEDIUM/LOW）
    → 下一个 task
全部 task 完成 → AskUserQuestion 定整合审位置（立即 ship → 交给 /pr-ship；暂不 ship → 本地跑 mode=integration；
                单 task 的 change 恒跳过）→ /opsx-verify → 收口（不 merge 不 archive）
```

**关键约束**：

- **不开 worktree**：逐 task 是串行累积（task2 依赖 task1 产出），在当前工作区。原生 `isolation: worktree` 每次派发开独立 worktree、看不到前序 task，不适用；这也让分级门禁 `intent-gate.py` 零改动生效。
- **subagent 不能嵌套**：`--no-confirm`（`/opsx-bulk-apply` 子 agent）一律走串行。
- **守门靠 review 水位线分层**：这些守门点的 diff 范围是**包含关系**（单 task ⊂ 累计 ≈ PR），光靠"范围不同"避免不了重复。`review-log.md` 记下已审区间与 deferred 清单，后续守门点读它决定审什么、不报什么：逐 task = `full`、回灌复核 = `follow-up`（只审 fix commit）、整合审 = `integration`（只报跨 task/整体/端到端/工件一致性，一次变更只跑一次）、PR 复审 = `follow-up`（只审修复补丁）。**读不到水位线一律回退全量审**——它只能缩小已覆盖部分的范围，不能放过未审代码。
- **`code-reviewer` 物理只读**：工具集仅 Read/Grep/Glob/Bash，从工具层面保证只 review 不改码；prompt 自包含、不带主会话上下文。

**为什么不再是默认**：2026-09-10 对 5 个跑该模式的会话做归因，每 task 链路 22–106 min，子 agent 时间里 review + fix 占 64–80%。详见 `.claude/skills/legacy/openspec-subagent-apply-change/SKILL.md` 与 `.claude/agents/code-reviewer.md`。

---

## 任务分级 · 何时必须走工作流，何时可跳过

这套 5 工件流不是对所有改动一刀切。按任务分级决定：**中级+ 必须严格走，mini 才允许跳过**。
源码写入由 PreToolUse 门禁 `.claude/hooks/intent-gate.py` 强制——绕不过去（需 python3）。

| | mini（允许跳过） | 中级+（必须严格工作流） |
| --- | --- | --- |
| 触发 | 文档/注释单改 · 依赖升级 · 配置值调整 · 单文件无行为变化 hotfix · 内部一次性脚本 | 新 capability · 新公共 API/命令 · 改公共契约(签名/返回/错误码/**数据投影·序列化**) · 跨模块 · 引入新抽象/依赖/模式 · 影响数据模型/迁移 · 长期不可逆设计决策 |
| 走法 | 文档/配置类自动放行；源码 mini 先 `/opsx-mini "<理由+范围>"` 留痕 | `/opsx-propose`（或 `/opsx-new`）建五工件 → `/opsx-apply` |

> **判据来源**：本表由 schema README 的 "Good fit / Not a good fit" 与下方旧「何时不用」固化而来，不另造词。

### 门禁怎么放行

`intent-gate.py` 拦 `Write|Edit`，命中任一即放行，否则 DENY 并回灌指引：

1. 项目无 `openspec/` → 放行（非 intent-driven 项目，门禁 no-op）
2. 目标命中豁免名单：文档（`*.md`/`*.rst`/`*.txt`）、`openspec/**`、`.claude/**`、`docs/**`、生成式 lockfile/清单（`*.lock`/`package-lock.json`/`pnpm-lock.yaml`/`go.sum`）。**通用 `*.json`/`*.yaml`/`*.toml`/`*.ini` 不再整类豁免**——它们可能是中级+ 的 CI/k8s/IaC/schema/app 配置改动，受门禁；确属 mini 走 `/opsx-mini`（`openspec/`、`.claude/` 内的配置仍按目录豁免）
3. 存在某个非 archive change 且其 `tasks.md` **仍有未勾选 `- [ ]`**（实现进行中）——全勾选（应归档）或无 checkbox 不再放行，避免「一个没归档的旧 change 永久放行后续所有源码写入」
4. `openspec/.mini-active` 有效（24h 内）且其 `scope` 覆盖该文件

配套提醒 `intent-reminder.py`（UserPromptSubmit）在每个任务开头注入本 rubric。

### 写入后的两道 lint（PostToolUse）

`intent-gate` 管「能不能写」，写完之后还有两道机械门禁，各守一个常驻上下文载体：

| lint | 守什么 | 拦什么 |
| --- | --- | --- |
| `claudemd-lint` | 仓库内的 `CLAUDE.md` | 字节预算 / 单行长度 / 悬空指针 / `@` 误用 |
| `memory-lint` | `~/.claude/projects/<slug>/memory/` | 索引↔文件双向闭合（悬空指针 · 孤儿）· 状态漂移 · 索引行长与常驻预算 |

memory 的加载条件是**索引每会话必付、正文按需 recall**，所以索引失真的代价与 `CLAUDE.md` 失真同级——而它此前完全没有守护。典型失效是 change 推进后 memory 文件改名，索引却没跟着改：指针悬空、新文件成孤儿、索引还在宣称一个早已过时的状态。跨几十个会话累积、由 agent 自动写入，人眼守不住。

两者都 **fail-open**：任何内部异常一律放行，坏门禁不能锁死编辑。没有 memory 目录的项目零输出、零影响。

### ⚠ plan mode 不等于工作流

原生 plan mode 产出的 markdown plan + `ExitPlanMode` 审批，**不满足**中级+ 的工件要求。
approve 一份 plan ≠ 建了 `proposal→specs→design→adr→tasks`。plan 是临时的、不归档、不可追溯；
五工件是持久、可审计、可归档的。**别让「规划过了」的错觉吞掉真正的工作流。**

### 反面教材（真实复盘）

> 「新增 a320 能力 + 动 RawParam 投影」被误判为「加性 non-breaking，可直接做」，于是切进 plan mode、
> approve 一份 markdown plan 后直接 TDD 实现，5 工件一个没建。
> 实则它同时命中两条中级+ 触发器——**新 capability + 改数据投影契约**——本该 `/opsx-propose`，
> 由 design 阶段把投影的架构决策摆出来给人审，而不是在代码里默默定掉。

### 何时整套都不用

- 纯文档单改、依赖升级、临时 hotfix：太重，commit message 就够（= mini，走 `/opsx-mini` 或直接改豁免路径）
- 行为驱动但不涉及架构决策：考虑用 `behaviour-driven` schema 替代
- 内部脚本 / 玩具项目：YAGNI

参考：[schema 仓库](https://github.com/intent-driven-dev/openspec-schemas) 还提供 `spec-driven`、`behaviour-driven` 等更轻量 schema。
