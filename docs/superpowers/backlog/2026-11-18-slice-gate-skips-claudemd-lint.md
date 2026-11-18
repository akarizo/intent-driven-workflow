# backlog · 切片门禁不跑 claudemd-lint，CLAUDE.md 超限漏到 pr-ship（2026-11-18）

## 现象（本轮 1 次，未达 E 类门槛）

change `slice-resume-deterministic` 的 S5 给根 `CLAUDE.md` 铁律 6 加了「切片临时 worktree 回收」例外，单行从 379B 涨到 534B，超过 `claudemd-lint.py` 的 400B ERROR 线。S5 门禁、final 全绿（`gate.lint` 只是 `compileall`），直到 `/pr-ship` step 2 的 CLAUDE.md 检查才拦下，飞行停在 PR 之前，需要人工改写（`23cb00a` 拆出「命令即授权」子条）。

证据：`template/openspec/changes/slice-resume-deterministic/gate-report.md` S5 行 ok；`23cb00a`。

## 防线（Q4 ✓：可机械判定）

`slice-gate.py gate` 在切片 diff 含 `CLAUDE.md` / `*.snippet` 时追加跑 `claudemd-lint.py`（ERROR 记 G1 或新 gate 项），让超限在切片内就红、由执行体当场改，而不是漏到收口。

## 落地后

无需常驻条目；门禁本身即防线。
