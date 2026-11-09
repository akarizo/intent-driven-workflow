## Context

**合并后清理**：现状只有 `openspec-git-discipline` 的两句话。
- 「清理只在主仓库根：`worktree remove` → `branch -d` → `worktree list`」；
- 飞行临时 worktree「有残留时由人确认内容已由 integrator `record` 写回后手动 remove」。

判断全靠人和模型临场完成。2026-11-09 的实测和玩具仓实验暴露了四处 git 行为。它们都不直观，判错的后果要么是命令失败，要么是丢数据：

| git 行为 | 依据 | 判错的后果 |
|---|---|---|
| `branch -d` 有 upstream 且能解析时按 upstream 判，否则按 HEAD 判 | `git help branch`；实测 6 个分支无 upstream、本地 main 落后时报 `not fully merged` | 命令失败；或者被诱导改用 `-D` |
| squash 合并后分支 tip 不是 target 的祖先，`-d` 永远失败 | git 语义 | 被诱导盲目使用 `-D` |
| 不加 `--force` 时，`worktree remove` 拒绝删除含已填充子仓或有未提交改动的 worktree | `git help worktree`；实测报 `working trees containing submodules cannot be moved or removed` | 命令失败 |
| linked worktree 里初始化的子仓，仓库本体在 `<主仓>/.git/worktrees/<id>/modules/<P>`；`--force` 删除时连同它一起删 | 2026-11-09 玩具仓实测：未推送的子仓提交在主 checkout 子仓和子仓远端都不存在 | **静默丢失子仓提交** |

**知识沉淀**：
- `/claudemd-commit` 有准入四问、§12b 分流、预算中性，但 step 6 要逐类用 AskUserQuestion 确认。
- `/pr-ship` 全程不问询，测试断言全文不含 `AskUserQuestion`。
- 两者只能靠人记得先后跑。
- C 类「本轮发现的工程偏差」2026-08-25 被废除，理由是它是增长引擎里唯一的无界项。

用户决策（2026-11-09，AskUserQuestion）：
- **知识沉淀**：`/claudemd-commit` 改为自动识别与录入，只有与已有认知有较大差异的条目才对齐。
- **反复错误**：有上限地恢复。
- **清理**：安全档自动执行，铁律 6 加授权例外。
- **组织方式**：一个 change 分三片。

在役 ADR 中相关的是 `DRAFT-memory-as-fifth-resident-carrier` 原则 4：「准入判断由人守，lint 不得裁决」。本设计不让 lint 裁决。人的审核点从逐条问答移到「较大差异对齐 + PR review」，见 Open Questions。

```
C4 · 容器图（本 change 触及的部分；★ 为新增，◆ 为修改）

 [人类] ──/clean-after-merged──▶ ★clean-after-merged.md ──plan/apply──▶ ★merged-cleanup.py
   ▲                                    │                                   │ git（只读判定 + safe 档执行）
   │ manual 命令清单                    │                                   ▼
   └────────────────────────────────────┘          [主仓 .git：worktrees/ · refs/heads · refs/remotes · refs/flight
                                                     · worktrees/<id>/modules（子仓本体）]  [linked worktree / 借出的子仓 worktree]

 [人类] ──/pr-ship──▶ ◆pr-ship.md step 2b ──自动模式──▶ ◆claudemd-commit.md ──写──▶ CLAUDE.md · rules · skill · memory · backlog
                          │                                   │
                          │ 飞行模式：重跑 slice-gate.py final │ 较大差异：不落盘
                          ▼                                   ▼
                      ship 裁决                       PR 正文「记忆层：需与你对齐」──▶ [人类 PR review]

 铁律文本：◆根 CLAUDE.md · ◆template/CLAUDE.md.snippet（铁律 6 例外）· ◆openspec-git-discipline（清理条款）
```

## Goals / Non-Goals

**Goals:**
- 每个 worktree、`worktree-*` 分支、远端分支和飞行快照 ref，都由脚本给出合并状态、是否需要 `--force`、档位和确切命令。模型不临场判断。
- `safe` 档在显式调用 `/clean-after-merged` 时自动执行。`manual` 档只输出命令，模型永不执行。
- 复现 2026-11-09 的失败场景（无 upstream、本地 target 落后）后，`apply` 一次清理干净。
- 子仓提交只存在于将被删除的子仓库时，永不进入 `safe` 档。
- `/pr-ship` 不问询地完成知识沉淀。只有较大差异的条目留给人类在 PR review 时裁决。
- 反复出现、且有证据的错误能进入载体体系，并且有上限。

