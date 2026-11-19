# backlog · `slice-gate.py record` 收下不存在的切片名，坏行让 ship 判 draft（2026-11-18）

## 现象（本轮 1 次，未达 E 类门槛）

change `tier-budgets` wave 2 的 integrator（sonnet）没有用门禁 JSON 原文，而是在 zsh 里用 `for p in "S3 <sha>" ...; do set -- $p; ... done` 自己拼 JSON。zsh 默认不对未加引号的 `$p` 拆词，`$1` 成了 `"S3 <sha>"`、`$2` 为空。`record` 照单全收、退出 0，gate-report.md 写进三行切片名为 `S3 bf28c50e…`、commit 为空的坏行。收口时 `ship` 判「切片 S3/S4/S5 无门禁记录」→ draft；主会话用工作流返回的门禁 JSON 原文重新 `record` 后转绿。

证据：`template/openspec/changes/tier-budgets/gate-report.md` 11:56:24Z 三行（切片列带 sha、commit 列空）与 12:14:27Z 补记行；integrator 返回的 warnings 含「record 输出的 commit 字段为空串」。

第 2 次（2026-11-18 `wave-integration-guard`）：另一会话的 wave 3 integrator 同样在 zsh 里手拼 `record --json`，gate-report.md 写进 `S3 b5d6709…` / `S5 d47925b…` / `S7 405bb6c…` 三行坏行（timeline 12:46:32Z），ship 判「切片 S3/S5/S7 无门禁记录」；主会话用留存的门禁 JSON（S5/S7）与在合回 commit 上重跑的门禁（S3）补录后转绿（`f15f07a`）。仍不入 CLAUDE.md：ship 会点名，不静默（准入闸门 Q3 ✗）。

## 防线（Q4 ✓：可机械判定）

`cmd_record` 写行前校验：`slice` 必须是 `slices.json` 里的切片 id 或 `fix` / `final`，`commit` 必须是本地存在的 commit（`git cat-file -t`）；不满足 → 非 0 退出并点名字段。integrator 拿到非 0 就会原样上报，坏行不会进 gate-report.md。

## 落地后

无需常驻条目；`record` 自身即防线。
