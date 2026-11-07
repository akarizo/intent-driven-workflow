<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall；命令与同名 skill 同改。
> wave 1 = S1；wave 2 = S2 + S4（owns 不相交）；wave 3 = S3（与 S1、S2 同改 `slice-gate.py`，只能串行）。

## 切片

- [ ] S1 契约 v2：声明形态与提供方解析、未声明判红与建立声明例外、builtin 误用判红、GATE_SCOPE_PLANNED / GATE_SCOPE_CHANGE、scope-seed、审批页提供方状态、测试基座默认声明 （deps: - · verify: `python3 -m pytest -q tests`）
- [ ] S2 内建提供方与 final 精度：_full_triggers 单一出处、计划期预测（lint 池锚点 · preflight 新鲜锚点 · 待定项）、声明文件排除、shell 静态闭包 （deps: S1 · verify: `python3 -m pytest -q tests/test_builtin_scope_precision.py tests/test_scope_contract_v2.py tests/test_gate_scope_lint.py tests/test_final_incremental.py tests/test_final_impacted.py tests/test_final_tiers.py tests/test_final_deps.py tests/test_final_reuse.py tests/test_tier_file_incremental.py tests/test_slice_gate_baseline_preflight.py`）
- [ ] S3 运行期守卫：baseline / final 开跑前复核、理由以 approve 提交为准、--full 豁免 （deps: S2 · verify: `python3 -m pytest -q tests/test_scope_runtime_guard.py tests/test_builtin_scope_precision.py tests/test_scope_contract_v2.py tests/test_slice_gate_final.py tests/test_slice_gate_baseline_preflight.py tests/test_baseline_incremental.py tests/test_baseline_pool.py tests/test_baseline_skip.py tests/test_final_incremental.py tests/test_final_impacted.py tests/test_gate_checks_baseline.py tests/test_gate_checks_final.py`）
- [ ] S4 安装器与文档：install.sh 调 scope-seed、本仓库声明 builtin、schema / 三个命令及同名 skill / README 同步契约 v2 （deps: S1 · verify: `python3 -m pytest -q tests/test_install.py tests/test_scope_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_incremental_final_docs.py tests/test_gate_checks_docs.py tests/test_tiers_docs.py tests/test_tiers_parts_docs.py tests/test_baseline_incremental_docs.py`）
