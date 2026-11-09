# 切片间接口（实现时以此为准；改签名须向后兼容）

依赖：S1 → S2 → S3；S1 → S4 → S5。`slice-gate.py` 只由 S1、S2、S3 串行修改；S4 只读它的函数，S5 只写文档。

## S1 提供（S2 / S3 / S4 依赖）

- **`run_test_gate(cmd, root, probe=False, deps=False, _plain=False, extra_env=None, cwd=None, keep_junit=None)`**
  - `keep_junit`：非 None 时，临时目录删除前把 junit 复制到该路径；
  - 返回值新增 `deps_kind`：`not-pytest` / `plugins-dropped` / `plugin-import-failed` / `incomplete` / `None`（已测或 `deps=False`）；
  - 加载插件时环境新增 `FLIGHT_PLUGIN_PATH`、`FLIGHT_PYTEST_ARGS`；`_plain` 时不设。
- **`_pytest_outcomes(root, targets, gate=None, durations=None, deps_out=None, probe_out=None, extra_env=None, keep_junit=None)`**：后两个参数与 `run_test_gate` 同义。
- **gate.test 环境**：baseline / final 经 `extra_env` 传 `{"GATE_PHASE": "baseline"|"final", "GATE_CHANGE": <change 目录名>}`，增量重跑与 `gate.impacted` 同样传。
- **基线 JSON**：依赖图未测时新增 `deps_unmeasured: {"kind": <类别>, "why": <人话+修法>}`；warning 文字为 `依赖图未测（<kind>）：<why>`。
- **锚点条目**：新增 `nodes: {仓库相对 nodeid: outcome}`（依赖图未测时为 `{}`）与 `deps_kind`。
- **结果文件**：`<git common dir>/flight-gate-checks/<change>/.gate-test-result.json`，字段见 `specs/gate-test-result-handoff/spec.md`。
  - outcome 一律小写：`passed` / `failed` / `error` / `skipped` / `xfailed` / `xpassed`；
  - junit 副本在同目录 `.gate-test-junit.xml`；
  - 检查环境 `GATE_TEST_RESULT` 为它的绝对路径（只在 final）。
- **`cmd_key(root, change_rel, cmd)`**：签名不变；算法见 design D9（内容按词边界把 `basename(change_rel)` 换成 `<change>`，并纳入 `_shell_closure`）。

## S2 提供（S3 / S4 依赖）

- **`ANCHOR_MAX_HOPS = 5`**（模块常量）。
- **`_scope_extras(change_dir) -> {"global": [str], "blind": [str], "anchor_max_hops": int}`**：文件缺失、字段缺失或形状错误都取缺省；形状错误由 `_scope_decl` 报。
  - 报错文字：`global 须是字符串数组` / `blind 须是字符串数组` / `anchor_max_hops 须是正整数`。
- **`_pick_anchor(root, akey, tkey, cur_snap, head, change_rel, name, max_hops=ANCHOR_MAX_HOPS)`**：前 7 个位置参数不变；滤掉 `hops >= max_hops` 的锚点。
- **`_anchor_hops(entry, max_hops) -> int`**：缺 `hops` 时按 design D6 推断。
- **`_full_triggers(..., declared_global=())`**：新触发项 `declared-global:<glob>`；链耗尽触发项 `final:anchor-hops`。
  - `full_why` 文字：
    - `Δ 命中项目声明的全局路径 <glob>：<路径>`；
    - `锚点链已达上限 <K> 代（anchor_max_hops）`。
- **`_final_select(root, anchor, delta, blind=())`**：`blind` 为 glob 列表，匹配的现存测试文件并入。
- **锚点 `hops`**：全量写 0，增量 final 写来源锚点 `hops` + 1。
- **final 全量按 nodeid 差分**：基线 `test.failed_form == "nodes"` 时用 `test.failed_nodes` 差分；本次没有依赖图逐用例结局时 G2 test 红，原因见 design D11。

