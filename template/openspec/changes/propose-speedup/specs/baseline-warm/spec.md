## ADDED Requirements

### Requirement: 规划开始时在后台预热全量，结果写成本 change 的旧基线
`slice-gate.py warm --change-dir D [--cmd CMD]` SHALL 按以下顺序定命令：
1. `--cmd` 显式给出时用它；
2. 否则，openspec 根有 `test-tiers.json` 时，打印以「跳过预热」开头的一行，exit 0，不写任何文件；
3. 否则，在 changes 根（不含 `archive/`）下，取 `slices.json` 最新且不是本 change 的那个 change，用它的 `gate.test`（连同 `gate.pytest`）；
4. 都没有时，打印以「跳过预热」开头的一行，exit 0。

命令引用的、位于来源 change 目录下的文件，SHALL 复制到 D 的同一相对位置（已存在则不覆盖），并把命令里的来源目录换成 D。

随后 SHALL 以与 `baseline` 相同的机制跑一次全量：只用 `gate.test`，不跑 verify、检查、lint 与 typecheck，不复用候选。结果写入 `D/gate-baseline.json`：
- 带 `"warm": true`，`plan_sha` 为 null；
- 带 `change`、`cmd_key` 与 `snapshot`；
- 运行期间的改动检测与 `baseline` 相同。

时间线记 `warm` 事件，stdout 的 JSON 带 `test_cmd`。

Feature: 基线预热
Rule: 提前跑全量，命令沿用最近的 change，分层仓库跳过

#### Scenario: warm-runs-full-suite-as-own-baseline
- **GIVEN** 一个仓库：change `prev` 的 `gate.test` 是直接的 pytest 全量命令；新 change `c` 只有目录，没有 `slices.json`
- **WHEN** 运行 `slice-gate.py warm --change-dir openspec/changes/c`
- **THEN** 退出 0；`c/gate-baseline.json` 的 `warm` 为 true、`change` 为 `c`、`ok` 为 true、`mode` 为 `full`、`plan_sha` 为 null
- **AND** stdout JSON 的 `test_cmd` 等于 `prev` 的 `gate.test`，`c/timeline.md` 有 `warm` 事件

#### Scenario: warm-adopts-latest-change-wrapper
- **GIVEN** change `prev` 的 `gate.test` 运行 `openspec/changes/prev/verify/full.py`
- **WHEN** 对新 change `c` 运行 `warm`
- **THEN** `openspec/changes/c/verify/full.py` 被创建，内容与 `prev` 的相同
- **AND** stdout JSON 的 `test_cmd` 引用 `openspec/changes/c/verify/full.py`，不再引用 `prev` 的目录

#### Scenario: warm-skips-tiered-repo
- **GIVEN** openspec 根有 `test-tiers.json`
- **WHEN** 对新 change `c` 运行 `warm`
- **THEN** 退出 0，输出以「跳过预热」开头，`c/gate-baseline.json` 不存在

### Requirement: 正式 baseline 等待预热并按旧基线规则复用
`slice-gate.py baseline` SHALL 在读取旧基线之前检查 `gate-baseline.json`：如果它是 `warm: true` 的运行标记，且 pid 仍存活，SHALL 等它结束，等待期间 stderr 打印一行「等待预热结束」。

之后 SHALL 按现有的本 change 旧基线规则判断复用。复用规则本身 MUST NOT 改动。

Feature: 复用预热结果
Rule: 先等预热，再按原规则复用

#### Scenario: baseline-reuses-warm-when-only-tests-changed
- **GIVEN** 新 change `c` 已预热成功
- **AND** 之后写入 `c/slices.json`（gate.test 等于预热打印的命令），并新增一个测试文件 `tests/test_new.py`
- **WHEN** 运行 `baseline --change-dir`
- **THEN** 退出 0，`mode` 为 `incremental`，`incremental.from.change` 为 `c`，`incremental.rerun_files` 为 `["tests/test_new.py"]`

#### Scenario: baseline-waits-for-running-warm
- **GIVEN** 对新 change `c` 在后台启动 `warm`，它的全量要跑几秒
- **AND** 预热写出运行标记后，写入 `c/slices.json`（gate.test 等于同一命令）
- **WHEN** 预热还在跑时运行 `baseline --change-dir`
- **THEN** stderr 含「等待预热结束」，结果 `mode` 为 `incremental`，`incremental.from.change` 为 `c`
