# 切片间接口（规划时的约定；合回后由 integrator 按实际签名刷新）

> wave 1 合回后核对：S1 的签名与 `slice-gate.py` 实际定义一致（`SCOPE_EXTRAS` 含 `inert`；`_scope_extras` / `_never_inert` / `_inert_ctx` / `_inert_paths` / `_recon_anchor` / `_inert_drop` / `_final_fresh(..., data=None)` / `_final_reusable(..., drop=None)` / `_pick_anchor(..., drop=None)` / `_baseline_anchor(..., drop=None)`）；S4 仅改文档。S2、S3 小节仍为规划约定，待其合回后刷新。

## S1 提供

- `gate-scope.json` 的可选字段 `inert`（字符串数组）；`_scope_extras(change_dir)` 的返回值多一个键 `"inert"`（缺省 `[]`）。
- `_never_inert(rel, ctx) -> str | None`（`slice-gate.py`）：类别文字固定为「测试路径」「全局文件」「声明的 global」「changes 根下」「声明文件」。
- `_inert_ctx(root, change_dir) -> {"inert", "global", "changes_rel", "decl"}`。
- `_inert_paths(root, paths, ctx, anchor=None) -> (set, [(路径, 测试文件)])`：生效的子集与矛盾；`anchor` 给了时被依赖的路径不生效。
- `_recon_anchor(root, change_dir, data) -> dict | None`：同命令指纹、同分层指纹、测到依赖图的最新一条锚点。
- `_inert_drop(root, change_dir, data=None, recon=True) -> (drop, ctx)`；`drop(delta, anchor=None) -> list`。
- 新增可选参数（缺省时行为与改前相同）：`_final_fresh(..., data=None)`、`_final_reusable(..., drop=None)`、`_pick_anchor(..., drop=None)`、`_baseline_anchor(..., drop=None)`。
- `cmd_final` 里有局部变量 `idrop` / `ictx`（同树沿用之前取得），S3 直接用。
- final 的 warnings 可能多出以 `inert 声明与依赖图矛盾：` 开头的条目。

## S2 提供

- `_lint_inert(gate, change_dir) -> [str]`（`slice-gate.py`）：违规都以 `scope: ` 开头；由 `_lint_scope` 在 `run_scope` 为真时调用（lint / preflight / baseline 开跑前）。
- `flight-doctor.py doctor` 的 `[declare]` 多一行 `inert：…`，声明了 `inert` 时另有对账行（「无法对账」/「inert 与依赖图矛盾：…」/「…无矛盾」）。

## S3 提供

- 常量 `TESTS_ONLY = "tests-only"`（`slice-gate.py`）。
- `_tests_only_pick(root, change_dir, data, rec, baseline, cur_snap, head, fps, tiers, drop) -> ((green, Δ, files) | None, 原因 | None)`。
- final 结果的 `incremental` 可能是 `{"mode": "incremental", "source": "tests-only", "anchor", "delta", "rerun", "rerun_tests", "inherited_tests": null}`；时间线备注形如 `增量（无图：上次绿 final <10 位>，只重跑 N 个测试文件） ok`。
- 全量原因可能形如 `没有可用锚点；上次绿 final <10 位> 后有非测试文件改动：<路径…>`。
- `GATE_TEST_RESULT` 的 `mode` 多一个取值 `tests-only`。
- `final_forecast` 可能返回 `("incremental", "无图：上次绿 final <10 位>，只重跑 N 个测试文件")`。

## S4 提供

- 无公开代码接口：只改文档（pr-ship 命令、flight-runner-contract、opsx-propose 命令与同名 skill、schema.yaml、README）与 `tests/test_ship_rerun_docs.py`。
