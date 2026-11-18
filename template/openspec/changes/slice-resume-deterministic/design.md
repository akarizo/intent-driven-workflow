## Context

飞行模式里，一个切片可能跑不止一轮：门禁红重派一次，执行体未交回重派一次，人类修完计划后还会再起飞。「下一轮接着上一轮干」现在由四段各管一截：

| 环节 | 现状（main `1dabeac`） | 出过的事 |
|---|---|---|
| 接上一轮的提交 | 工作流 prompt 的「第零步」：HEAD 不是上一轮 commit 就 `git cherry-pick <commit>`（`opsx-apply.js` `executorPrompt`） | 上一轮两个提交只接到后一个（F2） |
| 区间起点 | `start --base <上一轮门禁 JSON 的 base>`，脚本照单全收（`cmd_start`） | 分支在两轮之间多了记录提交，旧起点把它们算进切片，报 `G6 flight-record`（F3） |
| 轮次上限 | `slice-executor.md` frontmatter `maxTurns: 40`，常数 | 20 个文件、91 个文件的切片各撞四次、两次（F1） |
| 临时 worktree 的善后 | 留痕写在临时 worktree 的 change 目录；合回后 worktree 留在磁盘 | 分支上没有切片留痕；磁盘占满（F11） |

约束：

- Workflow 脚本的 `agent()` 没有轮次参数（只有 label / phase / schema / model / effort / isolation / agentType），上限只能来自 agent 定义文件的 frontmatter。
- 自举飞行（`useAgentTypes: false`）时执行体是默认 subagent，先读定义文件再干活，frontmatter 的 `maxTurns` 不生效。本仓自己的飞行因此没有轮次上限，这一点本 change 不改。
- 现行 ADR：`DRAFT-measurements-stay-out-of-plan-files`（脚本不写计划文件）、`DRAFT-gate-evidence-not-self-reported`（判据不由被门禁方提供）、`DRAFT-post-merge-cleanup-by-tiered-script`（铁律 6 的例外要成文，新增本地状态要登记清理规则或写明保留）、`DRAFT-submodule-slices-borrow-home-worktree`（临时 worktree 的子仓是从 change 家借出的 linked worktree）。

### 调查一：afa「每片都报无 evidence.log」的直接原因

**结论：已定位，是两个独立的缺口，都在模板里。**

1. **hook 只按命令文本里的运行器名字认测试运行**（`test-evidence.py` 的 `TEST_RE`）。afa 的切片用包装脚本跑测试，例如 `bash openspec/changes/key-features-keyft/verify/viewer.sh test …`，文本里没有 `pytest` / `vitest`，一行都不记。临时 worktree 是新开的，change 目录里本来就没有 `evidence.log`，于是门禁判 `missing_file`，文案却是「hook 未安装或未触发」。
   - 证据：工作流 `wf_503174f4-e61` 里 S6（`agent-ac1cb82c…`）、S9（`agent-afd1b247…`）命中运行器正则的命令数为 0，门禁报「无 evidence.log」；同一次工作流的 S5（`agent-a43e209a…`）有 3 条命中，报的是「未见 RED 先于 GREEN」，说明 hook 在临时 worktree 里是工作的。
   - 交接文档写「每片都报」不准确：是「命令没被认出来的那些片」和「重派轮一上来就跑门禁的那些片」（如 `wf_f0857049-1f4` 的 `agent-af97276d…`，门禁之前没有任何测试命令）。
   - 量：回放 1124 个执行体，231 个一条都没命中；其中 123 个其实跑过本片 `verify` 或 `gate.test` 里写的脚本（`calibration/replay-turns-20261118.txt` 末行）。
2. **临时 worktree 里的留痕没有回分支的路**。执行体不得提交 `evidence.log`（`G6 flight-record`），integrator 第 0 项只提交 change 家工作树里的那份。结果：afa `key-features-keyft` 的 change worktree 里那份 `evidence.log`（未入库）共 49 行，切片列全是 `-`（propose 期主会话留下的），九个已合回的切片一行都没有；本仓 `template/openspec/changes/*/` 下根本没有 `evidence.log`。而评审员的 prompt 写着「evidence：`<change>/evidence.log`（本切片的测试运行留痕，可 grep）」。

