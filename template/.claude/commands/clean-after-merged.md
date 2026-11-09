---
description: PR 合并后清理已合并的 worktree、分支与飞行快照（refs/flight/*）：先 --ff-only 同步 target，safe 档自动执行，manual 档只打印命令交你
---

PR 被人类合并后，把本仓库里已落地的 change 收尾干净：同步 target 分支 → 删除已合并的 worktree 与本地分支 → 删除已落地 change 的飞行快照 ref。是否已合并、是否需要 `--force`、用 `-d` 还是 `-D`，全部由 `.claude/hooks/merged-cleanup.py` 判定，模型不手工猜。命令本身即逻辑，无同名 skill。

**Input**：可选指定 target branch，缺省为远端默认分支（`<remote>/HEAD`），再缺省为 `main`。例如 `/clean-after-merged develop`。

**Steps**

1. **定位主 worktree 根**

   ```bash
   git rev-parse --path-format=absolute --git-common-dir   # 其父目录 = 主 worktree 根
   ```

   之后所有命令都在主 worktree 根运行。当前会话 CWD 若在某个 worktree 里，先切到主仓库根；禁止 `cd` 进待删的 worktree（CWD 卡死）。

2. **展示计划**

   ```bash
   python3 .claude/hooks/merged-cleanup.py plan --markdown --fetch [--target <T>]
   ```

   输出（safe / manual / keep 三段）原样展示，不改写、不删减。

3. **执行 safe 档**

   ```bash
   python3 .claude/hooks/merged-cleanup.py apply [--target <T>]
   ```

   脚本依次执行：`fetch --prune` → `--ff-only` 同步 target → 删除 safe 档 worktree（带或不带 `--force` 由脚本判定）→ `worktree prune` → 删除已落地 change 的 `refs/flight/*` → `branch -d`。只执行 safe 档。

4. **汇报**

   打印 JSON 里的 `done` 与 `failed`。`manual` 里的命令原样放进一个 ```` ```bash ```` 代码块交用户执行，按原因标记逐条加一行中文说明：

   | 原因标记 | 说明 |
   | --- | --- |
   | `content` | squash 合并：内容已在 target，但提交不是祖先，需 `git branch -D` |
   | `unpushed-submodule` | 子仓库有只存在于该 worktree 的提交，先推送子仓再删 |
   | `dirty` | worktree 有未提交改动，先看清改动再决定 |
   | `locked` | worktree 被锁定，确认没有运行中的 agent |
   | `outside` | worktree 在仓库目录外，确认后再删 |
   | 远端分支 | `git push <R> --delete <branch>`，确认后自己执行 |

5. **验证**

   ```bash
   git worktree list
   git branch --list 'worktree-*'
   ```

**退出码**：0 = 无失败；1 = 有失败（`failed` 逐条打印）；2 = 拒绝运行（不在主 worktree 等）→ 说明原因并停下，不改走其它路径。

**回退（merged-cleanup.py 不可用时）**

脚本缺失或报错无法运行时，只做两件安全的事：

```bash
git fetch --prune <R>
git merge --ff-only <R>/<T>        # 仅当当前在 T 上
```

然后输出 `git worktree list --porcelain` 与 `git branch --list 'worktree-*'`，附人工判据：

- 先同步 T，再 `git branch -d`；
- `-d` 报 not fully merged 时，先判断是否 squash 合并，再决定是否 `-D`；
- 含子仓的 worktree 先确认子仓提交已推送。

回退路径不自动删除任何东西，全部删除命令交用户执行。

**Guardrails**

- 只执行脚本判定的 safe 档。
- 不执行 `git branch -D`、`git push --delete`、`manual` 档的任何命令，也不 `git worktree unlock`。
- 不 `cd` 进待删的 worktree；全部命令在主 worktree 根运行。
- 不归档：`/opsx-archive` 另行触发。
- 显式运行本命令 = 授权 safe 档（铁律 6 例外）；越出 safe 档仍需单独授权。

**与已有命令的配合**

`/pr-ship`（送出）→ 人类合并 → `/clean-after-merged` → 可选 `/opsx-archive`。
