# DRAFT. 合并后清理由脚本分档判定，显式调用命令即授权 safe 档

- Status: accepted
- Date: 2026-11-09
- 关联：DRAFT-gate-evidence-not-self-reported（判定机械化，不靠自述）· DRAFT-submodule-slices-borrow-home-worktree（子仓借用带来的清理语义）
- 来源 change：post-ship-hygiene（design D1–D9）

## Context

铁律 6 写着「不删 worktree」，`openspec-git-discipline` 把 `worktree remove` / `branch -d` 列为「破坏性收尾，一律交用户授权」。清理时能依据的只有一句「由人确认后在主仓库根手动执行」。

2026-11-09，PR #11 合并后，按人工命令清单清理 9 个 worktree，结果 6 个 `git branch -d` 失败。原因是分支无 upstream 时 git 按本地 HEAD 判断，而本地 `main` 未同步。

同日的玩具仓实验又确认：在 linked worktree 里初始化的子仓，仓库本体在 `.git/worktrees/<id>/modules/` 下，`worktree remove --force` 会连同其中未推送的提交一起删掉。

要不要 `--force`、`-d` 还是 `-D`、删掉会不会丢东西，这些判断依赖四处不直观的 git 行为。交给人或模型临场判断，结果要么命令失败，要么静默丢数据。

## Decision

1. **判定全部由脚本完成**（`merged-cleanup.py`）。每项输出 `merged`（ancestor / content / fresh / unmerged / landed）、`tier`（safe / manual / keep）、`force`、以稳定标记开头的原因和确切命令。合并判定纯 git（祖先关系 + `merge-tree` 树等价），不依赖托管平台。
2. **三档语义固定**：
   - `safe`：执行后不丢任何未落地的内容，可自动执行；
   - `manual`：需要 `-D`、`push --delete`，或会丢失改动或子仓提交，或对象来历不明（被 lock、在约定目录外），只输出命令；
   - `keep`：未合并或无独有提交，不输出命令。

   判不准时一律往更保守的一档落。
3. **授权边界**：显式运行 `/clean-after-merged` = 授权其文档内的 `safe` 档，这是铁律 6 的唯一例外。`git branch -D`、`git push --delete` 与 `manual` 档永远交人执行。
4. **只在主 worktree 运行**：脚本机械拒绝在 linked worktree 里运行。
5. **子仓提交存活是 `safe` 的前提**：会随 worktree 一起删除的子仓库里，每个 tip 都必须能在别处找到。

## Consequences

- **更易**：合并后一条命令清理干净；2026-11-09 那类失败（未同步就 `-d`）由脚本先 `--ff-only` 同步，不再发生。
- **更易**：子仓提交丢失从「静默」变为「`manual` 档并写明先推送子仓」。
- **更难**：铁律 6 从「不删」变为「不删，除显式命令的 safe 档外」，每次扩大 safe 档都要改这份契约。新增 safe 判据必须附带「执行后不丢未落地内容」的论证。
- **约束后续变更**：任何新增的「会产生本地状态」的机制，如新的 ref 命名空间或新的临时目录，要么在本脚本里登记清理规则，要么明确写入 keep。
- **不影响**：没有 linked worktree 或 `worktree-*` 分支的仓库，脚本输出空清单。
