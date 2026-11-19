## Why

`/opsx-propose` 太慢。审批页 `docs/flight-routing-config.html` 第 02 节的实测（20 次有工件的 propose）：
- **四个阶段的平均耗时**：P0 准备 23.4 分钟、P1 成稿 16.3 分钟、P2 4.1 分钟、P3 收尾 15.5 分钟；
- **时间花在哪**：每次串行输出约 16 万 token，工具执行不到 4 分钟。所以快慢由「模型逐字写了多少」决定；
- **写入量的构成**：测试骨架占 24%，模型自己写的 `/tmp` 脚本占 20%，切片包占 16%，verify 脚本占 5%。其中很多是机械搬运：Gherkin 原文抄进 GWT 注释、owns / verify / deps 抄进切片包、tasks.md 按 slices.json 抄一遍、每个工件分别调用一次 `openspec instructions`；
- **P3 卡在 baseline**：P3 主要在等 baseline，afa 的中位数是 8.9 分钟，最长 64 分钟，而且它排在最后才开始跑。

用户 2026-11-19 回复「全按推荐」，C2 相关的选择：
- Q8-A：只在补断言这一步用 fork 并行，调研和决策类工件由主会话亲自做；
- Q9-A：做 baseline 预热；
- Q10-A：顺序为 C4 → C1 → C2 → C3。

另有用户原话约束：「最终的解决方案和规划还是要继承主会话」。规划期的模型产出只能来自主会话或 fork（铁律 11，C1 已落地）。

## What Changes

- **新增 `.claude/hooks/plan-kit.py`**，三个零 token 子命令：
  - `instructions --change <name>`：一次打印全部待建工件的 instruction / template / rules，代替逐个工件调用 `openspec instructions`；
  - `tasks --change-dir`：由 `slices.json` 生成 `tasks.md`，已勾选的切片保持勾选；
  - `packets --change-dir`：渲染 `slices/<S>.md` 的机械区（标题、owns、依赖切片、scenario 的 Gherkin 原文、verify），机械区由标记包住；标记之外由主会话写的说明原样保留。
- **新增 `.claude/hooks/plan-scaffold.py`**，两个子命令：
  - `scaffold --change-dir`：按 `scenario_tests` 为缺失的测试函数生成 strict-xfail 骨架。GWT 注释取 Gherkin 原文，函数体是一条带固定占位标记的必败断言；已有的函数不动；首版只支持 pytest，其他语言列为跳过；
  - `gwt --change-dir`：规划期的 G4 自查（GWT 注释齐全且顺序正确），并找出残留的占位标记。
- **`slice-gate.py lint` 加一条红线**：scenario 测试函数里还留着 scaffold 占位标记时判红，没补断言的计划不能起飞。
- **新增 `slice-gate.py warm --change-dir`**：建好 change 目录后立即在后台跑一次全量，结果写成本 change 的预热基线。
  - **命令怎么定**：`--cmd` 显式给出时用它；否则沿用最近一个 change 的 `gate.test`。该命令引用的、位于那个 change 目录下的脚本，复制到本 change 的同一相对位置，并把命令改为指向本 change。
  - **跳过条件**：分层仓库（有 `test-tiers.json`）恒走全量，预热帮不上，直接跳过；找不到可沿用的命令时也跳过。
  - **复用**：正式 `baseline` 按现有「本 change 旧基线」规则判断：命令指纹相同、Δ 只有测试文件 → 只补跑这些测试文件。
  - **等待**：正式 baseline 发现预热仍在跑时，先等它结束。
- **`/opsx-propose` 命令与 skill（同改）改用上面的工具**：
  1. 建 change 目录后后台预热；
  2. 一次取全部 instruction；
  3. 写完 slices.json 后依次 packets → scaffold；
  4. 补断言按测试文件分组：多于 1 组时用 fork 并行，每个 fork 只改分到的文件；fork 不可用时由主会话串行补；只有 1 组时由主会话自己写；
  5. 然后 gwt 自查 → tasks → lint → pin。
- **规划期不变式测试放宽一处**：规划类文档里的派发只允许 fork（`subagent_type: "fork"`），其他派发仍判红。

## Capabilities

### New Capabilities
- `plan-kit-commands`：instructions / tasks / packets 三个零 token 子命令。
- `scenario-scaffold`：scaffold 与 gwt 两个子命令，以及 lint 对占位标记的红线。
- `baseline-warm`：预热子命令、命令的沿用与跳过、正式 baseline 等待并复用预热结果。
- `propose-fork-assertions`：propose 流程改用工具链，补断言用 fork 并行并配串行回退，规划期派发只允许 fork。

### Modified Capabilities
（无：`openspec/specs/` 目前为空）

## Impact

- **新增**：
  - `template/.claude/hooks/plan-kit.py`、`template/.claude/hooks/plan-scaffold.py`；
  - `tests/test_plan_kit.py`、`tests/test_plan_scaffold.py`、`tests/test_baseline_warm.py`、`tests/test_propose_speedup_docs.py`。
- **修改**：
  - `template/.claude/hooks/slice-gate.py`：新增 warm 子命令；baseline 等待预热；lint 判占位标记；
  - `template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md`；
  - `tests/test_routing_docs.py`：放宽规划期派发，只允许 fork。
- **不变**：
  - baseline 的复用规则本身不改，预热只是提供一个候选；
  - takeoff-gate、preflight 不改：预热基线不带 `plan_sha`，正式 baseline 一定会覆盖它；
  - `/opsx-continue` 与 schema 的 tasks instruction 不改，留给后续。
- **验证方式**：合入后用同一套探针重测 3 次 propose，前后对比；提速幅度不预估。
