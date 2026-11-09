## Context

- **现状**：复用测试结果的三条路互不相通。
  - **基线**：`cmd_baseline` 的候选只有本 change 旧基线与基线池（`_baseline_candidates`，`slice-gate.py:4513`）；只有 Δ 全是 `test_*.py` 才复用（`_try_reuse`，`:5181`）；基线池只收全绿的全量。
  - **final**：有锚点与依赖图的增量（`_pick_anchor` / `_final_select` / `_full_triggers`），但锚点要 `measured` 才可用。
  - **检查**：环境只有 `GATE_PHASE` / `GATE_CHANGE` / `GATE_BASE_COMMIT` / `GATE_CHECK_DIR` 加 Δ 三件（`_check_env`，`:4568`），拿不到门禁刚跑出的测试结果。
- **实测**（2026-11-09，本机 7 个已安装项目只读盘点，数字均为下限）：
  - **afa**：
    - 全量基线 95 次、合计 37,633 秒；首个候选被拒理由：无候选 64 次 / 28,161 秒，有非测试改动 17 / 6,337，候选红 12 / 2,910，cmd_key 不同 2 / 225；
    - final 因"没有可用锚点"全量 33 次；锚点池 20 条里 2 条测到依赖图；
    - 检查有 25 次"未复用 head 全量：键不符"，全部含 `FLIGHT_*`，其中 21 次只差 `FLIGHT_*`。
  - **gateway**：cargo / pnpm，锚点 20 条全部未测，final 全量·无锚点 8 次。
  - **stc-foundation**：直接调 pytest，final 增量 19 次、沿用 6 次——契约满足时现有机制是有效的。
- **根因**（方案文档 03 节）：
  - **R1**：afa testgate 有意重建子进程环境，丢弃 `-p flight_*` 与 sitecustomize，依赖图永远测不到；今天只留一条"依赖图未测：没有依赖图输出（不是 pytest？）"警告。
  - **R2**：基线只认测试文件 Δ。
  - **R3**：跨 change 永远没有候选：基线池只收全绿；`cmd_key` 吃进了写死 change 名的包装脚本内容。
  - **R4**：检查拿不到结果，项目侧缓存键混进了每次运行都变的 `FLIGHT_*`。
  - **R5**：代价不可见。
  - **附**：`GLOBAL_FILES` 写死（`:4727`），项目无法声明按名字动态加载的目录（afa `executor/dlib_impl`）。
- **在役 ADR**：
  - `DRAFT-baseline-reuse-by-content-fingerprint`：本 change 取代其中两项；
  - `DRAFT-final-incremental-by-dependency-anchor`：决策 4 的一项已被 `DRAFT-builtin-scope-provider-and-shell-closure` 取代，分层一项已被 `DRAFT-tier-file-diffed-by-entry-in-final` 取代，其余在役，本 change 沿用；
  - `DRAFT-gate-paired-checks-by-exit-code`：本 change 只扩展其环境契约，判定仍只看退出码；
  - `DRAFT-scope-provider-mandatory-with-runtime-guard`：选测声明契约 v2，本 change 只加可选字段。
- **用户决策**（2026-11-09）：
  - Q1：跨 change 带预存红只经锚点放开；
  - Q2：锚点链按代数设上限，K=5，基线与 final 一起管；
  - Q3：只预告不阻断；
  - Q4：合成一个 change；
  - Q5：项目侧适配由用户自己做；
  - Q6：afa 临时修复先撤。
- **约束**：
  - 纯标准库，Python 3.9 兼容（禁 `match`、禁 `X | Y` 注解）；
  - 判定零 token；
  - `slice-gate.py` 是单文件，同 wave 的切片 owns 不能相交——这决定了切片形状（见 tasks）。

C4 · 容器图（本 change 触及的部分；★ 为新增，◆ 为修改）