**Non-Goals:**
- 不调用 `gh` / `glab` 查询 PR 状态。合并判定纯 git，平台中立，可离线。
- 不推送子仓，也不替用户 `push --delete`、`branch -D`、`worktree unlock`。
- 不清理 `worktree-*` 以外的本地分支（其他分支的用途未知）。
- 不做归档（`/opsx-archive` 另行触发）。
- 不机械抽取「反复错误」的证据。证据来源已经是结构化文件，由模型阅读；见 Open Questions。
- 不改 `claudemd-lint` / `memory-lint`。

## Decisions

### D1 · 判定放脚本，`plan` 只读、`apply` 只执行 `safe` 档（铁律 9）

`template/.claude/hooks/merged-cleanup.py` 有两个子命令，均只能在主 worktree 运行：
- **`plan [--target T] [--remote R] [--fetch] [--markdown]`**：默认不联网。输出 JSON，或带 `--markdown` 时输出 markdown。
- **`apply [--target T] [--remote R] [--no-fetch]`**：默认先 `fetch --prune`，再计算 plan，然后按 D6 的顺序执行 `safe` 档。

```
plan JSON：{ok, target, target_ref, sync, items:[{kind, name, merged, tier, force, reasons, dirty, command}], manual:[cmd], warnings:[...]}
  kind   ∈ worktree | branch | remote | ref
  merged ∈ ancestor | content | fresh | unmerged | landed | -
  tier   ∈ safe | manual | keep
  reasons 每条以稳定标记开头：flight-records / submodule / unpushed-submodule / dirty / locked / outside / prunable / content / reference / fresh / unmerged
apply JSON：{ok, done:[cmd], failed:[{command, error}], manual:[cmd], kept:[name]}
退出码：0 = 无失败；1 = apply 有失败项；2 = 拒绝运行（不在主 worktree / 不是 git 仓库），stdout 仍为 {ok:false, reasons}
```

- **备选**：由模型按文档逐条判断。否决：这正是 2026-11-09 失败的根源，四处 git 行为都不直观。
- **备选**：只出 plan，执行全部交人。否决：用户选了安全档自动执行。

### D2 · 合并状态四分，纯 git

依次判定以下四种状态，判定依据是 `target_ref`。有 `refs/remotes/<R>/<T>` 时用它，否则用 `refs/heads/<T>`。

1. **`fresh`**：tip 在 `git rev-list --first-parent <target_ref>` 上，即没有独有提交，可能是刚建的分支，也可能是 ff 或 rebase 合并 → `keep`。
   - 理由：刚为新工作建的 worktree 的 tip 就是 target 的 tip，也是 target 的祖先。不加这一判就会被当成已合并删掉。
   - 代价：ff 或 rebase 合并的分支保守地被保留。
2. **`ancestor`**：`merge-base --is-ancestor tip <target_ref>`。merge-commit 方式合并的 PR，其 head 是合并提交的第二父，不在主线上。
3. **`content`**：不是祖先，但 `merge-tree --write-tree <target_ref> tip` 退出 0，且树等于 `<target_ref>^{tree}`。也就是把它合进 target 不会改变任何东西，覆盖 squash 与 cherry-pick 两种情况。
4. **`unmerged`**：其余情况 → `keep`。

- **备选**：`gh pr list --state merged --head`。否决：平台相关，需要网络，GitLab 还要另写一份。
- **备选**：`git cherry` 比对 patch-id。否决：squash 后的单个提交与原分支逐个提交的 patch 对不上。
- **已知假阴性**：squash 之后 target 又改了同一处，`merge-tree` 会冲突或产出不同的树 → `unmerged`，保守保留。

### D3 · `branch -d` 的可行性按 git 自身规则推算；target 落后先 `--ff-only` 同步

- **参照点**：分支有 upstream 且能解析时用 upstream；否则用「有效 HEAD」。这是 git 自身的规则，见 `builtin/branch.c` 的 `branch_merged`。
- **有效 HEAD**：计划了同步时取 `target_ref` 的 SHA，否则取 HEAD。
- **同步条件**：主 worktree 的当前分支就是 `T`，HEAD ≠ `target_ref`，HEAD 是 `target_ref` 的祖先，且没有已跟踪文件的改动。子仓检出漂移不计入改动：`--ff-only` 不碰子仓工作树，而主 checkout 的子仓落后于 gitlink 是常态。满足时 `sync = {from, to, command: "git merge --ff-only <R>/<T>"}`，属于 `safe` 档。
- **不满足时**：写进 `warnings`，例如「当前不在 T」或「T 与 <R>/<T> 分叉」，不同步。

