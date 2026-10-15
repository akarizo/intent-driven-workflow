## ADDED Requirements

### Requirement: 安装器缺省从本仓下载
`install.sh` 的 `REPO_URL` 缺省 SHALL 为 `https://github.com/akarizo/intent-driven-workflow`（仍可用 `IDT_REPO_URL` 覆盖），`IDT_BRANCH` 缺省 SHALL 为 `main`。
Feature: installer-edition

#### Scenario: help-names-workflow-repo
- **GIVEN** 本仓的 `install.sh`
- **WHEN** 运行 `install.sh --help`
- **THEN** 输出里 `IDT_REPO_URL` 的缺省值是 `https://github.com/akarizo/intent-driven-workflow`
- **AND** 输出里 `IDT_BRANCH` 的说明含「分支或 tag」

### Requirement: pipe 模式按分支或 tag 下载并交给归档自带的安装器
pipe 模式 SHALL 依次尝试 `refs/heads/<ref>`、`refs/tags/<ref>` 的归档，都失败时 SHALL 以 4 退出、列出两个地址、不创建目标目录；下载后 SHALL 交给归档自带的 `install.sh`（`bash <解压目录>/install.sh [--upgrade] <TARGET>`，stdin 接 `/dev/null`）执行，退出码原样透传，退出时删除临时目录；归档里缺 `install.sh` 或 `template/` 时 SHALL 以 4 退出。

#### Scenario: pipe-installs-tag-only-ref
- **GIVEN** 源里只有 tag `stable-v9.9` 的归档（refs/tags 下），没有同名分支；归档里是桩 install.sh 与 `template/VERSION=v9.9`
- **WHEN** 以 `IDT_BRANCH=stable-v9.9` 用管道运行 install.sh
- **THEN** 以 0 退出
- **AND** 归档里的 install.sh 被执行，读到的 VERSION 是 v9.9

#### Scenario: pipe-default-ref-is-main-branch
- **GIVEN** 源里只有分支 main 的归档（refs/heads 下），归档里是桩 install.sh 与 `template/VERSION=main`
- **WHEN** 不设 `IDT_BRANCH`，用管道运行 install.sh
- **THEN** 以 0 退出
- **AND** 归档里的 install.sh 被执行，读到的 VERSION 是 main

#### Scenario: pipe-missing-ref-lists-both-urls
- **GIVEN** 源里只有分支 main 的归档
- **WHEN** 以 `IDT_BRANCH=nope` 用管道运行 install.sh
- **THEN** 以 4 退出；[err] 行里同时出现 `refs/heads/nope` 与 `refs/tags/nope`
- **AND** 目标目录没有被创建

#### Scenario: pipe-delegates-args-to-archived-installer
- **GIVEN** 源里有 tag `stable-v9.9` 的归档，其 install.sh 是记录参数的桩
- **WHEN** 以 `IDT_BRANCH=stable-v9.9` 用管道运行 `install.sh --upgrade <target>`
- **THEN** 以 0 退出，桩收到的参数恰为 `--upgrade <target>`
- **AND** 目标目录里没有 `.claude/`（引导器自身没有复制模板）

#### Scenario: pipe-propagates-exit-and-cleans-temp
- **GIVEN** 源里有 tag `stable-v9.9` 的归档，其 install.sh 是以 3 退出的桩；TMPDIR 指向一个空目录
- **WHEN** 以 `IDT_BRANCH=stable-v9.9` 用管道运行 install.sh
- **THEN** 以 3 退出
- **AND** TMPDIR 目录仍为空

#### Scenario: pipe-archive-without-template-exits-4
- **GIVEN** 源里有 tag `stable-v9.9` 的归档，里面只有记录调用的桩 install.sh，没有 `template/`
- **WHEN** 以 `IDT_BRANCH=stable-v9.9` 用管道运行 install.sh
- **THEN** 以 4 退出，[err] 行指出归档里没有 `template/`
- **AND** 桩没有被执行，目标目录没有被创建

#### Scenario: pipe-real-installer-runs-local-mode
- **GIVEN** 源里分支 main 的归档由本仓当前的 install.sh 与 `template/` 打成；PATH 上有 openspec 桩，没有 claude
- **WHEN** 用管道运行 `install.sh <target>`
- **THEN** 以 0 退出，目标含 `.claude/hooks/intent-gate.py`，CLAUDE.md 含 intent-driven:begin 段
- **AND** 只下载一次，且交接后按本地模式运行

### Requirement: 升级保留用户的 settings.json
`--upgrade` SHALL NOT 用模板覆盖 `.claude/settings.json`；SHALL 只补模板 settings.json 里用户缺失的顶层键（hooks 除外、已有键不动、不深合并），hooks 照旧按命令串去重合并。

#### Scenario: upgrade-adds-missing-template-settings-keys
- **GIVEN** 已安装的目标仓库，用户把 `.claude/settings.json` 改成 `{"env": {"MY_KEY": "1"}, "custom": true}`
- **WHEN** 运行 `install.sh --upgrade`
- **THEN** env 仍恰为 `{"MY_KEY": "1"}`、custom 仍为 true
- **AND** 补上了模板的 worktree 键 `{"baseRef": "head"}`