```
 [人类] ──/opsx-propose──▶ ◆opsx-propose.md / skill ──baseline──▶ ◆slice-gate.py baseline ──写──▶ gate-baseline.json
   │                              │ 报告行附预告                     │  ◆候选：旧基线 → 锚点池 → 基线池
   │                              ▼                                  │  ◆非测试 Δ：按依赖图补跑（_final_select）
   │                        ★flight-doctor.py forecast ◀──只读───────┤
   │                              ▲                                  ▼
   │ /opsx-apply ──▶ ◆opsx-apply.md ─preflight 后─┘        [git common dir]
   │                                                         ├─ flight-anchors/   ◆ +nodes +hops +deps_kind
   │                                                         ├─ flight-baseline-pool/（不变：只收全绿）
   │   ◆slice-gate.py final ──写──▶ ★flight-gate-checks/<change>/.gate-test-result.json
   │        │ run_test_gate：◆导出 FLIGHT_PLUGIN_PATH / FLIGHT_PYTEST_ARGS，◆设 GATE_PHASE / GATE_CHANGE
   │        ▼                                    │ GATE_TEST_RESULT
   │   [项目包装脚本 gate.test] ──转发契约──▶ pytest ＋ flight_deps / flight_guard
   │        ▼                                    ▼
   │   [项目检查 gate.checks final] ◀────────────┘（读结果，不再重跑全量）
   │
   └─ install.sh --upgrade ◆──▶ ★flight-doctor.py doctor（只报告）
      spec_html.py ◆「测试成本预告」段 ◀── ★flight-doctor.py forecast --json
      ★template/.claude/flight-runner-contract.md（随 .claude/ 下发，项目侧适配依据）
      ◆<openspec 根>/gate-scope.json：+global +blind +anchor_max_hops（可选）
```

- **边界**：模板只负责产出、交接与预告；项目侧的包装脚本与检查是否接入契约，由项目自己决定（Q5）。不接入的项目行为不变，只是会被预告和归因。
- **假设**：项目的 gate.test 最终调用 pytest，或者配了 `gate.impacted`。非 pytest、又没配 `gate.impacted` 的项目，依赖图无从谈起，本 change 只让这件事可见（`not-pytest`）。

## Goals / Non-Goals

**Goals:**
- 每份测试结果只产出一次，基线、final、检查都能取用。
- 重新规划（切片代码已落地）与首次基线，在锚点可用时按依赖图只补跑受影响的测试。
- 包装脚本有一条稳定、写成文档的路，把依赖图插件接进被测进程。
- 每次全量都有机读原因；起飞前预告，收口时归因。
- 依赖图盲区的累积有上限，项目能声明全局路径与盲区。

**Non-Goals:**
- 不改任何项目仓库（afa testgate、gateway 的 `gate.impacted`）：只交付契约文档（Q5）。
- 不改基线池入池条件（仍只收全绿）。
- 有测试分层文件时，基线仍恒全量（现状，`DRAFT-test-tiers-unit-baseline-by-audit-probe`）。
- 不做"源路径 → 测试 glob"的影响映射（只做 `global` / `blind`，见 Open Questions）。
- 不做跨机器共享锚点；不改 G7；不加 CI。
- 不阻断起飞（Q3）。

## Decisions

### D1 测试结果交接文件与 `GATE_TEST_RESULT`
- **写入时机**：final 在 gate.test（全量 / 内建增量 / `gate.impacted`）判定之后、运行任何检查之前写。路径 `<git common dir>/flight-gate-checks/<change>/.gate-test-result.json`，即 `_check_dir` 的父目录，原子写。同树沿用的 final 不运行检查，不写。
- **字段**：见 spec。
  - `nodes` 来自依赖图插件的逐用例结局（`_read_deps` 的 `nodes`），依赖图未测时为 `null`；
  - 增量时，`nodes` = 锚点 `nodes` 中未选中文件的条目 ∪ 本次重跑结局，`inherited` 为前者条数；
  - `complete` = 依赖图已测，且（全量，或锚点带 `nodes`）。
