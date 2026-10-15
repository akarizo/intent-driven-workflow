# Gate Report

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-10-15T06:11:29Z | S1 | ok | e0e25f7b11 | - | G5 evidence: 未见 RED 先于 GREEN 的测试运行记录 |
| 2026-10-15T06:11:30Z | S4 | ok | ff73630a59 | - | - |
| 2026-10-15T06:18:23Z | S2 | ok | f0ddd0e63d | - | 全量 tests 有 2 条红：tests/test_baseline_skip.py::test_lint_rerun_when_other_change_edited 与 ::test_lint_rerun_when_referenced_plan_file_changed（S3 的 strict xfail 在 base af45af9 上就已 XPASS，与 S2 无关，归 S3 处理） |
