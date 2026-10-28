## ADDED Requirements

### Requirement: 嵌套 pytest 会话不污染门禁的度量
库注入的每次 pytest 运行（`run_test_gate` 跑的全量与区域、增量 final 的重跑）SHALL 同时加载一个防护插件。防护插件这样区分外层与嵌套：

- **外层会话**：没有外层标记、也不是 xdist worker 的会话。它在 `pytest_configure` 里设外层标记，自己起的 xdist worker 带上「属于外层」的标记。
- **嵌套会话**：其余一切会话。它们 SHALL 关掉 junit 输出，不写探针记录，也不写依赖图记录。

于是，用例里起的、继承了环境的嵌套 pytest，既不会覆盖外层的 junit，也不会把自己的 nodeid 混进外层的探针或依赖图。

防护插件加载失败时（包装脚本覆写了 `PYTHONPATH` 等），门禁 SHALL 不带插件重跑一次并用这次的结果。这时依赖图判为没测到，同时给出警告。

#### Scenario: nested-pytest-does-not-overwrite-junit
- **GIVEN** 被测套件有一个必然失败的用例 `test_bad`
- **AND** 另一个用例用子进程起一个嵌套 pytest，嵌套会话继承全部环境变量，并在外层会话结束前跑完 0 个失败用例
- **WHEN** 门禁以 `run_test_gate` 运行这个套件
- **THEN** 结果可度量，失败清单恰好是 `test_bad`，不报「计数不一致」

#### Scenario: nested-pytest-not-recorded-in-probe-or-deps
- **GIVEN** 被测套件有一个用例用子进程起嵌套 pytest，嵌套会话跑的用例 nodeid 在外层套件里不存在
- **WHEN** 门禁以依赖图与探针方式运行这个套件
- **THEN** 依赖图与探针记录里都没有嵌套会话的用例或测试文件

#### Scenario: guard-plugin-load-failure-falls-back
- **GIVEN** `gate.test` 是一个包装脚本，它把 `PYTHONPATH` 覆写成固定值后再运行 pytest
- **WHEN** 门禁运行它
- **THEN** 门禁用不带插件重跑的结果判定（与没有防护插件时一致）
- **AND** 依赖图判为没测到，并给出说明原因的警告

### Requirement: 全量运行记录依赖图并写入锚点池
`gate.test` 是 pytest 时，每次全量运行（baseline 跑全量、final 跑全量）SHALL 顺带记录依赖图，以测试文件为单位（仓库相对路径）。一个测试文件的依赖是下列仓库内文件的并集：

- 它的静态 import 闭包，只算仓库内的 `.py` 模块；
- 收集期间与它的每个用例窗口内被 open 的文件；从 `__pycache__` 读字节码的，映射回对应的源文件；
- 它的用例起的子进程，命令行里出现的仓库内路径；
- 这些子进程若是 Python 解释器，并且继承了门禁注入的 `sitecustomize`：该进程加载过的模块文件与 open 过的文件。

一个用例起 Python 子进程时，如果显式给的 env 不含门禁注入的 `PYTHONPATH`，或者带 `-I` / `-S` / `-E`，录不到的那个测试文件 SHALL 记为「盲」。

运行结束后，门禁 SHALL 把一条锚点写进 `<git common dir>/flight-anchors/`（原子写，只留最新若干条）。锚点含：

- `change`、`commit`、`at`；
- 未提交改动的快照；
- `gate.test` 的命令指纹，以及分层文件指纹（有分层时）；
- 全部测试文件清单；
- 失败用例（仓库相对 nodeid）；
- 依赖图与盲文件清单；
- `measured` 标记，表示依赖图是否测到。

baseline 跑全量时，SHALL 同时在 `gate-baseline.json` 的 `test` 段记 `failed_nodes`：仓库相对 nodeid 形式的预存红。

#### Scenario: full-run-records-dependency-map
- **GIVEN** 被测仓库有三个测试文件：
  - `tests/test_a.py` 在模块顶部 import `src/a.py`；
  - `tests/test_b.py` 在用例里读 `data/b.json`；
  - `tests/test_c.py` 用子进程运行 `python tools/c.py`，而 `tools/c.py` import `src/c_lib.py`
- **WHEN** baseline 跑全量
- **THEN** 锚点池里有一条本 change 的锚点，`measured` 为真，依赖图是：
  - `tests/test_a.py` 含 `src/a.py`；
  - `tests/test_b.py` 含 `data/b.json`；
  - `tests/test_c.py` 含 `tools/c.py` 与 `src/c_lib.py`

#### Scenario: blind-subprocess-marks-test-file
- **GIVEN** 被测仓库的 `tests/test_iso.py` 用 `env={}` 起一个 Python 子进程去运行仓库内脚本
- **WHEN** baseline 跑全量
- **THEN** 锚点的盲文件清单含 `tests/test_iso.py`

