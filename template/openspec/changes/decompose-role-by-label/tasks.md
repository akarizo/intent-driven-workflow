> 本文件由 `slices.json` 生成（改动请改 `slices.json` 后重新生成）。切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。

## S1 对账：无 agentType 时按 label 判 integrator / reviewer，未知 label 退回按阶段；label 契约测试 · deps: - · verify: `python3 -m pytest -q tests/test_evidence_timeline.py tests/test_agents_workflow.py`

- [x] S1 `session-decompose.py` 角色判定改为 agentType → label → 阶段（`integrate:*` / `final-gate*` → integrator，`review:*` → reviewer）；补误报 / 漏报测试与 `opsx-apply.js` label 契约测试；scenarios：route-audit-role-resolution 4 条（含 1 条护栏）
