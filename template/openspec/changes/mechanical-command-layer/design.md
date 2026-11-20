## Context

现状（main @ e557aed，C4 / C1 / C2 已合入）：

- **执行层路由**：`template/.claude/hooks/model-routing.py` 的 `REGISTRY` 有 5 组 10 个键（flight 5、ship 2、archive.sync、claudemd.evidence、bulk.apply），`BUILTIN` 给内建默认。`effective(root)` 合并配置与默认；`show` / `pin` / `resolve` / `get` 四个子命令。规划期组名（`PLANNING_GROUPS`）被注册表拒收。
- **命令 frontmatter**：template 下的命令都没有 `model` / `effort` / `context`。`tests/test_routing_docs.py::test_planning_docs_carry_no_routing` 只检查规划类命令与 skill。
- **过时建议**：`opsx-sync.md` / `spec-html.md` / `claudemd-commit.md` 写着「主会话在 Opus 时先 `/model sonnet` 再跑，省约 5× token」，`opsx-explore.md` 也有类似一句。
- **下发方式**：`install.sh` 的 `copy_tree "$TEMPLATE_SRC/.claude" "$TARGET/.claude" "$UPGRADE" …` 在升级时整体覆盖 `.claude/`（只保留 `preferences.md`、`settings.json`）。`openspec/model-routing.json` 不在种子清单里，属于下游自己的数据。
- **`/clean-after-merged`**：命令本身即逻辑，无同名 skill。判定全在 `merged-cleanup.py plan` / `apply`。它不问询，只打印计划、执行 safe 档、把 manual 档命令交给用户。已有测试钉住的内容：
  - `tests/test_clean_after_merged_docs.py`：plan 在 apply 之前、`--git-common-dir`、`git worktree list`、回退段、Guardrails 关键词；
  - `tests/test_close_reap_docs.py`：原因表的 `landed` / `dead-attempt` 两行。

官方文档（2026-11-20 读取，Claude Code 2.1.329）：
- skills 的 `model` 字段只对当前这一轮生效，下一条人类消息恢复会话模型；带 `context: fork` 时它设的是子 agent 的模型。
- prompt-caching 页：命令 frontmatter 换模型就是一次模型切换，下一个请求整段不命中缓存。
- hooks 页：PreModelSwitch 只在 `/model`、模型选择器、`/config`、快速模式和 SDK 的 `set_model` 时运行。
- sub-agents 页：子 agent 的工具集不含 AskUserQuestion；`context: fork` 的子 agent 看不到对话历史。

在役 ADR：`DRAFT-execution-routing-by-config`。它规定执行层每个派发用途一个键、值只写模型名，「改注册表要新立 ADR」；规划期只用主会话或继承对话的 fork。

## 探针与数据

探针脚本在 `/tmp/c3probe/`（一次性，未入库）。用 Agent SDK 0.2.186 驱动本机 CLI，会话模型为 opus · medium，每组一个独立会话：普通消息 → 被测命令（中间问询一次）→ 普通消息。

| 组 | 命令那一轮的请求 | 首请求缓存 | 回到会话模型 |
|---|---|---|---|
| 对照（无覆盖） | 4 个，opus · medium | 读 13.3k / 写 7.1k | 全部命中 |
| `model: sonnet` | 4 个，**问询前后都是 sonnet** | 读 0 / 写 20.2k（整段未命中） | 写 7.5k（重写这一轮的内容） |
| `effort: low` | 4 个，问询前后都是 low | 与对照相同 | 全部命中 |
| `context: fork` + `model: haiku` | **主会话 0 个**；子 agent haiku · low | — | 只多一段命令输出 |

另外两条结果：
- PreModelSwitch / PostModelSwitch 日志 hook 在 frontmatter 换模型时没有任何记录；用 SDK 的 `set_model` 做阳性对照，两者都触发了。
- `/probe-fork develop` 在子 agent 里拿到了参数 `develop`。

真实账：扫描 `~/.claude/projects/*/*.jsonl` 主会话转录，取用户直接敲的 7 个机械命令那一轮，按官方价计算（Opus 5.5：1h 写缓存 $8、命中 $0.20、输出 $20；Sonnet 5.5 均减半）。

| 方案 | 样本 | 留在会话模型 | 方案成本 | 增减 |
|---|---|---|---|---|
| 主会话切 sonnet · 缓存热 | 18 | $11.79 | $23.17 | −96% |
| 主会话切 sonnet · 缓存凉 | 19 | $52.17 | $27.32 | +48% |
| `/clean-after-merged` 改 fork（sonnet · low） | 31 | $50.80 | $7.92 | +84% |

fork 的模拟口径：
- 子 agent 的起始上下文取本机近 3 周 471 个子 agent 转录首请求的中位数，31k；
- 每个样本保留实测的请求数、逐请求增量与输出 token；
- 主会话那一轮按 0 个请求计。

