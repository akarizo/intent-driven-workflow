# Gate Report

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-10-15T06:11:29Z | S1 | ok | e0e25f7b11 | - | G5 evidence: 未见 RED 先于 GREEN 的测试运行记录 |
| 2026-10-15T06:11:30Z | S4 | ok | ff73630a59 | - | - |
| 2026-10-15T06:18:23Z | S2 | ok | f0ddd0e63d | - | 全量 tests 有 2 条红：tests/test_baseline_skip.py::test_lint_rerun_when_other_change_edited 与 ::test_lint_rerun_when_referenced_plan_file_changed（S3 的 strict xfail 在 base af45af9 上就已 XPASS，与 S2 无关，归 S3 处理） |
| 2026-10-15T06:29:34Z | final | red | d7e2650109 | G7 scenario: baseline-redundant-run-skip#lint-reused-when-tree-unchanged → tests/test_baseline_skip.py::test_lint_reused_when_tree_unchanged 仍标记 xfail/skip; G7 scenario: baseline-redundant-run-skip#lint-rerun-when-other-change-edited → tests/test_baseline_skip.py::test_lint_rerun_when_other_change_edited 仍标记 xfail/skip; G7 scenario: baseline-redundant-run-skip#lint-rerun-when-referenced-plan-file-changed → tests/test_baseline_skip.py::test_lint_rerun_when_referenced_plan_file_changed 仍标记 xfail/skip; G7 scenario: baseline-redundant-run-skip#verify-derived-from-full-suite → tests/test_baseline_skip.py::test_verify_derived_from_full_suite 仍标记 xfail/skip | G2 全量未跑：G7 已红，scenario 全绿后重跑 final |
| 2026-10-15T06:37:31Z | S3 | ok | 5bf21144db | - | G5 evidence: 未见 RED 先于 GREEN 的测试运行记录 |
| 2026-10-15T06:42:39Z | final | ok | c8132ed81b | - | - |
