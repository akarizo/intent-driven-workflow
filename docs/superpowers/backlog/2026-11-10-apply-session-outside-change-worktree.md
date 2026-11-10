# backlog · 会话停在主仓库根起飞，执行体隔离 worktree 从 main 派生（2026-11-10）

## 现象（本轮 1 次，未达 E 类门槛，先记 backlog）

change `goal-authorized-takeoff` 首轮起飞时，会话的工作目录是主仓库根（main，`4c91dc6`）。只用 Bash 进入了 `.worktrees/goal-authorized-takeoff/`，没有把会话切进这个 worktree。仓库 `.claude/settings.json` 设了 `worktree.baseRef: head`，所以 Workflow 给执行体开的隔离 worktree 从**会话所在仓库的 HEAD**（main）派生，里面没有 change 目录：

- S1：`slice-gate.py start` 因缺 `slices.json` 以 exit 2 退出，stdout 没有 JSON；执行体靠 `git merge-base` 补报 `G0 base`，没做任何改动；
- S2：依赖 S1，直接记 blocked（infra）；final：scenario 0/7 红。

补救：`EnterWorktree(path=.worktrees/goal-authorized-takeoff)` 后重新起飞，第二轮两片都绿。

证据：`template/openspec/changes/goal-authorized-takeoff/timeline.md` 的 `01:15:34Z final red` / `01:15:37Z apply-done blocked=2`。

## 附带发现

- **start 先退出、后校验基点**：缺 `slices.json` 时，`slice-gate.py start` 在 `--expect-branch` 校验之前就以 exit 2 退出，不打印 G0 JSON。基点错误应先于其他检查报出，并给出可读的 `G0 base`。
- **转录随会话搬家**：`EnterWorktree` 之后，本会话转录从 `~/.claude/projects/<主仓 slug>/` 移到 `~/.claude/projects/<worktree slug>/`。`/opsx-apply` step 5「取 `~/.claude/projects/<slug>/` 下最新」按主仓 slug 找会落空，本轮 `session-decompose.py` 首跑 `FileNotFoundError`。`takeoff-gate.py` 按会话 id 定位，不受影响（已实测 exit 0）。

## 防线（Q4 ✓：可机械判定）

1. `/opsx-apply` step 1.5 改成机械检查：会话工作目录（Workflow / Agent 隔离派生的基准）必须是 `.worktrees/<name>/`，不满足时提示先 `EnterWorktree`。可行做法：`slice-gate.py preflight --expect-branch <branch>` 校验调用方 `git rev-parse --show-toplevel` 落在 change worktree；或在 PreToolUse hook 里比对 hook 输入的 `cwd` 与 change worktree。
2. `slice-gate.py start` 把 `--expect-branch` 基点校验提到读取计划文件之前。
3. `session-decompose.py` 的 `--session` 可省略：缺省时按会话 id 在 `~/.claude/projects/*/` 下查找，与 `takeoff-gate.py` 同口径。
