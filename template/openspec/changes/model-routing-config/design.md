## Context

现状（main @ dc6c26a）：

- `opsx-apply.js` 只认 3 个角色：`args.models` 必须有 `executor` / `reviewer` / `integrator`，否则抛错；`efforts` 缺省为 `{executor: high, reviewer: high, integrator: low}`。大片档执行体、批量修复、wave 跨片修复都用 `models.executor`。
- `/opsx-apply` 起飞时用 `session-model.py` 判定会话主模型 `<main>`，然后传入 `models: {executor: <main>, reviewer: <main>, integrator: "sonnet"}`。
- 收口时运行 `session-decompose.py --expect-models`，只对账模型，不对账 effort。角色判定的顺序是 agentType → label 前缀 → 阶段。
- 回退路径的文档写着「Agent 工具没有 effort 参数，effort 由 agent frontmatter 决定」。本会话的 Agent 工具定义已有 `effort` 参数（`low | medium | high | xhigh | max`），这句话已过时。
- 其他派发点：
  - `/pr-ship` 评审与复核：`model: "<main>"`；
  - archive 的 sync：`model: "sonnet"`；
  - claudemd-standardize 的证据调查：`model: sonnet`；
  - bulk-apply 的子 agent：没写 `model`；
  - legacy 的实现 / 修复：没写 `model`；legacy 的评审：`<main>`。

已核实的事实：

- **转录里有实际 effort**：Workflow 子 agent 的转录，assistant 行顶层有 `effort` 字段（另有 `perTurnEffort`，以及 api-request 里的 `output_config.effort`）。本仓库上一次飞行（wf_8435375a）实测：integrator 为 `low`，review 与切片为 `high`，与当时传入的 efforts 一致。
- **meta 里看不出大片档**：`useAgentTypes: false` 时，meta 的 `agentType` 是 `workflow-subagent`。大片档执行体的 label 就是切片 id，单看 meta 区分不出。
- **环境变量会覆盖 effort**（code.claude.com/docs/en/model-config，2026-11-19 读取）：「A subagent's `effort` applies while the subagent runs … If `CLAUDE_CODE_EFFORT_LEVEL` is set, that level applies instead」；`maxEffortLevel` 或组织上限同样会压低子 agent 的 effort。

在役 ADR：

- `DRAFT-model-routing-defaults-for-template`：第 2 条「需推理的 subagent 保留 inherit」与本 change 冲突，由新 ADR 取代这一条；第 1、3、4 条仍在役（`CLAUDE_CODE_SUBAGENT_MODEL=sonnet` 兜底、主会话低推理命令只做软引导、纪律下发到 snippet）。
- `DRAFT-apply-as-flight` 等 ADR 不涉及模型取值，不冲突。

## Goals / Non-Goals

**Goals**

- 执行层每个派发用途的 model 与 effort 都来自按仓库生效的配置，只写模型名。
- 人类在审批 spec.html 时看到本次飞行的路由；它被钉进计划工件，改动会让批准过期。
- 收口时机械对账 model 与 effort。
- 规划期不变式变成机械检查：配置里出现规划期的组名即判红；测试扫描规划类命令与 skill。

**Non-Goals**

- 主会话的模型与 effort（规划期一律继承主会话；机械命令的主会话层由 C3 处理）。
- agent frontmatter 的取值（派发时显式参数优先，frontmatter 只在参数缺失时兜底）。
- 评审类的下限（Q7-A：不设）。
- 自动迁移在途 change：由人运行 `pin`，并重新批准。

## Decisions

### D1 · 配置形状：两级 `组.键`，值为 `{model, effort}`，缺的键走内建默认

```json
{
  "flight": {
    "executor":       {"model": "opus", "effort": "medium"},
    "executor-large": {"model": "opus", "effort": "medium"}
  }
}
```

注册表固定为 10 个键：

| 组 | 键 | 内建默认 | 本仓库 |
|---|---|---|---|
| flight | executor | opus · high | opus · medium |
| flight | executor-large | opus · high | opus · medium |
| flight | fixer | opus · high | 内建 |
| flight | reviewer | opus · high | 内建 |
| flight | integrator | sonnet · low | 内建 |
| ship | reviewer | opus · high | 内建 |
| ship | followup | opus · high | 内建 |
| archive | sync | sonnet · low | 内建 |
| claudemd | evidence | sonnet · low | 内建 |
| bulk | apply | opus · medium | 内建 |

