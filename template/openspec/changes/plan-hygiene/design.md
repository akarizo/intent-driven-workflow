## Context

**现状**（行号指 `template/.claude/hooks/`，main `b7be9ed`）：

- **baseline 写计划文件**：`cmd_baseline` 结束时重读 `slices.json`，回填 `gate.full_suite_sec`（缺 `gate.test` 时连同探测到的命令），再整份 `save_plan`（`slice-gate.py:4187–4196`）。这是全仓唯一一处 `save_plan` 调用。
- **起飞门禁按修改时间判新鲜**：`takeoff-gate.py` 的计划工件是 `proposal.md` / `design.md` / `slices.json` / `specs/**/spec.md`（`:43`、`:212`），人类批准的时间早于它们的最大修改时间即「批准已过期」。
- **耗时有三处读取方**：`_g7_timeout`（`slice-gate.py:2887`，G7 与增量重跑的超时 = 3 倍全量耗时）、`_die_running_baseline`（`:4303`，「上次全量约 N 秒」）、`flight-doctor.py:142`（成本预告的 `final.sec`）。
- **内容快照不记子仓**：`_snapshot` 遇到目录直接跳过（`:4626`，注释「目录（嵌套仓库 / 子模块）不记」）。gitlink 暂存时快照里没有它，提交后 `_delta` 从两棵树里读到新旧两个 commit → 判为改动。
- **依赖图未测只是告警**：全量基线测不到依赖图时写 `deps_unmeasured: {kind, why}` 与一条 warning（`:4206–4208`）；`flight-doctor` 恒退出 0。
- **表态机制已经有一套**：选测退化为全选时，`gate.scope_full_reason` 须逐个触发项写理由（`_scope_reason_errors`）；lint、preflight、baseline 开跑前经 `_lint_scope` 复核，final 开跑前经 `_final_scope_guard` 与 approve 提交里的理由对账；`spec.html` 的「选测范围」小节把理由表原样列出（`spec_html.py:621`）。已有一个伪触发项先例 `scope:undeclared`。
- **`ship` 的过期理由只有两个 commit**：`final 过期：记录 X，HEAD Y`（`:5699`）。「补跑要多久」要另跑 `flight-doctor.py forecast`，而它的判定写在 `flight-doctor.py` 的 `_final_part` 里。

**用户决策**（2026-11-18，方案页 `docs/flight-fixes-and-test-governance.html`）：Q5 = A，契约没接 / 依赖图未测走表态制；本 change 只做 C1。

**在役 ADR 的约束**：

- `DRAFT-repo-selector-reports-scope-at-plan-time` 决策 5、6、7（逐项表态、审批页可见、理由不进 `plan_sha`）与 `DRAFT-scope-provider-mandatory-with-runtime-guard` 决策 4、5（开跑前复核、理由以 approve 提交为准）：D3 直接复用，不改。
- `DRAFT-builtin-scope-provider-and-shell-closure`：「非 pytest 运行器与部件形态的 final 恒全量，属于设计边界，只注明，不要求写理由」。D3 保留这条豁免。
- `DRAFT-baseline-reuse-by-content-fingerprint`：快照记「未提交改动的 git blob id；软链取链接文本的 blob」。D2 给 gitlink 补一种取值，是同一规则的延伸，不取代它。
- `DRAFT-gate-test-result-handoff-and-runner-contract` 决策 4（依赖图未测给四类原因与修法）：D3 在它之上加处置，不改分类。

```
C4 · 容器图（轻量 C4 风格；◆ 修改，✂ 删除的写入）

                      ┌──────────────── 计划文件（人批准的内容）────────────────┐
 [人类] ──批准──▶     │ proposal.md · design.md · specs/** · slices.json        │
     ▲                └───────▲──────────────────────────▲──────────────────────┘
     │ 看理由                 │ 只读                      │ ✂ 不再回写耗时
     │                        │                           │
 spec.html「选测范围」   takeoff-gate.py            ◆ slice-gate.py baseline
     ▲ 理由表            （按修改时间判新鲜）              │ 写
     │                                                     ▼
     │                                        ◆ gate-baseline.json
     │                                          ├ full_suite_sec（D1，新）
     │                                          ├ snapshot（D2：含 gitlink）
     │                                          └ deps_unmeasured（D3：增量时沿用）
     │                                                     │ 读
     │              ┌──────────────────────┬───────────────┼──────────────────┐
     │              ▼                      ▼               ▼                  ▼
     │      ◆ G7 超时推算        ◆「基线仍在跑」提示   ◆ 选测复核        ◆ final_forecast()
     │                                                 lint / preflight /     │
     └──── gate.scope_full_reason ◀── runner:deps-unmeasured ── final 开跑前  ├─▶ ◆ ship「final 过期」理由
                                                                              └─▶ ◆ flight-doctor.py forecast
```

