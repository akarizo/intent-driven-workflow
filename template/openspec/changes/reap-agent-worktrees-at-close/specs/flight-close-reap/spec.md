## ADDED Requirements

### Requirement: 收口时回收本次飞行留下的已落地临时 worktree
`slice-gate.py reap --change-dir <DIR>` 在 change 家运行时，SHALL 枚举 `git worktree list`，跳过主 worktree、change 家自身与 bare，只处理带本 change 飞行证据的 worktree。飞行证据为以下之一：
- 切片标记 `.openspec-slice` 的 `change_dir` 目录名等于本 change 名；
- 未提交改动里有 `**/changes/<本 change>/{timeline.md,gate-report.md,evidence.log}`。

没有飞行证据的 worktree MUST NOT 被触碰，也 MUST NOT 出现在输出的任何列表里。被锁定的 MUST 原样保留，并在 `kept` 写明已锁定。HEAD 是 change 家 HEAD 祖先的，SHALL 按合回回收的同一规则回收：
- 只丢弃飞行记录、切片标记与未跟踪字节码；
- 先归还借出的子仓；
- 用不带强制参数的 `git worktree remove` 删除；
- 分支仍指向该 HEAD 时 `git branch -d`。

Feature: 飞行收口回收
Rule: 只回收带本 change 飞行证据的临时 worktree；HEAD 已在 change 分支历史里的直接回收；锁定的不碰

#### Scenario: close-reap-removes-landed-slice-worktree
- **GIVEN** change 家检出 change 分支，一间临时 worktree 的提交已合进 change 分支
- **AND** 这间 worktree 里只剩本 change 的飞行记录改动、切片标记与字节码
- **WHEN** 在 change 家运行 `slice-gate.py reap --change-dir <本 change>`
- **THEN** 这间 worktree 的目录与 git 登记都消失，它的分支被删除
- **AND** 输出的 `reaped` 列出它，`archived` 为空，退出码为 0

#### Scenario: close-reap-ignores-worktrees-without-flight-evidence
- **GIVEN** 一间 HEAD 在 change 分支历史里、却既没有切片标记也没有本 change 飞行记录改动的 worktree
- **AND** 一间切片标记指向另一个 change 的 worktree
- **WHEN** 在 change 家运行 `reap`
- **THEN** 两间 worktree 与它们的分支原样保留
- **AND** 它们不出现在 `reaped`、`archived`、`kept` 任何一个列表里

#### Scenario: close-reap-skips-locked-worktree
- **GIVEN** 一间带本 change 飞行记录改动的临时 worktree 被 `git worktree lock` 锁住
- **WHEN** 在 change 家运行 `reap`
- **THEN** 这间 worktree 原样保留
- **AND** `kept` 里有它，原因写明已锁定，退出码为 0

### Requirement: 作废的尝试先归档再回收
HEAD 不是 change 家 HEAD 祖先的带证据 worktree（作废的尝试），`reap` SHALL 先写 `refs/flight/<change>/attic/<目录名>`，再删除目录：
- 除飞行记录、切片标记、未跟踪字节码外没有未提交改动时，ref 指向原 HEAD；
- 有这类改动时，ref 指向一个以原 HEAD 为唯一父提交、树里含这些改动（含未跟踪、不含被忽略）的新提交。

归档后，已归档的改动由脚本丢弃，再按上一条的规则删除目录。该 worktree 自己的未合入分支 MUST 保留。同名 ref 已存在且指向别的提交时，名字 SHALL 加 `-<原 HEAD 前 7 位>` 后缀。含自有子仓克隆（不是从 change 家借出）的 worktree MUST 原样保留，并在 `kept` 写明含自有子仓克隆。任何回收步骤 MUST NOT 使用强制参数或 `git branch -D`。

Feature: 作废尝试归档
Rule: 先把提交与未提交改动写进 attic ref，再删除目录；未合入的分支保留

#### Scenario: close-reap-archives-superseded-attempt
- **GIVEN** 一间临时 worktree 的提交没有进 change 分支（门禁红后重派留下的旧尝试）
- **AND** 它只剩本 change 的飞行记录改动
- **WHEN** 在 change 家运行 `reap`
- **THEN** `refs/flight/<change>/attic/<目录名>` 指向这间 worktree 原来的 HEAD
- **AND** 目录与 git 登记消失，它自己的分支仍在
- **AND** `archived` 列出这条路径与 ref

