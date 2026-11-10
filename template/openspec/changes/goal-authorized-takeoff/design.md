## Context

**现状**：`takeoff-gate.py` 的批准判据（mechanical-takeoff-gates，design D7 / D8）如下：

- **人类消息**：`type == "user"`，非 meta、非 sidechain，`userType` 为 external，内容是文本。
- **批准**：消息里有 `<command-name>/opsx-apply`，或整条不超过 40 字且含批准词。
- **新鲜度**：批准时间 ≥ 计划工件的最大 mtime。

这三条由 `verdict()` 统一判定，CLI 模式（`/opsx-apply` step 0）与 PreToolUse hook 模式（拦 `Workflow` / `Agent` / `Task` 起飞派发）共用。

**实测形状**：2026-11-10 从 7 份真实转录里提取了 `/goal` 事件与插话事件的形状（Claude Code v2.1.319）。

`goal_status` 附件（`type == "attachment"`、`attachment.type == "goal_status"`）：

| 事件 | 附件字段 | 出处 |
|---|---|---|
| `/goal <条件>` 设立（空闲时或工作中途） | `met: false, sentinel: true, condition` | afa `d2d21d53` 第 3087 行 · stc-foundation `6408285e` 第 1395 行 |
| Stop 评估未达成 | `met: false, condition, reason` | afa `d2d21d53` 多处 |
| 评估达成（自动清除） | `met: true, condition, reason, iterations, …` | stc-foundation `6408285e` 第 2142 行 |
| `/goal clear` | `met: true, sentinel: true, condition` | stc-foundation `fe89e6cc` 第 2908 行 · intent-driven-claude-code `b78eba23` 第 4990 行 |
| 连续未达成后暂停 | 不新增附件，只有一条 system「Goal paused · … send a message to continue」 | stc-foundation `fe89e6cc` 第 2906 行 |

`queued_command` 附件，即模型工作中途进来的消息。按 `origin.kind` 统计约 1300 条：

| `origin.kind` | 内容 | 是否人打的字 |
|---|---|---|
| `human`（`commandMode: prompt` · `humanTurn: true`） | 人类插话，如 afa 00:42 的「起飞」 | 是 |
| `task-notification` | 后台任务通知 | 否 |
| `coordinator` | Workflow 协调者续派 | 否 |
| `auto-continuation` | 「Goal set: …」回显 | 否（由 `/goal` 派生） |
| `peer` | 其他 Claude 会话经 SendMessage 发来 | 否，是**模型** |

afa 00:42 的「起飞」只留下了 `queued_command` 附件和一条 `queue-operation remove`（`absorbed_mid_turn`），没有对应的 `user` 行。

**约束**：在役 `ADR-DRAFT-gate-evidence-not-self-reported` 的决策 4 规定，人类审批证据 = `type: "user"` 行 + 晚于被批准物。本设计偏离了这两点，见 Open Questions，由新 ADR 部分取代。

**用户决策**（2026-11-10，AskUserQuestion）：

- **豁免范围**：goal 生效即放行。
- **附带修复**：中途插话也算人类消息。
- **不收紧**：非人类 `origin` 的 `user` 行，本次不收紧。

```
C4 · 容器图（轻量 C4 风格；★ 新增判据，◆ 修改）

 [人类] ──/goal <条件>──────────┐
 [人类] ──起飞 / /opsx-apply────┤ Claude Code CLI 写入
 [人类] ──工作中途插话──────────┤
 [其他会话 / 后台任务]──────────┘（peer · task-notification · coordinator：不是人）
                                 ▼
          [会话转录 ~/.claude/projects/*/<sid>.jsonl]
           · user 行（type=user）
           · ★ attachment: goal_status{met, sentinel, condition}
           · ★ attachment: queued_command{origin.kind, commandMode, prompt}
                                 │ 只读
                                 ▼
          ◆ takeoff-gate.py · verdict()
             ① ★ goal 生效？→ 放行（证据 /goal …，豁免新鲜度）
             ② 人类消息（user 行 + ★ human 插话）里找批准 → 新鲜度判定
                 ▲ CLI 模式                    ▲ hook 模式
                 │                              │
   ◆ /opsx-apply step 0 自检        [PreToolUse: Workflow | Agent | Task 起飞派发]
   ◆ /opsx-propose step 6：exit 0 且证据为 /goal → 不交接，等 baseline → commit 工件 → 起飞
```

**图例与说明**：

- **边界**：门禁只读转录与计划工件 mtime，不写任何文件。goal 状态只信 CLI 写下的附件，不信模型文本。
- **判定顺序**：goal 优先。goal 生效时不再看批准词与新鲜度；goal 结束后，第 ② 步与现状完全一致，只是人类消息多了一个来源。
- **假设**：`/goal` 只能由人在 CLI 输入，模型没有对应的工具。`goal_status` 附件由 CLI 写入，不经过模型输出。

## Goals / Non-Goals

**Goals:**
- `/goal` 生效期间，起飞门禁零拦截，包括计划修订之后、以及 goal 期间新 propose 的 change。复现 afa 那三次被拦的场景，全部放行。
- goal 达成或 `/goal clear` 之后，判据与现状完全一致。
- 人类在模型工作中途发出的批准当场有效，不必再发一次。
- 证据可追溯：goal 放行的证据行写进 approve 事件与 `.flight`，PR review 时看得到授权来自哪条 goal。

**Non-Goals:**
- 不改 PR review 这道人类审批（铁律 4 / 7 第二处）。
- 不收紧 `user` 行的 `origin`。auto-continuation 的「Goal set: 短条件」仍可能被当成口头批准，与本设计方向一致，不冲突。
- 不判断 goal 条件的语义是否与当前 change 有关，生效即放行（用户决定）。
- 不处理跨会话（`--resume` 新文件）的 goal 继承。看不到附件就按原判据处理。
- 不改 `/pr-ship` 及 apply 的其他暂停点。

