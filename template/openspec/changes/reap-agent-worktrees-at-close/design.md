## Context

**名词**：执行体临时 worktree = 飞行里切片执行体、批量修复、wave 跨片修复在运行时开的隔离 worktree（Claude Code 放在 `.claude/worktrees/` 下），下文简称「临时 worktree」。change 家 = 本 change 自己的 worktree（`.worktrees/<name>/`），即运行 `reap` 的 `root`。

**现状**

- **合回时回收**：`slice-gate.py` 的 `_reap(root, sid, sha, pre, warnings)`（`slice-gate.py:5506`）在 `merge` 每合回一片后，回收 HEAD 落在「本次合入的提交」里的临时 worktree。逐间回收由 `_reap_one`（`slice-gate.py:5463`）完成：
  - 只允许三类可丢弃改动：飞行记录、切片标记、字节码；
  - 先归还借出的子仓；
  - 不带 `--force` 删除；分支用 `-d` 删。
- **合并后清理**：`merged-cleanup.py` 判断 worktree 是否已合入只看 target（`Ctx.merged`，`merged-cleanup.py:90`）。`fresh` / `unmerged` 一律进 keep（`merged-cleanup.py:228`）。
- **切片标记**：`.openspec-slice` 是 JSON `{slice, change_dir, base, started}`，其中 `change_dir` 是绝对路径（`slice-gate.py:4240`）。门禁绿时删除标记。门禁在临时 worktree 里会改动 `<change>/timeline.md`、`gate-report.md`、`evidence.log`。

**漏网实测（2026-11-19，只读）**

| 仓库 | 临时 worktree | 漏网原因 |
|---|---|---|
| afa | 35 个 · 33.0G | 全部是 11-18 的产物；afa 11-19 才升级到带回收的版本。另有 2 个 change 分支已被删，挂在它们下面的无法再证明已落地 |
| stc-foundation | 6 个 · 6.4G | 4 个已在 change 分支里，2 个不在任何分支 |
| 本仓库 | 23 个 · 183M | 14 个是回收功能上线前的飞行留下的；8 个是重派留下的旧尝试，各有 1 个提交既不在任何分支里、也找不到 patch 等价；1 个是人工 regate 留下的 |

现有 `merged-cleanup.py plan` 的结果：afa 的 safe 档收 0 个，保留原因主要是 `unmerged`（相对 main）与 `submodule`。

**git 行为实测**（git 2.54.0，脚本 `/tmp/c4_probe/probe*.sh`）

| 待删 worktree 里的东西 | `git worktree remove`（不带 `--force`） |
|---|---|
| 被 `.gitignore` 忽略的文件 | 可删 |
| 未初始化的 submodule（空目录） | 可删 |
| 已初始化的 submodule（自有克隆） | 拒绝；先 `submodule deinit` 也照样拒绝，因为 `worktrees/<id>/modules` 还在 |
| 未跟踪文件 / 改动过的已跟踪文件 | 拒绝 |

afa 的 `admin/viewer` 子仓是从 change 家**借出**的子仓 worktree（`.git` 文件指向 `…/worktrees/dlib-impl-web-console/modules/admin/viewer/worktrees/viewer`），临时 worktree 自己没有 `modules` 目录。`_reap_one` 已经会先归还这类子仓。

**在役约束**

- 铁律 6；
- `DRAFT-slice-worktrees-reaped-after-merge`（决策 1–6，以及「merge 之外的脚本不得删除 worktree；需要新的回收时机时扩展本决策」）；
- `DRAFT-post-merge-cleanup-by-tiered-script`（三档语义：safe = 执行后不丢任何未落地内容；判不准往保守落；`branch -D` 永远交人）。

### 容器视图（ASCII，C4 风格的轻量容器图）

