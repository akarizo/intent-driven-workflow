## ADDED Requirements

### Requirement: 计划里的检查配置与仓库默认检查由 lint 校验
`slices.json` 的 `gate` MAY 带 `checks`（数组）与 `checks_skip`（对象）。`slice-gate.py lint`（preflight 内的同一份计划校验也一样）SHALL 在下面任一条不满足时退出非 0，stderr 每条违规以 `checks:` 开头并点名对象：

- `gate.checks` 是数组，每项是对象，只含 `name`、`baseline`、`final`、`timeout_sec` 这几个字段；
- `name` 匹配 `^[a-z0-9-]+$`，在本 change 内不重复；
- `final` 是非空字符串；
- `baseline` 缺省、为 null，或是非空字符串；
- `timeout_sec` 缺省，或是大于 0 的数（布尔值不算数）；
- `gate.checks_skip` 是对象，每个值去掉首尾空白后非空，键不同时是 `gate.checks` 里的 `name`。

仓库默认检查文件是 openspec 根目录下的 `gate-checks.json`，openspec 根目录 = change 目录的上两级（`<change_dir>/../..`）。文件存在时：

- 它 SHALL 是 JSON 数组，每项是带合法且不重复 `name` 的对象；否则 lint 红，点名该文件；
- 其中每个 `name` SHALL 出现在本 change 的 `gate.checks` 里（同名即可，命令可以不同），或是 `gate.checks_skip` 的键；否则 lint 红，点名该检查。

文件不存在时，这条规则不触发。

#### Scenario: lint-rejects-malformed-checks
- **GIVEN** `gate.checks` 有这几项：`name` 为 `Bad` 的、`no-final` 缺 `final` 的、两个 `name` 都是 `dup` 的、`zero-timeout` 的 `timeout_sec` 为 0 的、`typo` 带未知字段 `base_line` 的；`gate.checks_skip` 里 `empty-reason` 的理由是空白，`ok-check` 同时出现在 `gate.checks` 与 `checks_skip`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 里以 `checks:` 开头的行分别点名 `Bad`、`no-final`、`dup`、`zero-timeout`、`typo`、`empty-reason`、`ok-check`

#### Scenario: lint-accepts-valid-checks
- **GIVEN** `gate.checks` 有两项：`parity` 带 `baseline`、`final` 与 `timeout_sec: 60`；`linkage` 的 `baseline` 为 null、只有 `final`；`gate.checks_skip` 为 `{"other": "本 change 不碰共用包"}`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0，stdout 打印 waves

#### Scenario: lint-requires-repo-default-check
- **GIVEN** `openspec/gate-checks.json` 列出 `coverage-parity`；`openspec/changes/c` 的 `gate.checks` 与 `gate.checks_skip` 都没有它
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0；stderr 有一行以 `checks:` 开头并点名 `coverage-parity`

#### Scenario: lint-accepts-default-check-skipped-with-reason
- **GIVEN** `openspec/gate-checks.json` 列出 `coverage-parity`；本 change 的 `gate.checks_skip` 为 `{"coverage-parity": "只改文档，见 design D3"}`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0

#### Scenario: lint-repo-defaults-follow-change-dir
- **GIVEN** change 目录在 `template/openspec/changes/c`；`template/openspec/gate-checks.json` 列出 `coverage-parity`；`template/` 的上一级没有 `openspec/`；本 change 没写这个检查
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0；stderr 有一行以 `checks:` 开头并点名 `coverage-parity`

#### Scenario: lint-rejects-unreadable-repo-defaults
- **GIVEN** `openspec/gate-checks.json` 的内容不是合法 JSON；本 change 的计划其余部分合法
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0；stderr 有一行以 `checks:` 开头并含 `gate-checks.json`

### Requirement: 检查命令的运行契约
baseline 与 final 运行检查命令时，SHALL 满足：

- 工作目录是 git toplevel，命令经 shell 执行；
- 注入环境变量：
  - `GATE_PHASE` = `baseline` 或 `final`；
  - `GATE_CHANGE` = change 目录名；
  - `GATE_BASE_COMMIT` = `gate-baseline.json` 的 `commit`（baseline 时就是本次基线记下的 HEAD）；
  - `GATE_CHECK_DIR` = `<git common dir 的绝对路径>/flight-gate-checks/<change>/<name>/`，运行前已存在；
- 判定只看退出码：0 为绿，其余为红；slice-gate 不解析输出；
- 完整输出（stdout 与 stderr）覆盖写入 `$GATE_CHECK_DIR/.gate-<phase>.log`；红的提示带日志路径与输出末尾 20 行；
- 配置了 `timeout_sec` 时，到时结束检查进程所在的整个进程组并判红，提示写明「超时 N 秒」；没配置时不设超时。

