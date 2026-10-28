## Why

飞行流程的 baseline 与 final 每次都跑 `gate.test` 全量，没有「单元 / 集成」之分。本仓实测（2026-10-28，main `a20e532`，Python 3.9.6 / pytest 8.4.2，审计钩子探针逐用例记录）：

- 323 个用例里 312 个碰了真实文件或起了子进程，按「纯函数」口径只有 11 个是单元测试；
- 全量 84s，其中约 70s 来自 slice-gate 系列的子进程 + 临时仓库测试；
- 最慢单个用例 2.44s，目前没有 ≥3s 的单测，但没有任何机制防止它出现。

用户要求（2026-10-28）：

1. 测试分单元测试（纯函数、不碰真实文件，**基线就是它**）与集成测试（其余全部，只在判断确实影响到真实文件时，按模块 / package / library 分区域发起）；提供一个命令快速重划分；**设计新用例时先按这个划分定层**。
2. 每个单元测试必须 <3s，一旦超线需要人工审核放行。
3. （同日追加）每次跑门禁都要分别报告单元层耗时与集成层耗时。

用户决策（2026-10-28，决策页 `template/openspec/superpower/2026-10-28-test-tiers-decisions.html` 逐项选择，代替 grill-me 访谈；5 项全取推荐）：

- **Q1 粒度**：文件级，按路径归层；混合文件拆开。跨语言通用，区域天然对应目录 / package。
- **Q2 放行**：脚本核验人类原话后才写放行名单，判据复用 takeoff-gate 的「人类消息」口径。
- **Q3 纯度**：门禁机械强制——baseline / final 跑单元层时注入探针，碰真实文件即红。
- **Q4 范围**：本 change 只交付机制；本仓自己的 323 个测试留给下一个 change，用新命令重划分。
- **Q5 计时**：含 setup + call + teardown；超线者单独重跑一次仍 ≥3s 才判红。
- 「不得<3s」按笔误处理：每个单测必须 <3s，≥3s 触发放行流程（决策页已列明此解读，用户未反对）。

## What Changes

- **仓库级分层文件** `openspec/test-tiers.json`（openspec 根，与 `gate-checks.json` 同级）：
  - `unit`：`paths`（路径 glob）+ `cmd`（单元层运行命令）；
  - `regions`：每个区域 `paths` / `covers`（它守护的源码 glob）/ `cmd`；
  - `slow_allow`：经人工放行的慢单测，`{nodeid: {reason, approved}}`。
- **计划**：`slices.json` 的 `gate` 新增 `integration`（本 change 要跑的区域名）与 `integration_skip`（`{区域: 理由}`）。
- **lint**（前缀 `tiers:`）：分层文件形状；`gate.test` 必须等于 `unit.cmd`（基线就是单元层）；区域选择合法；`covers` 与任一切片 `owns` 相交的区域必须选上或写理由；每个 scenario 测试文件必须落在单元层或已选区域的 `paths` 内。
- **探针**：baseline / final 跑单元层时经 `PYTEST_ADDOPTS` 注入临时 pytest 插件，逐用例记「碰了文件 / 子进程 / 网络」与 setup+call+teardown 耗时；插件加载失败时去掉探针重跑，判为不可度量。
- **新失败编号**：
  - `G10` 慢单测：≥3s 且单独重跑仍 ≥3s、不在 `slow_allow` → 红；在 `slow_allow` → 警告；
  - `G11` 单测不纯：单元层用例碰了真实文件 / 子进程 / 网络 → 红；
  - `G12` 测试未归层：切片改动的测试文件不在单元层或已选区域的 `paths` 内 → 切片门禁红；
  - 区域差分沿用 `G2`：`G2 region <name>`。
