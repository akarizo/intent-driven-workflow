# Gate Report

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-11-19T02:26:26Z | S1 | ok | 4bc5256804 | - | - |
| 2026-11-19T02:26:26Z | S4 | ok | 09b56a6df4 | - | - |
| 2026-11-19T02:26:26Z | S6 | ok | 88504f279a | - | - |
| 2026-11-19T02:27:25Z | wave | ok | 624e8acf87 | - | - |
| 2026-11-19T02:36:50Z | S2 | ok | fc4c646591 | - | tests/test_audit_docs.py::test_standard_doc_matches_script_constants 现为 XPASS(strict)：S7 的对账骨架因 AUDIT_RULES 已与文档一致而通过，需由 S7 去掉 xfail 标记（该文件不在 S2 owns 内，未改动） |
| 2026-11-19T02:36:51Z | S5 | ok | 4b82b80632 | - | - |
| 2026-11-19T02:38:50Z | wave | ok | f5c00b0d72 | - | - |
| 2026-11-19T02:51:48Z | S3 | ok | 86506c4bc9 | - | 门禁外观察：全量 pytest 中 tests/test_audit_docs.py::test_standard_doc_matches_script_constants 是 S7 骨架，报 XPASS(strict)。它只依赖 AUDIT_RULES / ACTIONS / 文档，S3 没有改这三处，所以是 S2/S5/S6 合回后本来就有的状态，由 S7 解锁时处理 |
| 2026-11-19T02:51:48Z | S7 | ok | 38d62fc2af | - | - |
| 2026-11-19T02:53:56Z | wave | ok | 1676454851 | - | - |
| 2026-11-19T03:09:46Z | final | ok | 485245c4dc | - | - |
| 2026-11-19T03:12:24Z | final | ok | c73f0df51d | - | - |
| 2026-11-19T03:31:21Z | final | ok | f88a8d8d29 | - | - |
