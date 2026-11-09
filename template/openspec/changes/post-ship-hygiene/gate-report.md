# Gate Report

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-11-09T03:12:05Z | S1 | ok | 6e340eb891 | - | - |
| 2026-11-09T03:12:05Z | S3 | ok | 99e59c9c10 | - | - |
| 2026-11-09T03:31:52Z | final | red | a7a8a2219c | G7 scenario: clean-after-merged-command#command-runs-plan-then-apply → tests/test_clean_after_merged_docs.py::test_command_runs_plan_then_apply 实际结果 XFAIL（未真正通过）; G7 scenario: clean-after-merged-command#iron-rule-grants-cleanup-exception → tests/test_clean_after_merged_docs.py::test_iron_rule_grants_cleanup_exception 实际结果 XFAIL（未真正通过）; G7 scenario: clean-after-merged-command#git-discipline-points-to-command → tests/test_clean_after_merged_docs.py::test_git_discipline_points_to_command 实际结果 XFAIL（未真正通过）; G7 scenario: clean-after-merged-command#docs-list-new-command → tests/test_clean_after_merged_docs.py::test_docs_list_new_command 实际结果 XFAIL（未真正通过）; G7 scenario: clean-after-merged-command#readme-describes-auto-sedimentation → tests/test_clean_after_merged_docs.py::test_readme_describes_auto_sedimentation 实际结果 XFAIL（未真正通过） | G2 全量未跑：G7 已红，scenario 全绿后重跑 final |
