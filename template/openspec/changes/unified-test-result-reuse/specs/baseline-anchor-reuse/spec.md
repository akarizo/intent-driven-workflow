## ADDED Requirements

### Requirement: 基线经锚点复用，非测试改动按依赖图补跑
Rule: baseline（不带 `--full`、没有测试分层文件）SHALL 依次尝试三类候选：
1. 本 change 的旧基线（现有规则）；
2. 锚点池：条件是 `gate.test` 指纹与分层指纹都匹配、`measured` 为真、未达锚点链上限；多条可用时取 |Δ| 最小的；
3. 基线池。

经锚点复用时：
- Δ 命中全量触发项（与 final 同一套规则，含项目声明的 `global`）→ 不复用，原因写进 `reuse_skipped`；
- 否则只补跑 final 同一选择集合：依赖与 Δ 相交的测试文件 ∪ Δ 里现存的测试文件 ∪ 锚点失败所在的文件 ∪ 盲区 ∪ 声明的 `blind`。

经锚点复用的基线：
- 预存红 = 补跑结果中 `FAILED` / `ERROR` 的 nodeid，记在 `test.failed_nodes`，并标 `test.failed_form` 为 `nodes`；
- `mode` 为 `incremental`，`incremental.source` 为 `anchor`，`incremental.from` 点名锚点的 change 与 commit，`incremental.rerun_files` 列出补跑的测试文件。

基线池入池条件不变（只收全绿的全量）。跨 change 带预存红的结论只能经锚点路径复用；锚点失败用例所在的文件一定在补跑集合里。

#### Scenario: replan-after-landing-reuses-anchor
- **GIVEN** change `c` 有一次测到依赖图的全量基线
- **AND** 之后提交了非测试文件 `src/a.py` 的改动
- **WHEN** 再运行 baseline
- **THEN** `mode` 为 `incremental`、`incremental.source` 为 `anchor`
- **AND** `incremental.rerun_files` 恰为 `["tests/test_a.py"]`

#### Scenario: global-file-in-delta-forces-full-baseline
- **GIVEN** change `c` 有一次测到依赖图的全量基线
- **AND** 之后提交了 `pytest.ini` 的改动
- **WHEN** 再运行 baseline
- **THEN** `mode` 为 `full`
- **AND** `reuse_skipped` 里有一条锚点候选的理由，同时含「全局文件」与 `pytest.ini`

#### Scenario: cross-change-anchor-with-preexisting-red-reruns-failed
- **GIVEN** 仓库里有一个总是失败的用例 `tests/test_red.py::test_red`
- **AND** change `other` 跑过全量基线，锚点测到依赖图，预存红含该用例
- **AND** change `c` 与 `other` 的 gate.test 相同，且 `c` 还没有基线
- **WHEN** 对 `c` 运行 baseline
- **THEN** `mode` 为 `incremental`、`incremental.from.change` 为 `other`
- **AND** `incremental.rerun_files` 含 `tests/test_red.py`
- **AND** `test.failed_nodes` 含 `tests/test_red.py::test_red`

#### Scenario: anchor-baseline-diffs-final-by-nodes
- **GIVEN** change `c` 的基线 `test.failed_form` 为 `nodes`，`test.failed_nodes` 为 `["tests/test_red.py::test_red"]`，该用例在当前树上仍然失败
- **WHEN** 运行 `final --full`
- **THEN** final 不把 `tests/test_red.py::test_red` 判为新增失败，G2 test 不红

### Requirement: 红基线里有效的测试部分按部件复用
Rule: 基线 SHALL 记 `test_ok`：测试部分本身有效时为真（跑了、可度量、运行期间没有已有文件被改动）。
- 本 change 旧基线 `ok` 为假、但 `test_ok` 为真，且 Δ 满足复用条件时，复用它的测试部分；verify、lint、typecheck 与检查照常判定与重跑；
- 旧基线缺 `test_ok` 字段时不复用测试部分。