校验规则（任一命中即判红，exit 2）：

- 组或键不在注册表里 → 「未登记的键」；
- 组名是 propose / explore / new / continue / mini → 「规划期不进路由配置」；
- `model` 不是 `opus | sonnet | haiku | fable`，包括 `main` / `inherit` → 「只写模型名」；
- `effort` 不是 `low | medium | high | xhigh | max`；
- 值缺 `model` 或缺 `effort`。

备选：只写与默认不同的键，并允许只写 model。否决理由：effort 是这次的核心诉求，半写会让来源难以判断。允许整个键缺省（走内建），但一个键写了就必须两项都写。

配置的位置是 openspec 根下的 `model-routing.json`。openspec 根由 `--change-dir` 推出（`<change-dir>/../..`），或由 `--openspec` 显式给出，缺省为 `openspec`。本仓库自举时，openspec 根是 `template/openspec`。

### D2 · 内建默认采用 Q1-A，install 不种配置文件

没有配置文件的下游，从「随会话主模型」改为固定 opus · high，这一点在 proposal 标为 BREAKING。

备选：install 种一份配置，缺了就判红（Q1-B），否决。理由：升级会多出一个用户数据文件，而内建默认已经能表达同样的取值。

### D3 · 规划期确认 = 钉进 `slices.json.routing`；批准即确认

- propose 在 tasks 阶段运行 `model-routing.py pin --change-dir`，把 flight 与 ship 两组共 7 个键写进 `slices.json` 顶层的 `routing`：

  ```json
  "routing": {"source": "<相对路径或 builtin>", "flight": {...5 键}, "ship": {...2 键}}
  ```

- spec.html 渲染这张表；人类发出 `/opsx-apply` 即确认。
- `slices.json` 本来就在 takeoff-gate 的 `PLAN_FILES` 里，pin 之后再改，批准自动过期，不需要改 takeoff-gate。
- archive / claudemd / bulk 三组不钉，它们不属于某一次飞行，用的时候用 `get` 现取。

### D4 · 缺 routing 的判红放在 `model-routing.py resolve`，不放进 `slice-gate.py lint`

Q5-A 要的是：旧 change 缺 routing 时起飞被拒，提示 pin，然后由人重新批准。

实现位置有两个选择：

- **放进 `slice-gate.py lint`（否决）**：51 个测试文件的计划夹具都没有 routing，放进 lint 会让这些夹具全部判红，owns 会扩散到几十个无关测试。
- **放在 `resolve`（采用）**：它在 apply 的 step 2 紧跟 lint 和 preflight 运行，非 0 就停下报告。效果与 lint 判红相同：在派发任何 agent 之前停飞，并给出 pin 的命令。

这一点与审批页写的「lint 判红」措辞不同，在 spec.html 里写明，由人类审批。

`resolve` 同时检查环境：`CLAUDE_CODE_EFFORT_LEVEL` 或 `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` 非空时 exit 3，并点名是哪个变量。前者会覆盖子 agent 的 effort（见 Context 引用的官方文档），后者会覆盖子 agent 的模型。

### D5 · 工作流 5 个角色，新角色缺省同 executor（兼容旧调用）

- `opsx-apply.js` 用 `execRole(s)` 选角色：大片档 → `executor-large`，其余 → `executor`；`fix` / `fix:w<i>` 的派发用 `fixer`。
- `models['executor-large']` 与 `models.fixer` 缺省取 `models.executor`；effort 同理。这样旧的 3 角色 args（测试夹具、未升级的命令文档）行为不变。
- 每个 effort 必须在 `low | medium | high | xhigh | max` 之内，否则抛错拒绝起飞。
- 开头的路由日志打印 5 个角色；返回值里的 `models` / `efforts` 也是 5 个角色。

### D6 · 收口对账：`--expect-efforts`，新增两种角色判定，可选角色不算零覆盖

