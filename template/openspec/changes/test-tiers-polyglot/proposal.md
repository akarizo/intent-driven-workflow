## Why

测试分层（change `test-tiers`）目前只认 pytest、只认一个单元层：

- 分层文件只有一个 `unit.cmd`，lint 要求 `gate.test == unit.cmd`。Go、Python、TS 三个子项目的单元测试没法用一条命令表达。
- 探针只认 pytest，非 pytest 仓库的 G10 / G11 只能降级为警告。逐用例耗时只来自 pytest 插件。
- 失败差分要求输出里**恰好一行** pytest 汇总行（`slice-gate.py` `run_test_gate`）。先后跑两个 Python 子项目，就会被判「调用了多次 pytest」，差分失效。
- 命令都在 git 顶层运行，用例 id 也相对顶层。子项目各有自己的工具链根（`go.mod` / `package.json` / `pyproject.toml`），runner 输出相对子项目，和 `owns`、`scenario_tests` 对不上。
- 测试文件靠 `TEST_FILE_RE` 认，它不认识 `_test.go`、`FooTest.java` 这类命名。

用户要求（2026-10-29）：分层要语言通用，还要支持 monorepo，且 monorepo 可能是多语言的。

用户决策（2026-10-29，决策页 `template/openspec/superpower/2026-10-29-test-tiers-polyglot-decisions.html`，代替 grill-me 访谈；两轮共 8 项，全取推荐）：

- **Q1 切法**：路径与列表两种选择器（`paths` / `list`），`check` 机械校验不重不漏。
- **Q2 逐用例耗时**：JUnit XML 契约（`$FLIGHT_JUNIT` 或报告路径 glob）。
- **Q3 单测纯度**：探针适配器契约 + 库出题的金丝雀自检，适配器哈希锁定。
- **Q4 测试文件**：`test_files` glob，按部件填写。
- **Q5 范围**：只做分层。G7、失败差分走 junit、依赖图语言通用化，另立后续 change。
- **M1 结构**：全仓一份分层文件，内含多个**部件**。一个部件 = 一个子项目目录 × 一种 runner。旧写法视作单部件简写。
- **M2 `gate.test`**：部件形态下写库自带的驱动命令 `python3 .claude/hooks/test-tiers.py run unit`。baseline / final 认出它后逐部件运行、逐部件差分。
- **M3 跑哪些部件**：baseline / final 跑全部部件的单元层。

## What Changes

- **分层文件新增「部件形态」** `{"parts": {NAME: {root, test_files?, unit, regions?}}, "slow_allow"}`：
  - 旧的 `{unit, regions, slow_allow}` 是**简写形态**，字段、行为、输出不变；
  - 简写形态不接受新字段。要用 `list` / `junit` / `probe` / `test_files`，就写部件形态（一个部件也行）。
- **坐标系**：分层文件、`owns`、`covers`、`scenario_tests`、`slow_allow` 键里的路径一律相对 git 顶层。部件的命令在部件 `root` 下运行。runner 输出的路径由库补上 `root` 前缀。
- **选择器**：单元层与区域二选一：`paths`（glob）或 `list`（在部件 root 下运行的命令，每行输出一个测试文件路径）。
- **测试文件识别**：部件写了 `test_files` 就以它为准，没写就用 root 下的内置命名规则（在 `TEST_FILE_RE` 之外另认 Go、JVM、C#、Ruby、Rust 的常见命名）。
- **JUnit 契约**：库给每次部件运行设 `$FLIGHT_JUNIT`。命令可以把 junit 写到这里，也可以在 `unit.junit` 写报告路径 glob。耗时取自 junit 的 `time`。
- **探针适配器契约**：`unit.probe = {cmd, canary, canary_files, sha, checked}`：
  - 库运行 `probe.cmd` 时传 `FLIGHT_UNIT_CMD`（要跑的测试命令）与 `FLIGHT_TIER_OUT`（逐用例记录），格式与内置 pytest 探针相同；
  - `test-tiers.py canary` 生成随机令牌出题，跑金丝雀用例。纯用例无触碰、文件 / 子进程 / 网络三个用例各被报出、文件确实落盘，才算通过；
  - 通过后把适配器文件的 sha256 写进 `sha`。文件一改，lint 就红，直到重新自检。
