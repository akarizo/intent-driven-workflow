<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 + S4（owns 不相交）；wave 2 = S2（在 S1 的依赖图与锚点上做增量 final、同树沿用与 ship 新鲜度）；wave 3 = S3（在 S2 的增量路径上接 checks 注入、gate.impacted 与分层叠加）。S1–S3 同改 `slice-gate.py`，只能串行。

## 切片

- [x] S1 判定器：嵌套会话防护插件、依赖图插件与 sitecustomize、run_test_gate / _pytest_outcomes 可选记录依赖图、baseline 全量写锚点与 failed_nodes （deps: - · verify: `python3 -m pytest -q tests/test_final_guard.py tests/test_final_deps.py tests/test_tiers_probe.py tests/test_tiers_gate.py tests/test_slice_gate.py tests/test_slice_gate_baseline_preflight.py tests/test_baseline_incremental.py`）
- [x] S2 判定器：增量 final（取锚点、Δ、自动全量的触发条件、选测、判红、锚点前移、输出）、同树沿用、ship 按树判新鲜 （deps: S1 · verify: `python3 -m pytest -q tests/test_final_incremental.py tests/test_final_reuse.py tests/test_ship_verdict.py tests/test_slice_gate_final.py tests/test_tiers_gate.py tests/test_tiers_timing.py tests/test_gate_checks_final.py tests/test_evidence_timeline.py`）
- [x] S3 判定器：checks 注入 Δ 与锚点、gate.impacted（运行与 lint）、增量与测试分层叠加 （deps: S2 · verify: `python3 -m pytest -q tests/test_final_checks_env.py tests/test_final_impacted.py tests/test_final_tiers.py tests/test_final_incremental.py tests/test_gate_checks_final.py tests/test_gate_checks_lint.py tests/test_tiers_gate.py tests/test_tiers_plan.py tests/test_tiers_timing.py`）
- [x] S4 文档：/pr-ship 评审自动修复不询问；/opsx-verify、/opsx-apply 与同名 skill 写增量 final；schema tasks instruction 写 gate.impacted；README （deps: - · verify: `python3 -m pytest -q tests/test_incremental_final_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_gate_checks_docs.py tests/test_tiers_docs.py`）
