> 本文件由 `slices.json` 生成（改动请改 `slices.json` 后重新生成）。切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。
> wave 1 = S1 + S4（owns 不相交）；wave 2 = S2（与 S1 同改 `slice-gate.py`）；wave 3 = S3（与 S2 同改 `slice-gate.py`）。

## S1 判定器：基线内容指纹、同一 change 增量复用、verify 按需重跑、preflight 按内容判过期（摘自 #65；起飞判据改用 approve，修副产物 / 软链 / 补跑去重 / 不复用理由） · deps: - · verify: `python3 -m pytest -q tests/test_baseline_incremental.py tests/test_slice_gate.py tests/test_slice_gate_baseline_preflight.py tests/test_slice_gate_final.py`

- [ ] S1 `slice-gate.py` 落地内容指纹、同一 change 增量、verify 按需重跑、preflight 按内容判过期（看 timeline 的 approve）、运行期改动判定（副产物 / 软链 / 其他 change 目录）、补跑去重、`reuse_skipped`、`--full`；scenarios：baseline-incremental-reuse 23 条（含 4 条护栏）

## S2 判定器：基线池与跨 change 复用（只收全绿全量、指纹为空不入池、清理孤儿临时文件、写池失败只警告） · deps: S1 · verify: `python3 -m pytest -q tests/test_baseline_pool.py tests/test_baseline_incremental.py`

- [ ] S2 基线池（git common dir）与跨 change 复用：只收全绿且指纹非空的全量、保留 30 条、清理一小时前的临时文件、写池失败只警告；scenarios：baseline-incremental-reuse 6 条

## S3 判定器：代码树没变时 lint / typecheck 沿用、全量可度量时 verify 从全量 junit 推导 · deps: S2 · verify: `python3 -m pytest -q tests/test_baseline_skip.py tests/test_baseline_incremental.py tests/test_baseline_pool.py tests/test_slice_gate.py`

- [ ] S3 `run_test_gate` 交出 junit 用例集；可推导的 verify 不单独跑；本 change 严格差异为空且命令与指纹不变时 lint / typecheck 沿用；scenarios：baseline-redundant-run-skip 7 条（含 3 条护栏）

## S4 文档：propose 命令与同名 skill 的基线步骤、README 写明增量基线、跨 change、推导与沿用 · deps: - · verify: `python3 -m pytest -q tests/test_baseline_incremental_docs.py tests/test_template_docs.py tests/test_docs_iron_rules.py`

- [ ] S4 `opsx-propose` 命令与同名 skill 第 5 步写明增量、跨 change 全绿、推导、沿用、`--full`、改完计划重跑与一行报告格式；README 补一条；scenarios：baseline-incremental-reuse 1 条