## Decisions

**D1 · goal 是否生效：按文件顺序取最后一条主链 `goal_status`，`met is False` 即生效。**
- **理由**：转录是追加写入的，文件顺序就是事件顺序。附件是 CLI 写下的结构化字段，模型无法通过输出产生它。
- **备选（否）**：
  - 按时间戳排序：同一毫秒有多条附件，compact 续写后时间戳会交错。
  - 认 isMeta 文本「A session-scoped Stop hook is now active…」：它是注入文本，措辞随版本变化。
  - 认 `queue-operation` 的「Goal set:」：这类行没有 `origin`，还混着 task-notification。
- **sidechain 一律忽略**：子 agent 转录里的同名附件不代表主会话的状态。

**D2 · goal 生效即放行，豁免新鲜度（用户决策）。**
- **证据时间**：取最近一次设立的时间，即 `sentinel: true` 且 `met: false` 的那条。转录被截断、找不到设立行时，退用最后一条 `goal_status` 的时间。
- **证据摘要**：`/goal <条件>`，沿用 `summarize()` 的 40 字截断。
- **备选（否）**：只豁免新鲜度，要求该 change 至少有过一次人类批准。用户否决：goal 本身就是授权，goal 期间新开的 change 也不该停下。

**D3 · goal 判定优先于人类消息。**
- **理由**：goal 生效时直接返回 goal 证据，证据唯一，飞行记录一眼可读。
- **备选（否）**：两者取较新的那条。没有收益，还会让证据在「起飞」和「/goal」之间来回跳。

**D4 · 中途插话认人类：白名单 `origin.kind == "human"` 且 `commandMode == "prompt"`。**
- **取文本**：`prompt` 是字符串时直接用；是文本块列表时拼接，含非文本块就整条不算。
- **复用现有判据**：沿用 `NON_HUMAN_MARKERS`、`approval_of()` 与新鲜度规则。时间戳取行的 `timestamp`，缺失时取附件内的 `timestamp`。
- **为什么用白名单**：`peer` 来自其他 Claude 会话，本质是模型。认了它就等于模型自证批准，正是在役 ADR 要防的事。
- **重复不碍事**：同一插话之后若又落成 `user` 行，会被算两次，取最新一条，没有副作用。

**D5 · 不收紧 `user` 行 `origin`（用户决策）。** 现有判据只会多一个来源，不会少。

**D6 · propose 收尾的分支由脚本判定（铁律 9）。**
- **判定方式**：step 6 先跑 `takeoff-gate.py --change-dir`。exit 0 且 stdout 证据在 ` · ` 之后以 `/goal` 开头，就走 goal 分支；否则照旧硬交接，原措辞保留。模型不自行判断 goal 状态。
- **goal 分支的动作**：等 baseline 报告一行（preflight 会拒绝仍在跑的基线），计划工件单独 commit，再按 `/opsx-apply <name>` 的流程起飞。
- **commit 的授权依据**：goal 生效即放行（D2），goal 就是人类对「自主推进到收口」的授权。artifacts-only commit 是 apply step 2 的前置条件，不属于越权。
- **备选（否）**：只改门禁、propose 仍硬交接。goal 的 Stop hook 会一直推模型往前走，但文档又说「不得在同一轮继续」，两相冲突，正是 afa 那种空转。

**D7 · apply step 0 与铁律文本只补一句「证据也可来自会话 `/goal`」。** 流程不变，exit ≠ 0 时照旧停下。

## Risks / Trade-offs

- **[goal 条件与当前 change 无关也放行]** → 这是用户接受的取舍。缓解有三：goal 达成或 clear 后恢复原规则；证据行写明 `/goal <条件>` 并进入 approve 事件与 `.flight`；PR review 这道人类审批仍在。
- **[Claude Code 改了附件字段名或语义]** → goal 判不出，门禁回到原判据，结果是拦下而不是放行，属于 fail-closed，方向安全。测试用真实形状作夹具，字段漂移时能在升级后的实测里暴露。
- **[`--resume` 或 fork 出新转录文件，看不到旧的 goal 附件]** → 同上，回到原判据，最坏情况是像今天这样再问一次人。
- **[模型用 Bash 改写转录、伪造附件]** → 威胁等同于伪造 `user` 行，不在本门禁的防御范围内。在役 ADR 已接受「转录是真值源」。
- **[goal 暂停（Goal paused）期间仍算生效]** → 暂停时没有清除事件，goal 仍是人类设下的状态。人类发消息即可续跑，或 `/goal clear` 结束。
- **[插话的批准词判定沿用 40 字短句规则]** → 长插话里带「起飞」不算批准，与现状一致，不放宽。

## Migration Plan

- **部署**：合并后，下游仓库执行 `./install.sh --upgrade`，刷新 `.claude/hooks/takeoff-gate.py` 与命令 / skill 文本。
- **兼容**：旧转录没有 `goal_status` 和 `queued_command` 附件，判据与现状完全一致。
- **回滚**：revert `takeoff-gate.py` 与文档即可，没有数据迁移。

## Open Questions

- **在役 `ADR-DRAFT-gate-evidence-not-self-reported` 的决策 4 需要部分取代**。决策 4 把人类审批证据限定为 `type: "user"` 行，且必须晚于被批准物；本设计新增两类证据：
  - goal 附件，并豁免新鲜度；
  - human 插话附件。

  按 ADR 不可改的规则，新增 `DRAFT-goal-as-standing-takeoff-approval.md`，只取代决策 4。决策 1–3 继续在役：真值源四类、强制点在 hook、判不出 fail-closed / 异常 fail-open。
