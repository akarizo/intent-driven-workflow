# Gate Report

## 天花板

| 时间 | 切片 | 位置 | 限制 | 升级路径 |
|---|---|---|---|---|
| 2026-10-28T08:59:36Z | S1 | template/.claude/hooks/slice-gate.py:455 | 逐测试文件 BFS 求闭包，O(测试文件 × 模块) | 大仓收口变慢时改为 SCC 缩点后自底向上合并 |

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-10-28T08:59:36Z | S1 | ok | b659a7110f | - | - |
| 2026-10-28T09:15:37Z | S2 | ok | 216050471f | - | owns 之外的既有测试 tests/test_gate_checks_baseline.py::test_no_checks_behavior_unchanged 现在会失败：它断言 final JSON 的键是 {slice, ok, commit, failed, warnings, scenarios, summary, dirty} 的子集，而 spec 要求 final 输出带 `incremental`。所需修复只有一行（把 "incremental" 加进允许集合），但该文件不在任何切片的 owns 内，所以没有提交；需要由主会话处理。全量 `python3 -m pytest -q tests` 去掉这一条后：376 passed，7 xfailed。; 有分层时 S2 恒走全量（full_why「有测试分层（分层增量尚未支持）」），没有按切片包第 10 步走增量：只用 _pytest_outcomes 跑增量会丢掉 G10/G11 探针，tests/test_tiers_gate.py::test_final_red_on_new_impure_unit_test 会变红，test_final_diffs_regions_against_baseline 也会因为把区域文件放进单元层重跑而变红。这条规则单独放在 cmd_final 的 `if why is None and tiers is not None` 里，S3 加上 probe_out 后删掉这一行即可。 |
| 2026-10-28T09:25:38Z | S3 | ok | f6eed4b5a5 | - | owns 之外的既有测试 tests/test_gate_checks_baseline.py::test_no_checks_behavior_unchanged 仍失败（S2 已申报的问题：允许集合缺 incremental，需主会话处理）；全量 python3 -m pytest -q tests 的其余结果：381 passed，2 xfailed; gate.impacted 与分层同时配置时，增量路径不挂单元层探针（记 warning「G10/G11 未判」），已选区域全部运行 |