成本构成：读缓存 23%、写缓存 67%、输出 10%（输出里思考 token 占 47%）。

## Goals / Non-Goals

**Goals**
- 主会话里运行的命令不切模型，用机械检查保证。
- 不需要对话历史、也不问询的机械命令以 `context: fork` 子 agent 运行，模型按路由配置；首个是 `/clean-after-merged`。
- 下游改了路由配置后，安装与升级不会冲掉 frontmatter 里的值。
- 改正命令里过时的切模型建议。

**Non-Goals**
- 不 fork 其余 6 个机械命令。它们要么问询（verify / archive / sync / spec-html 无参数时问选哪个 change），要么依赖对话（claudemd-commit 取本会话证据，test-tiers 认转录里的人类放行）。
- 不在主会话写 `effort`（上限约 5%，且没有质量数据）。
- 不改 `merged-cleanup.py`，不改 flight / ship 的 pin / resolve / 对账。
- 不预估分钟数。

## Decisions

### D1 · 主会话层不切模型

主会话里运行的命令（没有 `context: fork` 的命令与 skill）frontmatter 不写 `model`。

- **理由**：缓存热时切过去成本接近翻倍，冷时才省；frontmatter 的切换对 hook 不可见，没有办法按冷热有条件地切。静态的 frontmatter 只能二选一，而真实样本里冷热各占一半。
- **备选**：
  - 照原方案 7 个命令都写 `model: sonnet`：净省 17%，热的一半样本亏一倍 → 否；
  - 只写 `effort: low`：缓存安全，但上限约 5%，还会降低 clean-after-merged 之外几个命令里判断步骤的质量，没有数据 → 否；
  - 加 `disable-model-invocation` 再切模型：只能挡住模型自己调用，挡不住缓存损失 → 否。

### D2 · `/clean-after-merged` 以 `context: fork` 子 agent 运行

frontmatter：

```yaml
---
description: …（不变）
context: fork
agent: general-purpose
background: false
model: sonnet
effort: low
---
```

- **`background: false`**：本轮等子 agent 跑完，用户当场看到汇报。缺省值 `true` 会让结果晚到。
- **`agent: general-purpose`**：需要完整工具集（Bash 跑脚本）。Explore / Plan 不带 CLAUDE.md，也不该写盘。
- **正文增加一段「运行方式」**，写明三点：
  - 本命令在不继承对话的子 agent 里运行，只认参数（末尾的 `ARGUMENTS:` 行，可为空）；
  - 不问询，所有判定交给脚本；
  - 最后一条回复就是交给用户的全部汇报，含 `done` / `failed` 与 manual 档代码块。
- 其余步骤、回退段、Guardrails 原样保留。已有测试的钉子不动。
- **可行性依据**：探针 3 表明主会话 0 个请求，模型与 effort 落在子 agent 上，参数照常传入。

**与规划期不变式的关系**：`context: fork` 虽然叫 fork，但官方文档写明它**不**继承对话，是一个新子 agent。仓库里说的「fork」指继承主会话的对话分叉（`subagent_type: "fork"`）。所以规划类命令与 skill 禁止写 `context`（D5 的测试），机械命令才可以用。

### D3 · 路由键 `cleanup.runner` 与 frontmatter 渲染

- **注册表**：`REGISTRY["cleanup"] = ("runner",)`，`BUILTIN["cleanup.runner"] = sonnet · low`（C1 的机械类默认）。新增常量 `FORK_COMMANDS = {"cleanup.runner": "clean-after-merged.md"}`，作为 fork 命令的唯一登记处。
  - `cleanup` 不进 `PINNED_GROUPS`：它不属于飞行；
  - `show` 列出 11 个键，`get cleanup.runner` 照常可用。
- **新子命令** `frontmatter [--check] [--openspec DIR] [--commands DIR]`：
  - `--commands` 缺省为脚本所在目录的 `../commands`（模板与下游一致）；`--openspec` 沿用现有规则，缺省 `./openspec`；
  - 对 `FORK_COMMANDS` 里每个命令：读文件，取首个 `---` 块。块里没有 `context: fork` 行 → 拒绝（exit 2）。否则把 `model:` / `effort:` 两行替换为生效值，没有就追加到块末，块外与块内其他行逐字保留；
  - 写模式逐个打印 `<文件>  <model> · <effort>`，exit 0；
  - `--check` 只比对：一致 exit 0；不一致逐条打印 `<文件>：<字段> 期望 <x> 实际 <y>`，exit 1，不写；
  - 配置非法（`effective` 报错）或命令文件缺失 → exit 2，不写任何文件。