#### Scenario: close-reap-archives-uncommitted-work
- **GIVEN** 一间未交回执行体的临时 worktree 带切片标记，有一处已跟踪源码文件的未提交修改和一个未跟踪的新源码文件
- **WHEN** 在 change 家运行 `reap`
- **THEN** attic ref 指向一个以原 HEAD 为唯一父提交的新提交，这个提交的树里有那处修改和那个新文件，不含切片标记
- **AND** 目录被删除后，从 attic ref `git worktree add` 出来的工作树里能读到这两处内容

#### Scenario: close-reap-keeps-worktree-with-own-submodule-clone
- **GIVEN** 一间带本 change 飞行记录改动、提交已合进 change 分支的临时 worktree，里面的子仓是它自己初始化的克隆
- **WHEN** 在 change 家运行 `reap`
- **THEN** 这间 worktree 原样保留，子仓内容不动
- **AND** `kept` 里有它，原因写明含自有子仓克隆，退出码为 0

### Requirement: 回收结果可度量
`reap` MUST 恒以 0 退出，stdout SHALL 是 JSON `{ok, reaped, archived, kept, freed_kb, warnings}`：
- `reaped`：被删除目录的路径；
- `archived`：`{path, ref}`；
- `kept`：`{path, why}`；
- `freed_kb`：被删除目录删除前的磁盘占用之和，整数。

每次运行 SHALL 在本 change 的 `timeline.md` 追加一条 `reap` 事件，备注为「回收 N 个 · 释放 X MB · 归档 M 个 · 保留 K 个」，N 为 0 时也写。不在 git 仓库或 change 目录不存在时，SHALL 输出空列表与一条 warning 并以 0 退出。

Feature: 回收留痕
Rule: `reap` 恒以 0 退出，打印完整 JSON，并在 timeline 追加一条 `reap` 事件

#### Scenario: close-reap-reports-and-records-timeline
- **GIVEN** 本次飞行留下一间已落地的临时 worktree 和一间作废的尝试
- **WHEN** 在 change 家运行 `reap`
- **THEN** stdout 是含 `reaped`、`archived`、`kept`、`freed_kb` 的 JSON，`reaped` 两条、`archived` 一条，`freed_kb` 大于 0
- **AND** 本 change 的 `timeline.md` 末尾追加一条 `reap` 事件，备注含「回收 2 个」与「归档 1 个」

### Requirement: 收口步骤运行回收
`/opsx-apply` 命令文档与 `openspec-apply-change` skill 的收口步骤 SHALL 在 `flight-doctor.py cost` 之后、写入 `review-findings.json` 之前运行 `slice-gate.py reap --change-dir openspec/changes/<name>`，原样打印回收一行；报 `invalid choice`（hooks 未升级）时 SHALL 跳过并照常往下。两份文档 MUST 同改。

Feature: 收口调用
Rule: 命令与 skill 的收口步骤都运行 `reap`，子命令不存在时跳过

#### Scenario: apply-close-runs-reap
- **GIVEN** `template/.claude/commands/opsx-apply.md` 与 `template/.claude/skills/openspec-apply-change/SKILL.md`
- **WHEN** 读它们的收口步骤
- **THEN** 两者都在 `flight-doctor.py cost` 之后、写入 `review-findings.json` 之前运行 `slice-gate.py reap --change-dir`
- **AND** 都写明打印回收一行，以及报 `invalid choice` 时跳过

### Requirement: 铁律 6 写明收口回收
根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet` 的铁律 6 SHALL 写明飞行收口由 `slice-gate.py reap` 回收本次飞行的临时 worktree、作废尝试先归档；原有的 `slice-gate.py merge` 回收、`/clean-after-merged` 授权、不删 worktree、不带强制参数、`branch -D` 交人等措辞 MUST 保留；snippet MUST NOT 超过 8KB。

Feature: 铁律措辞
Rule: 两处铁律 6 都写明收口回收与作废尝试先归档，原有措辞保留

#### Scenario: iron-rule-names-close-reap
- **GIVEN** 根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`
- **WHEN** 读两者的铁律 6
- **THEN** 两行都写明 `slice-gate.py reap` 在收口回收临时 worktree，并写明作废尝试先归档
- **AND** 两行仍写明 `slice-gate.py merge` 回收与 `/clean-after-merged`，根 `CLAUDE.md` 仍写明不删 worktree、不带强制参数与 `branch -D` 交人
- **AND** snippet 不超过 8KB