#### Scenario: red-baseline-test-part-reused
- **GIVEN** change `c` 的 gate.test 每运行一次就往仓库外的计数文件追加一行
- **AND** 第一次基线因 S1 的 verify 为 `false` 而红，测试部分绿且可度量
- **WHEN** 把 S1 的 verify 改为 `true` 后再运行 baseline
- **THEN** 基线 `ok` 为真、`verify.S1.exit` 为 0、`incremental.source` 为 `own`
- **AND** 计数文件只有一行

### Requirement: cmd_key 归一 change 名并覆盖 shell 闭包
Rule: `cmd_key` SHALL 取命令直接引用的仓库内文件及其静态 shell 闭包（被 `source` / `.` / `bash` 调用的仓库内脚本）的内容，先把其中本 change 目录名（按词边界）替换成 `<change>`，再与归一后的命令文本一起算指纹。
- 两个 change 的包装脚本只差 change 名时，指纹相同；
- 闭包里任一脚本的内容变了，指纹就变。

#### Scenario: cmd-key-normalizes-change-name
- **GIVEN** change `alpha` 与 `beta` 各有 `verify/full.sh`，内容只差各自的 change 名，都 `source` 同目录的 `_common.sh`
- **WHEN** 分别对两条 gate.test 算 `cmd_key`
- **THEN** 两个指纹相同
- **AND** 改动 `beta` 的 `_common.sh` 之后，`beta` 的指纹与 `alpha` 不同

### Requirement: 本 change 门禁脚本只按 gate.test 闭包影响测试结论
Rule: 用本 change 旧基线复用测试结论时，本 change 目录里的门禁脚本 SHALL 只计 gate.test（与 `gate.pytest`）静态 shell 闭包里的那些。其余脚本（例如只被 `gate.lint` 引用的）改动不让测试结论失效；lint、typecheck 与 verify 的沿用判定照旧把它们计入。

#### Scenario: lint-only-gate-script-change-keeps-test-reuse
- **GIVEN** change `c` 有一次全绿的全量基线，gate.lint 是 `bash <change>/verify/lint.sh`，gate.test 不引用它
- **AND** 之后只改了 `<change>/verify/lint.sh`
- **WHEN** 再运行 baseline
- **THEN** `mode` 为 `incremental`
- **AND** lint 记录没有 `reused` 标记（已重跑）

### Requirement: 锚点链上限
Rule: 锚点 SHALL 记 `hops`：
- 全量运行写出的锚点为 0；
- 由增量推出的锚点（增量 final、经锚点的增量基线）为来源锚点的 `hops` + 1。

`hops` ≥ K 的锚点不作 final 与基线的候选；K 取 `gate-scope.json` 的 `anchor_max_hops`，缺省 5。因此没有可用锚点时，`full_why` 或 `reuse_skipped` 写「锚点链已达上限 K 代」。

旧锚点缺 `hops` 时，`source` 为 `final-incremental` 的视为已达上限，其余视为 0。

#### Scenario: final-anchor-chain-limit-forces-full
- **GIVEN** `gate-scope.json` 声明 `anchor_max_hops: 2`
- **AND** 锚点池里全部锚点的 `hops` 都是 2
- **AND** 之后提交了 `src/a.py` 的改动
- **WHEN** 运行 final
- **THEN** `incremental.mode` 为 `full`，`full_why` 含「上限 2」
- **AND** 新写的锚点 `hops` 为 0

#### Scenario: baseline-anchor-chain-limit-forces-full
- **GIVEN** `gate-scope.json` 声明 `anchor_max_hops: 1`
- **AND** change `c` 的旧基线后有非测试改动，锚点池里全部锚点的 `hops` 都是 1
- **WHEN** 运行 baseline
- **THEN** `mode` 为 `full`
- **AND** `reuse_skipped` 有一条含「上限 1」