对照：afa 另一次飞行 `remove-pixi-remnants`（`wf_ecccf8fe-b5a`）的临时 worktree 里有 `evidence.log` 且带切片行，因为那里的命令叫 `verify/pytest-group.sh`，文本里恰好有 `pytest`。

### 调查二：轮次档位的依据

脚本 `calibration/replay-turns.py` 回放本机 `~/.claude/projects/*/*/subagents/workflows/*/agent-*.jsonl`，结果存 `calibration/replay-turns-20261118.txt`。

- **样本**：6 个仓库、186 个 change、1124 个切片执行体；能对上计划的首轮 890 个，其中 821 个带 40 轮上限（`agentType` 为 `slice-executor`），69 个没有上限（默认 subagent）。
- **用什么量**：计划提交时 owns 展开的现存文件数最能区分；scenario 数几乎不带信息（单看它，0–4 条与 9–12 条的撞限率是 9% 对 14%），加进去只会把阈值搅浑。
- **阈值**（带上限的 821 个首轮，「命中」= 轮数 ≥40 或未交回）：

  | 现存文件数 > | 划进大片档的占比 | 大片档命中率 | 标准档命中率 |
  |---|---|---|---|
  | 6 | 32% | 24.9% | 4.1% |
  | **8** | **23%** | **28.4%** | **5.5%** |
  | 10 | 17% | 34.5% | 6.0% |
  | 12 | 10% | 40.7% | 7.3% |

  取 8：不到四分之一的切片进大片档，却覆盖了多数撞限；标准档里剩下的约 5% 与规模关系不大（0–4 个文件的 468 片里也有 11 片撞 40 轮），靠续跑兜。
- **大片档的上限**：没有上限的 69 个首轮全部交回，最大 58 轮，规模靠上的几组 P90 在 52–55。取 **80**（观察到的最大值的 1.4 倍）。方案页草案写的 120 没有数据支撑。
- **样本的局限**：没有上限的样本里，文件数加 scenario 数超过 16 的只有 6 个；80 是草案，等大片档上线后用它自己的撞限样本复核。
- **「超大」阈值定不出来**：全部首轮里，现存文件数 13–20、21–40、41 以上三组撞 40 轮的比例是 42%（10/24）、40%（6/15）、42%（22/52），没有随规模继续上升（很多是宽通配的机械迁移，1087 个文件的一片 19 轮做完）；没有上限的样本无一未交回。现有数据给不出「大到必须拆」的线。

## Goals / Non-Goals

**Goals:**

- 重派与续跑时，上一轮的全部提交由脚本接上；接不上时脚本自己回滚并给出 `G0` JSON。
- 门禁区间的起点不依赖 prompt 回传的值。
- 轮次上限随切片大小分档，档位由脚本算，人类在审批页看得到。
- 撞上限后的 blocked 理由能直接指导下一步。
- 切片的测试留痕在门禁时读得到（不论是哪一轮、哪间 worktree 留下的），合回后在分支上读得到。
- 合回后临时 worktree 不再堆积。

**Non-Goals:**

- 不取消轮次上限，不做每片一个自定义数字（定义文件只有两份）。
- 不加「超大切片判红」（见调查二，定不出阈值）。
- 不改自举模式下执行体没有轮次上限这一点。
- 不做「重新起飞时首轮自动接上一次飞行的快照」：首轮 `start` 仍会清掉旧快照（防止把废弃尝试的半成品带进来）。blocked 理由如实写明这一点。
- 不回收未交回执行体留下的、带未提交改动的临时 worktree（删它要强制参数）。
- fix 执行体仍用标准档。
- 不动 `gate` 的 `--base` 参数、不动 `final` / `ship` / 选测（那是 `ship-rerun-hardening` 的范围）。

## Decisions

### D1 接续是 `start` 的一个参数，不是 prompt 里的 git 步骤

`start <S> --continue <commit>`，在基点校验之后、子仓填充之前执行：

1. `<commit>` 不在对象库 → `G0 base: 接续的 commit … 不存在`，退出 1。
2. `<commit>` 已是 HEAD 的祖先 → 什么都不做（`mode: noop`）。
3. HEAD 是 `<commit>` 的祖先 → `git merge --ff-only <commit>`（`mode: ff`）。
4. 否则取 `git rev-list --reverse <commit> --not HEAD`，即上一轮（及更早各轮）属于本片、当前 HEAD 还没有的提交，逐个 `git cherry-pick`（`mode: pick`）。区间里有合并提交 → `G0 base`，不重放。任何一步冲突 → `git cherry-pick --abort` 并 `git reset --keep <接续前的 HEAD>`，输出 `G0 base: 接续 <commit> 冲突：<文件>`，退出 1，不写标记。

