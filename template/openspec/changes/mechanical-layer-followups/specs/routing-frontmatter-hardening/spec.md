## ADDED Requirements

### Requirement: frontmatter 渲染保留换行风格
`model-routing.py frontmatter` 改写 fork 命令时 SHALL 只改 `model` / `effort` 两行的值，文件其余字节（含每行的换行符）SHALL 保持原样。收尾的 `---` 位于文件末尾、后面没有换行时，SHALL 照常识别为 fork 形态。

Feature: fork 命令 frontmatter 渲染
Rule: 渲染只动路由两行，不动文件的换行风格

#### Scenario: frontmatter-keeps-crlf
- **GIVEN** 命令目录里有 fork 形态的 `clean-after-merged.md`，每行都以 CRLF 结尾，frontmatter 里是 `model: sonnet` 与 `effort: low`；配置把 `cleanup.runner` 设为 haiku · medium
- **WHEN** 运行 `model-routing.py frontmatter`
- **THEN** 退出 0，frontmatter 里是 `model: haiku` 与 `effort: medium`
- **AND** 文件每一行仍以 CRLF 结尾，把这两行换回原值后与原文逐字节相同

#### Scenario: frontmatter-accepts-fence-at-eof
- **GIVEN** 命令目录里的 `clean-after-merged.md` 只有 frontmatter（含 `context: fork`），文件以收尾的 `---` 结束、后面没有换行；配置把 `cleanup.runner` 设为 haiku · medium
- **WHEN** 运行 `model-routing.py frontmatter`
- **THEN** 退出 0，frontmatter 里是 `model: haiku` 与 `effort: medium`
- **AND** 文件仍以 `---` 结束，后面没有补上换行

### Requirement: doctor 报告 frontmatter 漂移
`flight-doctor.py doctor` SHALL 输出 `[routing]` 段，内容是 fork 命令的 frontmatter 与生效路由的对账结果：一致时说明一致，漂移时逐条点名「文件：字段 期望 x 实际 y」并给出重新渲染的命令。doctor SHALL 恒 exit 0，SHALL NOT 改写命令文件。

Feature: 路由漂移体检
Rule: 漂移由脚本发现，不靠人记得手跑检查

#### Scenario: doctor-reports-frontmatter-drift
- **GIVEN** openspec 根的 `model-routing.json` 把 `cleanup.runner` 设为 haiku · medium，`clean-after-merged.md` 的 frontmatter 仍是 sonnet · low
- **WHEN** 运行 `flight-doctor.py doctor --openspec-root <该根>`
- **THEN** 退出 0，输出含 `[routing]` 段，段内点名 `clean-after-merged.md` 的 `model` 期望 haiku 实际 sonnet、`effort` 期望 medium 实际 low，并给出 `model-routing.py frontmatter` 的重跑命令
- **AND** `clean-after-merged.md` 的内容不变

#### Scenario: doctor-reports-frontmatter-in-sync
- **GIVEN** openspec 根没有 `model-routing.json`，`clean-after-merged.md` 的 frontmatter 等于 `cleanup.runner` 的内建默认
- **WHEN** 运行 `flight-doctor.py doctor --openspec-root <该根>`
- **THEN** 退出 0，`[routing]` 段说明 frontmatter 与路由一致，没有漂移条目

### Requirement: 安装补救提示给出升级出路
`install.sh` 渲染 fork 命令路由失败时，提示 SHALL 同时给出两条出路：修好 `openspec/model-routing.json`，或用 `install.sh --upgrade` 刷新 `.claude/`。install 的退出码 SHALL 不因渲染失败而改变。

Feature: 安装时的路由渲染
Rule: 补救提示覆盖与配置无关的失败原因

#### Scenario: install-hint-offers-upgrade
- **GIVEN** 一个已安装本模板的目标仓库，它的 `.claude/commands/clean-after-merged.md` 被换成没有 `context: fork` 的旧版命令
- **WHEN** 不带 `--upgrade` 再运行一次 `install.sh <目标>`
- **THEN** 退出 0，输出报告 fork 命令路由渲染失败
- **AND** 补救提示同时提到 `openspec/model-routing.json` 与 `install.sh --upgrade`
