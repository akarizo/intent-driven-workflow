---
name: openspec-git-discipline
description: Use when running OpenSpec propose, continue, apply, verify, archive, or worktree workflows where proposal artifacts, branches, merges, or archive timing affect git history.
license: MIT
compatibility: Requires git and OpenSpec workflow artifacts.
---

# OpenSpec Git Discipline

## Core Rule

Every OpenSpec state change must be captured as an explicit commit before the next lifecycle phase depends on it.

- Propose/continue artifacts are drafted inside the change's own worktree (see **Worktree Isolation** below), and must be committed as a dedicated artifacts-only commit (no implementation code mixed in) before apply starts. Merging to `main` first is NOT required.
- Apply runs inside that same worktree once the dedicated proposal commit exists.
- Archive may run only from `main` (the primary repo working tree) after implementation is merged back.

Never create commits, branches, or merges unless the user explicitly asks. This rule protects **lifecycle / shared state** — it forbids auto-committing proposal/archive artifacts, auto-creating branches, and above all any `merge` / `push` / `archive` that the user did not ask for.

## Worktree Isolation（每 change 一个独立 worktree）

**这是本 skill 的权威定义处**；其余生命周期 skill 只引用它，不重复。

规则：**每一个 OpenSpec change 从 propose 起手就在它自己的独立 git worktree + branch 里进行，该 change 的一切产物都落在这个 worktree 内，主仓库工作区（`main`）永远不落任何 change 产物。**

- **路径与命名（权威）**：worktree 目录严格位于仓库根下的 `.worktrees/<change>/`（复数 `.worktrees`），分支名 `worktree-<change>`。这是全库唯一权威路径 —— `bulk-apply` 的 `.worktrees/` 也是它。
- **入口时机**：`/opsx-propose`、`/opsx-new` 在跑 `openspec new change "<change>"` **之前**先建好该 change 的 worktree 并进入它（CWD = worktree 根）。之后 `openspec` CLI 与所有工件写入用的都是相对路径（`openspec/changes/<change>/…`），自然落在 worktree 内 —— **无需改写任何路径常量，只需切 CWD**。
- **产物范围**：5 工件（proposal→specs→design→adr→tasks）+ `spec.html` 审批面板 + apply 阶段的实现代码，**全部**落在 `.worktrees/<change>/` 内。禁止把任何 change 产物写到主仓库工作区。
- **粒度**：**每 change 一间**，不是每 task 一间。一个 change 内的逐 task 实现（含 `openspec-subagent-apply-change` 逐 task 守门）在**同一间** worktree 里串行累积（task 依赖前序产出）。禁止为单个 task 各开 worktree，也禁止在 change worktree 内再嵌套子 worktree。
- **建 worktree 是工作区准备，不是 lifecycle 推进**：因此生命周期 skill 可主动建 change worktree + 其分支（这不违反「不擅自建分支」——它不推进 propose→apply→archive 状态，也不 push/merge）。但 `merge` / `push` / `worktree remove` / `branch -d` 仍是破坏性收尾，一律交用户授权。
- **清理只在主仓库根**：`git worktree remove .worktrees/<change>` → `git branch -d worktree-<change>` → `git worktree list` 验证，全部在主仓库根执行；禁 `cd` 进 worktree 后再删自身（CWD 卡死）。

**Carve-out — per-task implementation commits during apply:** the `openspec-subagent-apply-change` (逐 task 守门) flow produces a small local commit per task during the apply phase. This is **allowed and not a violation**, because such commits are:

- **local only** — they land on the current feature branch / worktree, never on `main`, and are never `push`ed, `merge`d, or `archive`d by the flow;
- **lifecycle-neutral** — they do not advance the propose→apply→archive state; they are just the audit trail of "this task's implementation", fully `reset`-able;
- **already consented** — the user explicitly opted in by choosing the "subagent 逐 task 守门" mode at the `/opsx-apply` step-6 prompt (which states that per-task local commits will be created). This satisfies the "unless the user explicitly asks" condition for these commits only.

This carve-out covers **only** per-task implementation commits inside that apply flow. It does NOT relax anything about merge / push / archive, or about auto-committing proposal or archive artifacts without the user asking.

**Carve-out — 每个执行体的临时 worktree（flight apply）：** `opsx-apply` 飞行工作流（`Workflow` 工具，或其 `Agent` 工具回退路径）为每个执行体（含单片 wave 与 fix；wave 内并行的切片各自一个）开一个临时 worktree（`isolation: worktree`，见 `template/.claude/workflows/opsx-apply.js`）。这不违反上面「每 change 一间，禁止嵌套子 worktree」的规则，因为：

- **由运行时创建，不是 LLM 手动嵌套** —— 临时 worktree 由 Workflow/Agent 运行时在该切片执行期间创建，执行体本身不手动在 change worktree 内再开子 worktree；
- **以 SHA 合回，不是 `merge`/`push`** —— 每个切片（及 fix）的本地实现 commit 由 `integrator` 以其 HEAD 的 SHA 合回 change 分支，不 push、不 merge 进 main；
- **清理由运行时负责（无残留改动时）** —— 临时 worktree 内没有未提交改动时由运行时自动清理；若有残留（例如 hook 追加的飞行记录），运行时会保留它，由人确认内容已由 integrator `record` 写回后，在主仓库根手动 `git worktree remove` 清理，执行体不动它。