- **部件形态下的门禁**：
  - lint：`gate.test` 须逐字等于驱动命令；区域名全仓唯一；不允许 `gate.impacted`；
  - baseline / final 不运行驱动命令，而是在各部件 root 下直接逐个运行单元层；
  - 差分：pytest 部件按 junit 逐条差分，其他部件只看退出码；
  - G10 / G11 逐部件判：耗时取探针或 junit，慢候选以整部件重跑一次确认；纯度取探针，测不了时只给警告；
  - preflight 逐部件对账单元命令；
  - final 恒全量；
  - `tier_sec` 增加 `parts` 分项。
- **G12 / `check`**：每个测试文件须恰好属于一个部件，再在该部件内恰好落一层。
- **`test-tiers.py`**：
  - 新增 `run unit`（驱动）与 `canary`；
  - `probe` 增加 `--root` / `--adapter`；
  - `check` / `render` 支持部件形态。
- **文档**：`/test-tiers` 命令、schema tasks instruction、`opsx-propose` 命令与同名 skill、README、`CLAUDE.md.snippet`。

## Capabilities

### New Capabilities
- `test-tiers-polyglot`：分层文件的部件形态（root、test_files、paths / list 选择器、JUnit 契约、探针适配器与金丝雀自检），以及部件形态下的 lint、G12、逐部件运行的 baseline / final / preflight、G10 / G11、`tier_sec.parts`、驱动命令与 `test-tiers.py` 新子命令、文档。

### Modified Capabilities
<!-- 无：template/openspec/specs/ 不存在（test-tiers 尚未归档进主 spec）；简写形态的行为不变 -->

## Impact

- `template/.claude/hooks/slice-gate.py`：
  - 分层文件加载：区分两种形态，部件形态做形状校验、选择器解析、适配器哈希核对；
  - `_lint_tiers` 与 `cmd_gate` 的 G12 支持部件形态；
  - 新增部件运行器：在 root 下运行，提供 `FLIGHT_JUNIT` / `FLIGHT_UNIT_CMD` / `FLIGHT_TIER_OUT`，用例 id 换成相对顶层；
  - 新增逐部件 G10 / G11 判定；
  - `cmd_baseline` / `cmd_final` / `cmd_preflight` 增加部件形态分支，`tier_sec.parts`。
  - 简写形态与无分层文件的代码路径不改行为。
- `template/.claude/hooks/test-tiers.py`：新增 `run`、`canary` 子命令；`probe` / `check` / `render` 扩展。
- 文档：`template/.claude/commands/test-tiers.md`、`schema.yaml`、`opsx-propose` 命令与 `openspec-propose` skill、`README.md`、`template/CLAUDE.md.snippet`。
- 测试：新增 `tests/test_tiers_parts_plan.py`、`tests/test_tiers_parts_runner.py`、`tests/test_tiers_parts_gate.py`、`tests/test_tiers_parts_cli.py`、`tests/test_tiers_parts_docs.py`；既有测试不改。
- ADR：新增 `DRAFT-test-tiers-parts-and-runner-contracts`。`DRAFT-test-tiers-unit-baseline-by-audit-probe` 继续有效，不 supersede（关系见 design D10）。
- 兼容：
  - 没有分层文件、或用简写形态的仓库，lint / gate / baseline / final / preflight 的行为与输出不变；
  - 包括 `plan_sha`、增量 final、`gate-baseline.json` 的键。
- 已知边界（Q5 与决策页「代价与风险」）：
  - 部件形态下 final 不走增量（依赖图只认 pytest）；
  - 非 pytest 部件只看退出码，基线上已红的非 pytest 部件会让 baseline 停下；
  - G7 仍只实跑 pytest 形式的 scenario 测试；
  - 适配器能否测准取决于它自己，金丝雀只证明它报得出三类触碰；
  - `sha` / `checked` 被人手编辑可绕过自检，与 `slow_allow` 同一信任模型。
