## ADDED Requirements

### Requirement: 基线记录内容指纹
`slice-gate.py baseline` 结束时 SHALL 在 `gate-baseline.json` 写入：
- `change`：本 change 名；`mode`：`full` 或 `incremental`；
- `snapshot`：基线结束时工作区相对 HEAD 的未提交改动，路径映射到 git blob id，删除为 null。规则：
  - 不含字节码与 `.pytest_cache`；
  - 不含本 change 的计划工件，即 proposal.md、design.md、tasks.md、slices.json、spec.html、gate-baseline.json、.openspec.yaml、记账文件、`specs/` 与 `slices/`；
  - 符号链接记链接文本的 blob id，与 git 树里的表示一致，不跟随链接；
- `cmd_key`：全量命令指纹。取 `gate.test` 文本，把本 change 目录相对路径换成占位符 `<change>`，再加上命令里每个指向仓库内已存在文件的词所对应的文件内容。只算命令里直接写出的仓库内文件，不追踪它 source / import 的文件；
- `byproducts`：运行副产物路径（见下）；
- 每片 verify 的 `exit` 与 `cmd`。

基线运行期间的改动，开始与结束各取一次快照对比；`<changes 根>` 下其他 change 目录里的路径不比：
- 运行开始时就存在的文件（已跟踪或未跟踪）或测试文件内容有变 → 基线 SHALL 判红，原因含「重跑 baseline」；
- 例外：本 change 上一次基线 `byproducts` 里的非测试路径被改写 → SHALL 只记警告，仍算副产物；
- 运行期间新出现的非测试文件 SHALL 只记一条警告，并记入 `snapshot` 与 `byproducts`；
- 上一次基线 `byproducts` 里仍未提交的路径 SHALL 继续留在 `byproducts`。

#### Scenario: baseline-records-snapshot
- **GIVEN** change `c` 的计划已提交；工作区里未跟踪的 `tests/test_new.py` 含一个 strict-xfail 用例；`gate.test` 是本 change 目录下的全量脚本
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`gate-baseline.json` 的 `mode` 为 `full`，`change` 为 `c`
- **AND** `snapshot` 含 `tests/test_new.py`，值等于该文件的 `git hash-object`；不含 `slices.json`
- **AND** `cmd_key` 为非空字符串，`verify.S1.cmd` 等于 S1 的 verify 命令

#### Scenario: baseline-red-when-tracked-file-edited-while-running
- **GIVEN** `gate.test` 运行时会改写已跟踪的 `src/mod.py`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0；`reasons` 有一项同时含 `src/mod.py` 与「重跑 baseline」

#### Scenario: baseline-tolerates-new-byproduct
- **GIVEN** `gate.test` 运行时在仓库里新建未跟踪的 `out/report.txt`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`warnings` 有一项含 `out/report.txt`
- **AND** `snapshot` 与 `byproducts` 都含 `out/report.txt`

#### Scenario: baseline-tolerates-rewritten-byproduct
- **GIVEN** `gate.test` 每次运行都把当前时间写进未跟踪的 `out/report.txt`；change `c` 已有一次全量绿基线
- **WHEN** 运行 `slice-gate.py baseline --full`
- **THEN** 退出 0；`warnings` 有一项含 `out/report.txt`；`byproducts` 含 `out/report.txt`

#### Scenario: baseline-ignores-other-change-edits-while-running
- **GIVEN** 已提交的 `openspec/changes/other/proposal.md`；`gate.test` 运行时往它末尾追加一行
- **WHEN** 对 change `c` 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`mode` 为 `full`
- **AND** `reasons` 与 `warnings` 都不含 `openspec/changes/other/proposal.md`

#### Scenario: baseline-records-symlink-as-git-does
- **GIVEN** 仓库根有未跟踪的符号链接 `data`，指向不存在的 `../outside-target`
- **WHEN** 运行 `slice-gate.py baseline`，再把工作区全部提交，运行 `slice-gate.py preflight`
- **THEN** baseline 退出 0；`snapshot.data` 等于对链接文本 `../outside-target` 做 `git hash-object --stdin` 的结果
- **AND** preflight 退出 0

### Requirement: 只改测试文件时复用全量
有可复用的全量结果时，`slice-gate.py baseline` SHALL 不跑 `gate.test`，改走增量。

差异 Δ 的定义：
- 按内容比较 → 候选所测的代码树（候选 commit 加上候选的 `snapshot`）与当前代码树（HEAD 加上工作区）；
- 不计 → 字节码、`.pytest_cache`、`<changes 根>/**`，以及候选 `byproducts` 中在候选 commit 与当前 HEAD 都未跟踪的路径；
- 例外 → 候选来自本 change 时，本 change 目录里计划工件以外的文件照计。