- **effort 来源**：每个 agent 取第一条带 `effort` 字段的 assistant 行。所有 agent 都没有这个字段时（旧版 Claude Code），打印「转录无 effort 字段，effort 对账跳过」并跳过 effort 对账，不判红。部分 agent 有而对不上 → exit 3。
- **角色判定顺序**：
  1. label 去掉 `:retry` 后以 `fix` 开头 → `fixer`；
  2. 给了 `--turns` 且 label 在其中为 `large` → `executor-large`；
  3. 其余沿用 agentType → label 前缀 → 阶段；agentType 为 `slice-executor-large` → `executor-large`。
- **期望表没有新角色时**：`fixer` / `executor-large` 回落到 `executor`，旧的 3 角色 `--expect-models` 行为不变。
- **零覆盖**：`fixer` 与 `executor-large` 没有派发是常态，不算零覆盖。核心三角色的零覆盖规则不变。

### D7 · 回退路径与辅助派发点

- **apply 回退路径**：Agent 派发显式传 `model` 与 `effort`，取值来自 resolve。如果 Agent 工具没有 `effort` 参数（旧版本），由 agent frontmatter 决定，与路由不一定一致；回退路径不经 Workflow，收口不对账（与现状一致）。
- **其他派发点**：一律先运行 `python3 .claude/hooks/model-routing.py get <组.键> [--change-dir …]`，再按 stdout 的 `{model, effort}` 派发：
  - `/pr-ship`：`ship.reviewer` / `ship.followup`；
  - archive：`archive.sync`；
  - claudemd-standardize：`claudemd.evidence`；
  - bulk-apply：`bulk.apply`；
  - legacy：实现 `flight.executor`、修复 `flight.fixer`、评审 `flight.reviewer`。
- **`get` 的取值顺序**：钉住的值 → 仓库配置 → 内建默认。stdout 带 `source`。设了覆盖环境变量时，`get` 只往 stderr 打警告，不阻断：这些派发点不属于飞行，停下的代价大于收益。

### D8 · `<main>` 退出执行层路由

- apply、pr-ship、legacy 不再判定 `<main>`；`--model=` 旗标删除；`.flight` 的 `raw` 字段删除，`source` 改记路由来源。
- `session-model.py` 保留：`session-decompose` 仍用它的 `alias_of` 把模型 id 归一成别名，它自己的测试也不动。

### D9 · 规划期不变式的机械一侧

- **配置侧**：注册表拒收规划期组名（D1）。
- **文档侧**：`tests/test_routing_docs.py` 扫描 5 个规划类命令（opsx-explore / new / continue / propose / mini）和 4 个规划类 skill（openspec-explore / new-change / continue-change / propose）：
  - frontmatter 不得有 `model:` / `effort:`；
  - 正文不得出现 `subagent_type` 或 `model: "` 形式的派发。

  propose 文档里出现的 `model-routing.py pin` 只是钉配置，不是派发，不受影响。

## Risks / Trade-offs

- **执行体降到 medium，一次做对的比例可能下降**（风险） → 先跑 2–3 次飞行，用 timeline 与 flight-doctor 看重派与修复次数，再决定是否调回；调回只需改一行配置并重新 pin。
- **下游从「随主会话」变为固定 opus**（风险） → proposal 标为 BREAKING；README 写明可以用 `model-routing.json` 改回。
- **D4 偏离审批页的「lint 判红」措辞**（取舍） → 停飞效果等价，在 spec.html 写明，由人类审批。
- **Workflow 是否真按 `effort: "medium"` 运行未实测**（未验证） → 本 change 合入后的第一次飞行由 `--expect-efforts` 机械验证；对不上即 HIGH，PR 判 draft。
- **`maxEffortLevel` 或组织上限会压低 effort**（风险） → `resolve` 不读 settings，由收口的 effort 对账发现。
- **回退路径不对账 effort**（取舍） → 与现状一致，回退本身就是降级路径。

## Migration Plan

1. 合入后，本仓库的在途 change 起飞前运行 `python3 .claude/hooks/model-routing.py pin --change-dir <dir>`，然后重新批准。
2. 下游 `install.sh --upgrade` 拿到新的 hooks 和文档；不写配置时走内建默认；在途 change 同上先 pin。
3. 回滚：revert 本 change 即可。`slices.json.routing` 是新增的顶层键，旧脚本会忽略它。

## Open Questions

- 无阻断项。是否把 `executor` 调回 high，等 2–3 次飞行的数据再定（不在本 change 内）。
