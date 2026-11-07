# 切片间接口

- **S1 → S2 → S3** 同改 `template/.claude/hooks/slice-gate.py`，只能串行；**S4** 只依赖 S1 落地的 `scope-seed` 子命令与声明形态，与 S2 同属 wave 2，owns 不相交。
- 各片只动自己那一块：
  - S1：声明解析、提供方、lint 路径、`scope-seed`、审批页；
  - S2：内建预测与 final 判定 / 选中；
  - S3：baseline / final 的复核与 approve 绑定。

## S1 落地、后续切片依赖的签名（`slice-gate.py`）

- `SCOPE_UNDECLARED = "scope:undeclared"`：伪触发项。
- `def _scope_provider(gate, change_dir) -> (dict, list)`：
  - 返回 `({"kind": "cmd" | "builtin" | None, "cmd": str | None, "source": str | None}, errors)`；
  - 优先级：`gate.scope` > `<openspec 根>/gate-scope.json` > 未声明；
  - `errors` 是声明形态违规（只能取其一 / builtin 须为 true / 未知字段 / 读不出）。
- `def _plain_test_cmd(cmd) -> bool`：builtin 的 gate.test 识别（design D3），`scope-seed` 共用。
- `def _planned_owns(data) -> list`：各片 owns 按切片顺序去重。
- `def _establishes_decl(data, change_dir) -> bool`：任一 owns glob 匹配 `<openspec 根>/gate-scope.json` 的仓库相对路径。
- `def _run_scope(cmd, root, planned=(), change_rel="") -> (errors, report | None)`：另设 `GATE_SCOPE_PLANNED`（临时文件路径，一行一条）与 `GATE_SCOPE_CHANGE`。
- `def _builtin_report(root, change_dir, data, phase) -> dict`：
  - S1 先给最小实现：`{"full": False, "triggers": [], "pending": [], "notes": []}`；
  - S2 替换为真实预测，签名不变；
  - `phase ∈ {"lint", "preflight", "baseline", "final"}`。
- `def _scope_reason_errors(report, reasons, pending=())`：`pending` 里的键不算多余理由。
- `def _lint_scope(gate, change_dir, run_scope, data=None, phase="lint") -> (errors, note)`：
  - 实跑核对时处理三种提供方与「未声明」；
  - `run_scope` 为假时只做形状校验，不判未声明。
- `def lint_plan(data, change_dir=None, run_scope=False, phase="lint")`：
  - `cmd_lint` 传 `phase="lint"`；
  - `cmd_preflight` 传 `phase="preflight"`；
  - S3 的 baseline 复核直接调 `_lint_scope(..., phase="baseline")`。

## S2 落地、S3 依赖的签名

- `def _full_triggers(root, delta, anchor, baseline, gate, tier_rel=None, decl_rels=(), impacted=False) -> list`：
  - 返回全部触发项：文件类用路径；代码类用 `final:no-anchor` / `final:baseline-missing-failed-nodes` / `final:gate-test-unreproducible`；
  - `anchor is None` 表示没有可用锚点。
- `def _full_why(...)`：签名不变，改为基于 `_full_triggers` 的第一条拼原有措辞（现有测试断言的 `full_why` 子串不得变）。
- `def _shell_closure(root, files) -> set`：返回新到达的仓库相对路径，不含输入本身。
- `def _decl_rels(root, change_dir) -> set`：声明文件的仓库相对路径（`gate-scope.json`、`gate-checks.json`）；`.claude/` 前缀另判。

## S3 新增

- `def _approved_reasons(root, change_dir) -> dict | None`：最近一次新增 approve 行的提交里的 `gate.scope_full_reason`（缺省 `{}`）；没有 approve 提交 → `None`。

## S4 依赖

- CLI：`python3 <模板>/.claude/hooks/slice-gate.py scope-seed --openspec-root DIR`：
  - 恒退出 0；
  - stdout 首行含「已种」/「未种」/「保留已有声明」之一，「未种」时含例子与指引。
