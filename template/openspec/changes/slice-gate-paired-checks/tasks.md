> 本文件由 `slices.json` 生成（改动请改 `slices.json` 后重新生成）。切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 + S4（owns 不相交）；wave 2 = S2（与 S1 同改 `slice-gate.py`）；wave 3 = S3（与 S2 同改 `slice-gate.py`）。

## S1 判定器：lint 校验 gate.checks / checks_skip 的形状，并按 change 目录找仓库默认检查 gate-checks.json 对账 · deps: - · verify: `python3 -m pytest -q tests/test_gate_checks_lint.py tests/test_slice_gate.py tests/test_slice_gate_baseline_preflight.py`

- [ ] S1 `lint_plan(data, change_dir=None)` 校验检查形状（字段白名单、name、final、baseline、timeout_sec、checks_skip）与仓库默认检查对账；scenarios：gate-paired-checks 6 条（含 2 条护栏）

## S2 判定器：检查运行函数（GATE_* · 超时整组结束 · 输出落盘）、baseline 运行与记录检查（实跑前清空目录、照 D10 沿用）、plan_sha 并入检查 · deps: S1 · verify: `python3 -m pytest -q tests/test_gate_checks_baseline.py tests/test_baseline_incremental.py tests/test_baseline_pool.py tests/test_baseline_skip.py tests/test_slice_gate.py tests/test_slice_gate_baseline_preflight.py`

- [ ] S2 `_run_check` / `_check_env` / `_check_log` / `_check_dir`；baseline 在 verify 之后运行检查、记 `checks.<name>`、红即基线红、本 change 严格差异为空且命令与指纹不变且目录仍在时沿用；`plan_sha` 追加 `[name, baseline]`；scenarios：gate-paired-checks 10 条（含 2 条护栏）

## S3 判定器：final 在全量判定之后运行检查（核对基线记录、G9、G7 红时不跑并警告） · deps: S2 · verify: `python3 -m pytest -q tests/test_gate_checks_final.py tests/test_gate_checks_baseline.py tests/test_slice_gate_final.py tests/test_slice_gate.py tests/test_slice_gate_baseline_preflight.py`

- [ ] S3 final 核对基线记录与 commit、运行检查 final、红记 `G9 check <name>`（带日志路径与末尾 20 行）、G7 红时不跑并加警告；scenarios：gate-paired-checks 5 条

## S4 文档：schema tasks instruction、propose / verify 命令与同名 skill、README 写明 gate.checks 的配置、时机与契约 · deps: - · verify: `python3 -m pytest -q tests/test_gate_checks_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py tests/test_baseline_incremental_docs.py`

- [ ] S4 schema 的 tasks instruction、`opsx-propose` / `opsx-verify` 命令与同名 skill、README 写明检查的配置、时机、契约与仓库默认检查；scenarios：gate-paired-checks 1 条