- **边界**：计划文件只由人和 propose 写；脚本测出来的东西只进 `gate-baseline.json` 与飞行记录。
- **强制点**：依赖图未测的处置落在已有的三处复核上，不新增复核点。
- **假设**：下游仓库读 `gate.full_suite_sec` 的只有模板自带的三处；外部脚本若读它，升级后拿到的是旧值（不再更新）。

## Goals / Non-Goals

**Goals**：

- 批准之后，baseline 何时结束、重跑几次，都不让批准过期。
- 子仓 gitlink 暂存后再提交，基线不过期。
- 依赖图未测不能再被无视：要么修好，要么在计划里写理由给批准的人看。
- `ship` 说「final 过期」时，同一句里说清补跑的代价。

**Non-Goals**：

- 不改起飞门禁的判据（仍按修改时间）。
- 不做 `inert` 声明、final 的无图退路、pr-ship 先裁决再重跑（C1b）。
- 不做全机测试闸、final 耗时进时间线（C2）。
- 不改变「非 pytest 运行器 / 部件形态」的设计边界豁免。
- 不让 `flight-doctor.py` 阻断任何步骤。

## Decisions

### D1 · 全量耗时从 `slices.json` 搬到 `gate-baseline.json`，baseline 不再写计划文件

- **写**：
  - 全量基线：`gate-baseline.json` 顶层 `full_suite_sec` = 本次 `gate.test` 的墙钟（部件形态 = 各部件单元层之和），与原来回填的数相同。
  - 增量基线（任一复用路径）：沿用本 change 上一份基线的 `full_suite_sec`；没有时取旧计划里的 `gate.full_suite_sec`；再没有取候选的 `full_suite_sec`，最后取候选 `test.sec`。与原回填逻辑（`:4192–4195`）语义一致。
  - 运行标记：`{"running": true, "pid", "started"}` 之外带上开跑前解析到的 `full_suite_sec`（没有就不带）。
- **读**：新增一个解析函数 `suite_sec(change_dir, data=None)`：`gate-baseline.json`（含运行标记）里的数值 → 旧计划的 `gate.full_suite_sec` → `None`。三处读取方都经它取值。布尔值不算数值。
- **删**：`cmd_baseline` 末尾的 `save_plan` 调用，以及随之无人使用的 `save_plan` 函数。「运行期间 gate / verify 被修改」的判定保留（结束时重读计划、比 `plan_sha`），只是不再写回。
- **`gate.test` 缺失**：baseline 在写运行标记之前退出 2，stderr 写明 `gate.test` 须显式写出。原来的「探测后写回」与 lint 的硬性要求矛盾，而且不写回之后 preflight 的 `plan_sha` 会对不上。`detect_test_cmd` 仍由 `final`（`/opsx-verify` 可不经 preflight）与内建预测使用，不删。
- **为什么不保留字段、只是不落盘**：字段留在计划里就还会有人往里写。计划文件的内容应当全部来自人批准的那一版。
- **否决**：
  - 起飞门禁排除纯度量字段（交接的备选）：要在两个脚本里各维护一份「哪些字段不算计划」，写入方仍在改文件。
  - 起飞门禁改比内容指纹：改动大，而且不解决「脚本写计划文件」本身。

### D2 · gitlink 进内容快照

- `_snapshot` 遇到目录时，若该路径是索引里的 gitlink（mode 160000），记子仓当前 HEAD 的 commit；子仓未就绪（没有 `.git`）时记索引里的值。其他目录照旧不记。
- `_delta` 不改：树一侧 `git ls-tree` 对 gitlink 给出的本来就是 commit，两边同口径。
- 效果：gitlink 已暂存（或子仓已前进但未暂存）时跑 baseline，之后把同一个 commit 提交进父仓，Δ 为空。
- 子仓工作区里的未提交内容仍不进快照（与现状相同，写进 Risks）。