#### Scenario: check-env-and-dir-shared-across-phases
- **GIVEN** 在仓库的另一个 worktree 里有 change `c`，检查 `parity` 的 baseline 命令把收到的环境变量与工作目录写进 `$GATE_CHECK_DIR`，并写一个 `seed.txt`；final 命令同样记录环境变量，`seed.txt` 不存在就退出 4
- **WHEN** 在该 worktree 里依次运行 `slice-gate.py baseline` 与 `slice-gate.py final`
- **THEN** 两次都退出 0
- **AND** 两次拿到的 `GATE_CHECK_DIR` 相同，都是主仓库 `.git/flight-gate-checks/c/parity`
- **AND** 两次的 `GATE_CHANGE` 都是 `c`，`GATE_BASE_COMMIT` 都等于基线的 `commit`，工作目录都是该 worktree 的根
- **AND** `GATE_PHASE` 依次为 `baseline`、`final`

#### Scenario: check-timeout-is-red
- **GIVEN** 检查 `slow` 的 baseline 命令是 `sleep 30; echo done`，`timeout_sec` 为 1
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0，整体用时不到 20 秒
- **AND** `reasons` 有一条点名 `slow` 并含「超时」

### Requirement: baseline 运行并记录检查
`slice-gate.py baseline` SHALL 在全量 `gate.test`、lint / typecheck、每片 verify 之后，在运行期间改动判定之前，按 `gate.checks` 的顺序运行每个 `baseline` 非空的检查：

- 实跑前先清空该检查的 `GATE_CHECK_DIR` 再重建；
- 结果记入 `gate-baseline.json` 的 `checks.<name>` = `{exit, sec, cmd, key}`，`key` 按 `cmd_key` 对该命令计算；
- 退出非 0 或超时 → `reasons` 加一条以 `check <name>` 开头、写明退出码或超时的理由，基线判红；
- `baseline` 为 null 的检查在这里不运行、不记录；
- `gate.checks` 非空时 `gate-baseline.json` 有 `checks` 对象。

下面全部满足时，SHALL 不运行该检查、不清空它的目录，沿用本 change 上一次基线的记录，写 `{exit, sec, cmd, key, reused: true}`：

- 本次走增量，且候选是本 change 现有的基线；
- 严格差异为空（口径与 lint / typecheck 的沿用相同）；
- 上一次记录的 `cmd` 与 `key` 都与当前相同；
- 该检查的 `GATE_CHECK_DIR` 仍存在。

其余情况一律实跑：跨 change 的池候选、`--full`、命令或指纹变了、目录不在了。基线池条目不含检查结果。

#### Scenario: baseline-red-when-check-fails
- **GIVEN** 检查 `parity` 的 baseline 命令退出 3；全量、lint 与 verify 都绿
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0；`ok` 为 false
- **AND** `reasons` 有一条以 `check parity` 开头并含 `exit 3`；`checks.parity.exit` 为 3

#### Scenario: baseline-clears-check-dir-before-run
- **GIVEN** 检查 `parity` 的共用目录里有上一次留下的 `stale.txt`；本次 baseline 要实跑这个检查
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`stale.txt` 不存在，本次检查写下的文件存在

#### Scenario: baseline-check-reused-when-tree-unchanged
- **GIVEN** change `c` 已有一次全量绿基线，检查 `parity` 实跑过一次；之后只改了本 change 的 proposal.md
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；检查没有再运行
- **AND** `checks.parity.reused` 为 true，`checks.parity.exit` 为 0

#### Scenario: baseline-check-rerun-when-command-changed
- **GIVEN** change `c` 已有一次全量绿基线，检查 `parity` 实跑过一次；之后把它的 baseline 命令末尾多加一个参数
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；检查又运行了一次；`checks.parity` 没有 `reused`

#### Scenario: baseline-check-rerun-when-dir-missing
- **GIVEN** change `c` 已有一次全量绿基线，检查 `parity` 实跑过一次；之后删掉了它的共用目录，并改了本 change 的 proposal.md
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；检查又运行了一次；`checks.parity` 没有 `reused`

#### Scenario: baseline-check-rerun-on-cross-change-reuse
- **GIVEN** change `c` 跑过一次全绿的全量基线并进了基线池；change `d` 的全量脚本与 `c` 相同，配了检查 `parity`
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`d` 的 `mode` 为 `incremental`、复用来源是 `c`
- **AND** `d` 的检查运行了一次；`checks.parity` 没有 `reused`

### Requirement: preflight 按计划对账检查
`plan_sha` SHALL 在 `gate.checks` 非空时，把每个检查的 `[name, baseline]` 按顺序追加进参与哈希的内容；`gate.checks` 缺省或为空时，`plan_sha` 的结果与现状相同。preflight 不为检查新增校验：检查在基线上红时基线 `ok` 为 false，preflight 报「基线红」；计划新增、删除检查或改了 `baseline` 命令时 `plan_sha` 变化，preflight 报「基线过期」。只改检查的 `final` 或 `timeout_sec` 不让基线过期。

#### Scenario: preflight-stale-when-check-added
- **GIVEN** change `c` 已有一次绿基线，当时计划里没有检查；之后在计划里加了检查 `parity`（baseline 与 final 都是 `true`）并提交
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0；stderr 含「基线过期」

#### Scenario: preflight-ignores-check-final-edit
- **GIVEN** change `c` 的计划有检查 `parity`（baseline 与 final 都是 `true`），已有一次绿基线；之后只把它的 final 改成 `true x` 并提交
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出 0