`start` 的输出多一个 `continued: {"from", "mode", "applied"}`。放在子仓填充之前，是为了让 `_sub_sync` 直接按接续后的 gitlink 借出子仓（与今天「先 cherry-pick 再 start」的顺序等价，`tests/test_submodule_sync.py` 已有这条路径的用例）。

`--continue` 与 `--resume-checkpoint` 可以同时给吗：不需要。前者用于「上一轮交回了门禁 JSON（有 commit）」，后者用于「上一轮没交回（没有 commit）」；工作流不会同时给，argparse 不做互斥限制，同时给时先接续再恢复快照。

否决：

- **保留 prompt 的第零步，只把单个 commit 改成区间**：区间起点还得由 prompt 给，正是 F3 的病根；冲突处理仍靠模型照做。
- **新 worktree 里 `git reset --keep <commit>`**：分支在两轮之间前进时会把分支的新提交丢掉，过不了基点校验。

### D2 区间起点 = HEAD 与 change 分支的合并基点

带 `--expect-branch <B>` 时，标记里的 `base` 恒为 `git merge-base HEAD <B>`（接续之后算）。基点校验已保证 HEAD 是 B 最新提交的后代，所以它就是 B 的最新提交；门禁区间 `base..HEAD` 天然只有本片的提交。同时给了 `--base` 且与算出的不同 → 以算出的为准（旧工作流脚本仍会传 `--base`，要能照常跑）。

不带 `--expect-branch`（`--gate=per-task` 回退路径、手工调用）时行为不变：`--base` 生效，缺省为 HEAD。同片标记已存在时标记原样保留（现状，`start` 对同片幂等）。

### D3 档位由脚本算，计划只能升不能降

- **量**：owns 展开后的现存文件数，在 `gate-baseline.json` 记录的 `commit` 的树上数（`git ls-tree -r`）；没有基线或该 commit 取不到时在 HEAD 上数。owns 落在子仓里的条目，按那棵树记录的 gitlink 到子仓对象库里数，取不到按 0。只数已提交的文件。
- **规则**：超过 8 个 → `large`，否则 `standard`。常量 `TURN_LARGE_FILES = 8`。
- **计划字段**：切片可选 `"turns": "large"`，把按规模是标准档的片升到大片档（小而难的片）。写 `"standard"` 而规模是大片档 → lint 红；其他取值 → lint 红。不写就是按规模。
- **输出**：新子命令 `slice-gate.py turns --change-dir DIR` 打印 `{"S1": "standard", "S2": "large", …}`，退出 0；计划不合法时与 lint 一样退出 2。`lint` / `waves` / `preflight` 的 stdout 形状不变（仍是 waves 数组）。

为什么在基线 commit 上数：飞行中实现会往 owns 里加文件，在 HEAD 上数的话，同一片在起飞时是标准档、续飞时变成大片档，计划没变结论却变了。基线 commit 在一次飞行里是固定的；中途补 owns 会改计划、本来就要重新批准。

否决「lint 把档位写进 `slices.json`」（方案页的草案）：`DRAFT-measurements-stay-out-of-plan-files` 刚定下脚本不写计划文件，写了会让批准过期；把字段设成必填则所有在途计划都会红。

### D4 工作流按档位选定义文件

- `/opsx-apply` 起飞前运行 `slice-gate.py turns`，把输出原样作为 `args.turns` 传给工作流；没传时全部按标准档。
- 工作流：`large` 的片派 `agentType: slice-executor-large`，其余 `slice-executor`；首轮与重派同档。`useAgentTypes: false` 时让默认 subagent 读对应的定义文件。
- `slice-executor-large.md`：frontmatter 与 `slice-executor.md` 相同，只有 `name` 与 `maxTurns: 80` 不同；正文一句话——先读 `slice-executor.md` 并照它执行，轮次上限以本文件为准。纪律只有一份，不复制。
- `slice-executor.md` 的预算条改为「上限见 frontmatter（标准档 40；大片档由 `slice-executor-large.md` 给 80）」。
- 两个上限数字在工作流脚本里各出现一次（用于 D5 的理由文案），由测试对账：脚本里的数字必须等于两份定义文件的 `maxTurns`。
- 按 agent 类型名判定的两处同步认新类型：`takeoff-gate.py` 的 `TAKEOFF_AGENTS`（否则回退路径用 Agent 工具派 `slice-executor-large` 时不经起飞门禁，铁律 7 出缺口）、`session-decompose.py` 的 `AGENT_ROLE`（模型对账把它记为 executor）。

