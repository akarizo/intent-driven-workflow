> 本文件由 `slices.json` 生成（改动请改 `slices.json` 后重新生成）。切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿。
> wave 1 = S1 + S2 + S3 + S4（owns 不相交；S1 / S3 只在提示词与文档里引用 S2 的判定器行为，测试互不调用）。执行方式见 design D6：飞行外，主会话按 S1 → S4 逐片实现。

## S1 Workflow 引擎可靠性（摘自 #36 #37） · deps: - · verify: `python3 -m pytest -q tests/test_agents_workflow.py`

- [x] S1 `opsx-apply.js`、`integrator.md`、`slice-executor.md`、`openspec-git-discipline` 整份取原仓 `36d91c3`；`opsx-apply` 命令与同名 skill 只换 step 5 的 Agent 回退段；scenarios：workflow-engine-recovery 的 16 条工作流与文档 scenario

## S2 判定器（摘自 #36 #37 #40 #41 #45 #46 #60） · deps: - · verify: `python3 -m pytest -q tests/test_slice_gate.py tests/test_slice_gate_final.py tests/test_slice_gate_baseline_preflight.py tests/test_slice_gate_coverage.py tests/test_ship_verdict.py`

- [x] S2 `slice-gate.py` 取原仓 `36d91c3` 删账本 / measure / 护栏 / `--reuse-fix`，加 #60 覆盖率判定；scenarios：workflow-engine-recovery 的 5 条门禁结论 scenario · gate-scenario-run 9 条 · gate-change-scope 5 条 · gate-full-suite-baseline 18 条

## S3 propose / pr-ship / legacy / schema 文档（摘自 #45 #47 #51） · deps: - · verify: `python3 -m pytest -q tests/test_template_docs.py`

- [x] S3 `opsx-propose` 命令与 skill 换上审批与基线并行的步骤；`pr-ship` 第 4 步改 merge-tree 退出码；legacy 三处评审派发补 `model`；schema 补 `gate.pytest` / `gate.test` 必填 / 基线差分；scenarios：propose-parallel-baseline 3 条 · pr-ship-premerge-check 1 条 · legacy-review-routing 1 条

## S4 安装器与 README（摘自 #35 #36 #38 #55 + 本仓新增） · deps: - · verify: `python3 -m pytest -q tests/test_install.py`

- [x] S4 `install.sh` 缺省指本仓、pipe 认 tag 并交接、保留 settings、只下发种子、Mod 版退场提示；README 写安装指定版本与 Mod 版关系；scenarios：installer-edition 17 条

## R 收口后评审修复（2026-10-15 经用户授权）

- [ ] R1 按独立评审修：README tag 警告改准（老 tag 脚本缺省从原仓下载、装上的是 Mod 版）并补「老 tag 安装器带老缺陷，`--upgrade` 会覆盖 settings.json」；删 3 个测试文件里无用的 `import pytest`（G7 不写字节码缺测试覆盖，记入 PR 作跟进）
