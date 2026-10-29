# DRAFT. 测试分层按部件组织，非 pytest runner 经 JUnit 与探针适配器两种契约接入

- Status: accepted
- Date: 2026-10-29
- 关联：DRAFT-test-tiers-unit-baseline-by-audit-probe · DRAFT-test-gate-baseline-diff · DRAFT-final-incremental-by-dependency-anchor（均保持在役）
- 来源 change：test-tiers-polyglot（design D1–D10）

## Context

测试分层（DRAFT-test-tiers-unit-baseline-by-audit-probe）有两个前提：一个仓库只有一个单元层命令，探针只认 pytest。在多语言 monorepo 里，这两个前提都不成立：

- Go、Python、TS 子项目的单元测试没法用一条命令表达；
- 先后跑两个 pytest 会让失败差分判为不可度量；
- 各子项目的 runner 输出相对自己的工具链根，和以 git 顶层为准的 `owns`、`scenario_tests` 对不上；
- 非 pytest 语言没有 Python 审计钩子那样的进程内机制，纯度与耗时都无从取证。

用户（2026-10-29）两轮决策全取推荐：选择器 `paths` / `list`；JUnit 契约；探针适配器 + 库出题的金丝雀自检 + 哈希锁定；`test_files`；只做分层；全仓一份分层文件内含多个部件；`gate.test` 写驱动命令；baseline / final 全部部件都跑。

## Decision

- **部件**：
  - 一个部件 = 一个子项目目录（`root`）× 一种 runner，各有自己的 `test_files`、单元层、区域；
  - 全仓单元层 = 各部件单元层之并；
  - 分层文件全仓一份，顶层写 `parts`；
  - 旧的 `{unit, regions}` 是简写形态，行为原样保留，新能力只在部件形态提供。
- **顶层坐标**：
  - 分层文件、`owns`、`covers`、`scenario_tests`、`slow_allow` 与门禁文本里的路径一律相对 git 顶层；
  - 命令在部件 root 下运行；runner 输出由库补 root 前缀。
- **选择器**：每层二选一，`paths`（glob）或 `list`（root 下运行、每行输出一个测试文件的命令）。粒度仍是文件。
- **恰属一个部件、恰落一层**：
  - `check` 与 G12 机械校验；
  - 没写 `test_files` 的部件用内置的多语言命名规则兜底。
- **驱动命令**：
  - 部件形态下 `gate.test` 逐字等于 `python3 .claude/hooks/test-tiers.py run unit`，它是人与 CI 可跑的真实命令；
  - 门禁不执行它，而是逐部件运行、逐部件判定；
  - 部件命令由 preflight / final 与基线记录对账。
- **JUnit 契约**：逐用例耗时取自库给的 `$FLIGHT_JUNIT`，或本次运行新写出的 `unit.junit` 报告。
- **探针适配器契约**：
  - 库运行仓库内的适配器，传 `FLIGHT_UNIT_CMD`；
  - 适配器执行它，并按内置探针的同一 JSONL 格式报告逐用例触碰与耗时。
- **金丝雀自检**：
  - 库每次生成随机令牌与目录，让适配器跑四个约定命名的金丝雀用例；
  - 纯用例无触碰、文件 / 子进程 / 网络各被报出、令牌文件确实落盘，才写入适配器文件的 sha256；
  - 适配器改动后哈希不符即 lint 红。
- **逐部件判定**：
  - G10：耗时取探针或 junit，慢候选以整部件重跑一次确认；
  - G11：取探针，测不了时只警告；
  - pytest 部件保留逐条差分，其他部件按退出码判。

否决的方案：

- **每个子项目一份分层文件、递归发现**：跨子项目的 change 要合并多份，唯一性与不重不漏要跨文件校验。
- **单一单元层 + 聚合脚本**：多次 pytest 让差分失效，库无法逐部件判。
- **`gate.test` 留空、库直接读分层文件**：`gate.test` 被 `plan_sha`、G7 推导、verify 推导、增量 final 多处使用，也会失去一条命令跑全部单测的入口。
- **按 `covers` 选择性跑部件**：共享库被改时，`covers` 漏写就漏测。
- **为每种语言内置探针**：Go / JVM / Node 没有进程内审计机制，可用的系统级追踪与平台强相关，内置维护不起。
- **解析各 runner 文本输出取耗时**：每种 runner 一套解析器；JUnit XML 是公共格式。
- **简写在内部规范化成部件、走同一路径**：简写仓库会失去增量 final 与逐 nodeid 重跑。

## Consequences

- **更易**：多语言 monorepo 能用一份分层文件把每个子项目的单元层纳入基线；非 pytest 部件第一次有 G10，也能通过适配器得到 G11。
- **更易**：简写形态与无分层文件的仓库行为、输出、`plan_sha` 都不变。
- **更难**：仓库要维护部件声明。需要 G11 的非 pytest 部件还要维护适配器与金丝雀用例，适配器每次改动都要重新自检。
- **代价**：部件形态下 final 恒全量；非 pytest 部件只看退出码，基线已红就停飞；G7 仍只实跑 pytest scenario。三者都留给后续 change。
- **代价**：金丝雀只证明适配器报得出三类触碰，不证明没有盲区；适配器只对金丝雀认真属蓄意作弊，靠审批页与 PR diff 兜住。
- **代价**：`probe.sha` / `checked` 可被直接编辑绕过自检，与 `slow_allow` 同一信任模型（G6 所有权 + PR diff）。
- **与在役 ADR**：
  - DRAFT-test-tiers-unit-baseline-by-audit-probe 的各项决定全部保留，本 ADR 只扩展适用范围；
  - 差分仍按 DRAFT-test-gate-baseline-diff；
  - 部件形态不走增量，属 DRAFT-final-incremental-by-dependency-anchor 适用范围外。
  - 均不 supersede。