#### Scenario: baseline-records-failed-nodes
- **GIVEN** 被测仓库有一个预存失败的用例 `tests/test_old.py::test_broken`
- **WHEN** baseline 跑全量
- **THEN** `gate-baseline.json` 的 `test.failed_nodes` 恰好是 `["tests/test_old.py::test_broken"]`，锚点的失败用例相同

### Requirement: final 默认增量运行
final 在 G7 绿、且没有命中任何自动全量条件时，SHALL 增量运行 `gate.test`。

**取锚点**：从锚点池里挑可用的锚点。可用的条件：命令指纹与分层指纹都与当前相同，`measured` 为真，锚点 commit 是 HEAD 的祖先。可用的不止一个时，取 Δ 最小的，同样小取最新。Δ 是锚点树与当前树（含未提交改动）的内容差，按 blob 比较，不含本 change 的计划工件与其他 change 目录。

**选测**：重跑下列测试文件，用 `gate.pytest`（缺省从 `gate.test` 推导）实跑，并同样挂防护与依赖图插件：

- 依赖与 Δ 相交的测试文件；
- Δ 里现存的测试文件；
- 锚点里有失败用例的测试文件；
- 盲文件。

**判红**：没选中的用例沿用锚点结论。重跑出的失败里，不在基线 `failed_nodes` 里的，记 `G2 test` 红并逐条列出。重跑以超时、收集错误或异常退出码结束时，也记红并给出原因。

**前移锚点**：增量 final 结束后 SHALL 写一条新锚点。重跑过的测试文件用本次的结论与依赖，其余的沿用旧锚点。

**输出**：final 的 JSON SHALL 带 `incremental` 段，含 `mode`（`incremental`）、`source`（`builtin` / `impacted`）、锚点的 `change` 与 `commit`、Δ 文件数、重跑的测试文件清单 `rerun` 与用例数、沿用的用例数。`summary` 末尾追加 `；增量：重跑 a 个文件（b 个用例）/ 沿用 c 个，锚点 <commit 前 10 位>`。timeline 备注写 `增量（锚点 <commit 前 10 位>，重跑 a 个文件 / 沿用 c 个用例） ok|red`，结论词仍在末尾。`source` 为 `impacted` 时门禁不知道选测命令选了哪些用例：`rerun`、重跑用例数 `rerun_tests` 与沿用用例数 `inherited_tests` 照样给出、值为 null；`summary` 末尾改为追加 `；增量：gate.impacted，Δ n 个文件，锚点 <commit 前 10 位>`，timeline 备注写 `增量（gate.impacted，锚点 <commit 前 10 位>，Δ n 个文件） ok|red`。

#### Scenario: final-reruns-only-affected-tests
- **GIVEN** 依赖图已记录的仓库（同 `full-run-records-dependency-map`），baseline 绿
- **AND** 随后只改了 `src/a.py`，而且仍然正确
- **WHEN** 运行 final
- **THEN** final 绿；`incremental.mode` 为 `incremental`，只重跑了 `tests/test_a.py` 这一个测试文件
- **AND** `tests/test_b.py` 与 `tests/test_c.py` 的用例计入沿用数
- **AND** `summary` 与 timeline 备注含「增量」与锚点 commit 前缀

#### Scenario: final-incremental-red-on-new-failure
- **GIVEN** 依赖图已记录的仓库，baseline 绿
- **AND** 随后改坏了 `src/a.py`，使 `tests/test_a.py::test_a` 失败
- **WHEN** 运行 final
- **THEN** final 红，failed 里有一条 `G2 test` 列出 `tests/test_a.py::test_a`；`incremental.mode` 仍为 `incremental`

#### Scenario: final-reruns-anchor-failures-and-changed-tests
- **GIVEN** baseline 记录了预存红 `tests/test_old.py::test_broken`
- **AND** 随后只改了测试文件 `tests/test_b.py`
- **WHEN** 运行 final
- **THEN** 重跑的测试文件恰好是 `tests/test_b.py` 与 `tests/test_old.py`
- **AND** `test_broken` 仍失败，但它是基线预存红，不判红；final 绿

#### Scenario: final-moves-anchor-forward
- **GIVEN** 第一次 final 增量通过，之后又改了 `src/c_lib.py` 并提交
- **WHEN** 再运行一次 final
- **THEN** 第二次 final 的锚点 commit 是第一次 final 时的 HEAD，只重跑 `tests/test_c.py`

### Requirement: 命中触发条件时 final 自动跑全量
final 在下列任一条件成立时，SHALL 改为全量运行 `gate.test`（与今天的全量判定相同，按基线差分）：

