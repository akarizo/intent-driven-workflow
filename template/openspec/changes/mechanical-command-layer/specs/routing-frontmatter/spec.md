## ADDED Requirements

### Requirement: 路由注册表登记 fork 命令的键
`model-routing.py` SHALL 登记 `cleanup.runner`，内建默认 sonnet · low，执行层键共 11 个。`cleanup` 组 SHALL NOT 进入 `pin` 钉住的组。模块常量 `FORK_COMMANDS` SHALL 是 fork 命令的唯一登记处，把 `cleanup.runner` 映射到 `clean-after-merged.md`。

Feature: 路由注册表
Rule: 以 context: fork 运行的命令也是执行层派发点，必须有键

#### Scenario: registry-has-cleanup-runner
- **GIVEN** 一个 openspec 根，没有 `model-routing.json`
- **WHEN** 运行 `model-routing.py show --json`
- **THEN** 退出 0，输出 11 个键，其中 `cleanup.runner` 为 sonnet · low、来源 `builtin`
- **AND** 配置写了 `{"cleanup": {"runner": {"model": "haiku", "effort": "medium"}}}` 后再运行，`cleanup.runner` 为 haiku · medium、来源 `repo`

### Requirement: frontmatter 子命令把生效路由写进 fork 命令
`model-routing.py frontmatter [--check] [--openspec DIR] [--commands DIR]` SHALL 对 `FORK_COMMANDS` 里的每个命令文件：
- 取首个 `---` 块，把 `model:` / `effort:` 两行替换为生效值，没有这两行时追加到块末；
- 块内其他行与块外正文逐字保留；
- 写模式退出 0。

`--check` SHALL 只比对不写：一致退出 0；不一致时逐条打印「<文件>：<字段> 期望 <x> 实际 <y>」并退出 1。

以下情况 SHALL 退出 2 且不写任何文件：配置非法、命令文件缺失、命令文件的 frontmatter 没有 `context: fork`。

Feature: 路由渲染进 frontmatter
Rule: 只渲染 fork 形态的命令，只动 model 与 effort 两行

#### Scenario: frontmatter-writes-effective-values
- **GIVEN** 一个命令目录里有 fork 形态的 `clean-after-merged.md`（含 `description`、`context: fork`、`agent`、`background`、`model: sonnet`、`effort: low` 与正文）
- **AND** 配置把 `cleanup.runner` 设为 haiku · medium
- **WHEN** 运行 `model-routing.py frontmatter --commands <该目录> --openspec <openspec 根>`
- **THEN** 退出 0，文件的 frontmatter 里是 `model: haiku` 与 `effort: medium`
- **AND** 文件其余各行与原文逐字相同

#### Scenario: frontmatter-check-reports-drift
- **GIVEN** fork 形态的 `clean-after-merged.md` 写着 `model: sonnet`，配置把 `cleanup.runner` 设为 haiku · medium
- **WHEN** 运行 `model-routing.py frontmatter --check`
- **THEN** 退出 1，输出点名该文件与 `model` 的期望值 haiku、实际值 sonnet
- **AND** 文件内容不变；配置改回 sonnet · low 后再运行 `--check`，退出 0

#### Scenario: frontmatter-refuses-non-fork-command
- **GIVEN** `clean-after-merged.md` 的 frontmatter 只有 `description`，没有 `context: fork`
- **WHEN** 运行 `model-routing.py frontmatter`
- **THEN** 退出 2，输出说明它不是 fork 形态
- **AND** 文件内容不变

#### Scenario: frontmatter-invalid-config-writes-nothing
- **GIVEN** fork 形态的 `clean-after-merged.md`，配置把 `cleanup.runner` 的 model 写成 `main`
- **WHEN** 运行 `model-routing.py frontmatter`
- **THEN** 退出 2，输出点名 `cleanup.runner`
- **AND** 文件内容不变

### Requirement: 安装与升级后按目标仓库配置重渲
`install.sh`（安装与 `--upgrade`）SHALL 在复制完 `.claude/` 之后，有 python3 时运行目标仓库里的 `model-routing.py frontmatter --openspec <目标>/openspec`。渲染失败时 SHALL 打印错误与手动重跑的命令，安装照常完成。

Feature: 升级不冲掉下游路由
Rule: .claude/ 刷新后立即按下游自己的 model-routing.json 写回

#### Scenario: upgrade-rerenders-fork-frontmatter
- **GIVEN** 一个已安装本模板的目标仓库，`openspec/model-routing.json` 把 `cleanup.runner` 设为 haiku · medium
- **WHEN** 先运行 `install.sh <目标>`，再运行 `install.sh --upgrade <目标>`
- **THEN** 两次都退出 0
- **AND** 每次之后目标的 `.claude/commands/clean-after-merged.md` frontmatter 都是 `model: haiku` 与 `effort: medium`

#### Scenario: install-survives-invalid-routing
- **GIVEN** 目标仓库的 `openspec/model-routing.json` 把 `cleanup.runner` 的 model 写成 `main`
- **WHEN** 运行 `install.sh --upgrade <目标>`
- **THEN** 退出 0，输出含 `model-routing.py frontmatter` 的手动重跑提示
- **AND** 目标的 `clean-after-merged.md` frontmatter 是内建默认 `model: sonnet` 与 `effort: low`
