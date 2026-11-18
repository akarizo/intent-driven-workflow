# backlog · 部分切片 blocked 后的补飞没有成文路径（2026-11-18）

## 现象（观察到的偏差，1 次）

change `machine-test-lock` 首飞 S3 因计划漏 owns 被 blocked（S5 / S6 依赖跳过），S1 / S2 / S4 已绿并合回。补计划、重批之后，`/opsx-apply` 与 `openspec-apply-change` skill 都没写「只补飞未完成切片」怎么做。本次的做法是临时的：新开一次 Workflow，`waves: [["S3"],["S5","S6"]]`、`deps` 去掉已绿的依赖；已核实 `slice-gate.py start` 首轮会清掉旧快照、基点取新 HEAD，不会把已合回切片算进越界。

附带：final-gate integrator 已记过 `apply-done`，主会话按 opsx-apply step 6 又记了一次，时间线出现两条 `apply-done`。

## 建议

- opsx-apply 增加 `--only S3,S5,S6`（或按 gate-report 自动取未绿切片）：重算 waves、剔除已绿依赖，其余步骤不变；`.flight` 记 `resumed`。
- 明确 `apply-done` 由谁记（工作流 final 还是主会话 step 6），另一处改成「已有则跳过」。