### D5 未交回的 blocked 理由

工作流脚本拼不出「实际跑了多少轮」（它不碰文件系统），能确定的有：档位与该档上限、本次飞行内重派过一次、快照 ref 的名字（`refs/flight/<change>/<S>`，与 `_ckpt_ref` 同规则）。理由文案：

`执行体未返回（已重派一次）：<标准档|大片档>上限 <N> 轮；半成品快照在 refs/flight/<change>/<S>，重新起飞的首轮会清掉它，要保留先在新 worktree 里 start <S> --resume-checkpoint`

保留「未返回」「已重派」两个词（既有测试与 `/pr-ship` 文案在用）。

### D6 切片留痕写 git 共用目录

- **位置**：`<git common dir>/flight-evidence/<change>/<S>.log`，一片一个文件，行格式不变（`时间\t切片\tPASS|FAIL\t命令前 120 字符`）。`<change>` 取标记里 `change_dir` 的目录名（与快照 ref 同规则）。
- **hook（`test-evidence.py`）**：工作树根有切片标记时——
  - 任何 Bash 事件都确保该文件存在（空文件即心跳）；
  - 命令被认作测试运行时追加一行。认定 = 原有的运行器正则，**或** 命令执行位置上的脚本路径记号与本片 `verify` 或 `gate.test` 执行位置上的记号相同（按 `;` `&&` `||` `|` `&` 换行与括号切段；执行位置 = 段首词，或紧跟 `bash`/`sh`/`zsh`/`python`/`python3`/`node`/`npx`/`tsx` 的那个词；含 `/` 且以 `.sh` / `.py` / `.js` / `.mjs` / `.ts` 结尾；命中运行器正则的段不出记号。`cat` / `sed` / `git add` 这类只点名文件的命令不算，否则读测试文件就能伪造「先红」）。读不到 `slices.json` 时只用运行器正则。
  - 没有标记时（主会话）行为不变：写工作树里的 `<change>/evidence.log`。
- **门禁（`evidence_state`）**：本片的行 = 分支工作树里 `<change>/evidence.log` 的本片行 + 共用目录里本片文件的行。两处都不存在 → `missing_file`（警告，`hooks_missing: true`，现状）；存在但没有本片的行 → `no_rows`（红，文案改为「hook 在工作，但本片没跑过测试（先运行本片的 verify 再过门禁）」）；其余判定不变。门禁收尾时把共用目录里本片的行并进所在工作树的 `<change>/evidence.log`（去重），`--gate=per-task` 路径下这就是分支上的那份。
- **并回分支（`record`）**：integrator 在 change 家运行 `record --json` 时，把共用目录里该片的行追加进 `<change>/evidence.log`（已有的行不重复加），然后删掉共用目录里该片的文件。并回发生在「已记录过」的早退之前，重复执行是空操作。
- **首轮清残留（`start`）**：不带 `--continue`、不带 `--resume-checkpoint`、也没有同片标记的 `start` 删掉共用目录里该片的文件（上一次飞行的残留不属于本轮）；同时把 `flight-evidence/` 下的 change 目录修剪到最近 30 个（按修改时间）。两种接续都保留。

`no_rows` 判红是现有规则（`tests/test_slice_gate.py::test_gate_g5_fails_when_evidence_has_no_rows_for_slice`），不是新加的严格度；今天它在临时 worktree 里实际不生效，只是因为文件恰好不存在而落进了 `missing_file`。本 change 让它按原意生效，同时用「认脚本路径」和「跨轮保留」把误伤压下去。

否决：

- **门禁自己跑 verify 时也记一行**：那样 `no_rows` 永远不成立，「执行体亲眼看过红」这条留痕就没了。
- **让执行体提交 `evidence.log`**：并行切片合回时必冲突，这正是 `G6 flight-record` 存在的原因。
- **hook 同时写工作树与共用目录**：两份真值，门禁读哪份都要解释。