本 carve-out 只覆盖飞行 apply 工作流为每个执行体（含单片 wave 与 fix）产生的临时 worktree，不放松其它场景下「每 change 一间，禁止嵌套子 worktree」的规则，也不授权对 main 的 `push` 或 `merge`。

## Gates

| Moment | Gate |
| --- | --- |
| Before propose / new | Ensure the change's worktree exists at `.worktrees/<change>/` and the session is inside it (create + enter if missing). All artifacts land there, never in the primary `main` working tree. |
| Before continue / apply | Confirm the session is inside `.worktrees/<change>/`; if not, enter it before touching any file. |
| During continue | Before creating the next artifact, ask the user to commit completed artifact changes or explicitly continue without that checkpoint. |
| After propose | Ask the user to commit proposal artifacts as a dedicated artifacts-only commit; offer to create a PR branch for review. |
| Before apply | Confirm the proposal artifacts sit in a dedicated commit (artifacts only); then apply may run from `main`, a branch, or a worktree. |
| Before merging ADRs to `main` | If the branch created any `DRAFT-*.md` under `openspec/adr/`, number them first (see ADR numbering below). Never merge a `DRAFT-*` ADR into `main`. |
| Before archive | Stop unless implementation is merged back to `main` and archive is running from `main`. |
| After archive | Ask the user to commit archive/spec sync changes. |

## Required Checks

Before apply:

1. Run `git status --short`.
2. Verify `openspec/changes/<change>/` has no uncommitted proposal files.
3. Verify the proposal artifacts are captured in a dedicated commit (e.g. `git log --oneline -- openspec/changes/<change>/` shows one) and that commit contains no implementation code.

Use this language if the artifacts are not in a dedicated commit:

> I should not apply this yet because the proposal artifacts are not captured in a dedicated commit. A proposal can be drafted on any branch, but apply must start only after the artifacts are committed on their own (artifacts only, no implementation code). Please commit the proposal artifacts as a standalone commit first, then I can apply from `main`, a branch, or a worktree.

Before archive:

1. Run `git branch --show-current` and `git status --short`.
2. Stop if not on `main`.
3. Stop if implementation work has not been merged back to `main`.

Use this language:

> I should not archive this yet because archive must run from `main` after implementation is merged back. Verify makes a change eligible to merge; it does not replace the merge.

## ADR Numbering at Merge

ADRs are numbered with a repo-wide monotonic sequence (`NNNN-kebab-title.md`).
A sequence is a global counter, so two branches that each pick "highest + 1"
while proposing collide on the same number and conflict at merge - both on the
filename and on any `Supersedes:` / CLAUDE.md pointer to that number.

To prevent this, ADRs are created **unnumbered on a branch** (`DRAFT-kebab-title.md`)
and numbered **only at merge time**, by whoever lands the branch on `main`:

1. Check out the latest `main`. `ls openspec/adr/` and find the highest existing `NNNN`.
2. Assign `max+1, max+2, ...` to each `DRAFT-*.md` in this change, in logical order.
3. `git mv openspec/adr/DRAFT-kebab-title.md openspec/adr/NNNN-kebab-title.md` (preserves history).
4. Edit the title line inside the file: `# DRAFT.` → `# NNNN.`.
5. Back-fill any in-change reference to the draft (a sibling ADR's `Supersedes:`,
   a `design.md` pointer, a `（ADR-DRAFT-x）` placeholder in CLAUDE.md) with the real number.
6. Commit the numbering, then merge/PR to `main`.

Each branch re-scans `main` independently before it lands, so a branch that
merges after another sees the just-assigned numbers and continues from there -
the sequence stays gap-free and collision-free. A `Supersedes:` pointing at a
prior ADR keeps that prior ADR's real number: it already lives on `main` and is
stable; only the branch's own new ADRs are deferred.

Never create commits, branches, or merges unless the user explicitly asks; the
numbering steps above are what to do when the user drives the merge, not license
to merge on your own.

## Red Flags

- Writing any change artifact (工件 / `spec.html` / 实现代码) into the primary `main` working tree instead of `.worktrees/<change>/`.
- Opening a separate worktree per task, or nesting a child worktree inside a change's worktree — the granularity is one worktree per change, tasks accumulate inside it.
- Running `worktree remove` / `branch -d` from inside the worktree being removed (CWD deadlock) — do cleanup only from the primary repo root, and only when the user asks.
- Applying a proposal whose artifacts are uncommitted, or whose commit mixes artifacts with implementation code.
- Treating files visible on disk (or in a worktree) as proof that the artifacts were committed.
- Creating the next continue artifact without asking about committing the previous one.
- Archiving from a feature branch or before implementation is merged to `main`.
- Merging a `DRAFT-*.md` ADR into `main` without numbering it first.
- Assigning an ADR sequence number while still on a branch (that is what collides).
- Auto-merging or auto-pushing without explicit user approval; auto-committing proposal/archive artifacts; auto-creating branches without approval. (Per-task *implementation* commits inside the `openspec-subagent-apply-change` flow are exempt — see the Carve-out under Core Rule — but auto-merge / auto-push / auto-archive never are.)

All of these mean: pause, explain the boundary, and ask the user to make the git state explicit.
