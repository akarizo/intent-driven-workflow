## Why

模板里"复用测试结果"的三条路——基线复用、增量 final、检查——彼此不通，代价也看不见。afa 一个 change 一天跑了 5 次全量基线，final 里又多跑一遍全量，最后是人自己发现才来问。对本机 7 个已安装项目做了只读盘点（2026-11-09，数字均为下限）：

- **afa**：
  - 全量基线 95 次、合计 37,633 秒，复用成功只有 6 次；
  - 首次基线没有任何候选：64 次 / 28,161 秒；
  - 重新规划时，切片代码已经落地，基线必然全量：17 次 / 6,337 秒；
  - final 因"没有可用锚点"全量 33 次；锚点池 20 条里只有 2 条测到依赖图；
  - 检查因缓存键混进了 `FLIGHT_*`，再跑一遍全量：25 次。
- **gateway**：不是 pytest，又没配 `gate.impacted`，final 每次全量。
- **其余 6 个项目**的 slice-gate 都比模板旧。

方案与证据见 `docs/full-suite-reuse-rootfix.html`（主仓库工作区，未入库）。用户已逐项决策（Q1–Q6）：合成一个 change，项目侧适配由用户在各项目自己做。

## What Changes

- **结果交接**：final 跑完 gate.test 后写出本次测试结果文件，经新变量 `GATE_TEST_RESULT` 交给 `gate.checks`；锚点另记逐用例结局，增量 final 也能交出完整结局。`FLIGHT_*` / `GATE_*` 写进契约，声明为每次运行都会变的变量；gate.test 的环境里加上 `GATE_PHASE` / `GATE_CHANGE`，包装脚本不必再写死 change 名。
- **运行器契约**：新增导出 `FLIGHT_PLUGIN_PATH` / `FLIGHT_PYTEST_ARGS`，会重建环境的包装脚本把这两个变量转发给 pytest，依赖图就能测到。"依赖图未测"拆成四类原因（不是 pytest / 插件被丢弃 / 插件导入失败 / 记录不完整），每类带修法。新增契约文档 `template/.claude/flight-runner-contract.md`，随安装下发。
- **项目级声明**：`<openspec 根>/gate-scope.json` 在 `cmd` / `builtin` 之外可选 `global`（命中即全量）、`blind`（匹配的测试文件每次都重跑）、`anchor_max_hops`（锚点链上限）。
- **基线走锚点**：基线候选扩大为"本 change 旧基线 → 锚点池（任意来源，可跨 change，须测到依赖图）→ 基线池"。有非测试改动时，按 final 已有的选测与全量触发规则只补跑受影响的测试。跨 change 带预存红只能经锚点路径复用（锚点上失败的文件一定重跑），基线池仍只收全绿（**修订 2026-10-15 用户决策**，新 ADR 取代旧论证）。红基线的测试部分本身有效时可按部件复用。同 change 门禁脚本只计 gate.test 闭包里实际用到的。
- **cmd_key 归一**：命令直接引用的文件内容里出现的本 change 名，先归一再算指纹，并纳入静态 shell 闭包。各 change 的同款包装脚本因此能互相复用。**BREAKING（一次性）**：升级后旧的基线、锚点、池条目指纹全部失配，各跑一次全量后恢复。
- **锚点链上限**：锚点记录"由增量推出的代数"，达到 K 代（默认 5，`anchor_max_hops` 可调）就强制全量。基线与增量 final 共用这条规则（用户决策）。**BREAKING（行为）**：已经在正常增量的项目，升级后会周期性多跑一次全量。
- **测试成本可见**：新增零 token 脚本 `flight-doctor.py`：
  - `forecast`：在 baseline 报告行、`/opsx-apply` 起飞前和 spec.html 里，给出"这次 baseline / final 会不会全量、为什么、大约多少秒"；
  - `cost`：收口时汇总本 change 的全量次数与原因，分"必要"与"可避免"两类；
  - `doctor`：项目级体检，`install.sh --upgrade` 结束时自动跑，只报告。
  - 全部只预告，不阻断（用户决策 Q3）。
- **规划指引**：propose 的命令与 skill 同步写明——包装脚本要转发运行器契约、用 `$GATE_CHANGE`、不写死 change 名；基线复用规则的描述随实现更新。

## Capabilities

### New Capabilities
- `gate-test-result-handoff`：final 把本次测试结果交给检查；易变变量契约；gate.test 环境带阶段与 change 名。
- `flight-runner-contract`：包装脚本转发依赖图插件的契约变量；依赖图未测的四类原因；项目级 `global` / `blind` 声明。
- `baseline-anchor-reuse`：基线经锚点复用（含跨 change 带预存红）、红基线按部件复用、cmd_key 归一与 shell 闭包、门禁脚本闭包口径、锚点链上限。
- `test-cost-visibility`：成本预告（forecast）、收口全量归因（cost）、项目体检（doctor）及其在 propose / apply / spec.html / 安装升级中的出现位置。

### Modified Capabilities
- 无：`openspec/specs/` 下还没有已归档的规格。相关的旧行为（基线复用、增量 final、检查注入）都定义在尚未归档的 change 里，本 change 以新增能力的方式写明修订点，并在 design 里逐条对照。

## Impact

- **代码**：
  - `template/.claude/hooks/slice-gate.py`（基线、final、run_test_gate、锚点、cmd_key、选测声明、检查环境）；
  - 新增 `template/.claude/hooks/flight-doctor.py`；
  - `template/.claude/hooks/spec_html.py`（成本预告段）；
  - `install.sh`（升级后跑 doctor）。
- **文档**：
  - 新增 `template/.claude/flight-runner-contract.md`；
  - `opsx-propose` / `opsx-apply` 命令与同名 skill；
  - `template/openspec/schemas/intent-driven/schema.yaml` 的选测声明描述；
  - README。
- **ADR**：新增 `DRAFT-baseline-reuse-via-dependency-anchor`，取代 `DRAFT-baseline-reuse-by-content-fingerprint` 的"跨 change 只复用全绿"与"只认测试文件 Δ"两项；新增 `DRAFT-gate-test-result-handoff-and-runner-contract`（检查与包装脚本的两份运行契约）。
- **兼容**：
  - 旧检查不读 `GATE_TEST_RESULT`，行为不变；
  - 旧的 `gate-scope.json` 不带新字段，行为不变；
  - 不转发契约的包装脚本行为不变（全量），只是现在会被预告和归因；
  - cmd_key 算法变化与锚点链上限，各让每个项目多跑一次全量。
- **不在本 change**：afa testgate 的契约适配、检查改读 `GATE_TEST_RESULT`、headrun 缓存键剔除 `FLIGHT_*`、gateway 配 `gate.impacted`（用户在各项目自己做，本 change 只交付契约文档）；把 afa 临时修复加回去。
