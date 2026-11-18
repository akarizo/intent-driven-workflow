## ADDED Requirements

### Requirement: gate-scope.json 可声明 inert 路径
`<openspec 根>/gate-scope.json` SHALL 接受可选字段 `inert`：仓库相对路径 glob 的字符串数组，含义是「这些路径的改动不影响测试结论」。模板 MUST NOT 给它任何缺省值。形状不合法时 lint 与 preflight SHALL 判红并点名字段。
Feature: 仓库自己说哪些路径与测试无关
Rule: 不声明就不生效

#### Scenario: inert-shape-checked
- **GIVEN** `gate-scope.json` 的 `inert` 写成了字符串而不是数组
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出码非 0
- **AND** stderr 含「inert 须是字符串数组」

### Requirement: inert 路径在三处与记账文件同等看待
匹配 `inert` 的路径 SHALL 在以下三处不计入改动：`ship` 判 final 是否过期；final 的同树沿用与取锚点时的 Δ；baseline 的复用判定（本 change 旧基线、基线池、经锚点）。起飞前检查的「基线过期」判定与 lint / typecheck 结论的沿用条件 MUST NOT 受 `inert` 影响。
Feature: 与测试无关的改动不触发重跑
Rule: 只放宽测试结论的复用，不放宽其他判定

#### Scenario: final-reuses-same-tree-across-inert-change
- **GIVEN** 仓库声明 `inert` 为 `["CLAUDE.md"]`，final 已绿
- **AND** 之后只提交了 `CLAUDE.md` 的改动
- **WHEN** 再运行 `slice-gate.py final`
- **THEN** 结果 `incremental.mode` 为 `reused`，摘要含「同树沿用」

#### Scenario: baseline-reuse-ignores-inert-change
- **GIVEN** 依赖图测不到的仓库（包装脚本丢掉插件参数，计划已为此表态），声明 `inert` 为 `["docs/**"]`
- **AND** baseline 跑过一次全量，之后只提交了 `docs/notes.md` 的改动
- **WHEN** 重跑 `slice-gate.py baseline`
- **THEN** 基线 `mode` 为 `incremental`，`incremental.source` 为 `own`，`rerun_files` 为空

#### Scenario: anchor-delta-drops-inert-path
- **GIVEN** 仓库声明 `inert` 为 `["assets/**"]`，基线测到了依赖图，没有任何用例读 `assets/logo.bin`
- **AND** baseline 之后只提交了 `assets/logo.bin` 的改动
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 结果 `incremental.mode` 为 `incremental`，`rerun` 为空

### Requirement: 五类路径永不按 inert 处理
以下路径即使匹配 `inert` 的 glob，也 MUST 照常计入改动：测试路径；全局文件；`global` 命中的路径；`changes/` 下的路径；`gate-scope.json`、`gate-checks.json`、`test-tiers.json`。
Feature: 声明写宽了也不漏测
Rule: 测试与门禁自身的输入不能被声明成无关

#### Scenario: inert-never-covers-test-files-added-later
- **GIVEN** 仓库声明 `inert` 为 `["extras/**"]`，声明时该目录下只有说明文件，final 已绿
- **AND** 之后提交了新的测试文件 `extras/test_new.py`
- **WHEN** 运行 `slice-gate.py ship`
- **THEN** reasons 里有一条含「final 过期」

### Requirement: inert 与依赖图矛盾时依赖图优先
final 取到测到依赖图的锚点时，被任一测试文件依赖的路径 MUST NOT 按 `inert` 处理：依赖它的测试文件照常重跑，并 SHALL 给出一条警告，点名该路径与依赖它的测试文件。
Feature: 实测胜过声明
Rule: 声明错了不会让该重跑的测试被跳过

#### Scenario: graph-wins-when-inert-contradicts
- **GIVEN** 基线测到 `tests/test_b.py` 读 `data/b.json`
- **AND** 之后才把 `data/**` 声明成 `inert`，并提交了 `data/b.json` 的改动
- **WHEN** 运行 `slice-gate.py final`
- **THEN** 结果 `incremental.mode` 为 `incremental`，`rerun` 含 `tests/test_b.py`
- **AND** warnings 里有一条同时含 `inert`、`data/b.json` 与 `tests/test_b.py`