```
 ┌────────┐ /opsx-apply ┌──────────────────────────┐ python3 ┌───────────────────────────────┐
 │  人类   │────────────▶│ 主会话 · opsx-apply 收口  │────────▶│ slice-gate.py reap（新）      │
 └────────┘             └──────────────────────────┘         │  复用 _reap_one · 归档 attic   │
     │                          │ 打印一行                    └──────┬───────────┬────────────┘
     │ /clean-after-merged      ▼                                    │ git       │ 追加
     │                  ┌────────────────┐                           ▼           ▼
     └─────────────────▶│ merged-cleanup │──git──▶ ┌──────────────────────────┐ ┌─────────────┐
                        │ plan / apply   │         │ 仓库 .git                 │ │ timeline.md │
                        │ +landed        │         │ worktree 登记 · 分支       │ │ reap 事件    │
                        │ +dead-attempt  │         │ refs/flight/<c>/attic/*   │ └─────────────┘
                        └────────────────┘         └────────────┬─────────────┘
 ┌────────────┐ slice-gate.py merge ┌─────────────────┐          │ 登记
 │ integrator │────────────────────▶│ _reap（已有）    │──git────▶▼
 └────────────┘                     └─────────────────┘   ┌──────────────────────────────┐
                                                          │ .claude/worktrees/*（临时）  │
                                                          └──────────────────────────────┘
```

- **三个回收点，一套判据**：合回时（已有，只收本片已落地的）→ 收口时（新，收本次飞行的全部）→ `/clean-after-merged`（存量与漏网）。
- **只有脚本删除**：收口由主会话运行脚本完成。工作流脚本本身不碰文件系统（ADR 已否决在工作流里收尾）。
- **假设**：收口时本次飞行的执行体都已返回（工作流已结束），它们的 worktree 不在使用中。锁定的仍跳过。

### 动态视图：`reap --change-dir D`

```
for W in git worktree list（跳过主 worktree、change 家自身、bare）:
    W 锁定                                      → kept「已锁定」
    W 没有本 change 的飞行证据（D2）               → 不碰，不出现在输出里
    HEAD(W) 是 HEAD(change 家) 的祖先             → _reap_one(W)            → reaped
    否则（作废尝试）                               → 归档 attic（D4）→ 丢弃已归档改动 → _reap_one(W) → reaped + archived
    任一步失败                                     → kept「<原因>」，继续下一间
timeline 追加 reap 事件；打印 JSON；exit 0
```

## Goals / Non-Goals

**Goals:**
- 飞行收口时，本次飞行留下的临时 worktree 一间不剩（锁定的和自有子仓克隆的除外，并说明原因）。
- 不丢内容：
  - 已落地的，提交已在 change 分支上；
  - 作废的，提交与未提交改动都进 `refs/flight/<change>/attic/<名>`，可以 `git worktree add` 找回。
- `/clean-after-merged` 能收存量：已被合进 change 分支的临时 worktree；已落地 change 的、有自己分支的作废尝试。
- 不新增强制参数，不新增 `branch -D`。

**Non-Goals:**
- 不处理 change worktree（`.worktrees/<name>`），仍由 `/clean-after-merged` 按 target 判。
- 不删未合入的 `worktree-wf_*` 分支（几乎不占空间；`-D` 交人）。
- 不清 git 对象（gc 由 git 自理）。
- 不在实现里清理任何仓库的存量（由用户执行脚本或升级后运行 `/clean-after-merged`）。

## Decisions

**D1 · 新增收口回收点，不改合回回收**
`reap` 是 `slice-gate.py` 的新子命令，在 opsx-apply 收口步骤运行。合回时的 `_reap` 不变。
- *否决*：在工作流脚本收尾时清。脚本不碰文件系统，得再派 agent；中途 blocked 的飞行也走不到收尾（原 ADR 已否决）。
- *否决*：门禁结束时执行体自删。执行体的 CWD 就在要删的目录里，删了会卡住。

**D2 · 归属只认飞行证据，不看目录名，也不看派生关系**
满足任一条即属于本次飞行：
- (a) `W/.openspec-slice` 存在，且其 `change_dir` 的目录名等于本 change 名；
- (b) W 的未提交改动里有 `**/changes/<本 change>/{timeline.md, gate-report.md, evidence.log}`。

