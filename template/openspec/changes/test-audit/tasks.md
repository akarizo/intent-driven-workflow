<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿（gate.checks `schema-validate`）；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 ‖ S4 ‖ S6（超线清单纯函数 ‖ 整改稿审批页 ‖ 标准文档）；wave 2 = S2 ‖ S5（体检的不合规类别 ‖ 整改护栏）；wave 3 = S3 ‖ S7（体检的未判、筛选与前后对比 ‖ 命令文档与计数）。

## 切片

- [x] S1 test-ledger.py：全量超线清单 violations()，线的取法与 budget() 共用一处 （deps: - · verify: `python3 -m pytest -q tests/test_audit_core.py tests/test_budget_core.py tests/test_ledger_core.py tests/test_ledger_delta.py tests/test_flight_doctor_tests.py tests/test_budget_doctor.py`）
- [x] S2 test-tiers.py audit：只读体检的数据来源与归层、十个不合规类别、AUDIT_RULES、JSON 输出与基本退出码 （deps: S1 · verify: `python3 -m pytest -q tests/test_audit_scan.py tests/test_tiers_cli.py tests/test_tiers_parts_cli.py tests/test_budget_allow_cli.py tests/test_tiers_probe.py`）
- [x] S3 test-tiers.py audit：提示与未判、结论与退出码 3、文本输出、按范围 / 类别 / 最慢 N 条筛选、--compare 与 --plan （deps: S2 · verify: `python3 -m pytest -q tests/test_audit_verdict.py tests/test_audit_compare.py tests/test_audit_scan.py tests/test_tiers_cli.py tests/test_tiers_parts_cli.py`）
- [x] S4 test-audit.py render：整改稿校验、按去向归轨道（ACTIONS）、单文件审批页 （deps: - · verify: `python3 -m pytest -q tests/test_audit_render.py`）
- [x] S5 test-audit.py verify：整改护栏（改动范围、用例与断言不变、分层文件改动与稿一致、未核对清单） （deps: S4 · verify: `python3 -m pytest -q tests/test_audit_verify.py tests/test_audit_render.py`）
- [x] S6 文档：运行器契约新增「测试套件合规标准」一节，test-tiers 命令文档指向体检 （deps: - · verify: `python3 -m pytest -q tests/test_audit_standard_docs.py tests/test_budget_docs.py tests/test_ledger_docs.py tests/test_runner_contract_docs.py tests/test_lock_docs.py tests/test_plan_hygiene_docs.py tests/test_ship_rerun_docs.py tests/test_tiers_docs.py tests/test_tiers_parts_docs.py tests/test_scope_docs.py`）
- [x] S7 文档：新命令 /test-audit，README 与 install.sh 的命令计数 17 → 18，标准文档与脚本常量对账 （deps: S2, S5 · verify: `python3 -m pytest -q tests/test_audit_docs.py tests/test_audit_standard_docs.py tests/test_tiers_docs.py tests/test_clean_after_merged_docs.py tests/test_install.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_budget_docs.py tests/test_ledger_docs.py tests/test_lock_docs.py tests/test_resume_docs.py`）
