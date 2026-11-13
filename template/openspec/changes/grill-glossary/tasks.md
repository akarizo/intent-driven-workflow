<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿（gate.checks `schema-validate`）；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 ‖ S2（两片只共用术语表格式 design D2，无代码依赖，owns 不相交）。

## 切片

- [x] S1 spec_html.py 读 openspec/glossary.md，审批面板列出 proposal / design / specs 里的避用词命中（长者先占、跳过代码、只提示） （deps: - · verify: `python3 -m pytest -q tests/test_spec_html_glossary.py tests/test_spec_html.py tests/test_spec_html_scope.py tests/test_template_docs.py`）
- [x] S2 grill-me 新增术语表一节（对照 · 定下即写 · 默认分支先问 · 格式），schema 的 proposal / specs instruction 引用术语表，README 补一句 （deps: - · verify: `python3 -m pytest -q tests/test_glossary_docs.py tests/test_template_docs.py tests/test_gate_checks_docs.py tests/test_tiers_docs.py tests/test_tiers_parts_docs.py tests/test_docs_iron_rules.py tests/test_scope_docs.py tests/test_incremental_final_docs.py tests/test_install.py tests/test_baseline_incremental_docs.py tests/test_clean_after_merged_docs.py tests/test_goal_takeoff_docs.py`）