`ancestor` 状态的分支按参照点分三种情况：
- 是参照点的祖先 → `safe` 档 `git branch -d`；
- 是 target 的祖先但不是参照点的祖先 → `manual` 档 `git branch -D`，原因标 `reference`；
- `content` 状态 → `manual` 档 `git branch -D`，原因标 `content`，并附 merge-tree 证据。

全局规则禁止模型执行 `-D`，所以凡需要 `-D` 的都落 `manual`。

### D4 · 是否需要 `--force` 及档位（worktree）

先排除主 worktree，再按下表判定：

| 条件 | merged | tier | force | reason 标记 |
|---|---|---|---|---|
| 目录已不存在（porcelain 的 `prunable`） | - | safe（`git worktree prune`） | — | prunable |
| tip 为 fresh / unmerged | fresh / unmerged | keep | — | fresh / unmerged |
| 被 lock | * | manual（`git worktree unlock P && git worktree remove …`） | 视下行 | locked: <原因> |
| 路径不在 `<root>/.worktrees/`、`<root>/.claude/worktrees/` 之下 | * | manual | 视下行 | outside |
| 未提交改动全是飞行记录 | ancestor / content | safe | ✓ | flight-records: <文件> |
| 有其他未提交改动（含子仓 gitlink 本身显示为改动） | ancestor / content | manual | ✓ | dirty: <文件> |
| 有已填充的子仓，且子仓提交都能存活（D5） | ancestor / content | safe | ✓ | submodule: <P> |
| 有已填充的子仓，且某个子仓提交不能存活 | ancestor / content | manual | ✓ | unpushed-submodule: <P> <sha> |
| 干净 | ancestor / content | safe | ✗ | — |

- **未提交改动的列法**：`git -C W status --porcelain=v1 -z --ignore-submodules=none --untracked-files=all`。这与 git 自身的干净检查口径一致，只是展开到单个文件。
- **飞行记录白名单**：
  - 根目录的 `.openspec-slice`；
  - 任意前缀下 `openspec/changes/<c>/` 的 `timeline.md`、`gate-report.md`、`evidence.log`。
- **白名单为什么可以丢**：只有 tip 已合并时才进入 safe 档。这时 change 分支上由 integrator `record` 写回的版本已经随 PR 落地，临时 worktree 里那份是过程中的残片。

### D5 · 子仓提交存活校验

对 worktree W 中每个已填充的子仓 P（`ls-files -s` 的 160000 项，且 `W/P/.git` 存在）：

- **判定子仓库是否随 W 一起删除**：取 `common = git -C W/P rev-parse --path-format=absolute --git-common-dir`。common 落在 W 自己的 gitdir 之下，或落在 W 路径之下 → 这个子仓库会随 W 一起被删。
- **会被删除时**：取子仓 HEAD、`refs/heads/*`、`refs/flight-sub/*` 的每个 tip。每个 tip 必须满足下面任一条件：
  - 存在于主 checkout 的子仓（`git -C <root>/P cat-file -e <sha>^{commit}`）；
  - 能从该子仓的 `refs/remotes/*` 到达。

  任一不满足 → `unpushed-submodule`，落 `manual`，文案写「先推送子仓（或在主 checkout 里 fetch 它）」。
- **不会被删除时**（借出的 linked worktree，例如 submodule-aware-flight 的 `start` / `sub-sync`）：子仓库本体在家子仓里，不会被删 → 记入 `prune_subs`。W 删除后执行 `git --git-dir=<common> worktree prune`，清掉家子仓里残留的 worktree 元数据。

`refs/flight-sub/<change>/*` 锚点不单独处理：它们位于家子仓库里，随家 worktree 一起存废，由本条的存活校验兜住。

### D6 · `apply` 执行顺序

```
fetch --prune（--no-fetch 跳过；失败记 failed，继续离线判定）
 → 计算 plan → sync（git merge --ff-only）→ 重算 plan
 → 删除 safe 档 worktree：先 .claude/worktrees/ 下的，再 .worktrees/ 下的（借出子仓的临时 worktree 先删，家 worktree 后删）
   每删一个，对它的 prune_subs 跑 git --git-dir=<c> worktree prune
 → git worktree prune
 → 删除 safe 档 ref（update-ref -d）
 → 删除 safe 档分支（branch -d）
```

