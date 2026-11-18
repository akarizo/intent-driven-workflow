# DRAFT. 切片临时 worktree 在提交合回后由合回脚本回收

- Status: accepted
- Date: 2026-11-18
- 关联：DRAFT-post-merge-cleanup-by-tiered-script（本决策在其第 3 条之外增加铁律 6 的第二个例外；该 ADR 其余各条照旧有效，不被取代）· DRAFT-submodule-slices-borrow-home-worktree（借出的子仓 worktree 要归还）
- 来源 change：slice-resume-deterministic（design D7 · D8）

## Context

每个切片执行体在运行时开的临时 worktree 里干活，提交由 integrator 用 `slice-gate.py merge` 合回 change 分支。合回之后这些 worktree 没有人收：铁律 6 写着「不删 worktree」，`DRAFT-post-merge-cleanup-by-tiered-script` 把 `/clean-after-merged` 的 safe 档定为唯一例外，而那条命令要等 PR 合并之后由人运行。

afa 的 `.claude/worktrees/` 累积过约 64G 的历史临时 worktree，磁盘占满后切片的 verify 报空间不足（交接文档 F11）。

临时 worktree 与 change 的 worktree 不是一回事：前者是运行时的一次性产物，内容在提交合回的那一刻就已经全部落在 change 分支上了。

## Decision

1. **`slice-gate.py merge` 每成功合回一片，回收 HEAD 落在这次合并带进来的提交里的其他 worktree**。按「这次合并带进来的提交」判，不按「是 change 分支的祖先」判——后者会包含 `main` 与别的 change 的起点。
2. **只收没有未合回内容的**：除飞行记录（会由 `record` 重写到分支）、切片标记、未跟踪的字节码之外还有未提交改动的，一律留下。
3. **不用强制参数**：`git worktree remove` 与 `git branch -d` 都不带强制。被锁住的、带真 submodule 的、分支未合入的，git 自己会拒绝，脚本照单留下并写进 `warnings`。
4. **借出的子仓先归还**，前提是它的 HEAD 已并入 change 家的子仓。
5. **回收的成败不影响合回的结论**。
6. **铁律 6 写明这一例外**；change 自己的 worktree 仍然只由 `/clean-after-merged` 处理。

「执行后不丢未落地内容」的论证：提交已是 change 分支的祖先；飞行记录由门禁 JSON 原文重写；留痕的真值在共用目录（`DRAFT-slice-evidence-in-git-common-dir`）；字节码是副产物；其余未提交内容会让回收放弃。

否决的方案：

- **工作流收尾统一清**：工作流脚本不碰文件系统，得再派一个 agent；中途 blocked 的飞行不会走到收尾。
- **按目录名（`wf_*`）认临时 worktree**：名字是运行时的实现细节，换版本就失效，还会误伤同名前缀的东西。
- **连未交回执行体留下的半成品一起清**：那需要强制参数，而且半成品可能是人还想看的。

## Consequences

- **更易**：正常飞行结束时临时 worktree 数量回到接近 0；磁盘不再随飞行次数线性增长。
- **更难**：铁律 6 的例外从一个变成两个，以后每增加一种自动删除都要成文并附不丢内容的论证。
- **不覆盖**：存量的临时 worktree、未交回执行体留下的（带未提交改动）、blocked 后没有合回的，仍等 `/clean-after-merged` 或人工处理。
- **约束后续变更**：`merge` 之外的脚本不得删除 worktree；需要新的回收时机时扩展本决策，不另起一套判据。
