## Why

收口阶段的 final 在依赖图没接通的仓库里几乎每次都是全量（方案页 `docs/flight-fixes-and-test-governance.html` 第 02b 节，本 change 是其中的 C1b）：

- **为什么会重跑**：`slice-gate.py ship` 只认对齐 HEAD 的 final，final 之后只容忍记账文件。`/pr-ship` 自己还会产生两类提交——记忆沉淀（改 CLAUDE.md）与评审修复——所以命令文档规定这两处之后各重跑一次 final（`template/.claude/commands/pr-ship.md` step 2b 与收尾复裁）。
- **为什么是全量**：重跑走增量还是全量，只取决于上一次 final 留下的锚点有没有测到依赖图。没测到就是「没有可用锚点」。
- **实测**（各 change 时间线里 apply-done 之后的 final 行，2026-11-18 只读统计）：afa 收口阶段全量 49 次，原因全部是「没有可用锚点」；本仓 2 次，都在 `incremental-final` 这个 change 自己。本仓近期收口的重跑都是「增量，重跑 0–4 个文件」。

机制按设计在工作，出问题的是它的退路：一个只改了 CLAUDE.md 的提交、或只改了一个测试文件的修复提交，在没有依赖图的仓库里会换来一整遍全量，一次收口至少两遍。模板不该要求「先有完整依赖图」才能认出这两种最便宜的情形。

另外，基线复用把 `.claude/skills/…`、`CLAUDE.md`、迁移脚本这类与测试无关的改动一律算「有非测试文件改动」而退回全量（交接 T4）。仓库没有办法告诉门禁「这些路径不影响测试结论」。

C1 `plan-hygiene`（已合入）让「依赖图未测」必须表态；本 change 给表态之后仍然没有依赖图的仓库两条便宜的路，并让有依赖图的仓库也能少一次无意义的重跑。决策来自方案页与 2026-11-18 的对话，没有另开 `grill-me` 访谈。

## What Changes

- **`gate-scope.json` 新增可选字段 `inert`**（`template/.claude/hooks/slice-gate.py`）：仓库相对路径 glob 的字符串数组，含义是「这些路径的改动不影响测试结论」。不做任何缺省，由仓库自己声明。
  - 生效处与记账文件同等看待：`ship` 的新鲜度；final 的同树沿用与取锚点时的 Δ；baseline 的复用判定（本 change 旧基线 / 基线池路径，以及经锚点路径）。
  - 永不按 `inert` 处理的路径：测试路径、全局文件、`global` 命中的路径、`changes/` 下的路径、三份声明文件（`gate-scope.json` / `gate-checks.json` / `test-tiers.json`）。
  - 起飞前检查（preflight）的「基线过期」判定、lint / typecheck 结论的沿用条件不看 `inert`（见 design D2）。
- **`inert` 的静态核对与依赖图对账**（`slice-gate.py` 的选测复核、`flight-doctor.py doctor`）：
  - glob 匹配到已跟踪的测试路径、全局文件或 `global` 路径 → lint / preflight 判红并点名。
  - 有测到依赖图的锚点、且某个测试文件依赖了匹配 `inert` 的路径 → lint / preflight 判红，点名路径与测试文件。
  - final 运行时遇到这种矛盾，按依赖图处理（照常重跑）并给警告。
  - `doctor` 的 `[declare]` 一节列出 `inert` 的值与矛盾；没有测到依赖图的锚点时注明无法对账。
- **final 的无图退路**（`slice-gate.py` 的 `cmd_final` 与 `final_forecast`）：没有可用锚点、也没配 `gate.impacted` 时，若本 change 上一次绿 final 之后的 Δ（去掉记账文件与 `inert`）只含 `test_*.py`，只重跑这些测试文件，其余沿用上次绿 final 的结论。
  - 结果里 `incremental.source` 为 `tests-only`；时间线备注以「增量（无图」开头；`GATE_TEST_RESULT` 的 `mode` 新增取值 `tests-only`。
  - 不适用时仍全量；因为上次绿 final 之后有非测试文件改动而不适用时，全量原因点名这些文件，成本预告与 `ship` 的「final 过期」理由事先说明。
  - 这条路不写锚点。
- **`/pr-ship` 先裁决再重跑**（`template/.claude/commands/pr-ship.md`）：记忆沉淀提交之后先跑 `slice-gate.py ship`；reasons 里没有 `final 过期` 就不重跑 final。评审修复之后的重跑规则不变。
- **文档**：`flight-runner-contract.md`（`inert` 一行、边界与对账、结果文件 `mode` 的新取值、接入步骤）、`opsx-propose.md` 与同名 skill、schema 的 tasks instruction、`README.md` 的可选字段清单。
- **不做**：
  - 不给 `inert` 任何缺省值，也不按文件类型推断（本仓就有读 CLAUDE.md 与文档的测试）。
  - 不改 `gate.impacted` 路径的 Δ（仓库自己的选测自己负责）。
  - 无图退路不处理配了测试分层文件的仓库，也不处理增量重跑无法等价复现 `gate.test` 的仓库（没配 `gate.pytest` 的包装脚本）。
  - 不动全机测试闸与 final 耗时进时间线（C2）、切片接续与留痕（C3）、wave 集成检查（C4）。
  - C1 留下的「内建声明下的非 pytest 运行器与部件形态豁免表态」维持现状。

## Capabilities

### New Capabilities

- `inert-paths`：仓库声明改动不影响测试结论的路径；三处生效、五类路径永不生效；静态核对与依赖图对账；`doctor` 列出声明与矛盾。
- `tests-only-final`：没有可用锚点时，上次绿 final 之后只改了测试文件的 final 只重跑这些文件；预告、时间线、结果交接认得这个模式。
- `ship-rerun-decision`：只改 CLAUDE.md 的提交在三种配置下的收口行为；`/pr-ship` 先裁决再决定是否重跑 final。

### Modified Capabilities

- 无。`template/openspec/specs/` 不存在，现有行为的规格都还在各自的 change 目录里；本 change 的增量全部以 ADDED 写在上面三个新 capability 里。

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`、`template/.claude/hooks/flight-doctor.py`。
- **文档**：`template/.claude/commands/pr-ship.md`、`template/.claude/flight-runner-contract.md`、`template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md`、`template/openspec/schemas/intent-driven/schema.yaml`、`README.md`。
- **ADR**：新增 `DRAFT-inert-paths-declared-and-reconciled.md`、`DRAFT-final-tests-only-rerun-without-graph.md`（后者修订 `DRAFT-final-incremental-by-dependency-anchor` 决策 4 的「没有可用锚点即全量」，原文不改）。
- **测试**：新增 5 个测试文件（20 条 scenario 骨架 + 1 条既有行为守卫）。在一次性副本上按 design 做了原型并跑全量：没有旧测试受波及。
- **契约**：`GATE_TEST_RESULT` 的 `mode` 多一个取值 `tests-only`。按契约只认 `mode == "full"` 的检查不受影响；枚举了全部取值的检查需要补一支。
- **下游**：已安装的仓库 `./install.sh --upgrade` 后行为不变，直到在 `gate-scope.json` 里写了 `inert`，或出现「上次绿 final 之后只改了测试文件」的重跑。
- **与在途 change 的交叠**：C2 `machine-test-lock`（未合入）也改 `cmd_final` 的时间线备注与 `flight-doctor.py`，后合入的一方在预合并时要解冲突。
