<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->
> 切片规则：1–9 片 · DAG 深度 ≤ 3 · 同 wave 所有权不相交 · 每片 owns ≤ 12 条 · 每片一个 commit · 门禁绿才勾选。
> 本仓库自身纪律：Python 脚本 TDD（先写失败测试）；测试函数首行 `# Given:` 三段中文注释；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall；命令与同名 skill 同改。
> wave 1 = S1 + S3（owns 不相交）；wave 2 = S2（README 要写 S3 的语义，命令要调 S1 的接口，故依赖两者）。

## 切片

- [ ] S1 判定脚本 merged-cleanup.py：plan / apply、合并状态四分、--force 与档位、-d 按 git 规则 + ff 同步、子仓存活校验、飞行快照 ref （deps: - · verify: `python3 -m pytest -q tests/test_merged_cleanup.py`）
- [ ] S2 /clean-after-merged 命令、铁律 6 授权例外、git-discipline 清理条款、README / WORKFLOW_zh / install.sh 同步 （deps: S1, S3 · verify: `python3 -m pytest -q tests/test_clean_after_merged_docs.py tests/test_docs_iron_rules.py tests/test_template_docs.py tests/test_install.py tests/test_baseline_incremental_docs.py tests/test_gate_checks_docs.py tests/test_scope_docs.py tests/test_tiers_docs.py tests/test_tiers_parts_docs.py tests/test_incremental_final_docs.py`）
- [ ] S3 /pr-ship step 2b 记忆层沉淀 + /claudemd-commit 自动录入、较大差异对齐、E 类反复错误 + standard §13 （deps: - · verify: `python3 -m pytest -q tests/test_ship_memory_docs.py tests/test_template_docs.py tests/test_incremental_final_docs.py tests/test_ship_verdict.py tests/test_approval_gate.py tests/test_memory_lint.py`）
