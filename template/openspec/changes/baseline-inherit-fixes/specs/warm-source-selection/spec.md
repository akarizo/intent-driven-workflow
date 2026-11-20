## ADDED Requirements

### Requirement: 预热按 git 最后提交时间选来源
`slice-gate.py warm` 在没有 `--cmd` 时，SHALL 从 changes 根下其它 change 中选来源。候选是除 `archive` 与本 change 外，`slices.json` 存在且 `gate.test` 非空的 change。选择规则如下：
- 取 `slices.json` 在 git 里最后一次提交时间最新的；
- 时间相同取 change 名字典序最大的；
- 从没提交过的排在所有已提交的之后，它们之间同样按名字取。

结果 SHALL NOT 取决于文件修改时间。

Feature: 预热来源确定
Rule: 同一份 git 历史与 change 集合，预热总是选中同一个来源

#### Scenario: warm-picks-latest-committed-change
- **GIVEN** change old 与 new 的 `gate.test` 不同；new 的 `slices.json` 在 old 之后提交；之后把 old 的 `slices.json` 的修改时间改得比 new 晚
- **WHEN** 对新 change c 运行 warm
- **THEN** 退出 0，stdout 的 `test_cmd` 是 new 的 `gate.test`

#### Scenario: warm-breaks-commit-tie-by-name
- **GIVEN** change alpha 与 beta 的 `gate.test` 不同，两者的 `slices.json` 在同一次提交里
- **WHEN** 对新 change c 运行 warm
- **THEN** 退出 0，stdout 的 `test_cmd` 是 beta 的 `gate.test`

#### Scenario: warm-ranks-uncommitted-after-committed
- **GIVEN** change kept 的 `slices.json` 已提交；change draft 的 `slices.json` 从没提交过，修改时间更晚；两者 `gate.test` 不同
- **WHEN** 对新 change c 运行 warm
- **THEN** 退出 0，stdout 的 `test_cmd` 是 kept 的 `gate.test`