- **失败时**：单项失败不中断，后续项照常执行，失败项收进 `failed`。
- **命令的两种形式**：执行时用参数列表，不经 shell；`command` 字段是给人看的 shlex 引号形式。
- **分支跟随 worktree 档位**：分支若被某个 worktree 检出，就跟随该 worktree 的档位。worktree 为 keep → 分支 keep；为 manual → 分支 manual，排在该 worktree 命令之后。原因是 git 拒绝 `-d` 一个正被检出的分支。

### D7 · 已落地 change 的飞行快照 ref

`refs/flight/<change>/*` 是 `slice-gate.py checkpoint` 留下的半成品快照。主仓实测残留 1 个：`refs/flight/incremental-final/*`。

- **landed 判据**：`git ls-tree -r --name-only <target_ref>` 中有路径匹配 `(^|/)openspec/changes/<change>/`。
- **处理**：landed → `safe` 档 `git update-ref -d <ref>`；未落地的不列出。

### D8 · 范围与授权

- **范围**：
  - 所有 linked worktree；
  - 本地 `refs/heads/worktree-*`，排除当前分支；
  - 远端 `refs/remotes/<R>/worktree-*` 中已合并的，一律 `manual` 档 `git push <R> --delete <b>`；
  - landed change 的 `refs/flight/*`。
