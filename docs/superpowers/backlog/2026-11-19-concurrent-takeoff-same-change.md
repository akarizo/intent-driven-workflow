# backlog · 同一 change 两个会话同时起飞，没有任何互斥（2026-11-19）

## 现象（观察到的偏差，1 次）

change `wave-integration-guard`（2026-11-18）：会话 A 12:06 起飞（Workflow `wf_f94c474f-e91`），会话 B 12:28 在同一 worktree 再次起飞（`timeline.md` 第二条 `approve`，备注「重新起飞」）。B 把 A 当成已中断，其实 A 仍在跑：

- wave 2：A 的 S2（`23f94ee`）先合回，B 的 S2 晚到冲突，记 `blocked wave2 infra`。
- wave 3：B 的 S3/S5/S7（`b5d6709` / `d47925b` / `405bb6c`）先合回；A 的 wave 3 执行体白跑一遍，合回冲突，记 `blocked wave3 infra`（`review-findings.json`）。
- A 对 S3/S5/S7 的评审审的是没进分支的那份重复实现；两边 final 并行，A 的 final 排队 264.8 秒后放弃等锁。
- `refs/flight/<change>/gate-S3` 被 A 的重复门禁覆盖，B 合回的 `b5d6709` 的门禁 JSON 丢失，只能在该 commit 上重跑门禁补录。

附带（同一次）：B 的 integrator 没有原样转交门禁 JSON，而是在 zsh 里用循环手拼 `record --json`；zsh 对未加引号的 `$pair` 不分词，`$1` 成了 `S3 b5d6709…`、`$2` 为空，`gate-report.md` 三行切片列与 commit 列错位，`ship` 判「切片无门禁记录」。

## 建议

- 起飞互斥：`takeoff-gate.py`（或 step 4 写 `.flight` 时）若 `.flight` 已存在且其工作流仍活跃，拒绝起飞并打印持有方；只有确认原飞行已停（无活跃 Workflow / 超时）才允许覆盖。
- 附带的 `record` 坏行：防线见 `2026-11-18-record-accepts-unknown-slice.md`（本次记为第 2 次）。