复用条件（全部满足）：
- 候选基线 ok，且测试结果可度量：exit 0，或记有 `test.failed`；
- 候选来自别的 change 时，`test.exit` 为 0（没有预存红）；
- `cmd_key` 与当前相同；
- 候选 commit 是当前 HEAD 的祖先；
- 没有给 `--full`；
- Δ 里的路径全是文件名匹配 `test_*.py` 的文件；
- 候选 `test.failed` 里没有哪条的 classname 以点分段后含 Δ 中某个测试文件的文件名主干；
- Δ 里现存的测试文件用 `gate.pytest` 前缀补跑一次，结果同时满足：没有 FAILED / ERROR、没有超时、退出码为 0 或 5。

补跑规则：
- 路径与内容都相同的一组 Δ 文件，在一次 baseline 里 SHALL 至多补跑一次；
- 补跑红、超时或退出码不是 0 / 5 时，SHALL 不再尝试其余候选，直接跑全量。

复用时：
- `test` 沿用候选的 `exit`、`sec`、`failed`；
- 记 `mode: incremental` 与 `incremental: {from: {change, commit, at}, files, sec}`；
- 不改已有的 `gate.full_suite_sec`；本 change 还没有时，写入候选的 `test.sec`。

任一条件不满足 → 跑全量，`mode: full`。有候选但都没复用时，SHALL 在 `reuse_skipped` 记下判过的候选（change、commit、不复用的理由），至多 5 条。

#### Scenario: incremental-when-only-test-file-changed
- **GIVEN** change `c` 已有一次全量绿基线：预存红 1 条，在 `tests/test_old.py`；之后只往 `tests/test_cap.py` 末尾追加一个 strict-xfail 用例；`gate.lint` 运行时会写一个标记文件
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；`gate.test` 没有运行（全量标记文件不存在）；lint 标记文件存在
- **AND** `mode` 为 `incremental`，`incremental.files` 等于 `["tests/test_cap.py"]`，`incremental.from.change` 为 `c`
- **AND** `test.failed` 与第一次相同；`slices.json` 的 `gate.full_suite_sec` 与第一次相同

#### Scenario: incremental-noop-when-only-plan-changed
- **GIVEN** change `c` 已有一次全量绿基线；之后只改了本 change 的 proposal.md、`specs/` 下的 spec.md 与 `slices/S1.md`
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；`gate.test` 没有运行；`mode` 为 `incremental`，`incremental.files` 为空列表

#### Scenario: full-when-non-test-file-changed
- **GIVEN** change `c` 已有一次全量绿基线；之后改了 `src/mod.py`
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`mode` 为 `full`
- **AND** `reuse_skipped` 有一项的 change 为 `c`、理由含 `src/mod.py`

#### Scenario: full-when-changed-test-file-fails
- **GIVEN** change `c` 已有一次全量绿基线；之后往 `tests/test_cap.py` 追加一个会失败的用例（不带 xfail）
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`mode` 为 `full`；`test.failed` 含新用例

#### Scenario: full-when-test-file-had-preexisting-red
- **GIVEN** change `c` 已有一次全量绿基线：预存红 1 条，在 `tests/test_old.py`；之后往 `tests/test_old.py` 追加一个通过的用例
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`mode` 为 `full`

#### Scenario: full-flag-forces-full
- **GIVEN** change `c` 已有一次全量绿基线，之后没有任何改动
- **WHEN** 运行 `slice-gate.py baseline --full`
- **THEN** 退出 0；`gate.test` 运行了；`mode` 为 `full`

#### Scenario: full-when-gate-script-changed
- **GIVEN** change `c` 已有一次全量绿基线；之后改了 `gate.test` 引用的本 change 目录下全量脚本的内容（命令文本不变）
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`mode` 为 `full`

### Requirement: 跨 change 复用全量
每次全量基线同时满足以下条件时，`slice-gate.py baseline` SHALL 把这次结果写进基线池：
- 基线绿；
- `test.exit` 为 0；
- `cmd_key` 非空。

基线池的规则：
- 位置：git common dir 下的 `flight-baseline-pool/`，同一仓库的各 worktree 共享；
- 每条记录含 change、commit、at、ok、`cmd_key`、`snapshot`、`byproducts`、`test`；
- 写入：先写临时文件再改名；
- 保留：按 at 保留最新 30 条，清理时顺带删除一小时以前留下的 `.tmp-*` 临时文件；
- 容错：写池失败 SHALL 只记警告，不影响本次基线；读池时坏 JSON 跳过。