- **baseline**：配置了分层时只跑单元层（带探针）与已选区域；不走增量复用；区域失败按 junit 记基线；G10 / G11 红即基线红。
- **final**：G7 绿时，单元层差分 + G10 + G11，再逐个已选区域按基线差分。
- **preflight**：已选区域的命令与基线记录不符 → 基线过期。
- **分层耗时报告**：配置了分层时，`gate` / `baseline` / `final` 的输出带 `tier_sec`（`unit` / `integration` / 各区域秒数），并写进 `summary` 与 timeline 备注，飞行记录逐行可见；G7 按用例耗时归层，单元层与区域运行按墙钟计。
- **新命令 `/test-tiers`** 与脚本 `.claude/hooks/test-tiers.py`：
  - `probe`：实跑一次，逐用例给出层级证据与耗时，按文件汇总「单元 / 集成 / 混合」；
  - `render`：把探针结果与划分稿渲染成带导出按钮的审批页；
  - `check`：每个测试文件恰好归一层；
  - `allow-slow`：核验最新一条人类消息含该用例名与放行词后，写入 `slow_allow`。
- **文档**：schema tasks instruction、`opsx-propose` / `opsx-verify` 命令与同名 skill、TDD skill（写测试前先定层）、slice-executor、README、`install.sh` 提示、`CLAUDE.md.snippet`。

## Capabilities

### New Capabilities
- `test-tiers`：测试分层（单元层 = 基线、纯函数、每用例 <3s；集成层按区域按需发起）的配置与 lint、探针、G10–G12、baseline / final / preflight 接线、`/test-tiers` 重划分脚本、文档。

### Modified Capabilities
<!-- 无：template/openspec/specs/ 不存在，slice-gate 行为此前没有归档的 capability -->

## Impact

- `template/.claude/hooks/slice-gate.py`：
  - 分层文件读取与形状校验、`lint_plan` 的 `tiers:` 规则、`plan_sha` 在有 `gate.integration` 时追加区域名；
  - `run_test_gate` 可选注入探针；`cmd_gate` 加 G12；
  - `cmd_baseline` / `cmd_final` / `cmd_preflight` 接入单元层探针、G10 / G11 与区域差分；
  - G7 插件可选记录逐用例耗时；`cmd_gate` / `cmd_baseline` / `cmd_final` 输出 `tier_sec`。
- 新增 `template/.claude/hooks/test-tiers.py`（导入 slice-gate 与 takeoff-gate 的函数，不改它们的 CLI）。
- 新增 `template/.claude/commands/test-tiers.md`（命令本身即逻辑，无同名 skill，同 `/opsx-mini`、`/pr-ship`）。
- 文档：`schema.yaml`、`opsx-propose` / `opsx-verify` 命令与同名 skill、`test-driven-development/SKILL.md`、`agents/slice-executor.md`、`README.md`、`install.sh`（命令数提示）、`CLAUDE.md.snippet`。
- 测试：新增 `tests/test_tiers_plan.py`、`tests/test_tiers_probe.py`、`tests/test_tiers_verdict.py`、`tests/test_tiers_gate.py`、`tests/test_tiers_cli.py`、`tests/test_tiers_docs.py`、`tests/test_tiers_timing.py`；既有测试不改。
- ADR：新增 `DRAFT-test-tiers-unit-baseline-by-audit-probe`；`DRAFT-test-gate-baseline-diff`、`DRAFT-baseline-reuse-by-content-fingerprint`、`DRAFT-gate-evidence-not-self-reported` 继续有效，不 supersede（关系见 design D12）。
- 兼容：没有 `openspec/test-tiers.json` 的仓库，lint / gate / baseline / final / preflight 的行为与输出不变，`plan_sha` 不变，`gate-baseline.json` 不出现 `tiers` / `regions` / `tier_sec` 键。
- 已知边界：
  - 探针只认 pytest；非 pytest runner 的 G10 / G11 降级为警告；
  - `os.stat` / `os.path.exists` 不触发审计事件，只做存在性判断的用例测不出；C 扩展绕过 Python 层直接做的 I/O 也测不出；
  - 未选区域在本 change 内不跑；靠 lint 逼出「选上或写理由」与计划审批兜住；
  - 本仓自己的测试本 change 不重划分（Q4），本仓不放 `test-tiers.json`，本 change 的 `gate.test` 仍是全量。