- **junit 副本**：`run_test_gate` 新增参数 `keep_junit=<路径>`，临时目录删除前把 junit 复制过去。增量重跑经 `_pytest_outcomes` 也带同名参数。
- **锚点带 `nodes`**：锚点条目新增 `nodes`（仓库相对 nodeid → outcome），全量时取依赖图插件结果，增量时按 `_anchor_forward` 的同一口径换掉重跑过的文件。体积与已有的 `deps` 同量级，afa 可以接受。
- **为什么放 git common dir 而不是检查目录**：每项检查各有一个目录，baseline 实跑前会清空；结果是本次 final 共享的，放在它们的父目录。
- **否决**：
  - 把结局写进检查目录 → 每个检查一份，重复；
  - 让检查自己去读锚点池 → 锚点的选取与沿用规则在模板里，交给项目等于让它重写一遍；
  - 只交 junit → 增量时 junit 不完整，而且 nodeid 与 classname 对不齐（`baseline-incremental-reuse` D3 已否决这条路）。

### D2 gate.test 环境与易变变量
- `run_test_gate`、`_pytest_outcomes` 与 `gate.impacted` 的运行，在环境里设 `GATE_PHASE`（`baseline` / `final`）与 `GATE_CHANGE`（change 目录名）。调用方经 `extra_env` 传入，不改它们在检查环境里的含义。
- **契约声明**：`FLIGHT_` 与 `GATE_` 前缀的变量都是每次运行的易变量。项目侧任何按环境做键的缓存都必须剔除这两个前缀，建议直接改用白名单。afa 盘点里还见过 `CLAUDE_EFFORT` 混进键，所以白名单才是根治。
- **否决**：让 slice-gate 在 gate.test 环境里不设 `FLIGHT_*` → 插件靠它们定位输出，不设就测不到依赖图。

### D3 运行器契约变量
- `_flight_plugins` 写好插件目录之后，导出 `FLIGHT_PLUGIN_PATH=<该目录>` 与 `FLIGHT_PYTEST_ARGS=<shlex.join(["-p", "flight_guard", ("-p", "flight_deps"), ("-p", "flight_tier_probe"), "--junitxml=<path>"])>`。
- 现有的 `PYTEST_ADDOPTS` 注入与 `PYTHONPATH` 前置照旧，直接调 pytest 的项目零改动。
- **包装脚本的转发方法**（写进契约文档）：
  - 被测进程 `PYTHONPATH` 以 `$FLIGHT_PLUGIN_PATH` 开头；
  - 把 `$FLIGHT_PYTEST_ARGS` 按 shell 拆词后传给 pytest；
  - 两者都为空时什么也不加。
- **去插件重跑（`_plain`）**不导出这两个变量，包装脚本看到空值就不转发，与今天一致。
- **否决**：
  - 改用 `PYTEST_PLUGINS` → 会被同样的环境清洗丢掉（afa `runners.py:31` 同时丢 `PYTEST_ADDOPTS` 与 `PYTEST_PLUGINS`）；
  - 让模板识别并改写包装脚本 → 侵入项目代码。

### D4 依赖图未测的四分类
- `_read_deps` 返回 `(None, why)` 的地方，连同 `run_test_gate` 的去插件重跑分支，统一产出 `deps_kind`：
  - `not-pytest`：junit 不存在且输出里没有 pytest 汇总行（复用现有汇总行正则）；
  - `plugins-dropped`：pytest 跑了（junit 存在或有汇总行），但 `FLIGHT_GUARD_OK` 标记没写、输出里没有插件导入错误；
  - `plugin-import-failed`：沿用现有 `FLIGHT_PLUGIN_FAIL` 判定与去插件重跑；
  - `incomplete`：现有的"记录不完整""记录损坏"两种。
- **记录**：
  - 基线写 `deps_unmeasured: {kind, why}`，`warnings` 的文字改为 `依赖图未测（<kind>）：<why>`；
  - 锚点写 `deps_kind`；
  - final 的"没有可用锚点"原因附上最近一份基线的 `deps_unmeasured.kind`（有的话）。
- **why 带修法**：前两类点名 `FLIGHT_PLUGIN_PATH` / `FLIGHT_PYTEST_ARGS` 与 `.claude/flight-runner-contract.md`。
- **否决**：继续只给一句"不是 pytest？"→ afa 的真实原因是插件被丢弃，旧文字误导了排查。

