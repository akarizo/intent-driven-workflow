## ADDED Requirements

### Requirement: /clean-after-merged 以 context: fork 子 agent 运行
`template/.claude/commands/clean-after-merged.md` 的 frontmatter SHALL 含 `context: fork`、`agent: general-purpose`、`background: false`，`model` / `effort` SHALL 等于 `cleanup.runner` 的内建默认。正文 SHALL 写明三点：子 agent 不继承对话、只认参数；不问询；最后一条回复就是交给用户的全部汇报。正文 SHALL NOT 出现 AskUserQuestion。原有步骤、回退段与 Guardrails 保留。

Feature: 机械命令在独立子 agent 里运行
Rule: 不需要对话历史、不问询的机械命令不占用主会话的请求

#### Scenario: cleanup-command-runs-as-fork
- **GIVEN** 模板里的 `clean-after-merged.md` 与 `model-routing.py` 的内建默认
- **WHEN** 读取它的 frontmatter 与正文
- **THEN** frontmatter 有 `context: fork`、`agent: general-purpose`、`background: false`，`model` / `effort` 等于 `cleanup.runner` 的内建默认
- **AND** 正文含「不继承对话」与「最后一条回复」，不含 AskUserQuestion，仍含 `merged-cleanup.py plan --markdown` 与 `merged-cleanup.py apply`

### Requirement: 只有 fork 形态的命令能写 model
模板里所有命令与 skill 的 frontmatter SHALL 满足以下三条：
- 写了 `model` 的 SHALL 同时写 `context: fork`；
- 写了 `context: fork` 的命令文件集合 SHALL 等于 `FORK_COMMANDS` 登记的集合；
- 规划类命令（opsx-propose / explore / new / continue / mini）与规划类 skill SHALL NOT 写 `context`。

Feature: 主会话不被 frontmatter 换模型
Rule: frontmatter 切模型会让主会话整段丢缓存，只允许落在 fork 子 agent 上

#### Scenario: only-fork-commands-carry-model
- **GIVEN** `template/.claude/commands/*.md` 与 `template/.claude/skills/**/SKILL.md`
- **WHEN** 逐个解析 frontmatter
- **THEN** 每个写了 `model` 的文件都写了 `context: fork`
- **AND** 写了 `context: fork` 的命令文件名集合等于 `FORK_COMMANDS` 的值集合，规划类命令与 skill 都没有 `context`

### Requirement: 命令不再建议中途切模型
模板里的命令与 skill SHALL NOT 出现 `/model sonnet`。`opsx-sync.md`、`spec-html.md`、`claudemd-commit.md`、`opsx-explore.md` 原有的模型建议 SHALL 换成同一行说明：中途 `/model` 切换会让首个请求整段重发、不命中缓存，切回来还要再付一次。

Feature: 改正过时的切模型建议
Rule: 中途切模型会丢缓存，现价两档也只差 2 倍

#### Scenario: stale-model-advice-removed
- **GIVEN** 模板里的全部命令与 skill
- **WHEN** 搜索 `/model sonnet` 与新的说明行
- **THEN** 没有文件含 `/model sonnet`
- **AND** 四个命令都含同一行说明，说明里有「不命中缓存」

### Requirement: 自举仓库不覆盖 fork 命令的键
本仓库的 `template/openspec/model-routing.json` SHALL NOT 含 `FORK_COMMANDS` 涉及的组。在 `template/` 下运行 `model-routing.py frontmatter --check` SHALL 退出 0，保证模板发出去的 frontmatter 就是内建默认。

Feature: 自举一致
Rule: 模板文件就是本仓库在用的文件，本仓库配置不得改写它

#### Scenario: self-hosting-config-leaves-fork-keys
- **GIVEN** 本仓库的 `template/openspec/model-routing.json` 与模板命令
- **WHEN** 读取配置的组名，并在 `template/` 下运行 `model-routing.py frontmatter --check`
- **THEN** 配置里没有 `cleanup` 组
- **AND** `--check` 退出 0

### Requirement: 文档登记 cleanup.runner
README 的路由表 SHALL 有 `cleanup.runner` 一行，写明派发点 `/clean-after-merged`、内建默认 sonnet · low。README 与 `docs/WORKFLOW_zh.md` SHALL 写明 `model-routing.py frontmatter` 的用途：改配置后重渲，安装与升级自动运行。

Feature: 文档
Rule: 新键与新子命令进用户文档

#### Scenario: docs-register-cleanup-runner
- **GIVEN** `README.md` 与 `docs/WORKFLOW_zh.md`
- **WHEN** 查找路由表与键清单
- **THEN** README 有一行以 `` | `cleanup.runner` `` 开头，含 `/clean-after-merged` 与 `sonnet · low`
- **AND** 两份文档都含 `cleanup.runner` 与 `model-routing.py frontmatter`
