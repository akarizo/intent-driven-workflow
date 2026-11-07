<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall；命令与同名 skill 同改。
> wave 1 = S1 + S4（owns 不相交）；wave 2 = S2；wave 3 = S3（S1–S3 同改 `slice-gate.py`，只能串行）。

## 切片

- [ ] S1 门禁展开：gitlink → 子仓内文件（已提交 / 未提交）、G6 gitlink 未记录、added_lines 带 --submodule=diff、门禁绿锚定子仓提交 （deps: - · verify: `python3 -m pytest -q tests/test_submodule_gate.py tests/test_slice_gate.py`）
- [ ] S2 子仓填充与续跑：start 在 G0 后借出家子仓 linked worktree、sub-sync 子命令、快照恢复覆盖子仓、preflight 就绪校验 （deps: S1 · verify: `python3 -m pytest -q tests/test_submodule_sync.py tests/test_submodule_gate.py tests/test_slice_gate.py tests/test_slice_gate_baseline_preflight.py`）
- [ ] S3 合回脚本：slice-gate.py merge 逐片 --no-ff、gitlink 快进直钉 / 分叉在家子仓内合并后钉、检出同步、失败全回滚 （deps: S2 · verify: `python3 -m pytest -q tests/test_submodule_merge.py tests/test_submodule_sync.py tests/test_submodule_gate.py`）
- [ ] S4 编排与文档：opsx-apply.js 合回 / fix / 评审接上 merge · sub-sync · --submodule=diff，agent 定义、命令与同名 skill、git-discipline、README、WORKFLOW_zh （deps: - · verify: `python3 -m pytest -q tests/test_submodule_docs.py tests/test_agents_workflow.py tests/test_template_docs.py tests/test_docs_iron_rules.py`）