### D5 `gate-scope.json` 的可选字段
- `_scope_decl` 的字段白名单加上 `global`、`blind`、`anchor_max_hops`，形状错误按现有格式点名。新增 `_scope_extras(change_dir) -> {"global": [...], "blind": [...], "anchor_max_hops": int}`，文件缺失或无字段时取缺省（空、空、5）。
- **`global`**：
  - 进 `_full_triggers`：Δ 路径与任一 glob 匹配（`fnmatch` 对仓库相对完整路径）→ 触发项 `declared-global:<glob>`；
  - final 原因文字为"Δ 命中项目声明的全局路径 <glob>：<路径>"；
  - 内建提供方的计划期预测走同一函数，自动一致（`DRAFT-builtin-scope-provider-and-shell-closure` 决策 1）。
- **`blind`**：进 `_final_select`，匹配的现存测试文件并入选中集合。
- **为什么放 `gate-scope.json`**：它已是仓库级、声明式、被列为"声明文件不触发全量"的门禁配置，全局与盲区也直接影响选测预测。另开文件会让同一套触发规则读两处。
- **否决**：
  - 写进每个 change 的 `slices.json` → 全局路径是仓库的属性，不是某个 change 的；
  - 扩写死的 `GLOBAL_FILES` → 各项目各不相同。

### D6 锚点链上限
- **记录**：锚点条目新增 `hops`。
  - `baseline` 全量 / `final-full` 为 0；
  - `final-incremental` 与经锚点的增量基线为来源锚点 `hops + 1`；
  - 旧条目缺 `hops`：`source == "final-incremental"` 视为 K（不可用），其余视为 0。
- **选取**：`_pick_anchor` 与基线的锚点候选都先滤掉 `hops >= K` 的条目。K 来自 `_scope_extras`，`_pick_anchor` 新增关键字参数 `max_hops`，缺省为常量 `ANCHOR_MAX_HOPS = 5`。
- **原因**：被滤掉之后没有可用锚点时，原因写"锚点链已达上限 K 代（anchor_max_hops）"，触发项代码 `final:anchor-hops`。
- **为什么不是"锚点年龄"**：同一棵树上依赖图漂移的来源是一次次增量推导，不是时间（Q2=A）。
- **K=5 的依据**：用户在没有对账数据时选的保守值；对账后经 `anchor_max_hops` 调整，不改代码。

### D7 基线候选与锚点路径
- **候选顺序**：
  1. 本 change 旧基线（`_try_reuse` 现有规则，含 D8、D10 的修订）；
  2. 锚点候选：`_anchor_candidates(root, akey, None)`，条件是 measured、无分层、`hops < K`，用 `_delta` 算 Δ 后取 |Δ| 最小的；
  3. 基线池（现有规则）。
- **锚点路径判定**：
  - `_full_triggers(root, delta, anchor, None, gate, …)` 有触发项 → 跳过该锚点，原因进 `reuse_skipped`；
  - 否则 `sel = _final_select(root, anchor, delta)`（含 D5 的 blind），用 `_pytest_outcomes(root, sel, gate, deps_out=…)` 补跑。补跑超时、rc ∉ {0, 1, 5}、或有收集错误 → 中止，走全量。
- **结果**：
  - `test = {"exit": 0 或 1, "failed": None, "failed_nodes": [补跑中 FAILED/ERROR], "failed_form": "nodes", "sec": 补跑耗时}`；
  - `mode: incremental`，`incremental: {"source": "anchor", "from": {change, commit, at}, "rerun_files": sel, "hops": anchor.hops + 1}`；
  - 写新锚点：`_anchor_forward` 口径，`source: "baseline-incremental"`，`hops` 同上。
