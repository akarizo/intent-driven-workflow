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

## S5（`template/.claude/hooks/slice-gate.py` · `tests/test_evidence_shared_gate.py` · `tests/test_merge_reap.py`）

- `def _evidence_shared(root, change_dir, slice_id)`：共用目录里本切片的 evidence 文件。
- `def _evidence_merge(root, change_dir, slice_id, drop=False)`：合并共用 evidence 到分支留痕。
- `def _evidence_prune(root)`：清理共用 evidence 残留。
- `def evidence_state(change_dir, slice_id, root=None)`：evidence 留痕状态。
- `def _status_entries(root)` / `def _flight_dirt(xy, path)` / `def _drop_untracked(base, paths)`：合回前工作树状态与飞行记录脏文件处理。
- `def _reap_one(root, wt, warnings)` / `def _reap(root, sid, sha, pre, warnings)`：合回后回收切片临时 worktree。

## S6（文档与安装：`opsx-apply.md` · `SKILL.md` · `README.md` · `install.sh`）

- 无新增源码签名。

## S7（`template/.claude/hooks/spec_html.py` · `tests/test_spec_html_turns.py`）

- `def slice_turns(change_dir)`：读取各切片轮次档位供切片表渲染。
