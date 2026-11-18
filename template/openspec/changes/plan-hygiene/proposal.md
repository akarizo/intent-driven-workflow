## Why

afa 的 `key-features-keyft` 飞行一共要了 4 次「起飞」，其中 2 次与计划内容无关，是模板自己造成的（交接 F8）：

- **baseline 改计划文件**：`slice-gate.py baseline` 结束时无条件重写 `slices.json`，把全量耗时回填到 `gate.full_suite_sec`（`slice-gate.py:4196`）。起飞门禁按 `slices.json` 的修改时间判批准是否过期（`takeoff-gate.py:43`、`:212`）。baseline 在后台跑，人在它结束前批准，或批准后重跑 baseline，批准必然过期。
- **子仓 gitlink 的指纹前后不一**：基线的内容快照不记子仓目录（`_snapshot` 跳过目录）。gitlink 在 baseline 时只是暂存、随后提交，preflight 就判「基线过期：自基线以来有改动：<子仓>」，只能重跑 baseline。

同一次飞行还暴露了另一件事（交接 F10 / T3）：包装脚本不转发运行器契约变量，依赖图从没测到，final 每次都整跑 `gate.test`。这件事只出现在基线的 warnings 与 `flight-doctor` 的输出里，不拦任何步骤；afa 已有 14 份基线带着同一条告警起飞。2026-11-09 那轮定的是「只预告、不阻断」（unified-test-result-reuse design 的 Q3），结果就是没人处理。

2026-11-18 用户在方案页 `docs/flight-fixes-and-test-governance.html` 里定下（本 change 是其中的 C1；这些决策来自该页的问答，没有另开 `grill-me` 访谈）：

- **Q5 = A（表态制）**：契约没接、依赖图未测时判红，直到修好，或在计划里写明接受全量的理由，理由显示在 `spec.html`。
- **范围**：只做计划卫生四件事；`inert` 声明、final 的无图退路、pr-ship 先裁决再重跑属于后面的 C1b；全机测试闸与 final 耗时进时间线属于 C2。

## What Changes

- **baseline 不再写 `slices.json`**（`template/.claude/hooks/slice-gate.py`）：
  - 全量耗时改记在 `gate-baseline.json` 顶层的 `full_suite_sec`；增量基线沿用上一份的值，没有时取候选的测试耗时（语义与原来回填 `slices.json` 时相同）。
  - 运行标记（`{"running": true, …}`）带上上一份的 `full_suite_sec`，「基线仍在跑」的提示才说得出「上次全量约 N 秒」。
  - 三处读取方改读基线：G7 超时推算、运行中提示、`flight-doctor.py forecast` 的 `final.sec`。读不到再认旧的 `gate.full_suite_sec`（过渡，已安装仓库的在途 change 不用改）。
  - `gate.test` 缺失时 baseline 直接停（与 lint「须显式写出」一致），不再探测后写回。
  - **BREAKING（对读 `slices.json` 取耗时的外部脚本）**：`gate.full_suite_sec` 不再由模板写入；模板自带的读取方都已改。
- **子仓 gitlink 进内容快照**（`slice-gate.py` 的 `_snapshot`）：有未提交改动的 gitlink 路径记子仓当前 HEAD 的 commit，与提交后树里的值同口径。gitlink 暂存后再提交，基线不再过期。
- **依赖图未测须表态**（`slice-gate.py` 的选测复核）：
  - 本 change 的基线带 `deps_unmeasured` 时，选测复核多一个伪触发项 `runner:deps-unmeasured`，沿用现有的 `gate.scope_full_reason` 机制：没写理由 → lint、preflight 判红，final 开跑前复核判 `G2 scope` 红；违规文字带未测类别与契约文档路径。
  - 豁免：配了 `gate.impacted`（仓库自己选测）；内建声明下的非 pytest 运行器与部件形态（在役 ADR 已定为设计边界）。
  - 基线还没跑出来时不判红，允许预写这条理由；包装脚本的静态闭包里没出现 `FLIGHT_PYTEST_ARGS` 与 `FLIGHT_PLUGIN_PATH` 时，lint 打印一行提示并点名脚本。
  - 增量基线（复用旧结论）沿用来源的 `deps_unmeasured`，状态不因「这次没重测」而消失。
- **`ship` 的「final 过期」理由带补跑预告**（`slice-gate.py` 的 `cmd_ship`）：后面接一句「补跑将是增量（锚点 …，Δ N 个文件）」或「补跑将是全量（原因）」。预告函数放在 `slice-gate.py`，`flight-doctor.py forecast` 改为调用同一个函数。
- **文档**（命令与同名 skill 同改）：`opsx-propose.md` / `openspec-propose/SKILL.md` 删掉「耗时写回 `slices.json`」的两处说法，写明 baseline 不改计划文件、baseline 报告后重跑一次 lint 以及红了怎么办；`flight-runner-contract.md`、`README.md`、schema 的 tasks instruction 补上 `runner:deps-unmeasured`。
- **不做**：
  - 起飞门禁的新鲜度判据仍按修改时间，不改成内容指纹（baseline 不写计划文件之后，修改时间已经稳定）。
  - 不调换「工件在 baseline 报告之后提交」的顺序（见 design D4：提前提交会让 `gate-baseline.json` 把工作树弄脏，`/opsx-apply` 的干净检查会拦下）。
  - 不改 `flight-doctor.py` 恒退出 0 的约定；`doctor` / `cost` 两个子命令不动。
  - 不给 `not-pytest` 之外的仓库引入新的选测手段；`inert`、无图退路、全机锁都不在本 change。

## Capabilities

### New Capabilities

- `plan-hygiene`：baseline 不改计划文件；全量耗时记在基线里并被三处读取方使用；`gate.test` 缺失即停；子仓 gitlink 计入内容快照。
- `runner-statement`：基线的依赖图没测到时，计划必须在 `gate.scope_full_reason` 为 `runner:deps-unmeasured` 写理由，lint / preflight / final 复核同一口径。
- `ship-rerun-forecast`：`ship` 判「final 过期」时说明补跑是增量还是全量；成本预告与它用同一个判定函数。

### Modified Capabilities

- 无。`template/openspec/specs/` 不存在，现有行为的规格都还在各自的 change 目录里；本 change 的增量全部以 ADDED 写在上面三个新 capability 里。

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`、`template/.claude/hooks/flight-doctor.py`。
- **文档**：`template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md`、`template/.claude/flight-runner-contract.md`、`template/openspec/schemas/intent-driven/schema.yaml`、`README.md`。
- **ADR**：新增 `DRAFT-measurements-stay-out-of-plan-files.md`、`DRAFT-unmeasured-deps-need-plan-statement.md`。
- **测试**：新增 4 个测试文件；改 4 个钉着「耗时写回 `slices.json`」的旧测试（`tests/test_slice_gate.py`、`tests/test_baseline_pool.py`、`tests/test_baseline_incremental.py`、`tests/test_slice_gate_baseline_preflight.py`）。
- **下游**：已安装的仓库跑 `./install.sh --upgrade` 后：
  - 在途 change 不用重跑 baseline，旧的 `gate.full_suite_sec` 仍被读取；
  - 依赖图未测的仓库（afa 的 executor）下一次 lint / preflight 会判红，须修包装脚本或写理由——这是本 change 要的效果，升级说明里要写明。