- **verify**：经锚点（任意来源）时全部重跑，与跨 change 基线池候选一致。
- **lint / typecheck**：只在本 change 旧基线且严格 Δ 为空时沿用，规则不变。
- **跨 change 带预存红**：锚点的 `failed` 所在文件恒在 `sel` 里（`_final_select` 现有行为），所以别人的红一定被重跑、按本次结果记录，不会整份沿用别人的名单。这正是 2026-10-15 否决理由（"留着把红判成绿的窗口"）所指的那条路径，现在关上了（Q1=A）。基线池入池条件不变。
- **否决**：
  - 把基线池也放开带红 → 池条目没有依赖图，做不到"失败文件必重跑"；
  - 锚点路径只对本 change 开放 → 首次基线（afa 64 次）照样没有候选。

### D8 红基线按部件复用
- **记录**：基线新增 `test_ok`：gate.test 跑了、可度量（rc 0 或 `failed` 非 None），且 `reasons` 里没有"运行期间被修改""结束快照失败""运行期间 gate/verify 被修改"三类。
- **复用**：`_try_reuse` 对本 change 旧基线放宽：`ok is True` 或 `test_ok is True` 都可作测试部分的候选；跨 change 与池候选仍要求 `ok is True`。复用时 verify / lint / typecheck / 检查照常走各自的沿用规则，原来红的那一项会重新实跑。
- **缺字段**：旧基线缺 `test_ok` → 不放宽（安全方向）。

### D9 cmd_key 归一与 shell 闭包
- **算法**：`cmd_key` 对命令里直接写出的仓库内文件，加上它们经 `_shell_closure` 求出的静态闭包，逐个读内容。把本 change 目录名按词边界（前后不是 `[A-Za-z0-9_-]`）替换成 `<change>`，再算 sha1，与归一后的命令文本一起进指纹。读不到的文件按现状处理（只记路径）。
- **影响**：
  - 各 change 按同一模板生成的包装脚本（afa 89 个 change 的 `verify/full_suite.sh`）指纹相同，跨 change 的锚点与基线池都能命中；
  - 被 source 的 `_env.sh` 进了指纹：内容不同就不命中，这是正确的口径。
- **BREAKING（一次性）**：算法变了，升级后既有的基线、锚点、池条目全部失配，各项目第一次 baseline / final 全量，之后恢复。写进迁移说明与 doctor 提示。
- **否决**：只归一命令文本 → 内容里的 change 名才是 afa 指纹分裂的原因。

### D10 本 change 门禁脚本只按 gate.test 闭包影响测试结论
- `_try_reuse` 用本 change 旧基线时，`_delta(..., same_change=True)` 照旧计入本 change 目录里的门禁脚本。然后从"测试结论用的 Δ"里去掉不在 gate.test / `gate.pytest` 静态 shell 闭包里的那些（闭包同 D9）。
- verify 的重跑判定（`_verify_rerun`）与 lint / typecheck 的严格 Δ 仍用完整 Δ。
- **为什么**：afa 今天的重新规划改了 `_env.sh`（只被 lint / verify 的包装用到），按现规则这会让测试结论失效；D9 之后它在不在指纹里由闭包说了算，口径统一。

### D11 final 按 nodeid 差分
- 基线 `test.failed_form == "nodes"` 时，final 全量的 G2 test 按 `failed_nodes` 差分。
  - 需要本次全量的依赖图逐用例结局（`nodes`）；
  - 依赖图未测、无法得到 nodeid → G2 test 红，原因"基线只有 nodeid 形式的预存红，本次依赖图未测，无法差分；重跑 baseline --full"（安全方向：不会把红判成绿）。
- 增量 final 本来就按 `failed_nodes` 差分，不变。

### D12 `flight-doctor.py`：forecast / cost / doctor
- **新文件**：只读，恒 exit 0，纯标准库，3.9 兼容。经 `importlib` 按路径加载同目录的 `slice-gate.py`，复用：
  - `load_plan`、`load_baseline`、`_snapshot`、`_anchor_key`、`_tiers_key`、`_pick_anchor`、`_full_why`、`_scope_extras`；
  - 不复制判定逻辑，也就不会与门禁漂移。
