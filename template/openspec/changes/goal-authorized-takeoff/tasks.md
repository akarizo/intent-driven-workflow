<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall；命令与同名 skill 同改。
> wave 1 = S1；wave 2 = S2（文档描述 S1 的 `/goal` 证据接口；自举飞行时文档先合回会让后续派发按新契约走，故依赖 S1）。

## 切片

- [x] S1 takeoff-gate.py 认会话 /goal（主链最后一条 goal_status met=false 即放行、豁免新鲜度）与 human 来源的 queued_command 插话 （deps: - · verify: `python3 -m pytest -q tests/test_goal_takeoff.py tests/test_approval_gate.py`）
- [x] S2 propose 收尾在 /goal 下不硬交接、apply step 0 与铁律 7 / README / WORKFLOW_zh 写明 /goal 持续授权（命令与同名 skill 同改） （deps: S1 · verify: `python3 -m pytest -q tests/test_goal_takeoff_docs.py tests/test_approval_gate.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_install.py tests/test_agents_workflow.py tests/test_baseline_incremental_docs.py tests/test_clean_after_merged_docs.py tests/test_scope_docs.py tests/test_incremental_final_docs.py tests/test_gate_checks_docs.py tests/test_submodule_docs.py tests/test_tiers_docs.py tests/test_tiers_parts_docs.py tests/test_ship_memory_docs.py`）
