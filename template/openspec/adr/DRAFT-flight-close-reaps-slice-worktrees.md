# DRAFT. 飞行收口回收全部临时 worktree，作废尝试先归档

- Status: accepted, supersedes DRAFT-slice-worktrees-reaped-after-merge（仅「约束后续变更」中的「merge 之外的脚本不得删除 worktree」与「不覆盖」一节；决策 1–6 在役）
- Date: 2026-11-19
- Supersedes: DRAFT-slice-worktrees-reaped-after-merge（合并时回填真实号；只取代上述两项）
- 关联：DRAFT-post-merge-cleanup-by-tiered-script（本决策新增两条判据，三档语义不变，不取代）
- 来源 change：reap-agent-worktrees-at-close（design D1–D8）

## Context

`DRAFT-slice-worktrees-reaped-after-merge` 让 `slice-gate.py merge` 在合回一片后回收它的临时 worktree，判据是「HEAD 在本次合入的提交里」。它明确不覆盖存量、未交回执行体留下的、blocked 后没有合回的，还规定「merge 之外的脚本不得删除 worktree；需要新的回收时机时扩展本决策」。

2026-11-19 只读盘点发现，这些没覆盖的部分才是大头：

- afa 35 个、约 33G；
- 本仓库 23 个，其中 8 个是门禁红后重派留下的旧尝试：`--continue` 把提交接到新 HEAD 上，旧 SHA 永远不会进 change 分支；
- `/clean-after-merged` 拿 target 判合入，执行体提交只进了 change 分支，所以全部落到 keep，afa 的 safe 档收 0 个。

用户要求：确认无用即在释放后立即清理。

## Decision

1. **新增收口回收点**：opsx-apply 收口运行 `slice-gate.py reap --change-dir`，回收本次飞行的全部临时 worktree。合回时的回收不变。
2. **归属只认飞行证据**：
   - 切片标记的 `change_dir` 指向本 change，或者
   - 工作树里有本 change 的飞行记录改动。

   不看目录名，也不看 HEAD 是否从本 change 派生。
3. **已落地**（HEAD 是 change 家 HEAD 的祖先）→ 按原决策 2–4 回收（只丢弃飞行记录 / 切片标记 / 字节码，先归还借出子仓，不带强制参数）。
4. **作废尝试先归档再回收**：
   - 提交与可丢弃三类以外的未提交改动，写进 `refs/flight/<change>/attic/<目录名>`；
   - 有改动时，用临时索引做一个以 HEAD 为父的提交；
   - 随后丢弃已归档的改动，再按决策 3 删除目录；
   - 未合入的分支保留。

   attic 与其他 `refs/flight/<change>/*` 一样，在 `/clean-after-merged` 判定 change 已落地时删除。
5. **回收恒不影响收口结论**：恒 exit 0，结果进 JSON 与 timeline 的 `reap` 事件。
6. **`/clean-after-merged` 增加两条判据**，只对 `.claude/worktrees/` 下的 worktree 生效：
   - `landed`：HEAD 被 merge 进另一个本地分支，不在该分支的 first-parent 链上；
   - `dead-attempt`：属于已落地 change，包括已归档的。有自己分支的进 safe，游离 HEAD 的进 manual。
7. **铁律 6 写明收口回收这一例外**。

否决的方案：

- **按 `wf_*` 目录名认**：名字是运行时实现细节（原决策已否决）。
- **按 HEAD 派生关系认归属**：`worktree.baseRef = head` 时，人在 change 家开的 worktree 也从 change HEAD 派生，会被误收。
- **按「被分支包含」判 landed**：执行体从 change tip 派生，change tip 落在执行体分支的 first-parent 链上，会把 change 家判成已落地。
- **作废尝试直接删、不归档**：未交回执行体的半成品可能是人还想看的。
- **用 `--force` 收自有子仓克隆**：实测 git 2.54 不带强制参数必拒，`deinit` 后也拒；保留并交 `/clean-after-merged`（已有未推送提交防护）。

## Consequences

- **更易**：
  - 正常飞行收口后，临时 worktree 回到 0（锁定的、自有子仓克隆的除外，并写明原因）；
  - 存量可以由 `/clean-after-merged` 收走大部分；
  - timeline 的 `reap` 事件记录每次释放的空间，可度量。
- **更难**：
  - 铁律 6 的例外从两条变三条；
  - `refs/flight/<change>/attic/*` 会在 change 落地前一直存在（只占对象，不占工作树空间）。
- **不覆盖**：
  - change worktree（`.worktrees/`）仍只按 target 判；
  - 未合入的 `worktree-wf_*` 分支仍由人决定是否 `-D`；
  - 游离 HEAD 的作废尝试若漏过收口，在 `/clean-after-merged` 里进 manual。
- **约束后续变更**：
  - 删除临时 worktree 的脚本限于 `merge`、`reap` 与 `merged-cleanup`；
  - 新增回收时机时扩展本决策，并沿用「归属认飞行证据、已落地复用同一回收、作废先归档」三条判据。