### Requirement: final 运行检查并以 G9 判定
`slice-gate.py final` 在 G7 绿时，SHALL 在全量 `gate.test` 判定之后（全量红也照跑）按顺序处理每个检查：

- 先核对基线：`gate-baseline.json` 要有 `commit`；`baseline` 非空的检查还要有同名记录、`exit` 为 0、`cmd` 等于当前 `baseline` 命令。不满足 → `failed` 加一条以 `G9 check <name>` 开头、含「基线」的项，提示重跑 baseline，不运行该检查的 final；
- 核对通过 → 运行 `final` 命令；退出非 0 → `failed` 加 `G9 check <name>：exit N；日志 <路径>` 加输出末尾 20 行；超时 → 同样以 `G9 check <name>` 开头并写明超时；
- final 不清空共用目录，目录不存在时创建。

G7 红时 SHALL 不运行任何检查，`warnings` 加一条「G9 检查未跑：G7 已红，scenario 全绿后重跑 final」；原有的「G2 全量未跑」提示照旧。

#### Scenario: final-red-when-check-fails
- **GIVEN** 检查 `parity` 的 baseline 绿；final 命令依次打印 `line-01` 到 `line-30` 后退出 1；基线已绿
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `ok` 为 false；`failed` 有一项以 `G9 check parity` 开头，含 `exit 1` 与 `line-30`，不含 `line-10`，并含 `.gate-final.log` 的路径
- **AND** 该日志文件含 `line-01`

#### Scenario: final-skips-checks-when-g7-red
- **GIVEN** scenario 测试仍带 strict xfail；检查 `parity` 的 final 命令运行时会写一个标记文件
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `failed` 有 G7 项；标记文件不存在
- **AND** `warnings` 含「G9 检查未跑」，也仍含「G2 全量未跑」

#### Scenario: final-runs-checks-when-full-suite-red
- **GIVEN** 基线已绿，检查 `parity` 的 final 命令运行时会记一笔；之后新增了一个失败的测试并提交；scenario 全绿
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `ok` 为 false，`failed` 有 G2 test 项
- **AND** 检查的 final 运行了一次

#### Scenario: final-red-when-baseline-record-missing
- **GIVEN** change `c` 的基线是在计划里还没有检查时跑的；之后加了两个检查：`a` 的 baseline 为 `true`、final 运行时写标记 A；`b` 的 baseline 为 null、final 运行时写标记 B
- **WHEN** 运行 `slice-gate.py final`
- **THEN** `failed` 有一项以 `G9 check a` 开头并含「基线」；标记 A 不存在
- **AND** 标记 B 存在；`failed` 里没有 `G9 check b`

### Requirement: 未配置检查时行为不变
计划没有 `gate.checks`、openspec 根目录下也没有 `gate-checks.json` 时，baseline / final / preflight / lint SHALL 与本 change 之前一致：`gate-baseline.json` 不出现 `checks` 键；`plan_sha` 等于对 `[gate.test, gate.lint, gate.typecheck, [[id, verify], …]]` 的原算法结果；final 的输出不出现 G9；git common dir 下不创建 `flight-gate-checks`。

#### Scenario: no-checks-behavior-unchanged
- **GIVEN** change `c` 的计划没有 `gate.checks`，仓库没有 `gate-checks.json`
- **WHEN** 依次运行 `slice-gate.py baseline` 与 `slice-gate.py final`
- **THEN** 两次都退出 0；`gate-baseline.json` 没有 `checks` 键，`plan_sha` 等于原算法结果
- **AND** final 的 JSON 只有原有字段，`failed` 与 `warnings` 都不含 `G9`；git common dir 下没有 `flight-gate-checks`

### Requirement: 文档写明检查的配置、时机与契约
SHALL 写明：

- schema 的 tasks instruction：`gate.checks`、`gate.checks_skip`，以及仓库默认检查文件 `gate-checks.json` 要抄进 `gate.checks` 或在 `checks_skip` 写理由；
- `opsx-propose` 命令与同名 skill 的基线步骤：baseline 会运行检查的 `baseline`，红即基线红；
- `opsx-verify` 命令与同名 skill：final 会运行检查的 `final`，红记 G9；
- README：检查的运行契约（四个 `GATE_*` 环境变量、只看退出码）。

#### Scenario: docs-describe-paired-checks
- **GIVEN** schema.yaml、`opsx-propose` 与 `opsx-verify` 两个命令及其同名 skill、README.md
- **WHEN** 读取它们的正文
- **THEN** schema 的 tasks instruction 同时含 `gate.checks`、`checks_skip` 与 `gate-checks.json`
- **AND** 两份 propose 文档的基线步骤各有一行同时含 `gate.checks` 与「基线红」；两份 verify 文档各有一行同时含 `gate.checks` 与 `G9`
- **AND** README 含 `GATE_PHASE`、`GATE_CHANGE`、`GATE_BASE_COMMIT`、`GATE_CHECK_DIR`，且有一行同时含 `gate.checks` 与「退出码」
