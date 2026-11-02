<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall；命令与同名 skill 同改。
> wave 1 = S1 + S3 + S4（owns 不相交）；wave 2 = S2（与 S1 同改 `slice-gate.py`，只能串行）。

## 切片

- [ ] S1 判定器：分层指纹只取单元层、锚点记录区域与放行、final 按块收窄、分层文件不再是全局文件 （deps: - · verify: `python3 -m pytest -q tests/test_tier_file_incremental.py tests/test_final_tiers.py tests/test_final_incremental.py tests/test_final_impacted.py tests/test_final_reuse.py tests/test_tiers_gate.py tests/test_baseline_incremental.py`）
- [ ] S2 判定器：lint / preflight 的选测范围契约（gate.scope 与 gate-scope.json、实跑与报告校验、全选逐项表态） （deps: S1 · verify: `python3 -m pytest -q tests/test_gate_scope_lint.py tests/test_slice_gate.py tests/test_gate_checks_lint.py tests/test_tiers_plan.py tests/test_tiers_parts_plan.py tests/test_slice_gate_baseline_preflight.py`）
- [ ] S3 审批页：spec.html 渲染选测范围小节（命令、来源、触发项 → 理由） （deps: - · verify: `python3 -m pytest -q tests/test_spec_html_scope.py tests/test_spec_html.py`）
- [ ] S4 文档：schema、/opsx-propose 与同名 skill、/opsx-verify 与同名 skill、/test-tiers、README （deps: - · verify: `python3 -m pytest -q tests/test_scope_docs.py tests/test_tiers_docs.py tests/test_tiers_parts_docs.py tests/test_incremental_final_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_gate_checks_docs.py`）
