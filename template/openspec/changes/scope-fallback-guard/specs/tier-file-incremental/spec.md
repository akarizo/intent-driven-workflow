## ADDED Requirements

### Requirement: 分层文件按条目参与增量 final
配置了合法的简写形态 `test-tiers.json` 时，final 的增量判定 SHALL 把分层文件拆成三块与锚点比对，不再把整个文件当作一个指纹或全局文件：

- **单元层**（`unit` 的 `paths` 与 `cmd`）：锚点的分层指纹 SHALL 只由单元层算出；与当前单元层不同的锚点不可用（没有可用锚点 → 全量，`full_why` 照旧为「没有可用锚点」）；
- **区域**：已选区域（`gate.integration`）的条目（`paths` / `covers` / `cmd`）与锚点记录不同、或锚点没有该区域的记录时，该区域本次 SHALL 运行（不进 `regions_skipped`）；未选区域的增、删、改 SHALL NOT 影响 final；
- **`slow_allow`**：按用例 id 与锚点记录的清单比较；新增或删除的条目，其用例所在测试文件存在且落在 `unit.paths` 时，SHALL 并入本次重跑，G10 按当前名单判定；只改理由或批准文字不算变化。

Δ 里的分层文件本身 SHALL NOT 命中「Δ 含全局文件」或「Δ 含未被任何用例触及的非 Python 文件」两条全量条件。

每次写锚点（baseline 全量、final 全量与增量）SHALL 同时记录各区域条目的指纹与 `slow_allow` 的用例 id 清单。

配置了 `gate.impacted` 时，同样 SHALL NOT 因分层文件里单元层以外的改动退回全量。已选区域的命令改动仍按现有规则判红（「基线缺记录或命令已变，重跑 baseline」）。部件形态的 final 恒全量，不变。

#### Scenario: slow-allow-change-keeps-incremental
- **GIVEN** 配置了分层、已选区域 `hooks` 的仓库，baseline 绿
- **AND** 随后在 `slow_allow` 新增 `tests/unit/test_z.py::test_z` 的放行条目，并改了单元层依赖的 `src/a.py`
- **WHEN** 运行 final
- **THEN** final 绿，`incremental.mode` 为 `incremental`
- **AND** `incremental.rerun` 含 `tests/unit/test_a.py` 与 `tests/unit/test_z.py`
- **AND** `incremental.regions_skipped` 含 `hooks`

#### Scenario: selected-region-entry-change-runs-region
- **GIVEN** 配置了分层、已选区域 `hooks` 的仓库，baseline 绿
- **AND** 随后只给区域 `hooks` 的 `covers` 加了一个 glob，并改了 `src/a.py`
- **WHEN** 运行 final
- **THEN** final 绿，`incremental.mode` 为 `incremental`
- **AND** 区域 `hooks` 运行了：`tier_sec.regions` 含 `hooks`，`incremental.regions_skipped` 不含 `hooks`

#### Scenario: unselected-region-change-ignored
- **GIVEN** 配置了分层、已选区域 `hooks` 的仓库，baseline 绿
- **AND** 随后在分层文件里新增一个未选区域 `extra`，并改了 `src/a.py`
- **WHEN** 运行 final
- **THEN** final 绿，`incremental.mode` 为 `incremental`，`incremental.regions_skipped` 含 `hooks`

#### Scenario: unit-change-still-full
- **GIVEN** 配置了分层、已选区域 `hooks` 的仓库，baseline 绿
- **AND** 随后给 `unit.paths` 加了一个 glob `tests/unit2/**`，并改了 `src/a.py`
- **WHEN** 运行 final
- **THEN** `incremental.mode` 为 `full`，`incremental.full_why` 含「没有可用锚点」

#### Scenario: impacted-not-full-on-slow-allow-change
- **GIVEN** 配置了分层与 `gate.impacted`（只跑 `tests/unit/test_a.py` 的选测命令）的仓库，baseline 绿
- **AND** 随后在 `slow_allow` 新增一条放行条目，并改了 `src/a.py`
- **WHEN** 运行 final
- **THEN** final 绿，`incremental.source` 为 `impacted`

### Requirement: 文档描述分层文件按条目判定
`/test-tiers` 命令文档 SHALL 在「放行慢单测」一节写明：放行不会让 final 退回全量，final 只重跑该用例所在的测试文件。`/opsx-verify` 命令与同名 skill、README 列「自动全量」条件时 SHALL NOT 再把 `test-tiers.json` 列为全局文件，并 SHALL 写明锚点比对的是「单元层指纹」。

#### Scenario: docs-describe-tier-file-narrowing
- **GIVEN** 本 change 的文档改动已完成
- **WHEN** 检查 `/test-tiers` 命令文档、`/opsx-verify` 命令与同名 skill、README
- **THEN** `/test-tiers` 的「放行慢单测」一节含「不退回全量」
- **AND** `/opsx-verify` 命令与同名 skill 都含「单元层指纹」，其「自动全量」一行不含 `test-tiers.json`
- **AND** README 的「何时全量」一行不含 `test-tiers.json`