- 带了 `--full`；
- 没有可用锚点：池空、命令或分层指纹不同、锚点不是 HEAD 的祖先、依赖图没测到；
- 基线有预存红，但缺 `failed_nodes`；
- Δ 含全局文件：任何目录下的 `conftest.py`，或文件名是 `pytest.ini`、`pyproject.toml`、`setup.cfg`、`tox.ini`、`setup.py`、`requirements*.txt`、`Pipfile`、`Pipfile.lock`、`poetry.lock`、`uv.lock`、`.python-version`，或分层文件 `test-tiers.json`；
- Δ 含这样的文件：锚点时已存在、不在任何测试文件的依赖里、不是测试文件、扩展名不是 `.py`、也不是文档（`.md` / `.mdx` / `.markdown` / `.txt` / `.rst` / `.html`）。

全量跑完后同样写锚点。

`incremental.mode` 为 `full`，并在 `incremental.full_why` 写明命中的条件；timeline 备注写 `全量（<原因>） ok|red`。

Δ 里有锚点时已存在、不在任何依赖里的 `.py` 文件（非测试）时，不触发全量，只给警告「未被任何用例加载」。

#### Scenario: final-full-when-global-file-changes
- **GIVEN** 依赖图已记录的仓库，baseline 绿，随后改了 `tests/conftest.py`
- **WHEN** 运行 final
- **THEN** final 全量运行；`incremental.mode` 为 `full`，`full_why` 含 `conftest.py`

#### Scenario: final-full-when-no-anchor
- **GIVEN** 锚点池为空（例如锚点目录被删）
- **WHEN** 运行 final
- **THEN** final 全量运行，`full_why` 说明没有可用锚点；跑完后锚点池里有一条本次的锚点

#### Scenario: final-full-when-unseen-non-python-file-changes
- **GIVEN** 依赖图已记录的仓库里有一个从未被任何用例触及的 `scripts/helper.sh`，随后改了它
- **WHEN** 运行 final
- **THEN** final 全量运行，`full_why` 含 `scripts/helper.sh`

#### Scenario: final-full-flag-forces-full
- **GIVEN** 依赖图已记录的仓库，只改了 `src/a.py`
- **WHEN** 运行 `final --full`
- **THEN** final 全量运行，`full_why` 说明是手动要求

### Requirement: 同一棵代码树的 final 沿用上次结论
每次 final 结束后，SHALL 把以下内容写进 `<git common dir>/flight-final/<change>.json`：本次结果、commit、未提交改动快照，以及指纹集合。指纹集合包括：`plan_sha`、`scenario_tests`，以及 `gate.test` / `gate.lint` / `gate.typecheck` / `gate.checks` / `gate.impacted` / 分层文件的命令指纹。

下一次 final 开始时，如果同时满足以下条件，SHALL 直接沿用记录里的结论，不运行任何测试、lint、typecheck 或检查：

- 记录的结果是绿；
- 记录的树与当前树内容相同（不含记账文件）；
- 指纹集合全部相同。

沿用时：结果的 `commit` 是当前 HEAD，`incremental.mode` 为 `reused`，带被沿用记录的 commit；照常追加一行 gate-report，timeline 备注写 `同树沿用 <commit 前 10 位> ok`。

记录是红时不沿用，照常运行。

`ship` 判 final 是否过期时，SHALL 比较 final 行的 commit 与 HEAD 的树：两者之差只含记账文件（或没有差别）就算新鲜，不再要求 final commit 是 HEAD 的祖先。final commit 在本地不存在时仍判过期。

#### Scenario: same-tree-final-reuses-result
- **GIVEN** final 刚刚绿过，之后只提交了飞行记录文件
- **AND** 某个用例每次运行都会往仓库外的计数文件追加一行
- **WHEN** 再运行一次 final
- **THEN** final 绿，`incremental.mode` 为 `reused`；计数文件的行数没有增加
- **AND** timeline 备注含「同树沿用」

#### Scenario: red-final-is-not-reused
- **GIVEN** 上一次 final 红，之后代码没有变
- **WHEN** 再运行一次 final
- **THEN** final 照常运行，`incremental.mode` 不是 `reused`

#### Scenario: ship-fresh-when-tree-unchanged
- **GIVEN** final 在 commit X 上绿过
- **AND** 随后把 X 改写成内容相同、但不是 X 后代的 commit Y（例如 amend 只改提交说明），HEAD 为 Y
- **WHEN** 运行 `ship`
- **THEN** reasons 里没有「过期」

### Requirement: final 给检查命令注入 Δ 与锚点
final 运行 `gate.checks` 的 `final` 命令时，SHALL 在既有运行契约的环境变量之外再注入三个：

- `GATE_FINAL_MODE`：`incremental` 或 `full`；
- `GATE_DELTA_FILE`：一个文件的绝对路径，文件内容是 Δ 的仓库相对路径，每行一个；全量且没有锚点时为空串；
- `GATE_ANCHOR_COMMIT`：锚点 commit；没有锚点时为空串。

