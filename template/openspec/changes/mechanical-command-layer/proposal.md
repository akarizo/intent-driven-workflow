## Why

C3 原定在机械命令的 frontmatter 写 `model: sonnet`，让主会话跑这些命令的那一轮换成便宜模型（审批页 `docs/flight-routing-config.html` v4 第 07 节，「先探针」）。2026-11-20 的探针与本机 3 周真实转录推翻了这个做法：

- **探针 1（问询之后是否仍生效）**：frontmatter 的 `model` / `effort` 在同一轮内跨过 AskUserQuestion 仍然生效，下一条人类消息恢复会话模型。
- **探针 2（切一次模型的账）**：切模型那一轮的首个请求整段不命中缓存，回到会话模型时还要重写这一轮新增的内容。frontmatter 引起的切换**不触发** PreModelSwitch / PostModelSwitch hook（阳性对照：SDK 的 `set_model` 能触发），所以没法按缓存冷热决定切不切。只改 `effort` 不丢缓存（Opus 5.5 · 一方 API）。
- **真实账（2026-10-29 → 11-19，37 次直接调用，按官方价）**：
  - 会话缓存还热的 18 次，切到 sonnet 后成本接近翻倍（−96%）；已凉的 19 次省 48%；合计只省 17%。
  - 输出只占这些轮次成本的 10%，只降 effort 最多省约 5%。
  - 7 个机械命令里，只有 `/clean-after-merged`（31 次）、`/test-tiers`（5 次）、`/opsx-archive`（1 次）被直接敲过。
- **探针 3（`context: fork`）**：命令改在一个不继承对话的子 agent 里跑。主会话那一轮**一个请求都不发**，子 agent 的输出直接作为命令输出交给用户。frontmatter 的 `model` / `effort` 落在子 agent 上，并且压过 `CLAUDE_CODE_SUBAGENT_MODEL`；参数照常传入。
  - 代价：子 agent 看不到对话历史，也不能问询（子 agent 工具集不含 AskUserQuestion）。
  - `/clean-after-merged` 两条都满足：参数只有可选的 target，判定全在 `merged-cleanup.py`。按 31 个样本模拟，成本 $50.8 → $7.9（−84%），缓存冷热两种情况都省。

用户 2026-11-20 的选择（grill-me 访谈，均为推荐项）：
- C3 方向：只把 `/clean-after-merged` 改成 `context: fork`，其余机械命令不写 `model`，改正过时的切模型建议，决策写进 ADR；
- 模型值来源：登记路由键，由脚本按配置渲染进 frontmatter。原因是 `install.sh --upgrade` 会刷新 `.claude/`，下游手改的值会被冲掉。

## What Changes

- **路由注册表新增 `cleanup.runner`**（内建默认 sonnet · low）：执行层键从 10 个变为 11 个。`show` / `get` 照常可用；它不进 `slices.json.routing`，不参与起飞与收口对账。
- **`model-routing.py` 新增子命令 `frontmatter [--check] [--openspec DIR] [--commands DIR]`**：把生效的 `cleanup.runner` 写进 `clean-after-merged.md` frontmatter 的 `model` / `effort` 两行，其余行原样保留。
  - `--check` 只比对不写，漂移时退出 1；
  - 配置非法、命令文件缺失，或命令不是 `context: fork` 形态时退出 2，不写文件。最后一条用来防止误把主会话命令渲染成切模型。
- **`install.sh` 安装与升级末尾自动重渲**：复制完 `.claude/` 后，按目标仓库的 `openspec/model-routing.json` 运行一次 `frontmatter`。失败只打印警告，不中断安装。
- **`/clean-after-merged` 改为 `context: fork` 子 agent 运行**：frontmatter 增加 `context: fork`、`agent: general-purpose`、`background: false`、`model`、`effort`。正文写明三点：看不到对话历史；不问询；最后一条回复就是交给用户的全部汇报，manual 档命令放进代码块。步骤、脚本判定与 Guardrails 不变。
- **改正过时的切模型建议**：`opsx-sync` / `spec-html` / `claudemd-commit` / `opsx-explore` 四个命令里的「先 `/model sonnet` 再跑，省约 5× token」统一换成一行事实说明，并指向新 ADR。理由有两条：现价 Opus 5.5 与 Sonnet 5.5 只差 2 倍；中途切换会丢缓存，回切还要再付一次。
- **不变式测试**：
  - 命令与 skill 的 frontmatter 只有 `context: fork` 形态才允许写 `model`；
  - `context: fork` 的命令集合等于注册表登记的集合；
  - 规划类命令与 skill 不写 `context`；
  - 命令与 skill 里不再出现 `/model sonnet` 建议；
  - 本仓库（自举）的路由配置不覆盖 fork 命令的键，模板里的 frontmatter 与内建默认一致。
- **文档**：README 路由表与 `docs/WORKFLOW_zh.md` 的键清单登记 `cleanup.runner` 和 `frontmatter` 子命令。
- **新 ADR**：`DRAFT-mechanical-commands-run-in-isolated-subagent`，部分取代 `DRAFT-execution-routing-by-config` 决策第 1 条里的键清单（10 → 11）。

## Capabilities

### New Capabilities
- `routing-frontmatter`：`cleanup.runner` 键、`model-routing.py frontmatter` 渲染 / 漂移检查 / 拒绝条件、`install.sh` 安装与升级时重渲。
- `fork-mechanical-commands`：`/clean-after-merged` 以 `context: fork` 子 agent 运行；只有 fork 形态的命令能写 `model`；过时切模型建议的改正；自举仓库的配置锁定；文档登记。

### Modified Capabilities
（无：`openspec/specs/` 目前为空）

## Impact

- **新增**：`tests/test_routing_frontmatter.py`、`tests/test_install_routing.py`、`tests/test_fork_commands_docs.py`、`openspec/adr/DRAFT-mechanical-commands-run-in-isolated-subagent.md`。
- **修改**：
  - `template/.claude/hooks/model-routing.py`（注册表、新子命令）、`tests/test_model_routing.py`（键数 10 → 11）；
  - `install.sh`（末尾重渲）；
  - `template/.claude/commands/clean-after-merged.md`、`opsx-sync.md`、`spec-html.md`、`claudemd-commit.md`、`opsx-explore.md`；
  - `README.md`、`docs/WORKFLOW_zh.md`。
- **不变**：
  - 主会话里运行的命令一律不写 `model` / `effort`；
  - flight / ship 的 pin、resolve 与收口对账不变；
  - `merged-cleanup.py` 的判定逻辑不变；
  - 规划期不变式不变（规划期产出只来自主会话或继承对话的 fork）。
- **用户可见变化**：`/clean-after-merged` 的汇报由子 agent 给出，主会话不再复述。命令跑完后主会话里只多出这段汇报。
- **未验证（不编）**：sonnet · low 跑 `/clean-after-merged` 的质量没有对照数据，合入后观察前几次的汇报；模拟账按官方价算，订阅额度的折算没有公开口径。
