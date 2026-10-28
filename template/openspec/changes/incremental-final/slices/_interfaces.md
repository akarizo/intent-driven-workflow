# 公开接口摘要

## S1

文件 template/.claude/hooks/slice-gate.py（另内嵌嵌套会话防护插件、依赖图插件、sitecustomize 源码串）

- `def _read_probe(path)`
- `def _flight_plugins(tmp, env, root, deps)`
- `def _read_deps(path)`
- `def _deps_merge(a, b)`
- `def run_test_gate(cmd, root, probe=False, deps=False, _plain=False)`
- `def load_baseline(change_dir)`
- `def gate_cmd_verdict(kind, cmd, root, baseline)`
- `def full_suite_verdict(cmd, root, baseline)`
- `def _diff_verdict(label, tg, known_failed)`

## S2

文件 template/.claude/hooks/slice-gate.py（增量 final、自动全量、同树沿用、ship 按树判新鲜）

- `def _snapshot(root, change_rel)` 工作树快照
- `def cmd_key(root, change_rel, cmd)` 命令键
- `def _delta(root, cand, cur_snap, head, change_rel, same_change, strict=False)` 与候选基线的差异
- `def _baseline_candidates(root, old, key, name, full)`
- `def _pool_dir(root, sub=POOL_DIR)` / `_pool_read` / `_pool_write(root, entry, sub, keep, label)` / `_pool_candidates(...)` 基线池
- `def _anchor_write(root, entry)` / `_anchor_candidates(root, cmd_key, tiers_key, limit=10)` 锚点
- `def _tiers_key(root, change_dir, tiers)`
- `def _final_fps(root, change_rel, data, tiers)` 指纹
- `def _final_rec_read(root, name)` / `_final_rec_write(root, name, rec)` / `_final_reusable(...)` 同树沿用
- `def _pick_anchor(root, key, tkey, cur_snap, head, change_rel, name)`
- `def _full_why(root, full, pick, baseline, snap_why)` 自动全量原因
- `def _final_select(root, anchor, delta)` / `_anchor_forward(...)` 增量选择
- `def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache)`
- `def _verify_paths(root, cmd, delta)` / `_verify_rerun(root, cmd, prev, delta)`
- `def _final_fresh(root, change_dir, final_commit)` ship 按树判新鲜
- `def cmd_final(args)` / `def cmd_ship(args)`

## S3

文件 template/.claude/hooks/slice-gate.py（final 增量路径与分层探针联动；签名沿用 S2，行为调整）；测试 tests/test_final_checks_env.py / test_final_impacted.py / test_final_tiers.py

- `def cmd_final(args)`：gate.impacted 与分层同时配置时增量路径不挂单元层探针，记 warning「G10/G11 未判」
