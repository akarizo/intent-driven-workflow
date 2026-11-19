# 起飞前 change 分支落后 main，没有机械检查

**现象（2026-11-19 test-audit）**：工件写在 780a686 上。起飞时 main 已合入 #23（0b80797），改了 `opsx-apply.js`、`agents/slice-executor.md`、`agents/integrator.md`、`slice-gate.py`，还和本 change 的 owns 在 `README.md`、`flight-runner-contract.md` 上重叠。
在旧基点上起飞，会用旧的飞行机制跑；预合并 main 的冲突也要拖到 `/pr-ship` step 4 才暴露。这次是主会话在 git 纪律检查时顺手看了 `git log HEAD..main` 才发现的，没有任何脚本报出来：takeoff-gate、lint、preflight 全绿。
用户选择先并入 main，再重跑 baseline。基线因此过期，补了一次全量，用时 470.6 秒（`flight-doctor.py cost` 把它归为「可避免」）。

**证据**：`template/openspec/changes/test-audit/timeline.md` 中 `2026-11-19T02:15:54Z baseline … 全量：有非测试文件改动：README.md … opsx-apply.md …`。

**可选防线**：
- `preflight` 或 `opsx-apply` step 2 比对 `merge-base HEAD main` 与 `main`。落后时报 warning，点名落后提交里改了的 `template/.claude/{workflows,agents,hooks}` 与 owns 交集；只提示，不阻断。
- `/opsx-propose` 收尾提交工件前先并入 main，再跑 baseline，免得起飞前补一次全量。
