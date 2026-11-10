## Why

`/goal` 是人类交给会话的持续授权，但起飞门禁（`takeoff-gate.py`）不认它。2026-11-09 至 11-10，afa 仓库 change `tko-ldg-ralt-plus-ground`（转录 `d2d21d53`）实测：

- **11-09 16:01**：人类发出 `/goal`，条件是「后续的修订都按你推荐选择最优选择推荐，继续完成……一切稳妥后 pr-ship……直到逻辑可靠」。
- **三次被拦**：模型按 goal 去 UAT 实测，先后三次修订计划（S6 / S7 / S8）。每次计划工件一改，此前的人类批准就「过期」，门禁要人再回「起飞」：
  - 16:47 被拦，人类 22:59 回「起飞」；
  - 23:57 被拦，人类 23:58 回「起飞」；
  - 00:42 被拦，人类 00:45 回「起飞」。
- **空转**：16:47 被拦后，goal 的 Stop hook 一直判「未达成」。17:36 前后 70 秒内连续空转 16 轮评估，最后进入「Goal paused」。
- **插话漏判**：00:42 人类在模型工作中途发了一句「起飞」。Claude Code 把它记成 `queued_command` 附件，不是 `user` 行，门禁没认，人类 00:45 只好再发一次。

根因：

1. **门禁不认 goal**：批准只认 `user` 行里的 `/opsx-apply`，或不超过 40 字、含批准词的短句。goal 记在 `goal_status` 附件里，条件通常远超 40 字。新鲜度规则对 goal 期间的计划修订照样生效。另一个仓库里，「Goal set: 没问题就起飞，快速交付」这种短条件因为恰好不超过 40 字、又含「起飞」，被当成口头批准放行了。所以 goal 是否放行取决于条件写多长，用户看到的行为前后不一致。
2. **只看 `user` 行**：人类在模型工作中途发的消息被记成附件，门禁看不到。

## What Changes

- **门禁认 goal**：`takeoff-gate.py` 新增判据「会话 goal 生效」。
  - **生效**：转录主链（非 sidechain）里，按文件顺序取最后一条 `goal_status` 附件，它的 `met` 为 false。
  - **生效时**：批准成立，并豁免新鲜度。证据行为 `<goal 设立时间> · /goal <条件摘要>`。
  - **结束后**：`met` 为 true（条件达成后自动清除，或人类执行 `/goal clear`），回到原判据。
  - CLI 模式与 PreToolUse hook 模式用同一套判据。
- **中途插话也算人类消息**：`queued_command` 附件满足 `origin.kind == "human"` 且 `commandMode == "prompt"` 时，按人类消息判定，同样套用批准词与新鲜度。其他来源一律不算，包括 `peer`（其他会话）、`task-notification`、`coordinator`、`auto-continuation`。
- **propose 收尾**（`/opsx-propose` 与 `openspec-propose` 同改）：先跑 `takeoff-gate.py --change-dir`。
  - 证据以 `/goal` 开头：不硬交接。等 baseline 报告一行，把计划工件单独 commit，然后直接按 `/opsx-apply` 流程起飞。
  - 其他情况：照旧硬交接。
- **apply step 0**（`/opsx-apply` 与 `openspec-apply-change` 同改）：写明 exit 0 的证据也可以来自会话 `/goal`。
- **铁律 7 与说明文档**：根 `CLAUDE.md`、`template/CLAUDE.md.snippet`、`README.md`、`docs/WORKFLOW_zh.md` 写明「`/goal` 生效 = 人类持续授权，豁免新鲜度」。
- **新 ADR**：部分取代 `ADR-DRAFT-gate-evidence-not-self-reported` 的决策 4。
- **不改**：
  - PR review 这道人类审批；
  - 没有 goal 时的新鲜度规则；
  - `user` 行的来源判定（不收紧 `origin`，用户 2026-11-10 决定）。

## Capabilities

### New Capabilities

- `goal-takeoff-authorization`：会话 `/goal` 生效即人类持续授权起飞（豁免新鲜度）；人类中途插话按人类消息判定；propose 收尾与 apply 自检在 goal 生效时不交接给人。

### Modified Capabilities

- 无。`takeoff-approval`（change `mechanical-takeoff-gates`）没有主 spec（`openspec/specs/` 不存在），它原有的需求保持不变，本 change 的行为增量以 ADDED 写在新 capability 里。

## Impact

- **代码**：`template/.claude/hooks/takeoff-gate.py`。
- **文档**：
  - `template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md`；
  - `template/.claude/commands/opsx-apply.md`、`template/.claude/skills/openspec-apply-change/SKILL.md`；
  - `CLAUDE.md`、`template/CLAUDE.md.snippet`、`README.md`、`docs/WORKFLOW_zh.md`。
- **ADR**：新增 `template/openspec/adr/DRAFT-goal-as-standing-takeoff-approval.md`。
- **测试**：新增 `tests/test_goal_takeoff.py`、`tests/test_goal_takeoff_docs.py`。现有 `tests/test_approval_gate.py` 不改，须保持绿。
- **下游**：afa 等已安装的仓库要跑 `./install.sh --upgrade` 才能拿到新门禁。
- **外部依赖**：依赖 Claude Code 转录字段，已在 v2.1.319 实测：
  - `goal_status{met, sentinel, condition}`；
  - `queued_command{origin.kind, commandMode, prompt}`。

  字段一旦变化，goal 就判不出来，门禁回到原判据，结果是拦下而不是放行。
