## ADDED Requirements

### Requirement: 路由配置默认存在且自带说明
`model-routing.py init` 在 openspec 根没有 `model-routing.json` 时 SHALL 写出全部已登记的键，每个键的 `model` / `effort` 等于内建默认，并带非空的 `desc` 说明该键对应的派发用途；顶层 SHALL 带 `$comment` 说明可选的模型名与 effort。写出的文件 SHALL 能被 `show` / `get` / `pin` 正常读取。

Feature: 执行层路由配置
Rule: 打开文件就能看到所有派发用途和它们的当前值

#### Scenario: init-writes-full-config
- **GIVEN** openspec 根没有 `model-routing.json`
- **WHEN** 运行 `model-routing.py init`
- **THEN** 退出 0，`model-routing.json` 含全部 11 个键，每个键的 `model` / `effort` 等于没有配置文件时 `show` 给出的内建默认，且带非空的 `desc`
- **AND** 顶层有非空的 `$comment`，随后运行 `show` 退出 0，11 个键的来源都是 `repo`

### Requirement: 补全配置不改已有的值
`model-routing.py init` 在 `model-routing.json` 已存在且合法时 SHALL 只补缺失的键（内建默认值加 `desc`）与已有键缺失的 `desc`。已有键的 `model` / `effort` 与已有的 `desc` SHALL 保持原样。配置非法时 SHALL 以退出码 2 点名错误，文件 SHALL 保持不变。

Feature: 执行层路由配置
Rule: 用户写过的值只由用户改

#### Scenario: init-fills-missing-keeps-values
- **GIVEN** `model-routing.json` 只写了 `flight.executor` = haiku · low，没有 `desc`
- **WHEN** 运行 `model-routing.py init`
- **THEN** 退出 0，`flight.executor` 仍是 haiku · low 并补上了 `desc`
- **AND** 其余 10 个键补上了内建默认值与 `desc`

#### Scenario: init-leaves-invalid-config-untouched
- **GIVEN** `model-routing.json` 把 `flight.executor` 的 model 写成 `main`
- **WHEN** 运行 `model-routing.py init`
- **THEN** 退出 2，stderr 点名 `flight.executor`
- **AND** `model-routing.json` 的字节不变

### Requirement: 安装与升级种下路由配置
`install.sh` 安装与 `--upgrade` SHALL 运行 `model-routing.py init`：目标仓库没有 `model-routing.json` 时种下完整文件；已有时只补缺。`init` 失败 SHALL NOT 改变 install 的退出码。

Feature: 安装时的路由配置
Rule: 装完就有可直接改的配置，升级不冲掉用户的值

#### Scenario: install-seeds-routing-config
- **GIVEN** 一个还没装过本模板的目标仓库
- **WHEN** 运行 `install.sh <目标>`，再把目标的 `flight.executor` 改成 haiku · low 后运行 `install.sh --upgrade <目标>`
- **THEN** 两次都退出 0；第一次之后目标的 `openspec/model-routing.json` 含 11 个带 `desc` 的键
- **AND** 升级之后 `flight.executor` 仍是 haiku · low