## S3 提供（S4 读、S5 写进文档）

- **基线 JSON**：
  - `test_ok: bool`；
  - 经锚点时 `test = {"exit", "failed": None, "failed_nodes", "failed_form": "nodes", "sec"}`；
  - `mode: "incremental"`，`incremental: {"source": "own"|"anchor"|"pool", "from": {"change", "commit", "at"}, "rerun_files": [...], "hops": n}`；
  - 本 change 旧基线与池候选复用时 `source` 分别为 `own` / `pool`，其余字段沿用现状。
- **锚点**：经锚点的增量基线写 `source: "baseline-incremental"`、`hops` = 来源 + 1。
- **timeline baseline 备注**（design D13）：
  - 全量：`exit <e>, <s>s ok|red；全量：<原因>`；
  - 经锚点增量：`增量（经锚点 <change>@<commit 前 10 位>，补跑 <n> 个测试文件 <t>s） ok|red`；
  - 其余增量保持现有格式（含「增量」二字）。
  - 全量原因的固定文字：`无可用候选（锚点池为空）`、`锚点不可用（依赖图未测：<kind>）`、`锚点链已达上限 <K> 代`、`手动要求 --full`、`有测试分层文件（恒全量）`；其余直接取首个候选的拒绝理由。

- **已合回的实际签名（S3，`template/.claude/hooks/slice-gate.py`）**：
  - `_baseline_full_reason(root, full, tiers, skipped, akey)`：全量原因文字；
  - `_baseline_candidates(root, old, key, name, full, anchor=None)`：旧基线 -> 锚点 -> 池；
  - `_baseline_anchor(root, akey, cur_snap, head, change_rel, name, max_hops)`：写锚点基线；
  - `_try_anchor(root, change_dir, data, cand, extras)`：经锚点增量；
  - `_test_gate_files(root, gate)`：gate.test 静态闭包文件；
  - `_try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache, own=False)`：`own=True` 时接受 `test_ok`。
- **S5 已合回**：只含文档与 `tests/test_runner_contract_docs.py`，无源码接口。

## S4 提供（S5 写进文档）

```
python3 .claude/hooks/flight-doctor.py forecast --change-dir DIR [--json]
python3 .claude/hooks/flight-doctor.py cost --change-dir DIR [--json]
python3 .claude/hooks/flight-doctor.py doctor [--openspec-root DIR]
```

- **均恒 exit 0、只读**。
- **forecast --json**：
  ```json
  {"baseline": {"mode": "full|incremental|pending|missing", "why": "...", "sec": 816.0},
   "final": {"mode": "incremental|full|impacted|unknown", "why": "...", "sec": 816},
   "checks": ["..."]}
  ```
  不带 `--json` 时打印一行：`测试成本预告：baseline <mode>（<why>）· final <mode>（<why>，约 <sec> 秒）· 检查 <n> 项`。
- **cost --json**：
  ```json
  {"baseline": {"full": n, "incremental": m, "full_sec": s},
   "final": {"full": n, "incremental": m, "full_sec": s},
   "full_runs": [{"event": "baseline|final", "reason": "...", "class": "必要|可避免|未分类", "sec": s|null}]}
  ```
- **doctor**：按顺序打印 `[runner]` `[anchors]` `[gate.test]` `[declare]` 四节，每节首行就是节名。
- **对 slice-gate 的依赖**：经 importlib 按路径加载同目录的 `slice-gate.py`，只调用 `load_plan`、`load_baseline`、`_snapshot`、`_anchor_key`、`_tiers_key`、`_load_tiers`、`tiers_is_parts`、`_change_rel`、`_pick_anchor`（7 个位置参数）、`_full_why`、`git`、`toplevel`。
  - `_scope_extras` 存在时才调用，不存在时 K 取 5；
  - 任一调用抛错 → 该段 `mode: unknown`，`why` 写异常文字。