两条都不满足就不碰。
- *否决*：按 `wf_*` 目录名认。名字是运行时的实现细节（原 ADR 已否决）。
- *否决*：按「HEAD 从本 change 派生」认。本仓库 `worktree.baseRef = head`，会话在 change 家里用 EnterWorktree 开的 worktree 同样从 change HEAD 派生，会被误收。

**D3 · 已落地 = HEAD 是 change 家 HEAD 的祖先 → 复用 `_reap_one`**
飞行记录、切片标记、字节码的丢弃，借出子仓的归还，不带 `--force` 的删除，分支 `-d`，全部沿用 `_reap_one`。

**D4 · 作废尝试先归档到 `refs/flight/<change>/attic/<W 的目录名>`，再删**
- 没有可丢弃三类以外的改动 → ref 直接指向 HEAD。
- 有 → 用临时索引（`GIT_INDEX_FILE` 指向临时文件，先 `read-tree HEAD`）把这些路径（含未跟踪、不含被忽略的）写进去，`write-tree` 后用 `commit-tree -p HEAD` 做一个提交，ref 指向它。随后丢弃这些改动（已跟踪的 `checkout --`，未跟踪的删文件），再交给 `_reap_one`。
- 同名 ref 已存在且指向别的提交时，名字后加 `-<HEAD 前 7 位>`。
- 分支 `-d` 会因未合入而失败：保留分支，不告警。
- **生命周期**：attic 与 `refs/flight/<change>/*` 其他快照一样，在 `/clean-after-merged` 判定该 change 已落地时由 safe 档删除。这与现有快照 ref 的处理一致，也是用户批准的口径（审批页 v4：归档保留到 change 合并为止）。
- **找回**：`git worktree add <路径> refs/flight/<change>/attic/<名>`。
- *否决*：直接删、不归档。未交回执行体的半成品可能是人还想看的，铁律要求不丢未落地内容。

**D5 · 子仓**
- 借出的子仓：`_reap_one` 已处理（先在 change 家子仓里 `worktree remove` 归还）。
- 自有子仓克隆：git 不带 `--force` 必拒（见实测）。保留，`kept` 写「含自有子仓克隆 <路径>，交 /clean-after-merged」。`merged-cleanup` 已有带未推送提交防护的 force 处理。

**D6 · 输出与留痕：恒 exit 0**
- stdout：`{"ok": true, "reaped": [路径], "archived": [{"path", "ref"}], "kept": [{"path", "why"}], "freed_kb": N, "warnings": [...]}`。
- `freed_kb` 是删除前对被删目录的磁盘占用统计（遍历文件，用 `st_blocks × 512`，取不到时退回 `st_size`）。
- timeline 追加事件 `reap`，备注 `回收 N 个 · 释放 X MB · 归档 M 个 · 保留 K 个`；N 为 0 也写，供度量。
- 回收是善后，任何异常都只进 `kept` / `warnings`，不影响收口结论。
- 不在 git 仓库或 change 目录不存在时，输出 `ok: true` 与空列表加一条 warning。

**D7 · 收口调用位置**
在 opsx-apply step 6，`flight-doctor.py cost` 之后、写 `review-findings.json` 之前运行。这样 timeline 的 reap 事件能进同一次 `chore(flight)` 提交。打印 `reap` 的一行汇总。报 `invalid choice`（hooks 未升级）时跳过、照常往下。命令文档与 skill 同改。回退路径与 Workflow 路径共用 step 6，不另写。

