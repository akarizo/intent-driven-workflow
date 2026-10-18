## Why

afa 仓（`ameco-rsr2602/decoder/air-fanst`）正在把 executor 的测试体系拆成 S0–S4 五个 change 重构，用户硬要求每一步「迁移之后代码覆盖对得上」。落到门禁上要两类检查：

- **覆盖对拍**：merge-base 量一次、分支头再量一次，按「模块 · 函数 · 行文本」对齐比较；
- **共用包联动回归**：改动碰到 `packages/` 时另一个子项目的环境也跑回归，按它自己的基线差分。

两者都是「两次测量 + 比较」或「按改动触发、自带基线」，今天的 `gate.test` / `lint` / `typecheck` 只有单次运行加失败集差分，表达不了。afa 的 CI 里 executor 没有测试 job，所以飞行流程的 slice-gate 是唯一生效的门禁。

覆盖测量、对齐规则、子项目回归都与仓库强相关，不进模板。模板只需要一个通用扩展点：baseline 与 final 各调用一次仓库自定义命令，红就不收口。

来源：afa 的跨仓提案 `docs/proposals/2026-10-17-slice-gate-paired-checks-from-afa.md`（主仓库工作区，未入库）。对照代码 `template/.claude/hooks/slice-gate.py` @ main `766d3fa`。

用户决策（2026-10-17，评审页逐项选择，代替 grill-me 访谈；6 项全取推荐）：

- **沿用规则完全照 D10**（`baseline-incremental-reuse` design D10）：本次增量、候选是本 change 旧基线、严格差异为空、命令与 `cmd_key` 不变才沿用；跨 change 候选与 `--full` 一律实跑。提案 §2.3「增量模式一律不沿用」与此矛盾，按 D10 改正。
- **preflight 不加新规则**：检查的 `name` 与 `baseline` 命令并入 `plan_sha`（只在配置了检查时追加），复用现有「基线红 / 基线过期」。
- **仓库默认检查本 change 一起做**，默认文件按 change 目录往上两级找（`<change_dir>/../../gate-checks.json`），安装后的仓库与本仓库（`template/openspec/`）两种布局都成立。
- **检查的 baseline 实跑前清空它的共用目录**，防止 final 读到上一次基线的残留。
- **完整输出落盘**：`$GATE_CHECK_DIR/.gate-<phase>.log`；红时只带末尾 20 行加日志路径。
- **命名照提案**：`gate.checks` / `gate.checks_skip` / 环境变量 `GATE_*` / 目录 `flight-gate-checks` / 失败编号 G9。

评审页还列了 6 条直接写进规格的约定，用户未反对：final 缺基线记录即红；超时整组结束进程；未配置时行为与输出不变；G7 红时另加一条「G9 检查未跑」；lint 校验检查的形状；命令与同名 skill 同改。

## What Changes

- **配置**：`slices.json` 的 `gate` 新增可选 `checks`（数组：`name` / `baseline` / `final` / `timeout_sec`）与 `checks_skip`（`{name: 理由}`）。
- **运行契约**：检查命令在 git toplevel 经 shell 执行，注入 `GATE_PHASE` / `GATE_CHANGE` / `GATE_BASE_COMMIT` / `GATE_CHECK_DIR`；共用目录在 `<git common dir>/flight-gate-checks/<change>/<name>/`，同仓各 worktree 可见、不进 commit；只看退出码；完整输出写 `.gate-<phase>.log`；配置了 `timeout_sec` 时超时整组结束进程并判红。
- **baseline**：在全量、lint / typecheck、每片 verify 之后运行每个 `baseline` 非空的检查，记入 `gate-baseline.json` 的 `checks.<name>`；红即基线红；沿用照 D10；实跑前清空共用目录；基线池条目不含检查结果。
- **preflight**：只把检查的 `name` 与 `baseline` 命令并入 `plan_sha`，不新增校验代码。
- **final**：G7 绿时，在全量 `gate.test` 判定之后（无论全量红绿）运行每个检查的 `final`，非 0 记 `G9 check <name>`；基线缺记录也记 G9；G7 红时不跑并另加一条警告。
- **仓库默认检查**：openspec 根目录下可放 `gate-checks.json`；`slice-gate.py lint` 要求其中每个检查出现在本 change 的 `gate.checks`，或在 `gate.checks_skip` 写明非空理由。
- **lint 校验形状**：`name` 合法且不重复、`final` 非空、`baseline` 为 null 或非空字符串、`timeout_sec` 为正数、不认识的字段报错、`checks_skip` 理由非空且不与 `gate.checks` 同名。
- **文档**：schema 的 tasks instruction 写明 `gate.checks` 与仓库默认检查；`opsx-propose` / `opsx-verify` 命令与同名 skill、README 写明检查的运行时机与契约。

## Capabilities

### New Capabilities
- `gate-paired-checks`：slice-gate 的成对检查扩展点：计划校验与仓库默认检查、运行契约、baseline 运行与沿用、preflight 对账、final 的 G9、未配置时不变、文档。

### Modified Capabilities
<!-- 无：template/openspec/specs/ 不存在，slice-gate 行为此前没有归档的 capability -->

## Impact

- `template/.claude/hooks/slice-gate.py`：
  - `lint_plan` 增加检查形状与仓库默认检查规则（调用方 `cmd_lint` / `cmd_preflight` 传 change 目录）；
  - `plan_sha` 在配置了检查时追加 `[name, baseline]`；
  - `cmd_baseline` 在 verify 之后、运行期间改动判定（D6）之前运行检查；
  - `cmd_final` 在全量判定之后运行检查；
  - 新增带超时、整组结束进程、完整输出落盘的检查运行函数。
- 文档：`template/openspec/schemas/intent-driven/schema.yaml`（tasks instruction）、`template/.claude/commands/opsx-propose.md` 与 `template/.claude/skills/openspec-propose/SKILL.md`、`template/.claude/commands/opsx-verify.md` 与 `template/.claude/skills/openspec-verify-change/SKILL.md`、`README.md`。
- 测试：新增 `tests/test_gate_checks_lint.py`、`tests/test_gate_checks_baseline.py`、`tests/test_gate_checks_final.py`、`tests/test_gate_checks_docs.py`；既有测试不改。
- ADR：新增 `DRAFT-gate-paired-checks-by-exit-code`；`DRAFT-test-gate-baseline-diff`、`DRAFT-baseline-reuse-by-content-fingerprint` 继续有效，不 supersede。
- 兼容：没有 `gate.checks`、也没有仓库默认文件时，baseline / final / preflight / lint 的行为与输出不变，`plan_sha` 算法结果不变，`gate-baseline.json` 不出现 `checks` 键；旧基线照常可读。
- 已知边界：
  - 检查测的往往是仓外状态（如 afa 的数据仓指纹），沿用时看不出仓外变化，与 lint / typecheck 一样用 `--full` 兜底；
  - 检查脚本如果被本 change 的切片划进 `owns`，执行体可以改弱它；信任模型与 `gate.test` 相同，靠计划审批与 G6 所有权兜住；
  - 共用目录随 change 留在 git common dir 里，没有自动回收。
