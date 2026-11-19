## Why

切片执行体的临时 worktree 在飞行结束后大量残留，持续吃磁盘。2026-11-19 只读盘点：afa 有 35 个、约 33G（该仓此前就因磁盘写满导致 verify 失败），stc-foundation 6 个、6.4G，本仓库 23 个。

现有回收只在 `slice-gate.py merge` 合回那一刻判一次（判据是「HEAD 在本次合入的提交里」）。下面几类都没人收：

- 门禁红后重派留下的旧尝试：`--continue` 把提交接到新 HEAD 上，SHA 变了；
- blocked 的切片、未交回的执行体；
- 合回时因故没收掉的。

`/clean-after-merged` 拿 target（main）判断「是否已合入」，可执行体的提交只合进了 change 分支，所以一律落到 keep。afa 实测 safe 档一个也收不了。

用户要求（2026-11-19）：agent worktree 一旦确认无用，就在释放后立即清理。

意图访谈以四轮审批页代替：`docs/flight-routing-config.html` v1–v4，在主仓库工作区，未入库。用户 2026-11-19 回复「全按推荐」，其中 Q11-A 定为「作废尝试先归档再删」，Q10-A 定本 change 为四个中的第一个。

## What Changes

- **新增 `slice-gate.py reap --change-dir DIR`**：飞行收口时回收本次飞行留下的全部执行体临时 worktree。
  - 已落地的（HEAD 在 change 分支历史里）直接删。
  - 作废的尝试，先把提交与未提交改动归档到 `refs/flight/<change>/attic/<名>`，再删。
  - 归属只认飞行证据（切片标记或本 change 的飞行记录改动），不看目录名。
  - 删除不带 `--force`。未合入的分支不删。锁定的不碰。
  - 输出 JSON，恒退出 0，并写 timeline 事件 `reap`。
- **`/opsx-apply` 收口步骤（命令与 skill 同改）**：运行 `reap`，并打印「回收 N 个 · 释放 X MB · 归档 M 个」。子命令不存在时跳过。
- **`merged-cleanup.py` 新增两条判据**：
  - `landed`：worktree 的 HEAD 被 merge 进了另一个本地分支（不在该分支的 first-parent 链上）。
  - `dead-attempt`：worktree 属于已落地 change，提交没进任何其他分支。有自己的分支 → safe；游离 HEAD → manual。
  - 已归档的 change（`openspec/changes/archive/<日期>-<名>/`）也算已落地。
- **文档同步**：`clean-after-merged.md` 原因表补 `landed` / `dead-attempt`；铁律 6（根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`）写明收口回收与归档；README 同步。
- **新 ADR**：扩展 `DRAFT-slice-worktrees-reaped-after-merge` 的回收时机与判据。只取代它的「merge 之外的脚本不得删除 worktree」一条，其余在役。

## Capabilities

### New Capabilities
- `flight-close-reap`：飞行收口时回收本次飞行的执行体临时 worktree，包括归属认定、已落地直接删、作废尝试归档后删、子仓处理、输出与留痕、收口调用、铁律 6 措辞。
- `merged-cleanup-agent-worktrees`：`/clean-after-merged` 识别「已被合进其他分支」与「已落地 change 的作废尝试」两类执行体 worktree，已归档 change 视同已落地。

### Modified Capabilities
（无：`openspec/specs/` 目前为空）

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`（新子命令 `reap`，复用现有 `_reap_one`）、`template/.claude/hooks/merged-cleanup.py`（判据与已落地 change 识别）。
- **文档**：`template/.claude/commands/opsx-apply.md`、`template/.claude/skills/openspec-apply-change/SKILL.md`、`template/.claude/commands/clean-after-merged.md`、`CLAUDE.md`、`template/CLAUDE.md.snippet`、`README.md`。
- **ADR**：新增 `template/openspec/adr/DRAFT-flight-close-reaps-slice-worktrees.md`。
- **行为**：
  - 收口多一步，秒级。
  - `/clean-after-merged` 的 safe 档会多收执行体 worktree。
  - 铁律 6 的例外多一条。
- **依赖**：无新依赖，纯标准库 + git。
- **存量**：本 change 不在实现里动存量。afa / stc 的 A 类由用户执行 `/tmp/worktree-cleanup-{afa,stc}.sh`。B 类等本 change 落地、各仓升级后用 `/clean-after-merged` 处理。
