# 公开接口摘要

## S1（`template/.claude/hooks/slice-gate.py` · `tests/test_start_continue.py`）

- `def _continue_from(root, commit)`：`start --continue` 的区间起点解析。

## S2（`template/.claude/hooks/test-evidence.py` · 测试文件）

- `def common_dir(root)`：留痕共用目录。
- `def read_marker(root)`：读取标记。
- `def find_change(root)`：定位 change。
- `def script_tokens(change_dir, slice_id)`：脚本 token。
