<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 + S4（owns 不相交）；wave 2 = S2 + S3（S2 与 S1 同改 `slice-gate.py`；S3 只新增 `test-tiers.py`，两者 owns 不相交）；wave 3 = S5（在 S2 接好的 baseline / final 上加分层耗时报告）。

## 切片

- [x] S1 判定器：分层文件读取与 lint 的 tiers: 规则、plan_sha 追加区域、切片门禁 G12、探针插件与 run_test_gate(probe=True) （deps: - · verify: `python3 -m pytest -q tests/test_tiers_plan.py tests/test_tiers_probe.py tests/test_slice_gate.py tests/test_gate_checks_lint.py tests/test_slice_gate_baseline_preflight.py tests/test_slice_gate_coverage.py`）
- [x] S2 判定器：G10 / G11 纯函数判定与候选重跑，baseline / final / preflight 按分层运行（单元层探针、已选区域差分、不走增量） （deps: S1 · verify: `python3 -m pytest -q tests/test_tiers_verdict.py tests/test_tiers_gate.py tests/test_slice_gate.py tests/test_slice_gate_final.py tests/test_slice_gate_baseline_preflight.py tests/test_baseline_incremental.py tests/test_baseline_pool.py tests/test_baseline_skip.py tests/test_gate_checks_baseline.py tests/test_gate_checks_final.py`）
- [x] S3 脚本：test-tiers.py 的 probe / check / allow-slow / render（复用 slice-gate 与 takeoff-gate 的函数） （deps: S1 · verify: `python3 -m pytest -q tests/test_tiers_cli.py tests/test_approval_gate.py`）
- [x] S4 文档：/test-tiers 命令、schema tasks instruction、propose / verify 命令与同名 skill、TDD skill 先定层、slice-executor、README、install.sh、CLAUDE.md.snippet （deps: - · verify: `python3 -m pytest -q tests/test_tiers_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_gate_checks_docs.py tests/test_baseline_incremental_docs.py tests/test_agents_workflow.py tests/test_install.py`）
- [x] S5 判定器：每次门禁分层报告耗时（G7 逐用例耗时归层、单元层与区域墙钟，gate / baseline / final 输出 tier_sec 并写进 summary 与 timeline） （deps: S2 · verify: `python3 -m pytest -q tests/test_tiers_timing.py tests/test_tiers_gate.py tests/test_tiers_verdict.py tests/test_slice_gate.py tests/test_slice_gate_final.py tests/test_slice_gate_baseline_preflight.py tests/test_evidence_timeline.py tests/test_baseline_incremental.py`）
