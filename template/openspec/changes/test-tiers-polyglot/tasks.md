<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 + S5（owns 不相交）；wave 2 = S2（在 S1 的部件模型上做运行器与逐部件判定）；wave 3 = S3 + S4（S3 接线 baseline / final / preflight，S4 扩展 test-tiers.py）。S1–S3 同改 `slice-gate.py`，只能串行。

## 切片

- [ ] S1 判定器：分层文件部件形态的加载与形状校验、list 选择器解析、适配器 sha 核对、lint 的部件规则、部件归属与 G12 （deps: - · verify: `python3 -m pytest -q tests/test_tiers_parts_plan.py tests/test_tiers_plan.py tests/test_slice_gate.py tests/test_gate_checks_lint.py tests/test_final_impacted.py`）
- [ ] S2 判定器：部件运行器（root 下运行、FLIGHT_JUNIT 与 unit.junit、探针适配器契约、内置探针顶层 id）与逐部件 G10 / G11 判定 （deps: S1 · verify: `python3 -m pytest -q tests/test_tiers_parts_runner.py tests/test_tiers_probe.py tests/test_tiers_verdict.py tests/test_tiers_gate.py tests/test_final_guard.py`）
- [ ] S3 判定器：部件形态下 baseline / final / preflight 逐部件运行与对账、区域在所属部件 root 下运行、tier_sec.parts （deps: S2 · verify: `python3 -m pytest -q tests/test_tiers_parts_gate.py tests/test_tiers_gate.py tests/test_tiers_timing.py tests/test_final_tiers.py tests/test_slice_gate_final.py tests/test_slice_gate_baseline_preflight.py tests/test_baseline_incremental.py`）
- [ ] S4 脚本：test-tiers.py 的 run unit 驱动、canary 金丝雀自检、probe --root / --adapter、check 与 render 支持部件形态 （deps: S2 · verify: `python3 -m pytest -q tests/test_tiers_parts_cli.py tests/test_tiers_cli.py tests/test_approval_gate.py`）
- [ ] S5 文档：/test-tiers 命令写部件形态、两种契约、金丝雀与多部件发现；schema tasks instruction、opsx-propose 命令与同名 skill、README、CLAUDE.md.snippet （deps: - · verify: `python3 -m pytest -q tests/test_tiers_parts_docs.py tests/test_tiers_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_gate_checks_docs.py tests/test_incremental_final_docs.py`）