### D7 合回后回收临时 worktree

`merge` 每成功合回一片 `<S>=<sha>`，取这次合并带进来的提交集合 `git rev-list <sha> --not <合并前的 HEAD>`，对 `git worktree list --porcelain` 里**不是当前 worktree**、且 HEAD 落在该集合里的每一间（被锁住的直接记「未回收：已锁定」，不动它的任何文件）：

1. 列出它的未提交改动，去掉三类：飞行记录（路径形如 `…/changes/<名>/` 下的 `timeline.md` / `gate-report.md` / `evidence.log`）、切片标记 `.openspec-slice`、未跟踪的字节码（`__pycache__` / `.pyc`）。还有剩的 → 不回收，`warnings` 写「未回收 <路径>：有未提交改动 <前几个文件>」。
2. 借出的子仓（gitlink 路径下有 `.git` 的）：子仓 HEAD 必须已是 change 家对应子仓 HEAD 的祖先，且除字节码外没有未提交改动；满足则删掉字节码后在 change 家的子仓里 `git worktree remove <该路径>`。不满足 → 不回收。
3. 丢掉第 1 步列出的三类文件（已跟踪的 `git checkout --`，未跟踪的删除），`git worktree remove <路径>`（不带 `--force`）。
4. 它有自己的分支且分支指向的就是那个 HEAD → `git branch -d <分支>`（不带 `-D`）。
5. 任一步失败 → 停在那一步，`warnings` 写「未回收 <路径>：<git 的首行报错>」。**回收失败不影响 `ok` 与退出码。**

输出在有回收时多一个 `reaped: [路径…]`；没有回收时不出现这个键（`tests/test_submodule_merge.py` 有整体相等的断言）。

「执行后不丢未落地内容」的论证（`DRAFT-post-merge-cleanup-by-tiered-script` 要求新增的自动清理附带）：

- 提交：HEAD 在刚合入的集合里，已是 change 分支的祖先。
- 飞行记录：`timeline.md` / `gate-report.md` 的内容由工作流经 `record --json` 用门禁 JSON 原文重写到分支（`opsx-apply.js` 已如此）；`evidence.log` 的真值在共用目录（D6）。
- 字节码：跑测试的副产物（`is_bytecode` 已是这个口径）。
- 其余任何未提交内容都会让回收放弃。
- 被锁住的 worktree（多半是正在跑的 agent）一开始就跳过，连飞行记录都不动。
- 子仓：只归还 HEAD 已并入 change 家子仓的借出 worktree；在临时 worktree 里初始化出来的真 submodule（仓库本体在 `.git/worktrees/<id>/modules/`）git 不带强制参数不肯删，同样落进第 5 步。

为什么只认「HEAD 在刚合入的集合里」：change 分支的祖先还包括 `main` 和别的 change 的起点，按「是分支祖先」判会误删别人的 worktree。集合判定同时覆盖了同一片上一轮留下的 worktree（它停在本片较早的提交上）。

为什么放在 `merge` 里而不是新子命令：不改 integrator 与工作流的契约，旧工作流脚本也能受益；自举飞行中途合回不会断。

### D8 铁律 6 的措辞

根 `CLAUDE.md`：「不删 worktree」之后加例外——切片临时 worktree 的提交已合回 change 分支、且没有未合回的改动时，由 `slice-gate.py merge` 不带强制参数回收。`template/CLAUDE.md.snippet` 的同一条同步一句短的。两处都保留 `/clean-after-merged` 的例外与 `branch -D` 永远交人。`integrator.md` 的「不删 worktree」不变（回收是脚本做的，integrator 自己仍不删），补一句说明 `merge` 的 `reaped` / 「未回收」警告原样带回。

### D9 落地顺序与兼容

| 组合 | 行为 |
|---|---|
| 旧工作流脚本 + 新 hooks | prompt 仍让执行体 cherry-pick 并传 `--base`；`start` 把起点规范成合并基点，照常跑 |
| 新工作流脚本 + 旧 hooks | `start` 报 `unrecognized arguments: --continue`（退出 2，无 JSON）。重派 prompt 写明这种情况的回退：HEAD 不是该 commit 就 `git cherry-pick <commit>`，再运行不带 `--continue` 的 `start` |
| 新 hook 写共用目录 + 旧门禁 | 门禁在临时 worktree 里读不到文件，报 `missing_file` 警告（与今天多数情况相同），不红 |