### D3 · 依赖图未测 → 伪触发项 `runner:deps-unmeasured`，复用 `gate.scope_full_reason`

- **判定以基线为准，不以脚本文本为准**。触发条件（全部满足）：
  - 本 change 有一份跑完的基线（不是运行标记），且带 `deps_unmeasured`；
  - 计划没配 `gate.impacted`；
  - 不属于设计边界（`_builtin_by_design`：内建声明下的 `npm test` / `go test ./...` / `cargo test`，或部件形态）。
- **并入方式**：在提供方报告之上追加——报告原本未全选时变为全选、触发项只有它；原本已全选时在触发项后追加它。之后走现有的 `_scope_reason_errors`，键集合须相等。
- **各阶段**：

  | 阶段 | 有跑完的基线且未测 | 还没有跑完的基线 |
  |---|---|---|
  | `lint` / `preflight` | 触发项，缺理由判红 | 待定项：可预写理由，不要求 |
  | `baseline` 开跑前复核 | 待定项（基线即将重测，不能要求先写理由才让它跑） | 待定项 |
  | `final` 开跑前复核 | 触发项，须在 approve 提交的理由里；`--full` 豁免 | 不触发 |

- **违规文字**：在现有「触发项 … 缺理由」之后追加一句，带未测类别（`plugins-dropped` 等）与 `.claude/flight-runner-contract.md`，让人知道修哪里。
- **静态检查只作提示**：`gate.test` 不是可识别的直接测试命令、没配 `gate.impacted`、还没有跑完的基线时，取 `_test_gate_files` 的结果（命令里直接写出的仓库文件及其 shell 静态闭包），这些文件的文本里没有同时出现 `FLIGHT_PYTEST_ARGS` 与 `FLIGHT_PLUGIN_PATH` → lint 通过时在摘要后多打印一行 `runner:` 提示，点名直接写在命令里的脚本。
  - 不拿它判红的原因：照常继承环境的包装脚本（如 `pixi run test`、一行 `exec pytest "$@"`）文本里没有这两个名字，依赖图却测得到；按文本判红会逼这类仓库写一条套话理由，等基线测到后又得删。基线是事实，文本只是线索。
  - 方案页写的是「闭包里缺了就要表态」，这里改成「缺了提示、基线未测才要表态」，在 Open Questions 里点名。
- **增量基线沿用状态**：经旧基线 / 基线池复用（非锚点）时，新基线带上来源的 `deps_unmeasured`；基线池条目多存这个字段。经锚点复用说明依赖图是测到的，不带。
- **`plan_sha` 不变**：理由仍不进 `plan_sha`（在役 ADR 决策 7）。
- **否决**：
  - 新开一个字段（如 `gate.runner_unmeasured_reason`）：要在 lint、final 复核、approve 绑定、spec.html 四处各接一遍，现有机制已经全有。
  - `doctor` 加退出码、接会话钩子定期打印（Q5 的 B）：仍然没有人必须回应。
  - 把 `not-pytest` 也按文本静态判：非 pytest 的仓库出路是 `gate.impacted`，由基线的 `deps_unmeasured.kind` 说明即可。

### D4 · propose 的提交顺序不调换，只改说法

- 方案页原想把「子仓 gitlink 与计划工件在 baseline 之前一起提交」写进 propose 指引。读代码后不采用：
  - baseline 的产物 `gate-baseline.json` 在 change 目录里。工件先提交，baseline 跑完它就是未提交改动，`/opsx-apply` step 2 的「工件已单独 commit、工作树干净」会拦下；要放行就得再改 `/opsx-apply` 与它的同名 skill，或多一次提交。
  - 顺序靠模型照文档做，gitlink 那个缺口仍在脚本里；D2 在脚本里把它补上后，先提交后提交结果相同。
- 文档改三处（命令与同名 skill 同文）：
  - 基线步骤：删「把耗时写回 `slices.json.gate.full_suite_sec`」，改为「耗时记在 `gate-baseline.json`，不改任何计划文件」。
  - 硬交接第 4 条：提交时机仍在 baseline 报告之后，理由改为「`gate-baseline.json` 是本次基线的产物，随工件一起入库」；补一句「子仓 gitlink 的改动与工件同一次提交，暂存与否不影响基线」。
  - baseline 报告之后、forecast 之前：重跑一次 `slice-gate.py lint`；因 `runner:deps-unmeasured` 判红时，修包装脚本后重跑 baseline，或在 `gate.scope_full_reason` 写理由并重渲 `spec.html`。