baseline 阶段不注入这三个变量。同树沿用时，检查不运行。

#### Scenario: final-checks-receive-delta-and-anchor
- **GIVEN** 依赖图已记录的仓库，配置了一项检查，它的 `final` 命令把上述三个环境变量和 Δ 文件内容写到仓库外的文件里
- **AND** 随后只改了 `src/a.py`
- **WHEN** 运行 final
- **THEN** 写出的记录里：`GATE_FINAL_MODE` 为 `incremental`，Δ 文件恰好含 `src/a.py`，`GATE_ANCHOR_COMMIT` 等于 final 输出里的锚点 commit

### Requirement: 仓库可用 gate.impacted 代替内建选测
`slices.json` 的 `gate.impacted`（可选）是一条测试命令。它存在时，增量 final SHALL 不用内建选测，改为：

1. 运行这条命令，同样经 `run_test_gate` 注入 junit 与防护插件；
2. 注入 `GATE_FINAL_MODE=incremental`、`GATE_DELTA_FILE`、`GATE_ANCHOR_COMMIT`；
3. 失败用例按基线的 `test.failed` 差分判红。

这时锚点取本 change 最近一次绿的 final 记录，若它不是 HEAD 的祖先就取基线 commit，不要求依赖图。命中「自动全量」的全局文件条件，或带 `--full` 时，仍跑全量 `gate.test`。`incremental` 段的 `source` 为 `impacted`。

`gate.impacted` 存在但不是非空字符串时，`lint` SHALL 判红。

#### Scenario: impacted-command-replaces-builtin-selection
- **GIVEN** 配置了 `gate.impacted`，它把 `GATE_DELTA_FILE` 的内容写到仓库外的文件，然后用 pytest 跑 `tests/test_a.py`
- **AND** baseline 绿后只改了 `src/a.py`
- **WHEN** 运行 final
- **THEN** final 绿，`incremental.source` 为 `impacted`；写出的 Δ 内容含 `src/a.py`

#### Scenario: lint-rejects-bad-impacted
- **GIVEN** `slices.json` 的 `gate.impacted` 是空串
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** lint 失败，stderr 点名 `gate.impacted`

### Requirement: 增量 final 与测试分层叠加
配置了合法的 `test-tiers.json` 时，增量 final SHALL 这样运行：

- **单元层**：选中的测试文件里落在 `unit.paths` 的，重跑时同时挂单元层探针，对这些用例判 G10 / G11（与全量时同一口径）；
- **集成区域**：已选区域只有在选中的测试文件落在该区域 `paths` 里时才运行（与全量时相同：运行区域 `cmd`，按基线的区域记录差分），否则不运行，并在 `incremental` 段的 `regions_skipped` 列出；
- **`tier_sec`**：只计实际运行的部分。

#### Scenario: tiers-incremental-probes-selected-unit-files
- **GIVEN** 配置了分层的仓库，baseline 绿
- **AND** 随后改了 `src/a.py`，使单元层 `tests/unit/test_a.py` 的用例开始写真实文件
- **AND** 另一个单元层文件 `tests/unit/test_z.py` 不依赖 `src/a.py`
- **WHEN** 运行 final
- **THEN** final 红，failed 里有 `G11` 点名 `tests/unit/test_a.py` 的用例；`tests/unit/test_z.py` 没有被重跑

#### Scenario: tiers-region-runs-only-when-selected
- **GIVEN** 配置了分层、已选区域 `hooks` 的仓库，baseline 绿，随后只改了单元层依赖的 `src/a.py`
- **WHEN** 运行 final
- **THEN** 区域 `hooks` 没有运行，`incremental.regions_skipped` 含 `hooks`；final 绿

### Requirement: 文档描述增量 final
下列文档 SHALL 描述增量 final：

- `/opsx-verify` 命令与同名 skill `openspec-verify-change`：final 默认增量，以及何时自动全量、`--full`、同树沿用；
- `/opsx-apply` 命令与同名 skill `openspec-apply-change`：final 过期时重跑 final，同树会秒回；
- schema 的 tasks instruction：可选字段 `gate.impacted`；
- README：增量 final 与锚点池。

命令与同名 skill 的说法 SHALL 一致。

#### Scenario: docs-describe-incremental-final
- **GIVEN** 本 change 合入后的模板文档
- **WHEN** 检查 `opsx-verify.md`、`openspec-verify-change/SKILL.md`、`opsx-apply.md`、`openspec-apply-change/SKILL.md`、`schema.yaml`、`README.md`
- **THEN** verify 的命令与 skill 都含「增量」「--full」「同树沿用」
- **AND** apply 的命令与 skill 都含「同树」
- **AND** schema 的 tasks instruction 含 `gate.impacted`
- **AND** README 含「增量 final」与「锚点」