选候选的顺序：
1. 本 change 现有的 `gate-baseline.json`；
2. 池里 `cmd_key` 相同的条目，按 at 由新到旧，最多看 10 条。

逐个按上一条 Requirement 的复用条件判断，取第一个满足的。

#### Scenario: cross-change-reuse-same-tree
- **GIVEN** change `c` 跑过一次全量绿基线，没有预存红；同一仓库里另有 change `d`，它的全量脚本与 `c` 的内容相同、命令只差 change 目录名，`d` 还没有基线；`c` 的工件与门禁脚本都没有提交
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`gate.test` 没有运行；`d` 的 `mode` 为 `incremental`，`incremental.from.change` 为 `c`
- **AND** `d` 的 `test.exit` 为 0；`d` 的 `slices.json` 里 `gate.full_suite_sec` 等于 `c` 基线的 `test.sec`

#### Scenario: cross-change-reuse-after-test-only-commit
- **GIVEN** change `c` 跑过一次全量绿基线，没有预存红；之后提交了一个只新增 `tests/test_more.py`（用例通过）的 commit；change `d` 的全量脚本与 `c` 的内容相同
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** `gate.test` 没有运行；`mode` 为 `incremental`，`incremental.files` 等于 `["tests/test_more.py"]`

#### Scenario: cross-change-ignores-sourced-files
- **GIVEN** change `c` 跑过一次全量绿基线，没有预存红；`d` 的全量脚本与 `c` 的内容相同，但两者各自 source 的 `verify/_env.sh` 内容不同
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** `gate.test` 没有运行；`mode` 为 `incremental`，`incremental.from.change` 为 `c`

#### Scenario: cross-change-refused-when-script-differs
- **GIVEN** change `c` 跑过一次全量绿基线，没有预存红；change `d` 的全量脚本比 `c` 的多一行注释
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`mode` 为 `full`

#### Scenario: cross-change-refused-when-candidate-has-preexisting-red
- **GIVEN** change `c` 跑过一次全量绿基线，预存红 1 条；change `d` 的全量脚本与 `c` 的内容相同，代码树与 `c` 所测的相同
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`d` 的 `mode` 为 `full`

#### Scenario: failed-rerun-not-repeated-across-candidates
- **GIVEN** change `c` 与 `d` 的全量脚本内容相同，各跑过一次全量绿基线（`d` 用 `--full`），池里至少有它们两条；之后往 `tests/test_cap.py` 追加一个会失败的用例，它每运行一次就往仓外计数文件追加一个字符
- **WHEN** 对 `d` 运行 `slice-gate.py baseline`
- **THEN** `gate.test` 运行了；`mode` 为 `full`
- **AND** 计数文件恰好 2 个字符（补跑 1 次、全量 1 次）

#### Scenario: pool-pruned-and-tolerant
- **GIVEN** 基线池里预置 31 条 `cmd_key` 不同的旧条目、1 个内容不是 JSON 的 `bad.json`，以及一个修改时间在两小时前的 `.tmp-stale.json`；change `c` 没有预存红
- **WHEN** 对 `c` 运行 `slice-gate.py baseline`
- **THEN** 退出 0；池里不以 `.tmp-` 开头的 `.json` 文件恰好 30 个，其中有一条的 change 为 `c`
- **AND** `.tmp-stale.json` 已不存在

#### Scenario: pool-write-failure-only-warns
- **GIVEN** git common dir 下的 `flight-baseline-pool` 是一个普通文件；change `c` 没有预存红
- **WHEN** 对 `c` 运行 `slice-gate.py baseline`
- **THEN** 退出 0；`warnings` 有一项含「基线池写入失败」

### Requirement: verify 按需重跑
增量基线 SHALL 只重跑下面这些片的 verify：
- 上一次没有记录（包括候选来自别的 change）、或记录的 `cmd` 与当前不同的片；
- 命令里有路径覆盖到 Δ 中某个文件的片；
- 命令里一个路径都认不出的片。

其余片沿用本 change 上一次基线的 `exit`，并标 `reused: true`。

路径的认法：命令按 shell 规则切词，每个词去掉 `::` 之后的部分；它指向已存在的路径、或等于 Δ 里的路径时算路径。Δ 文件等于它、或位于它这个目录下，即为覆盖。

全量基线照旧处理全部 verify。