### D5 · final 预告函数收进 `slice-gate.py`，`ship` 与 forecast 共用

- 把 `flight-doctor.py` 的 `_final_part` 原样搬成 `slice-gate.py` 的 `final_forecast(change_dir, data, baseline)`，返回 `(mode, why)`，取值与文字不变（`impacted` / `full` / `incremental` / `unknown`）。`flight-doctor.py` 改为调用它，自己不再留判定。
- `cmd_ship` 判 final 过期时调用它，在理由后追加：
  - `incremental` → `；补跑将是增量（<why>）`
  - `full` → `；补跑将是全量（<why>）`
  - `impacted` → `；补跑由 gate.impacted 选测`
  - `unknown` 或调用抛异常 → 不追加（裁决不能因预告出错而失败）。
- `forecast` 的 `final.sec` 改经 D1 的 `suite_sec` 取值。
- **否决**：`ship` 起子进程跑 `flight-doctor.py forecast`——判定函数本来就该在门禁里，反向依赖会让 `ship` 多一个失败点。

### D6 · 切片顺序

`slice-gate.py` 被三片先后修改，同一文件不能同 wave，所以串成 S1 → S2 → S3（深度 3）；文档片 S4 与 S1 同 wave。S3 依赖 S2 只因为同文件；它用到的接口（`suite_sec`）来自 S1。

## Risks / Trade-offs

- [下游仓库升级后 lint / preflight 变红（afa 的 executor 在途 change）] → 这是决策要的效果；违规文字带类别与契约文档路径；写理由即可放行；升级说明写明。
- [在途 change 的旧基线没有 `full_suite_sec`] → `suite_sec` 回退读旧计划字段；两处都没有时超时取现有缺省（600 秒），与今天「尚无耗时」时相同。
- [外部脚本读 `slices.json` 的 `gate.full_suite_sec`] → 值不再更新；proposal 标了 BREAKING；模板内已无读取方依赖它被更新。
- [子仓工作区有未提交内容时快照仍看不见] → 与现状相同；G6 的 gitlink 检查与 submodule 就绪检查照旧兜着。
- [基线未测的状态靠增量基线沿用，来源是很旧的基线池条目时可能缺字段] → 缺字段按「测到」处理（与今天相同，不会误拦）；下一次全量基线会重新写准。
- [`final_forecast` 搬家时文字走样，`spec.html` 的成本预告跟着变] → 现有 `tests/test_flight_doctor.py` 钉着这些文字，S3 的 verify 带它。
- [静态提示误报 / 漏报] → 只是一行提示，不影响退出码；真正的判定在基线。

## Migration Plan

- 模板合入后，下游 `./install.sh --upgrade`。不需要数据迁移：
  - 旧 `slices.json` 里的 `gate.full_suite_sec` 留着无害，继续作为回退值；
  - 旧 `gate-baseline.json` 没有新字段，下一次 baseline 自动带上。
- 回退：还原 `slice-gate.py` 与 `flight-doctor.py` 即可；新字段被旧脚本忽略。

## Open Questions

- **与方案页不一致的两处**（都已按上面的决策写进规格，请在审批时确认）：
  - D4：没有把「工件在 baseline 之前提交」写进 propose，改为在脚本里让 gitlink 的指纹前后一致。
  - D3：包装脚本的静态检查只提示不判红；判红以基线的 `deps_unmeasured` 为准。
- **内建声明下的非 pytest 仓库**（如 gateway 的 `cargo test`）按在役 ADR 仍是设计边界，不要求写理由。方案页 Q5 的字面范围包含它们；要纳入就得另立 ADR 取代 `DRAFT-builtin-scope-provider-and-shell-closure` 的那一条，本 change 没做。
- **顺带发现（不在范围）**：`spec_html.py` 的 `scope_provider` 用 `len(decl) != 1` 判声明形状，`gate-scope.json` 带了 `global` / `blind` / `anchor_max_hops` 时会被显示成「未声明选测范围」。
