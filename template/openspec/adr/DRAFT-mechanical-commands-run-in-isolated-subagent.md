# DRAFT. 主会话不被 frontmatter 换模型；不需对话历史的机械命令以 context: fork 子 agent 运行，模型由路由配置渲染

- Status: accepted, supersedes DRAFT-execution-routing-by-config（仅决策第 1 条的键清单「共 10 个」；其余条款在役）
- Date: 2026-11-20
- Supersedes: DRAFT-execution-routing-by-config（合并时回填真实号；只取代上述一处）
- 来源 change：mechanical-command-layer（design D1–D5）

## Context

审批页 `docs/flight-routing-config.html` v4 第 07 节把 C3 定为「机械命令的主会话层，先探针」：在 verify / archive / sync / spec-html / claudemd-commit / test-tiers / clean-after-merged 的 frontmatter 写 `model`，让主会话跑这些命令时换成便宜模型。

2026-11-20 的探针（Agent SDK 驱动 Claude Code 2.1.329，会话 opus · medium）：

- **问询之后**：frontmatter 的 `model` / `effort` 在同一轮内跨过 AskUserQuestion 仍生效，下一条人类消息恢复会话模型。
- **切模型的账**：切模型那一轮的首个请求整段不命中缓存，回到会话模型时要重写这一轮新增的内容。frontmatter 引起的切换不触发 PreModelSwitch / PostModelSwitch（阳性对照 SDK `set_model` 能触发），无法按缓存冷热决定切不切。只改 effort 不丢缓存。
- **`context: fork`**：主会话那一轮 0 个请求；子 agent 用 frontmatter 的 model / effort（压过 `CLAUDE_CODE_SUBAGENT_MODEL`），参数照常传入，最后一条回复直接作为命令输出。子 agent 看不到对话历史，也没有 AskUserQuestion。

本机 3 周真实转录（2026-10-29 → 11-19）里，用户直接敲机械命令 37 次。按官方价计算：
- 主会话切 sonnet：缓存热的 18 次成本 −96%（接近翻倍），凉的 19 次 +48%，合计 +17%；
- 只降 effort：上限约 5%（输出只占成本 10%）；
- `/clean-after-merged`（31 次）改 fork：模拟 $50.8 → $7.9（+84%）。

用户 2026-11-20 在 grill-me 访谈中选了推荐项：只 fork `/clean-after-merged`；模型值登记路由键，并由脚本渲染进 frontmatter。

## Decision

1. **主会话里运行的命令与 skill 不写 `model`**。frontmatter 写 `model` 只允许与 `context: fork` 同时出现。规划类命令与 skill 也不写 `context`：`context: fork` 不继承对话，与规划期「只来自主会话或继承对话的 fork」相冲。
2. **不需要对话历史、也不问询的机械命令以 `context: fork` 子 agent 运行**（`agent: general-purpose`、`background: false`），首个是 `/clean-after-merged`。正文写明：只认参数、不问询、最后一条回复即汇报。
3. **fork 命令是执行层派发点**，每个登记一个路由键。首个是 `cleanup.runner`（内建默认 sonnet · low），执行层键共 11 个；`FORK_COMMANDS` 是唯一登记处。
4. **frontmatter 里的 model / effort 由 `model-routing.py frontmatter` 按生效路由渲染**。`install.sh` 安装与升级时自动重渲，`--check` 检查漂移。只渲染带 `context: fork` 的命令；配置非法或形态不符时不写文件。自举仓库（本仓库）的配置不得覆盖 fork 命令的键。
5. **命令里不再建议中途 `/model` 切换**。原因有两条：中途切换会整段丢缓存，回切还要再付一次；现价 Opus 5.5 与 Sonnet 5.5 只差 2 倍。

## Consequences

- **更易**：`/clean-after-merged` 不再按主会话的长上下文计费，冷热两种情况都省；主会话的缓存不受影响；下游改一份 JSON 即可换它的模型，升级不冲掉。
- **更难 / 代价**：
  - 子 agent 看不到对话，用户在对话里给的信息不会被采用，只认参数；
  - `/clean-after-merged` 的汇报由 sonnet · low 给出，质量没有对照数据，合入后观察；
  - 下游改了配置要重渲（安装与升级自动做，平时手动跑一次）；
  - 本仓库不能单独给自己换这个键的值。
- **约束后续变更**：
  - 再把一个命令改成 fork，必须先满足「无需对话历史、不问询」，再登记一个键进 `FORK_COMMANDS`，并同步不变式测试；
  - 想在主会话层换模型的提议，要先拿出能按缓存冷热判定的机制（例如 hook 能看到 frontmatter 切换），否则不做；
  - 探针口径（会话结构、计价、模拟方法）记在来源 change 的 design.md，复测时沿用。
