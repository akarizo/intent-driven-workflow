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
