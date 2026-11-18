# 公开接口摘要

## S1（`template/.claude/hooks/slice-gate.py` · `tests/test_start_continue.py`）

- `def _continue_from(root, commit)`：`start --continue` 的区间起点解析。

## S2（`template/.claude/hooks/test-evidence.py` · 测试文件）

- `def common_dir(root)`：留痕共用目录。
- `def read_marker(root)`：读取标记。
- `def find_change(root)`：定位 change。
- `def script_tokens(change_dir, slice_id)`：脚本 token。

## S3（`template/.claude/hooks/slice-gate.py` · `tests/test_turn_tiers.py`）

- `def _turn_tree(root, change_dir)`：轮次分档的基线树解析。
- `def _owned_file_count(root, commit, owns)`：基线 commit 上 owns 现存文件数。
- `def slice_turns(data, change_dir, root)`：算各切片轮次档位。
- `def cmd_turns(args)`：`turns` 子命令。

## S4（`template/.claude/workflows/opsx-apply.js` · `template/.claude/agents/slice-executor-large.md`）

- `CAPS = { standard: 40, large: 80 }`：各档轮次上限。
- `tierOf(s)` / `execDef(s)`：按 turns 选档位与执行体定义（standard→slice-executor，large→slice-executor-large）。
- `startCmd(s, cont, resume)`：重派经 `start --continue` 的命令串。
- agent `slice-executor-large`：大片档薄定义，纪律同 slice-executor。