#### Scenario: upgrade-reregisters-v2-hooks
- **GIVEN** 已安装的目标仓库，其 `.claude/settings.json` 里没有 takeoff-gate、`slice-gate.py checkpoint`、stop-gate 三条注册（Mod 版安装器升级时移除过）
- **WHEN** 运行 `install.sh --upgrade`
- **THEN** 三条注册都回到 settings.json 的 hooks 里

### Requirement: openspec/ 只下发种子
安装与升级 SHALL 只按清单下发 `openspec/` 的种子（`.gitignore`、`config.yaml`、`changes/.gitkeep`、`adr/.gitkeep`、`superpower/.gitkeep` 与 `schemas/` 整个目录），已存在即跳过；本库自己的 change 目录与 ADR 草稿 SHALL NOT 再拷贝；目标项目里与它们同名的条目 SHALL 以 [info] 列出，提示多半是旧版安装器误拷、可手动删除（不代删）。

#### Scenario: fresh-install-ships-only-seeds
- **GIVEN** 一个空目录
- **WHEN** 运行 `install.sh <目录>`
- **THEN** 以 0 退出
- **AND** `openspec/` 里的文件恰为种子清单加上模板 `openspec/schemas/` 下的全部文件

#### Scenario: upgrade-adds-no-dev-artifacts
- **GIVEN** 用 install.sh 装好的项目；用户自己建了 change my-change（含 proposal.md）与 ADR `0001-mine.md`
- **WHEN** 运行 `install.sh --upgrade <项目>`
- **THEN** 以 0 退出；changes/ 下只有 `.gitkeep` 与 my-change，adr/ 下只有 `.gitkeep` 与 `0001-mine.md`
- **AND** 输出不含「旧版安装器」

#### Scenario: upgrade-keeps-user-seed-edits
- **GIVEN** 用 install.sh 装好的项目；用户改过 `openspec/config.yaml`，`openspec/schemas/intent-driven/schema.yaml` 被本地改坏
- **WHEN** 运行 `install.sh --upgrade <项目>`
- **THEN** 以 0 退出；config.yaml 仍是用户的内容
- **AND** schema.yaml 恢复为模板原文

#### Scenario: upgrade-lists-suspected-dev-artifacts
- **GIVEN** 已装项目里有与模板 change 目录同名的目录、与模板 DRAFT ADR 同名的文件（模拟旧版安装器误拷），另有用户自己的 my-change
- **WHEN** 运行 `install.sh --upgrade <项目>`
- **THEN** 以 0 退出；输出含「旧版安装器」与「安装器不代删」；提示段列出那个 change 目录与那份 ADR，不列 my-change
- **AND** 三者都仍在

### Requirement: 从 Mod 版切换过来时提示退场
目标项目 `.claude/settings.json` 的 `enabledPlugins` 里 `flight@intent-driven` 为 true 时，安装器 SHALL 在结束前醒目提示该插件会接管 `/opsx-apply`、与本版冲突，并打印 `claude plugin uninstall flight@intent-driven -s project` 与 `claude plugin marketplace remove intent-driven --scope project`；SHALL NOT 代为执行、SHALL NOT 改退出码。目标里存在 Mod 版遗留的 `.claude/hooks/ledger.py`、`.claude/hooks/plan_fp.py` 时 SHALL 列出并提示可手动删除（不代删）。

#### Scenario: upgrade-warns-enabled-flight-plugin
- **GIVEN** 已安装的目标仓库，其 `.claude/settings.json` 的 `enabledPlugins` 含 `"flight@intent-driven": true`
- **WHEN** 运行 `install.sh --upgrade`
- **THEN** 以 0 退出；输出含 flight@intent-driven、`claude plugin uninstall flight@intent-driven -s project` 与 `claude plugin marketplace remove intent-driven --scope project`
- **AND** settings.json 里的 enabledPlugins 原样保留

#### Scenario: upgrade-lists-mod-leftovers
- **GIVEN** 已安装的目标仓库里有 Mod 版留下的 `.claude/hooks/ledger.py` 与 `.claude/hooks/plan_fp.py`
- **WHEN** 运行 `install.sh --upgrade`
- **THEN** 输出列出这两个文件并提示可手动删除
- **AND** 两个文件都仍在

### Requirement: README 写明本仓的版本与安装方式
README 的「安装指定版本」SHALL 写明：pipe 写法用本仓 main 上的 install.sh 加 `IDT_BRANCH`、clone 写法用 `--branch`，列出本仓可用 tag，并提醒不支持用 `--upgrade` 降级；README SHALL 另写明与 Mod 版（`akarizo/intent-driven-claude-code`）的关系与从 Mod 版切换的步骤。

#### Scenario: readme-documents-pinned-install
- **GIVEN** README.md
- **WHEN** 取 README 中「### 安装指定版本」到下一个二级或三级标题之间的内容
- **THEN** 这段含本仓 main 的 install.sh 地址、`IDT_BRANCH=stable-v2.0`、`--branch stable-v2.0` 与「降级」
- **AND** README 另有一段写明 `akarizo/intent-driven-claude-code` 与 `claude plugin uninstall flight@intent-driven -s project`
