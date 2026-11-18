## ADDED Requirements

### Requirement: 合回后回收切片临时 worktree
`slice-gate.py merge` 每成功合回一片 `<S>=<sha>` 后，SHALL 回收这样的 worktree：不是当前 worktree，且 HEAD 落在这次合并带进来的提交里（`git rev-list <sha> --not <合并前的 HEAD>`）。回收前它的未提交改动里除三类之外 MUST 为空：change 目录下的飞行记录（`timeline.md` / `gate-report.md` / `evidence.log`）、切片标记、未跟踪的字节码；这三类由脚本丢弃。回收 SHALL 用不带强制参数的 `git worktree remove`；该 worktree 有自己的分支且分支正指向那个 HEAD 时，随后用 `git branch -d` 删除它。借出的子仓 worktree SHALL 先归还（在 change 家的子仓里不带强制参数移除），前提是它的 HEAD 已是 change 家子仓 HEAD 的祖先且除字节码外没有未提交改动。输出 JSON 在有回收时 SHALL 多一个 `reaped`（被回收的路径数组）；没有回收时 MUST NOT 出现这个键。任何一间不满足条件或移除失败时 MUST 原样留下，在 `warnings` 里写「未回收 <路径>：<原因>」（有未提交改动时点名文件）；回收的成败 MUST NOT 影响 `ok`、`merged`、`failed` 与退出码。HEAD 不在上述提交集合里的 worktree MUST NOT 被触碰。
Feature: 合回的切片不再占着磁盘
Rule: 只收「提交已合回、没有别的未合回内容」的；收不掉就留着并说明

#### Scenario: merge-reaps-merged-slice-worktrees
- **GIVEN** 两间切片临时 worktree 各提交了一个文件，各有自己的临时分支
- **AND** 里面只剩门禁留下的飞行记录改动与未跟踪的字节码
- **WHEN** 在 change 家运行 `merge S1=<提交一> S2=<提交二>`
- **THEN** 退出 0，`merged` 为 `["S1", "S2"]`，`reaped` 列出这两间的路径
- **AND** 两间 worktree 的目录与登记都不在了，它们的临时分支也删除了
- **AND** change 家仍检出 change 分支，两片的文件都已合入

#### Scenario: merge-keeps-worktree-with-unmerged-work
- **GIVEN** 切片临时 worktree 提交之后，工作树里还有一个不属于飞行记录的未提交文件
- **WHEN** 在 change 家运行 `merge S1=<提交>`
- **THEN** 合回成功，输出没有 `reaped`（或为空）
- **AND** 该 worktree、其中的未提交文件、飞行记录与临时分支都原样还在
- **AND** `warnings` 有一条含「未回收」、该 worktree 的路径与那个文件的路径

#### Scenario: merge-never-touches-unrelated-worktrees
- **GIVEN** 除了本片最终那间临时 worktree，还有一间停在本片较早提交上的上一轮 worktree
- **AND** 另有一间属于别的 change 的 worktree，它的 HEAD 是 change 分支的祖先但不是本片的提交
- **WHEN** 在 change 家运行 `merge S1=<最终提交>`
- **THEN** 本片的两间 worktree 都被回收
- **AND** 别的 change 的 worktree 与它的分支原样还在，change 家也在

#### Scenario: merge-reap-returns-borrowed-submodule
- **GIVEN** 带 submodule 的仓库，隔离执行体在临时 worktree 里借出了子仓，提交了子仓与父仓（gitlink），并跑过门禁
- **WHEN** 在 change 家运行 `merge S1=<父仓提交>`
- **THEN** 合回成功，临时 worktree 的目录不在了
- **AND** change 家子仓的 worktree 清单里不再有借出的那一间，子仓提交仍在对象库里，该片的文件在 change 家的子仓里

#### Scenario: reap-failure-does-not-fail-merge
- **GIVEN** 切片临时 worktree 被 `git worktree lock` 锁住
- **WHEN** 在 change 家运行 `merge S1=<提交>`
- **THEN** 退出 0，`ok` 为 true，`merged` 为 `["S1"]`
- **AND** 该 worktree 原样还在，`warnings` 有一条含「未回收」与它的路径

### Requirement: 铁律 6 写明回收这一例外
根 `CLAUDE.md` 的铁律 6 SHALL 在「不删 worktree」之后写明例外：切片临时 worktree 的提交已合回 change 分支、且没有未合回的改动时，由 `slice-gate.py merge` 不带强制参数回收。`template/CLAUDE.md.snippet` 的铁律 6 SHALL 同步这一例外。两处 MUST 保留 `/clean-after-merged` 的例外；根 `CLAUDE.md` MUST 保留「不删 worktree」与 `branch -D` 交人的措辞；snippet MUST NOT 超过 8KB。
Feature: 规则与脚本的行为一致
Rule: 自动删除的每一种情形都写在铁律里

#### Scenario: iron-rule-names-reap-exception
- **GIVEN** 根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`
- **WHEN** 取两者以「6. Git 边界」开头的那一行
- **THEN** 两行都含「临时 worktree」「`slice-gate.py merge`」与 `/clean-after-merged`
- **AND** 根那一行含「不删 worktree」「不带强制参数」与 `branch -D`
- **AND** snippet 不超过 8KB