**D8 · merged-cleanup 的两条新判据只对 `.claude/worktrees/` 下的 worktree 生效**
- **landed**：
  - 条件：W 的 HEAD 在另一个本地分支 B 的历史里，且不在 B 的 first-parent 链上（即被 merge 进 B，而不是 B 从它派生）。B 不是 W 自己的分支。
  - 结果：不再因相对 target 的 `unmerged` / `fresh` 进 keep，按现有的 dirty / submodule / locked / outside 规则分档，原因以 `landed:` 开头并写明 B。
  - 实现：`for-each-ref --contains <HEAD> refs/heads/` 一次取候选，每个分支的 first-parent 列表缓存一次。
  - *为什么排除 first-parent*：执行体从 change 分支的 tip 派生，所以 change 分支的 tip 落在执行体分支的 first-parent 链上。按「被包含」判，会把正在飞行的 change 家或同类 worktree 误判为已落地。
- **dead-attempt**：
  - 条件：W 未 landed、相对 target 也未合入，但从切片标记或飞行记录改动能认出它属于 change C，且 C 已落地。
  - 已落地 = target 树里有 `openspec/changes/C/`，或有 `openspec/changes/archive/<YYYY-MM-DD>-C/`。归档目录的识别同时让已归档 change 的 `refs/flight/C/*` 进 safe。
  - 结果：W 有自己的分支 → 分支保住提交，按现有规则分档，原因 `dead-attempt: C`。游离 HEAD → 删除会丢提交，进 manual，原因写明。
- **为什么只限 `.claude/worktrees/`**：这是看位置不是看名字，与 `merged-cleanup` 已有的 `HOME_DIRS` 区分一致。change worktree（`.worktrees/`）仍只按 target 判，避免把人正在用、刚好干净的 change worktree 收走。

**D9 · 铁律 6 与文档**
- 根 `CLAUDE.md` 与 snippet 的铁律 6 例外加一句：飞行收口由 `slice-gate.py reap` 回收本次飞行的临时 worktree，作废尝试先归档。现有措辞全部保留（`tests/test_merge_reap.py:153` 钉住）。
- `clean-after-merged.md` 的原因表补 `landed`、`dead-attempt` 两行。
- README「切片留痕与临时 worktree 回收」一条同步。

## Risks / Trade-offs

- [归属证据缺失：门禁绿且没有飞行记录改动的临时 worktree，D2 认不出] → 这类本就是已落地的，合回时的 `_reap` 已收；漏网的由 `/clean-after-merged` 的 landed 判据兜底。
- [作废尝试的目录被删后，人想现场查看] → attic ref 可随时 `git worktree add` 找回；ref 保留到该 change 落地。
- [收口时仍有执行体在跑（例如人在飞行中途手动收口）] → 锁定的跳过。未锁定却在跑的，其 worktree 的提交和改动都会先归档，不丢内容，但执行体会失去工作目录。opsx-apply 只在工作流返回后才进入收口。
- [landed 判据遍历分支有开销] → 一次 `for-each-ref --contains` 加按分支缓存的 first-parent 列表，规模与分支数线性。
- [游离 HEAD 的作废尝试在 merged-cleanup 里进 manual] → 符合「判不准往保守落」；收口时的 `reap` 已经先归档，正常飞行不会留下这类。

## Migration Plan

1. 本 change 落地后，本仓库与下游 `install.sh --upgrade` 即生效。之后每次飞行收口都会自动回收。
2. 存量：
   - A 类（已在 change 分支里、只脏在飞行记录），由用户执行 `/tmp/worktree-cleanup-{afa,stc}.sh`（只读核对后生成，带 HEAD 复核，不带 `--force`）。
   - 其余在升级后运行 `/clean-after-merged`：landed 与有分支的 dead-attempt 进 safe，游离的进 manual。
3. 回滚：revert 本 change。attic ref 无副作用，可留可删。

## Open Questions

- 无阻断项。ADR 步骤会新立 `DRAFT-flight-close-reaps-slice-worktrees`，只取代 `DRAFT-slice-worktrees-reaped-after-merge` 的「merge 之外的脚本不得删除 worktree」与「不覆盖存量 / 未交回 / blocked」两条，决策 1–6 在役；与 `DRAFT-post-merge-cleanup-by-tiered-script` 是扩展关系（新增判据，三档语义不变），不取代。
