## Why

切片门禁只看本片自己的 `verify`，合回之后没有任何一步检查「合在一起还对不对」。afa 的 `key-features-keyft` 飞行里这条缺口出了四件事（交接文档 F4 / F5 / F6 / F7）：

- **跨片问题拖到下游才爆，爆了没有修复通道**。S8 新增了一个没声明的跨包 import，它自己的门禁是绿的（verify 不含分层测试），合回后把下一个 wave 的 S3、S7 拖红。工作流的 Fix 阶段只吃评审 finding，而且排在所有 wave 之后，只能人工手写一个「前置 fix」工作流。
- **全局守护不在每片门禁里**。分层 / 依赖声明 / 组合根这类几秒就能跑完的检查，只出现在部分切片的 verify 里，引入新跨包依赖的切片照样绿。
- **owns 漏列靠连红两次才暴露**。规划期预测不准哪个替身、哪个桩要跟着接口变，每漏一个就是一次停飞、改计划、重新批准；重新起飞时已经合回的切片还要再派一遍执行体。
- **owns 上限 12 条逼人放宽通配**。回放本机 6 个仓库 805 个切片：大片档（现存文件多于 8 个）的切片有 28.7% 恰好写满 12 条，写满的切片里 48% 用了通配（其他切片是 7%–17%），门禁报「写了 owns 之外的文件」的比例是 19.2%（其他切片 2%–4%）。数据与脚本在 `calibration/`。

## What Changes

- **全局守护**：`gate.checks` 的每个检查新增可选的 `slice` 命令，与 `baseline` / `final` 并列。写了 `slice` 的检查在 baseline（证明起点是绿的）、每片门禁（新门禁项 `G15 guard`）与每次 wave 集成检查里运行。仓库默认清单 `gate-checks.json` 里声明了 `slice` 的检查，计划里的同名检查必须带上。
- **wave 集成检查**：新子命令 `slice-gate.py wave-check`，integrator 每个 wave 合回后运行：先跑全部守护，再按依赖图只重跑受影响的测试（与增量 final 同一选法）。没有可用锚点、估算耗时超过预算（缺省 120 秒，计划可调）、或仓库配了分层文件时，测试那一半跳过并在时间线写明原因，不退化成全量。结论记进 `gate-report.md` 的 `wave` 行与时间线的 `wave-check` 事件；`ship` 见到最新的 `wave` 行是红的就判 draft。
- **跨片修复通道**：集成检查红 → 工作流当场派一个不受 owns 限制的修复执行体，修完在它自己的 worktree 里重跑一次集成检查；绿了由 integrator 合回并把结论写回分支，修复提交照常进评审。仍红才记 blocked：守护红时后面的 wave 全部停下，只有测试红时只停依赖本 wave 的切片。修复改了哪些文件、哪些落在所有切片的 owns 之外，写进集成检查的输出并进 PR 正文。
- **owns 上限按轮次档**：标准档 12 条不变，大片档 30 条。单条通配展开出 20 个以上现存文件时，须在该片的 `owns_wide` 里写理由；lint 把每条通配展开的文件数打印出来。已经批准过的在途 change 不因这条新规则变红。
- **重新起飞不重做已落地的切片**：新子命令 `slice-gate.py landed` 列出「门禁绿、提交已在分支上、计划里本片没再改过」的切片；工作流收到后不再派它们的执行体，只照常派评审。补 owns 之后的重新起飞因此只花被改那一片的钱。
- 审批页显示哪些检查是全局守护、哪些通配写了理由；`flight-doctor.py cost` 多一行 wave 集成检查的次数与秒数；命令文档、同名 skill、运行器契约、README、schema 同步。

没有 **BREAKING**：不写 `slice` 的检查、不带新参数的工作流、旧 hooks 配新工作流（integrator 报子命令不存在时不带回检查结果，工作流照常往下走）都与今天的行为相同。

## Capabilities

### New Capabilities
- `slice-guards`: 检查可以声明一条每片门禁与每个 wave 都运行的 `slice` 命令，基线先证明它是绿的。
- `wave-check`: 每个 wave 合回后的集成检查（守护 + 受影响的测试），结论进飞行记录并参与 draft / ready 裁决。
- `wave-fix`: 集成检查红时工作流内的跨片修复通道，以及修不好时的停飞范围。
- `owns-tiers`: owns 条数上限随轮次档变化，宽通配要写理由。
- `retakeoff-landed`: 重新起飞时已落地的切片不再派执行体。

### Modified Capabilities

（无。`template/openspec/specs/` 目前没有已归档的规格。）

## Impact

- `template/.claude/hooks/slice-gate.py`：检查的 `slice` 字段（lint、`plan_sha`、baseline、`gate` 的 G15）；新子命令 `wave-check` 与 `landed`；`record` 认 `wave` 行；`ship` 读 `wave` 行；lint 的 owns 上限与 `owns_wide`。
- `template/.claude/workflows/opsx-apply.js`：integrator 的合回派发带上集成检查；红时派跨片修复并合回；停飞范围；新参数 `args.landed`（可选）；返回值多 `waves`。
- `template/.claude/agents/integrator.md`、`slice-executor.md`：各补一段。
- `template/.claude/hooks/flight-doctor.py`（`cost` 多一行）、`spec_html.py`（审批页两处）。
- `template/.claude/commands/opsx-apply.md` 与同名 skill、`pr-ship.md`、`opsx-propose.md` 与同名 skill、`template/.claude/flight-runner-contract.md`、`README.md`、`template/openspec/schemas/intent-driven/schema.yaml`。
- 运行契约：检查命令的 `GATE_PHASE` 多两个取值 `slice` 与 `wave`；`slice` 阶段会被同一 wave 的多个切片并行调用。
- 每个 wave 多一次集成检查的墙钟：守护是仓库自己声明的快检查；测试那一半有预算。本仓实测一次改到 `slice-gate.py` 的增量要 512–571 秒，会被预算挡下、留给 final。
- 与待飞的 `tier-budgets`（C5b）同改 `slice-gate.py`、`flight-doctor.py`、契约文档与 README，函数与段落不重叠，见 design 的风险一节。