#### Scenario: verify-rerun-only-covering-slices
- **GIVEN** change `c` 有三片：S1 的 verify 只跑 `tests/test_a.py`；S2 的 verify 只跑 `tests/test_b.py`；S3 的 verify 命令里没有路径。三片的 verify 运行时各写一个自己的标记文件。已有一次全量绿基线，之后只往 `tests/test_a.py` 追加一个 strict-xfail 用例，并清掉三个标记文件
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `mode` 为 `incremental`；S1、S3 的标记文件存在，S2 的不存在
- **AND** `verify.S2.reused` 为 true，`verify.S2.exit` 为 0

#### Scenario: verify-rerun-when-command-changed
- **GIVEN** 同上的三片与一次全量绿基线；之后只把 S2 的 verify 命令改成多带一个 `-q` 参数，并清掉三个标记文件
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `mode` 为 `incremental`；S2 的标记文件存在；`verify.S2` 没有 `reused`

### Requirement: preflight 按内容判过期
以下两条都满足时，`slice-gate.py preflight` SHALL 在原有四项校验之外按内容判过期：
- 基线带 `snapshot`；
- 本 change 的 `timeline.md` 里没有 `approve` 事件；`timeline.md` 读不出时按没有处理。

判法：以本 change 现有基线为候选，按上一条 Requirement 的 Δ 定义求 Δ。Δ 非空 → 退出非 0，stderr 含「基线过期」，并列出至多 8 个 Δ 路径。

旧格式基线（没有 `snapshot`）与已经有 `approve` 事件的 change，SHALL 保持原有四项校验。

#### Scenario: preflight-stale-when-test-file-changed-after-baseline
- **GIVEN** change `c` 有一次全量绿基线，之后往 `tests/test_cap.py` 追加了一个用例；gate 与 verify 命令都没变
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0；stderr 含「基线过期」与 `tests/test_cap.py`

#### Scenario: preflight-passes-after-artifact-commit
- **GIVEN** change `c` 在未跟踪的 `tests/test_new.py` 存在时跑过一次全量绿基线；之后把工作区全部提交，内容不变
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出 0

#### Scenario: preflight-skips-content-check-after-approve
- **GIVEN** change `c` 有一次全量绿基线；`timeline.md` 里已有一条 `approve` 事件并已提交；之后改了 `src/mod.py` 并提交
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出 0

#### Scenario: preflight-old-baseline-compatible
- **GIVEN** change `c` 的 `gate-baseline.json` 是旧格式（有 commit、ok、plan_sha，没有 snapshot），plan_sha 与当前计划一致；之后改了 `tests/test_cap.py`
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出 0

#### Scenario: preflight-ignores-removed-byproduct
- **GIVEN** change `c` 有一次全量绿基线，期间 `gate.test` 新建了未跟踪的 `out/report.txt`；之后人删掉了 `out/report.txt`
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出 0

### Requirement: 记录与文档写明增量基线
`slice-gate.py baseline` 写进 `timeline.md` 的 baseline 行：`mode` 为 `incremental` 时，SHALL 含「增量」与复用来源 change。

`opsx-propose.md` 与 `openspec-propose/SKILL.md` 的基线步骤 SHALL 写明以下内容，各占至少一行：
- 改完计划后重跑 `baseline`，全量还是增量由脚本判定；
- 增量条件：只有 `test_*.py` 变了，且这些文件不含上次全量的预存红；
- 跨 change 只复用全绿的全量；
- verify 从全量结果推导；
- lint / typecheck 在代码树没变时沿用；
- `--full` 强制全量；
- 增量时的一行报告形如「基线绿（增量：复用 …」。

README SHALL 有一行同时提到「基线」与「增量」。

#### Scenario: timeline-marks-incremental-baseline
- **GIVEN** change `alpha` 已有一次全量绿基线；之后只往 `tests/test_cap.py` 追加一个 strict-xfail 用例
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `timeline.md` 的最后一行 baseline 记录同时含「增量」与 `alpha`

#### Scenario: propose-docs-describe-incremental
- **GIVEN** `template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md` 与 `README.md`
- **WHEN** 取两份命令文档的基线步骤段（从 `slice-gate.py baseline` 到下一个步骤标题），并读取 README 全文
- **THEN** 两段都含 `--full` 与「增量：复用」
- **AND** 两段各有一行同时含「改完计划」与 `baseline`；各有一行同时含 `test_*.py` 与「预存红」；各有一行同时含「跨 change」与「全绿」；各有一行同时含「推导」与 `verify`；各有一行同时含「沿用」与 `lint`
- **AND** README 有一行同时含「基线」与「增量」