本 change 自己的飞行：工作流脚本在起飞时载入，整趟用旧脚本；agent 定义与 hooks 随合回逐步变新。切片依赖按「引用新参数 / 新子命令的片依赖提供它的片」排：改工作流与 agent 定义的 S4 依赖提供 `--continue` 的 S1；改命令文档（引用 `turns` 子命令）的 S6 依赖 S3、S4。

## Risks / Trade-offs

- [与在飞的 `ship-rerun-hardening` 同改 `slice-gate.py` 与 `README.md`] → 它改 `final` / `ship` / 选测复核 / `inert`，本 change 改 `start` / `gate` 的留痕 / `record` / `merge` / lint 的切片循环与一个新子命令，函数不重叠；`README.md` 它改可选字段清单，本 change 改 agent 一节。它合入后本分支快进到新 main 并重跑 baseline；PR 前预合并。**没有碰** 它改的 `flight-doctor.py`、`pr-ship.md`、`flight-runner-contract.md`、`opsx-propose.md` 与同名 skill、`schema.yaml`。
- [与待飞的 `test-ledger` 同改 `slice-gate.py`、`README.md`] → 它改采集 / baseline / final 落账，函数不重叠；谁后合谁预合并。
- [`no_rows` 在临时 worktree 里开始按原意判红] → 误伤面：执行体用既不含运行器名字、也不在 `verify` / `gate.test` 里的命令跑测试。回放里 231 个零命中的执行体有 123 个会被「认脚本路径」救回；剩下的红了以后理由里直接写了做法（先运行本片的 verify），执行体同轮内可自愈。人类可在审批时改判为警告（见 Open Questions）。
- [档位在自举模式不生效] → 如实写进 README；本仓飞行本来就没有上限。
- [80 轮的依据样本小] → 常量集中在两份定义文件与工作流脚本一处，由测试对账；改数只动这三处。
- [回收删掉了有人还想看的临时 worktree] → 只删「提交已合回、无其他未提交内容」的；门禁输出在 `gate-report.md`，留痕在分支的 `evidence.log`，提交在分支上。未交回执行体的 worktree（有半成品）不会被删。
- [新 hook 合回后、新门禁合回前，本次飞行后两个 wave 的切片留痕只进共用目录、进不了分支] → 只影响本 change 自己的飞行记录；合入后的飞行不受影响。
- [`flight-evidence/` 是新的本地状态] → 自带上限（30 个 change 目录，首轮 `start` 修剪）；`merged-cleanup.py` 不登记它，按「保留」处理，写进 ADR。

## Migration Plan

无数据迁移。升级后：

- 在途 change 的计划不需要改（`turns` 可选，不写按规模算）。
- 已有的临时 worktree 不会被追溯回收（只在 `merge` 当次处理刚合入的片）；存量仍走 `/clean-after-merged`。
- 回滚：还原本 change 的提交即可；`flight-evidence/` 目录可直接删除，无人依赖。

## Open Questions

1. **大片档上限取 80 还是方案页草案的 120？** 本设计取 80（依据见调查二）。只是三处常量。
2. **`no_rows` 在临时 worktree 里按原意判红，还是首版先降为警告？** 本设计判红（它是现有规则，只是以前没生效）。
3. **回收时是否顺手 `git branch -d` 临时分支？** 本设计删（只删已合入的；失败留着并警告）。不删的话一次九片的飞行会留下九条 `worktree-wf_*` 分支，等 `/clean-after-merged`。
4. **重新起飞时要不要自动接上一次飞行的快照？** 本 change 不做（Non-Goals）。若要做，需要先定「怎样区分可接续的快照与废弃尝试的残留」。
5. 现行 ADR 需要补充的一处：`DRAFT-post-merge-cleanup-by-tiered-script` 第 3 条说 `/clean-after-merged` 的 safe 档是铁律 6 的「唯一例外」。本 change 增加第二个例外，由新 ADR `DRAFT-slice-worktrees-reaped-after-merge` 记录；原 ADR 其余各条照旧有效，不整体取代。
