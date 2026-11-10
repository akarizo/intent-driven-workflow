## ADDED Requirements

### Requirement: 会话 /goal 生效即为人类持续授权起飞
会话转录主链上最后一条 `goal_status` 附件的 `met` 为 false 时，起飞门禁 SHALL 判批准成立并豁免新鲜度，证据 SHALL 写明 goal 设立时间与 `/goal <条件摘要>`；goal 达成或被清除（最后一条 `met` 为 true）后，门禁 MUST 回到原有的人类消息 + 新鲜度判据。
Feature: /goal 是人亲手交出的授权，门禁不再要人重复回「起飞」
Rule: 只认 CLI 写下的主链 goal_status 附件，不认模型文本，不认子 agent 转录

#### Scenario: goal-active-approves-without-approval-word
- **GIVEN** 一份转录：人类只发过长指令（无 `/opsx-apply`、无短批准词），随后有一条 `goal_status` 附件（`met: false`、`sentinel: true`、条件为一段超过 40 字的长句），计划工件早于它
- **WHEN** 运行 `python3 .claude/hooks/takeoff-gate.py --change-dir <dir> --session <转录>`
- **THEN** 退出码为 0
- **AND** stdout 的证据行含 goal 设立时间，且摘要以 `/goal` 开头

#### Scenario: goal-active-waives-freshness
- **GIVEN** 人类 15:18 回过「起飞 授权提交」，16:01 设立 goal，此后又有一条 `met: false` 的评估附件；计划工件在 16:47 又被改过（晚于批准与 goal 设立）
- **WHEN** 分别以 CLI 模式与 hook 模式（`Agent` 派 `slice-executor`，prompt 指向该 change）判定
- **THEN** CLI 退出码为 0，证据摘要以 `/goal` 开头
- **AND** hook 静默放行（无输出、退出码 0），不再报「批准已过期」

#### Scenario: goal-ended-restores-freshness
- **GIVEN** 与上一场景相同的转录与计划 mtime
- **WHEN** 在转录末尾追加一条 `met: true` 的 `goal_status`（分别用「评估达成」形状与 `/goal clear` 形状 `met: true, sentinel: true`）后再判定
- **THEN** 追加之前放行；追加之后 CLI 非 0 退出，stderr 含「重新批准」
- **AND** 两种结束形状结论相同

#### Scenario: goal-sidechain-ignored
- **GIVEN** 两份转录，只差一处：同一条 `met: false` 的 `goal_status` 附件，一份在主链，一份标着 `isSidechain: true`；两份都没有人类批准
- **WHEN** 分别判定
- **THEN** 主链那份退出码为 0
- **AND** sidechain 那份非 0 退出——子 agent 转录里的 goal 不代表主会话授权

### Requirement: 人类中途插话按人类消息判定
转录里 `origin.kind` 为 `human` 且 `commandMode` 为 `prompt` 的 `queued_command` 附件 SHALL 按人类消息参与批准判定（同一批准词与新鲜度规则）；其他来源（`peer` · `task-notification` · `coordinator` · `auto-continuation`）的 `queued_command` MUST NOT 构成批准。
Feature: 人在模型干活时插一句「起飞」，当场就算数
Rule: 白名单只放行 human，其他会话发来的消息是模型，不是人

#### Scenario: queued-command-counts-only-human-origin
- **GIVEN** 计划工件 00:41 改过；转录里没有晚于它的 `user` 行，只有一条 00:42 的 `queued_command` 附件（`prompt: 起飞`）
- **WHEN** 附件 `origin.kind` 为 `human`、`commandMode` 为 `prompt` 时判定；再把同一附件的 `origin.kind` 分别换成 `peer` · `task-notification` · `coordinator` · `auto-continuation` 判定
- **THEN** human 那份退出码为 0，证据含 00:42 时间与「起飞」
- **AND** 其余四份都非 0 退出

### Requirement: goal 生效时规划收尾不交接、起飞自检写明 goal 证据
`/opsx-propose` 与 `openspec-propose` 的收尾 SHALL 先跑 `takeoff-gate.py --change-dir`，证据为 `/goal` 时不硬交接，等 baseline 报告后单独 commit 计划工件并直接按 `/opsx-apply` 流程起飞；否则 MUST 保留原有硬交接。`/opsx-apply` 与 `openspec-apply-change` 的 step 0、铁律 7 及说明文档 SHALL 写明会话 `/goal` 生效是人类持续授权、豁免新鲜度。
Feature: 文档与门禁同一口径，模型不在 goal 下停下等人
Rule: 走哪条分支由脚本判，不由模型判；命令与同名 skill 同改

#### Scenario: propose-continues-under-goal
- **GIVEN** `template/.claude/commands/opsx-propose.md` 与 `template/.claude/skills/openspec-propose/SKILL.md`
- **WHEN** 阅读两者 step 6「收尾」
- **THEN** 都写明先跑 `takeoff-gate.py --change-dir`，证据为 `/goal` 时「不硬交接」，等 baseline 报告后把计划工件单独 commit，再按 `/opsx-apply` 起飞
- **AND** 原硬交接措辞（「本命令到此结束」/「本 skill 到此结束」、spec.html 绝对路径）仍在

#### Scenario: apply-and-iron-rule-name-goal
- **GIVEN** `opsx-apply.md` 与 `openspec-apply-change/SKILL.md` 的 step 0、根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet` 的铁律 7、`README.md` 与 `docs/WORKFLOW_zh.md`
- **WHEN** 逐一阅读
- **THEN** 两处 step 0 都写明 exit 0 的证据可以来自会话 `/goal`
- **AND** 两处铁律 7 都写明 `/goal` 生效即人类持续授权；根 `CLAUDE.md` 的铁律 7 同时保留「新鲜度」并写明 goal 豁免它
- **AND** `README.md` 与 `docs/WORKFLOW_zh.md` 都提到 `/goal`
