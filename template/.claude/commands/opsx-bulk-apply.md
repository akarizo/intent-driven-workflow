---
description: Apply multiple OpenSpec changes concurrently in isolated worktrees
---

Apply multiple active OpenSpec changes concurrently.

**Input**: Optionally specify two or more change names (e.g., `/opsx-bulk-apply add-auth improve-search`). If omitted, discover active changes with `openspec list --json`.

**Required skill**: Use `openspec-bulk-apply-change`.

**Steps**

1. **Get candidate changes**

   Run:

   ```bash
   openspec list --json
   ```

   If change names were provided, limit candidates to those names.

2. **Check candidate count**

   - If fewer than 2 active candidate changes remain, stop and tell the user to use `/opsx-apply <change>`.
   - If 2 or more candidates remain, continue with `openspec-bulk-apply-change`.

3. **MANDATORY: confirm batch with user before dispatch**

   Before creating any worktree or dispatching any subagent, you MUST stop and ask the user.

   Show:
   - Change list to be applied (names only)
   - Worktree root that will be used (default `.worktrees/`)

   Call the **AskUserQuestion tool** with:
   - question: `确认并行 apply 这 N 个变更吗？将创建独立 worktree 并派发子 agent。`
   - header: `开始 bulk`
   - options:
     - `确认开始` — proceed to step 4
     - `先看每个 change 的 tasks` — for each change in the list, print the first 3 pending task titles, then re-ask this question
     - `取消` — abort, no worktree or subagent created

   The batch-level confirmation is collected ONCE here. Each dispatched subagent is invoked with `/opsx-apply <change> --no-confirm` so it skips its own per-change confirmation.

4. **Follow the bulk apply skill exactly**

   The skill must:

   - Run OpenSpec git discipline checks before apply.
   - Create isolated worktrees under `.worktrees/<change>` on branch `worktree-<change>` (authoritative path/naming from `.claude/skills/openspec-git-discipline/`) unless another root is requested.
   - Dispatch one subagent per change. Before dispatching, run `python3 .claude/hooks/model-routing.py get bulk.apply` and pass its `model` and `effort` explicitly on every subagent dispatch (never leave `model` empty).
   - Run `/opsx-apply <change> --no-confirm` and `/opsx-verify <change>` in each subagent. The `--no-confirm` flag suppresses the per-change confirmation (batch was already approved in step 3).
   - Collect normalized apply and verify reports.
   - Report results without merging or archiving.

**Output**

```markdown
## Bulk Apply Report

### Changes Analyzed
- <change>

### Worktrees
- `<path>`

### Results
| Change | Apply | Verify | Review Ready |
| --- | --- | --- | --- |
| <change> | complete | ready | yes |

### Blockers and Warnings
- <change>: <details>

No merge or archive was performed. Explicit user approval is required before any merge or archive.
```

**Guardrails**

- Do not modify existing single-change `/opsx-apply` behavior.
- Do not ask the user to choose one change when the request is clearly bulk apply and 2 or more candidates exist.
- Do not apply changes directly in the parent workspace.
- Do not merge, archive, or commit unless the user explicitly asks for that follow-up action.
