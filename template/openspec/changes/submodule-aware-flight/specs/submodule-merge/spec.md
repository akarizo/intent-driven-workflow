## ADDED Requirements

### Requirement: merge 子命令逐片合回并处理 gitlink
Rule: `slice-gate.py merge <S>=<sha> ...` SHALL 按参数顺序逐片执行父仓 `git merge --no-ff --no-commit`，再以说明 `integrate: <S>` 提交。被合入一侧改了 gitlink 时，按两侧 gitlink 的关系处理：
- **快进**（一方是另一方的祖先）→ 直接钉较新的那个。
- **分叉** → 先在本仓（change 家）子仓内执行 `merge --no-ff`，合入被合入一侧的子仓提交；再用 `update-index --cacheinfo 160000,<子仓合并结果>,<路径>` 钉 gitlink。

每片合回后，子仓的检出 SHALL 等于父仓 HEAD 的 gitlink：子仓在分支上时分支快进，detached 时检出到该提交。

开跑前，已填充子仓的检出 SHALL 等于父仓 HEAD 的 gitlink，否则不合任何一片。

输出 JSON `{ok, merged, failed, warnings}`，全部成功时退出 0。

#### Scenario: merge-parallel-submodule-slices
- **GIVEN** 同一 wave 的 S1、S2 在各自的隔离 worktree 里改子仓（文件不相交），各自提交 gitlink，门禁都绿
- **WHEN** 在 change 家运行 `slice-gate.py merge S1=<C1> S2=<C2>`
- **THEN** 退出 0，`merged` 为 `[S1, S2]`
- **AND** 家子仓的分支与检出都等于父仓 HEAD 的 gitlink，并包含两片的子仓提交
- **AND** 父仓工作树干净，最近两个提交的说明依次为 `integrate: S1`、`integrate: S2`

#### Scenario: next-wave-populates-from-merged-gitlink
- **GIVEN** wave 1 的 S1、S2 已由 `merge` 合回
- **WHEN** wave 2 的 S3 在新的隔离 worktree 里走完执行体流程
- **THEN** S3 的子仓起点包含 S1、S2 的文件，门禁绿

### Requirement: 合回失败全回滚
Rule: 遇到以下任一情况，`merge` SHALL 中止父仓合并（`merge --abort`）、中止子仓合并，并回滚本片已做的子仓合并，然后停止，不再合后续片：
- 非 gitlink 的文件冲突；
- 子仓内的合并冲突；
- 子仓未填充；
- 遇到新增 submodule。

返回 `ok` 为 false，`merged` 只列此前成功的片。`failed` 首项以 `merge <S>` 开头，点名冲突文件或子仓路径。

#### Scenario: merge-rolls-back-on-submodule-conflict
- **GIVEN** S1 改子仓 `lib1.py`；S2 在另一个隔离 worktree 里把同一个 `lib1.py` 改成不同内容
- **WHEN** 运行 `merge S1=<C1> S2=<C2>`
- **THEN** 退出 1，`merged` 为 `[S1]`，`failed` 首项含 `S2` 与 `mods/sub`
- **AND** 父仓与子仓都不在合并中，子仓检出等于父仓 HEAD 的 gitlink，HEAD 说明为 `integrate: S1`

#### Scenario: merge-aborts-on-file-conflict
- **GIVEN** 没有 submodule 的仓库，两个旁支把 `README.md` 改成不同内容
- **WHEN** 运行 `merge S1=<a> S2=<b>`
- **THEN** 退出 1，`merged` 为 `[S1]`，`failed` 首项以 `merge S2` 开头并含 `README.md`
- **AND** 不在合并中，HEAD 说明为 `integrate: S1`

### Requirement: 无 submodule 时与 merge --no-ff 等价
Rule: 仓库没有 gitlink 时，`merge` 的结果 SHALL 与逐条执行 `git merge --no-ff <sha> -m "integrate: <S>"` 一致：每片一个双亲 merge commit，说明为 `integrate: <S>`。

#### Scenario: merge-plain-repo-equals-no-ff
- **GIVEN** 没有 submodule 的仓库，两个从 main 分叉的旁支分别新增 `a.txt`、`b.txt`
- **WHEN** 运行 `merge S1=<a> S2=<b>`
- **THEN** 退出 0，输出为 `{"ok": true, "merged": ["S1", "S2"], "failed": [], "warnings": []}`
- **AND** `HEAD~1`、`HEAD` 都是双亲 merge commit，说明依次为 `integrate: S1`、`integrate: S2`