- **授权**：铁律 6（根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`）加例外：显式运行 `/clean-after-merged` = 授权其文档内的 `safe` 档。`branch -D`、`push --delete`、`manual` 档的 worktree 删除永远交人。
- **git-discipline 同步**：
  - 「破坏性收尾一律交用户授权」改为「…除显式运行 `/clean-after-merged` 的 safe 档外」；
  - 两处「手动 remove」改为指向该命令。
- **运行位置**：脚本拒绝在 linked worktree 里运行（exit 2）。这是「清理只在主仓库根」的机械化。

### D9 · `/clean-after-merged` 命令与回退（铁律 10）

步骤：
1. 定位主 worktree 根：`git rev-parse --path-format=absolute --git-common-dir` 的父目录。
2. `plan --markdown`，展示结果。
3. `apply`，执行 safe 档。
4. 打印 `done` / `failed`，以及原样的 `manual` 命令块。
5. `git worktree list` 验证。

**回退**：脚本不存在或异常退出时，只做两件安全的事：
- `git fetch --prune`；
- 在 T 上 `git merge --ff-only <R>/<T>`。

然后输出 `git worktree list --porcelain` 与 `git branch --list 'worktree-*'`，附一份带判据的人工清单交用户逐条执行，不再自动删除任何东西。人工清单的判据是：先同步 T 再 `-d`；含子仓的 worktree 先确认子仓提交已推送。

### D10 · `/claudemd-commit`：自动录入，较大差异才对齐

把 step 6「与用户逐类确认」改为「自动录入 + 差异对齐」。

**较大差异**命中以下任一条：
- ① 删除或反转既有条目的含义，包括 B 类和为预算而删掉知识的减法；
- ② 与既有条目或在役 ADR 同题异令；
- ③ 改动铁律或「核心约束」段；
- ④ 写到仓库外的全局 `~/.claude/CLAUDE.md`。

处理方式：
- **较大差异**：单独跑 `/claudemd-commit` 时用 AskUserQuestion 逐条对齐；被 `/pr-ship` 调用时不落盘，返回给调用方列进 PR 正文。
- **其余条目**，包括通过四问与预算闸的 A / D / E 类新增，以及不丢含义的迁移（指针化、分流到 rules / skill）：直接写入，并在报告里逐条列出。

- **备选**：维持逐条确认。否决：用户明确要求自动录入。
- **备选**：全部自动、不对齐。否决：用户保留「较大差异需对齐」。

### D11 · E 类「反复错误」：有上限地恢复

**准入**（必须同时满足）：
- 同一错误在本轮至少出现 2 次；
- 每次都有证据指针，可以是以下任一：
  - `gate-report.md` / `timeline.md` 的门禁红记录；
  - `review-findings.json` 中的 `blocked` / `fixed` 条目；
  - fix commit 的 SHA；
  - 本会话里用户的原话纠正。

只出现 1 次，或给不出证据 → 照旧进 backlog。

**载体**：仍要过准入四问和预算中性。
- Q4 ✓（能写成测试、lint 或 hook）→ 进 backlog，立项实现这道机械防线。常驻层只留一行带 backlog 指针的过渡条目。防线落地后，下一轮 B 类把这行改成「防线索引」。
- Q4 ✗ → 按 §12b 分流表定载体。

**与 C 类的区别**：C 类让模型主动「发明」观察，规模没有上界。E 类的规模受「本轮实际发生、且至少 2 次留了证据」约束。C 类维持废除。

### D12 · `/pr-ship` step 2b「记忆层沉淀」

**位置**：step 2（梳理范围）之后、step 3（commit）之前。编号用 2b，不重排后续步骤，既有测试按步骤号切片。

**流程**：
1. 按 `/claudemd-commit` 的自动模式运行，base = `origin/<target>`。
2. 巡视三处来源：
   - 本会话对话，包括 compact 摘要。用户给过的规则、纠正、偏好归 D 类，纠正同时是 E 类的证据。
   - 分支 diff，归 A / B 类。
   - 飞行记录与评审：`timeline.md`、`gate-report.md`、`review-findings.json`、`git log` 中的 `fix:` commit，作为 E 类的证据。
3. 产出写成独立 commit `docs(memory): 沉淀本轮知识（+N / −M）`。`claudemd-lint` 与 `memory-lint` 须全绿；红了就当场减，减完再提交。
4. **飞行模式**下，沉淀 commit 之后重跑 `slice-gate.py final`。`_final_fresh` 只容忍 final 之后出现记账文件，CLAUDE.md 不在其列，不重跑会让 ship 判「final 过期」。
5. 修改 PR 正文与收尾输出：
   - 正文追加「## 记忆层沉淀」，逐条写载体、路径、动作和一行证据；
   - 正文追加「## 记忆层：需与你对齐」，列出较大差异条目；
   - Output Summary 加一行沉淀统计；
   - step 11 提示合并后在主仓根运行 `/clean-after-merged`。

`pr-ship.md` 全文仍不出现 `AskUserQuestion`，Guardrails 仍写「全程不问询」。

## Risks / Trade-offs

- [风险] `merge-tree` 假阴性（squash 后 target 又改同一处）→ 判 `unmerged` 保留，宁漏删不误删。
- [风险] 飞行记录白名单丢掉了未写回的残片 → 只在 tip 已合并时适用。change 分支上的权威版本已随 PR 落地。白名单只含 3 个记账文件和标记文件，不含源码。
- [风险] 正在运行的 agent 的 worktree 被删 → 运行中工作的 tip 不在 target 里，判 `unmerged` / `fresh` 保留；被 lock 的进 `manual`。⚠ Claude Code 是否 lock 隔离 worktree 未实测，所以不依赖 lock 作为唯一防线。
- [风险] 子仓存活校验漏掉了某个只在子仓 reflog 或 stash 里的提交 → 校验覆盖 HEAD、`refs/heads`、`refs/flight-sub`。reflog 与 stash 不在合同内，文档写明「子仓 stash 不受保护」。
- [风险] 自动录入让 CLAUDE.md 混入低质条目 → 准入四问、预算中性、lint 全绿照旧，较大差异要对齐，最后还有 PR review 兜底。沉淀写成独立 commit，可以整体 revert。
- [风险] E 类仍可能膨胀 → 上界是证据数。能机械化的条目会被引导去写防线，常驻层只留一行。
- [取舍] `fresh` 判定会保守地保留 ff 或 rebase 合并的分支 → plan 表格里写明原因，用户可手动处理。

## Migration Plan

- **安装**：纯新增加文档修改，无数据迁移。已安装模板的仓库重新运行 `install.sh` 即获得新命令和脚本，`install.sh` 的命令计数改为 17。
- **回滚**：revert 本 change 的合并提交。脚本不持久化任何状态，已删除的 worktree 和分支不可回滚，这也是 `safe` 档判据从严的原因。
- **自举**：本仓库本身就是使用者。合并后在主仓根跑一次 `/clean-after-merged`，作为实地验收。

## Open Questions

- **原则 4 是否需要 supersede**：在役 ADR `DRAFT-memory-as-fifth-resident-carrier` 原则 4 写「准入判断由人守，lint 不得裁决」。本设计不让 lint 裁决，所以不违背它的字面。人的审核点从逐条问答移到较大差异对齐和 PR review。判断是补充而非推翻，因此不 supersede，由新 ADR `DRAFT-memory-sedimentation-auto-with-divergence-alignment` 记录。审批时若认为这属于推翻，应改为 supersede。
- **E 类证据的机械抽取**：可以从 `gate-report.md` 按 G 编号聚合红记录，从 `review-findings.json` 聚合 `blocked` / `fixed`，做成零 token 的抽取器。本 change 不做；连续 2 个 change 出现模型漏报或错报 E 类时再立项。
- **Claude Code 是否 lock 隔离 worktree**：未实测。D4 不依赖它；可以在下一次飞行时顺带观察。