- **为什么单独成文件**：`slice-gate.py` 单文件被 S1–S3 串行占用。可见性只读这些数据，独立出来既能与 S2 并行，也让"门禁判定"与"报告"职责分开。
- **forecast**：
  - baseline 段读 `gate-baseline.json`：`running` → `pending`；缺 → `missing`；否则取 `mode`、`reuse_skipped[0].reason`、`test.sec`；
  - final 段：有 `gate.impacted` → `impacted`；有分层部件形态 → `full`（部件恒全量）；否则用当前树调 `_pick_anchor` 与 `_full_why`：
    - 有原因 → `full` + 原因；
    - 无锚点且基线有 `deps_unmeasured` → `full` + 类别与修法；
    - 都没有 → `incremental`；
    - 任何异常 → `unknown` + 异常文字；
  - `sec` 取 `gate.full_suite_sec`；
  - checks 段列 `gate.checks[].name`。
- **cost**：
  - 解析 `timeline.md` 的 `baseline` / `final` 行：
    - 备注含 `增量` 或 `同树沿用` → 增量；
    - 含 `全量` → 全量，`exit e, Ns` 里的秒数计入；
    - 原因取 `全量：` 之后或 `全量（…）` 括号里的文字；
  - 归类表（关键词 → 必要 / 可避免）写在文件顶部常量里，认不出 → `未分类`。
  - 依赖 D13 的基线 timeline 备注格式。
- **doctor**：
  - 扫 `<openspec 根>/changes/*/gate-baseline.json`（不含 `archive/`）、锚点池、各 `slices.json` 的 gate、`gate-scope.json`，输出四节；
  - 另提示 cmd_key 算法变化后首次全量属正常（D9）。

### D13 基线 timeline 备注写全量原因
- 全量基线的 timeline 备注，由 `exit e, Ns ok|red` 改为 `exit e, Ns ok|red；全量：<原因>`。
- 原因取首个候选的拒绝理由，或下列固定文字：
  - `无可用候选（锚点池为空）`；
  - `锚点不可用（依赖图未测：<kind>）`；
  - `锚点链已达上限 K 代`；
  - `手动要求 --full`；
  - `有测试分层文件（恒全量）`。
- 经锚点的增量基线备注为 `增量（经锚点 <change>@<commit 前 10 位>，补跑 n 个测试文件 t秒） ok|red`。
- `timeline.py` 不改，只按列追加。

### D14 出现位置
- **`/opsx-propose` step 5**：baseline 结束的报告行，后面追加 `flight-doctor.py forecast` 的一行输出（原样转述）。
- **`/opsx-apply` step 3**：preflight 之后运行 `forecast` 并原样打印，不影响是否起飞。
- **step 6 收口**：在 `timeline.py report` 之后运行 `cost`。
- **spec.html**：`spec_html.py` 渲染时子进程调 `forecast --json`，渲染「测试成本预告」段；失败、超时（30 秒）或非 JSON → 占位文字"预告不可用：<原因>"（铁律 10）。
- **`install.sh --upgrade`**：结束时，若目标有 `openspec/` 且有 `python3`，运行 `python3 "$TARGET/.claude/hooks/flight-doctor.py" doctor --openspec-root "$TARGET/openspec"`，输出原样打印，`|| true`。
- **命令与同名 skill 同改**：`opsx-propose.md` ↔ `openspec-propose/SKILL.md`，`opsx-apply.md` ↔ `openspec-apply-change/SKILL.md`。

## Risks / Trade-offs

- **[依赖图漏记 → 基线把红记成绿]**：基线现在也会经锚点推导，与增量 final 是同一类盲区（`DRAFT-final-incremental-by-dependency-anchor` 已接受）。
  → 对策：
  - 锚点失败的文件必重跑；
  - 全局文件与声明的 `global` 触发全量；
  - 盲区与声明的 `blind` 必重跑；
  - 链长上限 K=5；
  - `--full` 随时可用；
  - 项目启用前先做一次对账：同一棵树上分别跑增量与全量，逐条比对结果（写进契约文档的"接入步骤"）。
