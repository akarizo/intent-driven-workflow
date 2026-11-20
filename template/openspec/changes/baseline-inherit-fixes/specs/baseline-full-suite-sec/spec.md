## ADDED Requirements

### Requirement: 锚点条目记录全量耗时
全量 baseline 写出的锚点 SHALL 带 `full_suite_sec`，值等于该基线记下的全量耗时。增量 baseline 与增量 final 写出的新锚点 SHALL 沿用来源锚点的 `full_suite_sec`。全量 final 写出的锚点 SHALL 带本次全量运行的耗时。

Feature: 全量耗时沿锚点链传递
Rule: 锚点是跨 change 复用的来源，全量耗时要跟着锚点走

#### Scenario: anchor-carries-full-suite-sec
- **GIVEN** change c 跑过一次全量 baseline
- **WHEN** 读取锚点池里最新的锚点
- **THEN** 它的 `full_suite_sec` 是数值，等于 c 的 `gate-baseline.json` 里的 `full_suite_sec`

#### Scenario: final-anchor-keeps-full-suite-sec
- **GIVEN** change c 跑过一次全量 baseline，记下的全量耗时为 T；之后提交了非测试文件 `src/a.py` 的改动
- **WHEN** 对 c 运行 final，读取锚点池里最新的锚点；再运行 `final --full`，再读一次
- **THEN** 第一次 final 走增量，最新锚点的 `full_suite_sec` 等于 T
- **AND** `final --full` 之后，最新锚点的 `full_suite_sec` 是大于 0 的数值

### Requirement: 经锚点的 baseline 继承全量耗时
经锚点走增量的 baseline，在本 change 没有已知全量耗时时，SHALL 把来源锚点的 `full_suite_sec` 记作自己的 `full_suite_sec`，SHALL NOT 用补跑耗时代替。

Feature: 增量基线的全量耗时
Rule: 全量耗时只来自真实的全量测量

#### Scenario: anchor-baseline-inherits-full-suite-sec
- **GIVEN** change other 跑过全量 baseline，全量耗时为 T；change c 与 other 的 `gate.test` 相同，c 还没有基线
- **WHEN** 对 c 运行 baseline
- **THEN** c 的基线经锚点走增量，来源是 other
- **AND** c 的 `full_suite_sec` 等于 T

### Requirement: 复用增量基线不拿补跑耗时充当全量
复用本 change 旧基线时，旧基线 `mode` 为 `incremental` 且没有 `full_suite_sec`，新基线的 `full_suite_sec` SHALL 为空，SHALL NOT 取旧基线的 `test.sec`。旧基线带 `full_suite_sec` 时 SHALL 沿用它。

Feature: 复用链上的全量耗时
Rule: 增量基线的 test.sec 是补跑耗时，不是全量耗时

#### Scenario: own-reuse-keeps-inherited-full-suite-sec
- **GIVEN** change c 的基线经 other 的锚点走增量，`full_suite_sec` 等于 other 的全量耗时 T
- **AND** 之后只提交了测试文件的改动
- **WHEN** 再对 c 运行 baseline
- **THEN** c 的基线复用本 change 旧基线（增量）
- **AND** `full_suite_sec` 仍等于 T，不等于本次或上次的 `test.sec`

#### Scenario: legacy-anchor-leaves-full-suite-sec-unknown
- **GIVEN** change other 跑过全量 baseline，锚点池里的锚点都去掉了 `full_suite_sec`（模拟旧版本写的锚点）；change c 还没有基线
- **WHEN** 对 c 运行 baseline，之后只提交测试文件的改动，再运行一次 baseline
- **THEN** 两次 c 的基线都是增量，`full_suite_sec` 都为空
