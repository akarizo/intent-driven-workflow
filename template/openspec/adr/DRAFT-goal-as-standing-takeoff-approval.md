# DRAFT. 会话 /goal 生效即人类持续授权起飞，人类插话附件也是人类消息

- Status: accepted, supersedes ADR-DRAFT-gate-evidence-not-self-reported（仅决策 4）
- Date: 2026-11-10
- Supersedes: ADR-DRAFT-gate-evidence-not-self-reported（仅决策 4；决策 1–3 在役）
- 来源 change：goal-authorized-takeoff（design D1–D6）

## Context

`ADR-DRAFT-gate-evidence-not-self-reported` 的决策 4 规定：人类审批的证据是转录里 `type: "user"` 的人类消息，且必须晚于被批准物的最后一次改动。

2026-11-09 至 11-10，afa 仓库 change `tko-ldg-ralt-plus-ground`（转录 `d2d21d53`）暴露出这条规则的两个缺口：

1. **不认 `/goal`**：人类用 `/goal` 交代「后续修订按你推荐的选，一切稳妥后 pr-ship」，之后不再介入。模型按 goal 三次修订计划，每次修订都让此前的批准「过期」，门禁拦停了三次。goal 的 Stop hook 又不断判「未达成」，空转了十几轮评估，人类只能反复回「起飞」。`/goal` 只能由人在 CLI 输入，CLI 会在转录里写下结构化的 `goal_status` 附件，但它不是 `type: "user"` 行，所以不被承认。
2. **不认插话**：人类在模型工作中途发的「起飞」，被 CLI 记成 `queued_command` 附件（`origin.kind: human`），没有对应的 `user` 行，门禁也不承认。

决策 1–3 不受影响：真值源只认转录 / 文件系统 / git / hook 留痕，强制点放在 hook，判不出 fail-closed、异常 fail-open。本 ADR 只重写决策 4。

## Decision

决策 4 改为下面三条：

1. **人类消息的来源有两种**：
   - `type: "user"` 行，判法同原决策 4；
   - `queued_command` 附件，要求 `origin.kind == "human"` 且 `commandMode == "prompt"`。

   其余 `origin`（`peer` · `task-notification` · `coordinator` · `auto-continuation` 等）都不是人。其中 `peer` 来自其他模型会话，认了就等于模型自证。
2. **人类批准分两种**：
   - **一次性批准**：人类消息里有 `/opsx-apply`，或是短批准词。它必须晚于计划工件的最后一次改动（新鲜度）。
   - **持续授权**：会话 `/goal` 生效，即转录主链上按文件顺序最后一条 `goal_status` 附件的 `met` 为 false。生效期间批准成立，豁免新鲜度。goal 达成或被清除（最后一条 `met` 为 true）后，持续授权立即失效。
3. **判定顺序与证据**：持续授权优先。证据行写明 goal 设立时间与 `/goal <条件摘要>`，进入 approve 事件与 `.flight`，供 PR review 追溯。

## Consequences

- **更易**：`/goal` 成为真正的无人值守模式。goal 期间修订计划、新开 change 都不再停下等人，也不会出现 Stop hook 与门禁互相顶牛的空转。
- **更易**：人类插话的批准当场生效。
- **更难 / 代价**：
  - goal 期间，人类不再逐次看到计划修订后的 spec.html。这是用户 2026-11-10 明确接受的取舍。
  - 第二道人类审批（PR review）成为 goal 期间唯一的人工关口。
  - 门禁只认 goal 是否生效，不判断 goal 条件与当前 change 是否相关。
- **依赖**：门禁多依赖两个 Claude Code 转录字段，`goal_status{met, sentinel}` 与 `queued_command{origin.kind, commandMode}`。字段变化时判不出 goal、认不出插话，门禁回到一次性批准与新鲜度判定，方向是 fail-closed。
- **不变**：
  - 没有 goal 时，新鲜度规则不放松；
  - 模型代记的批准事件仍然无效；
  - 不收紧 `user` 行的 `origin`。