- **备选**：
  - 模板写死：违反 C1「新增执行层派发点必须登记一个键」，下游只能升级后手改 → 否（用户选择）；
  - 由主会话按 `get` 现取再派 Agent：主会话至少要发 2～3 个请求，缓存凉时省不下多少 → 否。

### D4 · 安装与升级时重渲

`install.sh` 在选测种子（`scope-seed`）之后、schema 刷新之前，`PYTHON_OK=1` 时运行：

```bash
python3 "$TARGET/.claude/hooks/model-routing.py" frontmatter --openspec "$TARGET/openspec"
```

- 成功：逐行用 `log_info` 打印「fork 命令路由：<那一行>」；
- 失败（如配置非法）：`log_err` 打印 stderr，并提示修好 `openspec/model-routing.json` 后手动重跑这条命令。安装照常继续、照常退出，frontmatter 保持模板默认；
- 没有 python3：打印一行手动指引。

本仓库（自举）的 `template/openspec/model-routing.json` 不得覆盖 `FORK_COMMANDS` 里的组。否则模板发出去的 frontmatter 会带上本仓库的值，而下游没有配置时应拿到内建默认。由测试锁定：配置里没有这些组，且 `frontmatter --check` 在 `template/` 下 exit 0。

### D5 · 不变式与过时建议

- **新测试 `tests/test_fork_commands_docs.py`**：
  - 扫描 `template/.claude/commands/*.md` 与 `template/.claude/skills/**/SKILL.md` 的 frontmatter：凡写了 `model` 的都必须有 `context: fork`；有 `context: fork` 的命令集合必须等于 `FORK_COMMANDS` 的值；规划类命令与 skill 不写 `context`；
  - 命令与 skill 全文不再出现 `/model sonnet`。
- **四个命令的建议行**：`opsx-sync` / `spec-html` / `claudemd-commit` / `opsx-explore` 的「模型建议」引用块统一换成下面这一行（逐字相同，便于测试）：

  > **模型**：不要为本命令中途用 `/model` 切换模型：切换后的首个请求要把整段上下文重发给新模型、不命中缓存，切回来还要再付一次。

  不写 ADR 指针，因为 ADR 不随模板下发，到下游会成为悬空指针。

### 数据流（C4 dynamic，轻量 ASCII）

```
用户 ──/clean-after-merged [T]──▶ Claude Code
                                   │  frontmatter: context: fork · model/effort（由 D3 渲染）
                                   │  主会话：0 个请求，模型与缓存不动
                                   ▼
                         general-purpose 子 agent（sonnet · low，起始约 31k）
                                   │  Bash: merged-cleanup.py plan → apply
                                   ▼
                         最后一条回复 ──▶ 作为命令输出直接显示给用户
                                         （主会话上下文只多这一段）

install.sh [--upgrade] ── copy_tree .claude/（冲掉 frontmatter）
                      └─▶ model-routing.py frontmatter --openspec $TARGET/openspec
                           （按下游 model-routing.json 写回 cleanup.runner）
```

## Risks / Trade-offs

- [sonnet · low 的汇报质量没有对照数据] → 判定都在脚本里，模型只负责转述和执行 safe 档。合入后看前几次汇报；需要时改配置（`cleanup.runner`）后重渲，无需改代码。
- [子 agent 看不到对话，用户在对话里说的「target 是 develop」不会被采用] → 正文写明只认参数。命令说明本来就以参数为准。
- [下游改了配置、忘了重渲] → 安装和升级时自动重渲；README 写明改配置后手动运行 `model-routing.py frontmatter`；`--check` 可放进下游自己的检查。
- [子 agent 的权限提示] → `background: false` 时在前台运行，权限提示照常交给用户，与原来在主会话里执行相同。
- [官方文档改了 `context: fork` 语义] → 不变式测试只钉住本仓库的文件形态；行为变化要靠重跑 `/tmp/c3probe` 的探针发现。脚本未入库，ADR 里记下探针口径以便复现。

## Migration Plan

1. 本仓库合入后，`/clean-after-merged` 立即以 fork 运行（命令文件即模板文件）。
2. 下游：`install.sh --upgrade` 后自动渲染。没有 `cleanup` 配置的拿到 sonnet · low。
3. **回退**：把 `clean-after-merged.md` 的 frontmatter 还原为只有 `description`，并从 `FORK_COMMANDS` 去掉这一项，就回到主会话运行，语义不变（铁律 10）。

## Open Questions

- `DRAFT-execution-routing-by-config` 决策第 1 条写死了「共 10 个」键。本 change 新立 `DRAFT-mechanical-commands-run-in-isolated-subagent`，只取代这一处键清单，其余条款在役。
- 其余机械命令能否改成「参数必填 + fork」（如 `spec-html <change>`）：本次不做，它们没有被直接敲过的记录。