### Requirement: lint 与 preflight 核对 inert 声明
选测复核（lint、preflight、baseline 开跑前）SHALL 对 `inert` 做两项核对，任一不过即判红：
- glob 匹配到已跟踪的测试路径、全局文件或 `global` 命中的路径 → 点名 glob、路径与类别；
- 锚点池里有与本计划同命令指纹、同分层指纹且测到依赖图的锚点时，取最新一条对账：有测试文件依赖了匹配 `inert` 的路径 → 点名路径与测试文件。
没有这样的锚点时 MUST NOT 因对账判红。
Feature: 起飞前发现写错的声明
Rule: 能机械判定的矛盾不留到运行时

#### Scenario: lint-rejects-inert-matching-test-or-global-files
- **GIVEN** `inert` 写了 `["tests/**", "*.ini"]`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出码非 0
- **AND** 有一条违规同时含 `tests/**`、`tests/test_a.py` 与「测试路径」
- **AND** 有一条违规同时含 `*.ini`、`pytest.ini` 与「全局文件」

#### Scenario: lint-reconciles-inert-with-dependency-graph
- **GIVEN** 基线测到 `tests/test_b.py` 读 `data/b.json`
- **AND** 之后把 `data/**` 声明成 `inert`
- **WHEN** 分别运行 `slice-gate.py lint` 与 `slice-gate.py preflight`
- **THEN** 两者退出码都非 0
- **AND** 各有一条违规同时含 `data/b.json` 与 `tests/test_b.py`

#### Scenario: inert-consistent-with-graph-passes-lint
- **GIVEN** 基线测到了依赖图，没有任何用例触及 `scripts/helper.sh`
- **AND** 之后把 `scripts/**` 声明成 `inert`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出码为 0

### Requirement: doctor 列出 inert 声明与对账结果
`flight-doctor.py doctor` 的 `[declare]` 一节 SHALL 列出 `inert` 的值；声明了 `inert` 时另列出它与锚点池里各条测到依赖图的锚点的矛盾（路径与测试文件）；没有这样的锚点时 SHALL 注明无法对账。`flight-doctor.py` MUST 仍恒退出 0。
Feature: 体检看得见声明对不对
Rule: 只读，不阻断

#### Scenario: doctor-lists-inert-and-conflicts
- **GIVEN** 仓库声明了 `inert`，锚点池为空
- **WHEN** 运行 `flight-doctor.py doctor`
- **THEN** 退出码为 0，输出里有一行含 `inert` 与「无法对账」
- **AND** 基线测到 `tests/test_b.py` 读 `data/b.json`、再把 `data/**` 声明成 `inert` 后重跑，输出里有一行含 `data/**`，另有一行同时含「矛盾」、`data/b.json` 与 `tests/test_b.py`

### Requirement: 文档写明 inert 与无图退路
`flight-runner-contract.md` SHALL 在可选字段表里列出 `inert` 并写明对账、永不按 `inert` 处理的路径、依赖图未测时无法对账；结果文件 `mode` 的取值 SHALL 列出 `tests-only`；接入步骤 SHALL 提到 `inert`。`opsx-propose.md`、同名 skill、schema 的 tasks instruction 与 `README.md` 的可选字段清单 SHALL 含 `inert`。
Feature: 接入的唯一依据是契约文档
Rule: 命令与同名 skill 同改

#### Scenario: docs-describe-inert-and-tests-only
- **GIVEN** 本 change 合入后的模板
- **WHEN** 读运行器契约、propose 命令与同名 skill、schema、README
- **THEN** 契约的可选字段表有以 `inert` 开头的一行且含「对账」
- **AND** 契约含「无法对账」与「永不」，结果文件 `mode` 一行含 `tests-only`，「接入步骤」一节含 `inert`
- **AND** 其余四处都含 `inert`