- **[cmd_key 算法变化导致一次性全量]**：升级后每个项目多跑一次全量基线和全量 final。
  → doctor 与迁移说明写明这是一次性的；之后跨 change 能命中，长期是净收益。
- **[链长上限让已在增量的项目周期性多跑全量]**：stc-foundation 一类项目升级后，每 5 次增量多一次全量（用户已接受，Q2 补充决策）。
  → `anchor_max_hops` 可按对账结果调大。
- **[合成结局交给检查，检查误把它当成实跑]**：增量时 `nodes` 里有沿用的条目。
  → 文件里有 `mode` / `inherited` / `complete`，契约文档要求只想要实跑结果的检查看 `mode == "full"`。
- **[flight-doctor 依赖 slice-gate 的私有函数名]**：S2 / S3 改了签名就会坏。
  → `_interfaces.md` 钉住所用函数的签名；flight-doctor 捕获异常输出 `unknown`，不会让任何流程失败；S4 的测试会实际调这些函数。
- **[包装脚本转发 sitecustomize 改变项目的冷启动约定]**：afa testgate 有意重建环境。
  → 契约只要求加审计钩子、不改 import 结果；接不接入由项目决定（Q5）；不接入就保持全量，但会被预告。
- **[`gate-scope.json` 字段变多]**：契约 v2 写的是"恰含 cmd 或 builtin 之一"。
  → 这一条不变，新字段都是可选附加，旧文件全部合法；文档措辞随之更新（S5 owns 钉住它的测试）。
- **[`nodes` 让锚点体积变大]**：afa 上万用例。
  → 与已有 `deps` 同量级，锚点池只留 20 条；体积问题出现时再压缩（不在本 change）。

## Migration Plan

- **升级**：`install.sh --upgrade` 下发新 `slice-gate.py`、`flight-doctor.py` 与契约文档，结束时打印 doctor 报告。
- **一次性全量**：cmd_key 算法变了，各项目升级后的第一次 baseline / final 全量；缺 `hops` 的 `final-incremental` 锚点视为已达上限，也让第一次 final 全量。之后恢复增量。
- **兼容**：
  - 旧 `gate-scope.json`（无新字段）、旧检查（不读 `GATE_TEST_RESULT`）、不转发契约的包装脚本，行为都与今天相同；
  - 旧基线缺 `test_ok` / `failed_form` → 按旧规则处理。
- **回退**：
  - `baseline --full` / `final --full` 恒等于不复用；
  - 删掉 `<git common dir>/flight-anchors/` 即回到"每次全量"，下一次全量后重建；
  - 回滚代码时，新字段被旧代码忽略。
- **项目侧接入**（不在本 change，用户执行）：
  1. 按契约文档改包装脚本；
  2. 跑一次 baseline，确认依赖图测到；
  3. 对账；
  4. 声明 `global` / `blind`；
  5. 检查改读 `GATE_TEST_RESULT`。

## Open Questions

- **ADR 取代**：`DRAFT-baseline-reuse-by-content-fingerprint` 的两项决策被本 change 修订：
  - "只有测试文件变了才复用全量"——扩展为经锚点按依赖图复用；
  - "跨 change 只复用全绿"——锚点路径放开带红，基线池不变。
  由新 ADR `DRAFT-baseline-reuse-via-dependency-anchor` 记录取代，原 ADR 不改；其"盲区"一节的兜底论证随之换成 D7 的"失败文件必重跑"与 D6 的链长上限。
- **检查契约扩展**：`DRAFT-gate-paired-checks-by-exit-code` 的环境契约新增 `GATE_TEST_RESULT`，判定仍只看退出码，不构成取代；与运行器契约一起记入新 ADR `DRAFT-gate-test-result-handoff-and-runner-contract`。
- **K 的默认值**：5 是没有对账数据时的保守选择；afa 接入后用对账结果复核，经 `anchor_max_hops` 调整。
- **影响映射**（"源路径 glob → 测试 glob"）：比 `global` 更精确，afa 的 `dlib_impl` 会受益。等 `global` 的实际命中数据出来再定（backlog）。
