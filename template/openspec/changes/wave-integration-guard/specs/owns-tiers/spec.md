## ADDED Requirements

### Requirement: owns 条数上限随轮次档
计划校验（`lint`、`waves`、`turns`、`preflight`）SHALL 按切片的轮次档决定 owns 条数上限：标准档 1–12 条，大片档 1–30 条。档位与 `slice-gate.py turns` 的算法相同（计划写 `"turns": "large"`，或 owns 展开后的现存文件数多于 8 个）；不在 git 仓库里时只认计划里的 `turns`。超限时 MUST 判计划不合法，点名该切片并写出两档的上限。
Feature: 大切片可以把文件一条条写清楚
Rule: 上限跟着切片的大小走，小切片想多写要先声明自己是大片

#### Scenario: owns-cap-follows-turn-tier
- **GIVEN** 切片 S1 的 13 条 owns 都是现存文件；切片 S2 的 13 条 owns 里只有 2 个现存文件
- **WHEN** 运行 `waves`；给 S2 写上 `"turns": "large"` 后再运行；再把 S1 的 owns 加到 31 条后运行
- **THEN** 第一次以 2 退出，stderr 点名 S2 并含 12 与 30，不点名 S1
- **AND** 第二次退出 0
- **AND** 第三次以 2 退出，stderr 点名 S1

### Requirement: 宽通配要写理由
带通配符的 owns 条目在轮次档所用的那棵树上展开出多于 20 个现存文件时，该切片 MUST 在 `owns_wide`（对象，键是该片 owns 里的条目原文，值是非空理由）里为它写理由，否则计划不合法，stderr 点名该切片、该条目、展开的文件数与 `owns_wide`。`owns_wide` 的键不是该片的 owns 条目、或理由为空时同样不合法。计划合法时 stderr SHALL 为每个带通配的条目打印一行 `owns: <切片> <条目> → <N> 个文件`。change 的时间线已有 approve 事件时，缺理由 MUST NOT 判红，只打印提示。不在 git 仓库里时不做这项检查。
Feature: 一条通配盖住很多文件时，批准的人看得到为什么
Rule: 宽不是错，但要有一句话的理由

#### Scenario: wide-glob-needs-reason
- **GIVEN** 切片 S1 的 owns 是一条展开出 21 个现存文件的通配
- **WHEN** 运行 `waves`；在 `owns_wide` 里为它写了理由后再运行；再把理由改成空串后运行；再把 `owns_wide` 的键换成不在 owns 里的条目后运行
- **THEN** 第一次以 2 退出，stderr 含该通配、21 与 `owns_wide`
- **AND** 第二次退出 0
- **AND** 后两次都以 2 退出，stderr 含 `owns_wide`

#### Scenario: lint-prints-glob-expansion
- **GIVEN** 切片 S1 的 owns 有一条展开出 21 个现存文件的通配并写了理由，另有一条字面路径
- **WHEN** 运行 `waves`
- **THEN** 退出 0，stderr 有一行 `owns: S1 <该通配> → 21 个文件`
- **AND** 字面路径不出现在这类行里

#### Scenario: approved-change-not-reddened-by-wide-rule
- **GIVEN** 切片 S1 的 owns 是一条展开出 21 个现存文件的通配，没有写理由；该 change 的时间线已有 approve 事件
- **WHEN** 运行 `waves`
- **THEN** 退出 0
- **AND** stderr 仍有该通配的展开行，并提示 `owns_wide`
