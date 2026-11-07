## Context

飞行模式的执行体一律跑在 Claude Code 的隔离 worktree（`isolation: worktree`）里，由 integrator 在 change 家把各片 commit 合回。整条链路默认是单仓：

- 隔离 worktree 只检出父仓的 tracked 文件。submodule 是空目录。
- 执行体不能自己从家里取。Claude Code 官方文档（worktrees · How Claude Code enforces isolation）写明，Bash 里 `git -C`、`--git-dir`、`GIT_DIR` 指向主 checkout 的命令会被拦下；本会话所在的 linked worktree 及其主 checkout 都算在内。
- 合回、门禁、快照都只看父仓。gitlink 只是一条 mode 160000 的伪路径。

afa（2026-11-07）实测了三处失败（proposal 第 1–3 条）。本会话在 /tmp 玩具仓（git 2.54）做了两组实验：

- **E1**：让隔离 worktree 借用家子仓的 linked worktree，可行。
  - 吸收进 `modules/` 的 gitdir 带有 `core.worktree`，但不影响 linked worktree。
  - 执行体的提交在家里即刻可见。
  - 父仓 status / add / diff 都正常。
- **E2**：两片并行改子仓后合回。
  - S1 是快进，无冲突。
  - S2 冲突只出现在 gitlink 上，在家子仓内合并后再 `update-index` 即可解。
  - 合回后，下一 wave 能从新 gitlink 填充。
  - 在未填充的隔离 worktree 里 cherry-pick 上一轮提交可行。
  - `git show --submodule=diff` 能展开子仓 diff。
- **核对项**：
  - `diff -U0 --submodule=diff` 输出的路径带 `<子仓>/` 前缀。
  - 合并态下 `commit -m` 生成双亲提交，说明不变。
  - `worktree list --porcelain` 能按 `branch refs/heads/<B>` 定位家。

在役 ADR：
- `DRAFT-apply-as-flight`：五原则。本设计不改原则，只让原则 2（所有权）、3（确定性调度）、4（机械门禁）在多仓下成立。
- `DRAFT-gate-evidence-not-self-reported`：门禁证据不靠自述。gitlink 展开同样是机械判定。

## Goals / Non-Goals

**Goals:**
- 含 submodule 的 change 能走飞行模式：同一 wave 内多片并行改同一子仓，结果正确合回。
- 门禁按子仓内的真实文件判。per-task 路径同样受益。
- 重派、快照恢复、preflight 的语义在子仓上与父仓一致（铁律 10）。
- 无 submodule 的仓库零行为变化（场景 `merge-plain-repo-equals-no-ff` 加上既有全量用例守住）。

**Non-Goals:**
- final 增量选测展开 gitlink（Q5-A）：gitlink 变动 → 全量，保守而且正确。
- 嵌套 submodule，以及新增或删除 submodule 的切片（Q6-A）。
- 访问远端：不 fetch、不 push 子仓。
- 子仓自身的 MR 编排：子仓分支的推送与 MR 仍由人或 `/pr-ship` 之外的流程处理。

## Decisions

### D1 · 隔离 worktree 的子仓借用家子仓的 linked worktree（Q1-A）
- **做法**：`_sub_sync(root, branch, need)` 在 `start`（G0 通过后）和新子命令 `sub-sync` 里执行：
  - **家定位**：在 `git worktree list --porcelain` 中找 `branch refs/heads/<branch>` 那一块，取它的 `worktree` 路径。
  - **gitlink 清单**：`git ls-files -s -z` 里 mode 为 160000 的条目。目标提交为 `git rev-parse HEAD:<P>`。
  - **已填充**（`<root>/<P>/.git` 存在）：不改动。检出 ≠ 目标时只给 warning。
  - **未填充**：家里同一子仓已初始化，且目标在家子仓对象库里 → 执行 `git -C <家>/<P> worktree add --detach <root>/<P> <目标>`。
  - **失败**：以下任一情况，若该子仓属于 `need`（本片 owns，或 `--change-dir` 下全部切片 owns 有路径落在 `<P>/` 下）→ 记 `G0 submodule: …`；否则 warning 并跳过：
    - 家定位不到，或家就是本 worktree；
    - 家子仓未初始化；
    - 目标不在家子仓对象库；
    - `<root>/<P>` 非空；
    - `worktree add` 失败。
  - **嵌套 submodule**：子仓里有 `.gitmodules` → warning：嵌套 submodule 不填充。
- **为什么借 linked worktree**：对象库共享，执行体提交即落进家子仓，不需要搬运。写入只发生在共享 `.git` 内：家子仓 gitdir（如 `afa/.git/worktrees/<家>/modules/<P>`）下的 `worktrees/<id>` 登记、对象、per-worktree HEAD。不碰家的工作区文件，也不改家子仓的分支。这与父仓提交写共享 `.git` 是同一类操作。
- **由 hook 脚本代办**：执行体直接 `git -C <家>` 会被隔离检查拦下，所以这一步由 hook 脚本执行。这是有意的选择，ADR 记录，人在决策页 Q1 批准。
- **备选**：
  - B · `clone --shared` 后由 integrator 从隔离目录 fetch：门禁 JSON 要带路径；重派要从上一轮的隔离目录取；隔离目录被清理就丢提交。
  - C · `WorktreeCreate` hook：会替换 Claude Code 默认的 worktree 创建逻辑，要自行实现 baseRef、`.worktreeinclude`、锁、LFS 中和，而且不进定期清扫。
  - D · 改 submodule 的切片不隔离、串行：这正是本次要消除的退化。

### D2 · gitlink 随切片 commit 提交（Q2-A）
执行体顺序：
1. `git -C <P> add <子仓内相对路径>` + `git -C <P> commit`；
2. 父仓 `git add <P> <父仓 owns 文件>`，一个切片 commit。

门禁、评审、重派 cherry-pick 都只认这一个父仓 commit。冲突交给 D5。

备选「执行体只提交子仓、integrator 统一钉 gitlink」被否：
- 纯子仓切片的父仓 commit 为空；
- 评审与重派都要另传子仓提交；
- 「别 git add P」是反直觉纪律。

### D3 · 门禁展开（Q4-A 之一）
- **`changed_files(root, base)`**：签名不变，在结果上展开 gitlink：
  - **已提交**：`git diff --raw -z --no-renames base..HEAD` 中旧 / 新 mode 任一为 160000 的条目 P。两侧都是 160000、P 已填充、两个提交都在子仓里 → 用 `P/` + `git -C P diff --name-only -z --no-renames old new` 替换 P；否则保留 P，由 G6 点名。
  - **未提交**：父仓 porcelain 列出的路径中属于 gitlink 的 P，替换为两部分之和：
    - `P/` + `git -C P status --porcelain -z --untracked-files=all` 的路径（改名取新路径）；
    - 子仓检出与 `HEAD:P` 不同、且两者都在子仓时，`P/` + `diff --name-only HEAD:P..子仓 HEAD`。
  - 展开结果同样过 `is_bytecode` 过滤。
- **`G6 gitlink`**：`cmd_gate` 对每个已填充的 gitlink P，若子仓检出 ≠ `HEAD:P`，记一条：
  `G6 gitlink: <P> 的检出 <x10> 未记录进父仓 HEAD（父仓记录 <y10>；git add <P> 后并入本切片 commit）`
- **`added_lines`**：git diff 加 `--submodule=diff`。git 原生输出 `+++ b/<P>/<文件>`，解析逻辑不用改。
- **锚定**：门禁绿时，对区间内 gitlink 变化、已填充的子仓，执行 `git -C P update-ref refs/flight-sub/<change>/<S> <new>`。
  - 命名不用 `refs/flight/<change>/<S>/…`：子仓里同名快照 ref 已存在，会形成 D/F 冲突。
  - 这些 ref 不清理（每片一条，体积可忽略），用来覆盖「门禁绿后飞行中断、数周后恢复」的 gc 窗口。

### D4 · 快照与恢复覆盖子仓（Q4-A 之二）
- **`_checkpoint`**：拆出 `_ckpt_commit(repo, head, files, msg)`，即临时 index → `read-tree` → `add` → `write-tree` → `commit-tree`。父仓与子仓共用。
  - 父仓段原来的提前 `return` 改为「跳过父仓段」，避免漏掉子仓。
  - **子仓段**：对每个已填充、`owns` 有 `P/` 前缀的 P，处理 owns 内的未提交文件（相对子仓）。若有这类文件，或子仓 HEAD ≠ `<marker.base>:P`，就快照到子仓的同名 ref `_ckpt_ref(change_dir, S)`。
- **`_ckpt_restore`**：父仓段不变。另对每个已填充、有 owns 的子仓：子仓 HEAD 须是快照的祖先，然后恢复差异里匹配 owns 的文件，`restored` 记 `P/<f>`。父仓「无快照」时不得提前返回。
- **`_ckpt_delete`**：调用点（`cmd_start` 首轮、`cmd_gate` 绿、`cmd_record`）改为 `_ckpt_delete_all`，同时删除各已填充子仓里的同名 ref。

### D5 · 合回脚本 `slice-gate.py merge <S>=<sha> ...`（Q3-A）
- **开跑前复核**：每个已填充的 gitlink P，子仓检出须等于 `HEAD:P`，且不在合并中。否则一片不合，`failed: ["merge: <P> 的检出 … 与 gitlink … 不一致，先同步"]`。
- **逐片**：
  1. `git merge --no-ff --no-commit -m "integrate: <S>" <sha>`。
  2. 冲突集合：`diff --name-only --diff-filter=U -z`。gitlink 集合：`git diff --raw -z --no-renames $(merge-base HEAD sha) sha` 里新 mode 为 160000 的 P。
  3. 冲突里有非 gitlink 的路径 → `merge --abort`，记 `merge <S>: 冲突文件 …`，停止。
  4. 对每个 gitlink P，取 ours = `HEAD:P`、theirs = `<sha>:P`：
     - 相等 → 跳过；
     - ours 不存在（新增 submodule）→ 回滚，记「不支持」；
     - 一方是另一方的祖先 → 取较新者；
     - 分叉 → 在子仓 `merge --no-ff --no-edit -m "integrate: <S>" theirs`。失败则依次执行：子仓 `merge --abort`；已在本片做过的其他子仓 `reset -q --keep <合前>`；父仓 `merge --abort`。记 `merge <S>: <P> 子仓合并冲突 …`，停止。
     - 最后 `update-index --cacheinfo 160000,<目标>,P`。
  5. 存在 MERGE_HEAD 时执行 `git commit -q -m "integrate: <S>"`。已是最新则视为合回成功。
  6. **同步检出**：子仓 HEAD ≠ 目标时，子仓在分支上 → `merge --ff-only`；detached → `checkout --detach`；做不到 → warning。
- **输出**：`{ok, merged, failed, warnings}`，退出 0 / 1。参数格式错 → `die`（退出 2）。
- **为什么用脚本**：零 token 优先（铁律 9），integrator 不解冲突。没有 gitlink 时，第 4、6 步为空，结果与原来的逐条 `merge --no-ff -m` 等价。备选「只在冲突时调脚本」被否：每次合回后的检出同步也要模型判断，容易漏。

### D6 · preflight 就绪校验（Q4-A 之三）
- **位置**：`cmd_preflight` 在 `lint_plan` 之后、基线检查之前。
- **范围**：每个 gitlink P，只要计划里任一切片 owns 有 `P/` 前缀。
- **要求**：已初始化、`HEAD:P` 在子仓里、子仓检出 = `HEAD:P`。否则 `die("submodule 未就绪：…")`，点名 P 与 gitlink 并给出修法。
- **不校验子仓脏不脏**：合回时由 D5 的子仓合并失败兜住。

### D7 · 编排与文档（S4）
- **`opsx-apply.js`**：
  - wave 合回：「按第 1 项运行 `python3 <hooksDir>/slice-gate.py merge S1=<c1> S2=<c2>` …非 0 → 把它 JSON 的 failed 原样返回、ok:false」。
  - finalize：`merge fix=<commit>`，位于 `final` 之前。
  - fix prompt：基点校验之后、`start fix` 之前运行 `slice-gate.py sub-sync --change-dir <dir>[ --expect-branch <branch>]`，非 0 → 原样返回其 failed。以 G0 开头的失败沿用 `baseRejected` 重派一次。
  - 评审：`git show --submodule=diff <commit>`。
- **`integrator.md` 第 1 项**：改为运行 `slice-gate.py merge`，写明它逐片 `git merge --no-ff -m "integrate: <S>"`、自行处理 gitlink、冲突时自行 abort。保留 `git merge` 字样，既有用例 `test_integrator_agent_contract` 断言它。
- **`slice-executor.md`**：
  - 纪律段加一条：submodule 内的 owns，先 `git -C <P>` 提交再并入 gitlink；不切分支、不 push。
  - 开工段加一句：start 已填充子仓，失败以 `G0 submodule` 返回。
- **`opsx-apply.md` 回退段与 `openspec-apply-change/SKILL.md`**：同步改，命令与 skill 不漂移。
- **`openspec-git-discipline`**：新增 `## Submodule` 小节。
- **README、WORKFLOW_zh**：在飞行模式说明处各补一句。

### D8 · 测试夹具
`tests/submodule_helpers.py` 用本地路径子仓（`-c protocol.file.allow=always`），搭出「主 checkout / change 家 / 隔离 worktree」三处。隔离 worktree 用 `git worktree add --detach` 从主 checkout 建出，模拟 Claude Code（afa 实测其隔离 worktree 位于主 checkout 的 `.claude/worktrees/` 下）。夹具在 propose 期写全，S1 拥有它；S2、S3 只引用、不改。

### D9 · 切片与 wave
- **wave 1**：S1（门禁展开）∥ S4（编排与文档，接口以本设计为准）。
- **wave 2**：S2（填充、快照、preflight、`sub-sync`）。
- **wave 3**：S3（`merge`）。

S1–S3 都改 `slice-gate.py`，只能串行；S3 的端到端场景依赖 S1、S2。

## Risks / Trade-offs

- **[绕开文本检查的写入]** hook 脚本在 Claude Code 文本检查之外写家子仓的 git 元数据 → 只做 `worktree add --detach`、`update-ref refs/flight*`、落对象，全部在共享 `.git` 内。不改家的分支和工作区；家子仓分支只由家里的 `merge` 推进。写进 ADR，人已在 Q1 批准。若 Claude Code 将来把这类写入也列为拦截对象，回退到 D1 备选 B。
- **[执行体用 `git -C <P>` 提交]** 未在真实 Claude Code 里实测。路径在隔离 worktree 内，按文档不属于「指向主 checkout」。若被拦，执行体可改用 `cd <P> && git …`（文档只拦 cd 进主 checkout）。合入后在 afa 的下一个 viewer change 上实测（Q8-A）。
- **[含已填充 submodule 的隔离 worktree，`git worktree remove` 会拒删]**（E1 已验证）→ 有提交的隔离 worktree 本来就保留到定期清扫；G0 不通过时不填充，所以不会出现「无改动却删不掉」。Claude Code 清扫时如何处理未实测，最坏是残留，用 `git worktree remove --force` + 子仓 `git worktree prune` 清理。
- **[每片多检出一份子仓]** → 只检出家里已初始化的子仓；afa 的 viewer 是 197 个文件。大型子仓会增加起步耗时，记为天花板。
- **[final 遇 gitlink 变动即全量]** → 保守而且正确（Q5-A）；配了 `gate.scope` 的仓库由提供方裁决。升级条件：内建依赖图展开 gitlink。
- **[本 change 自己的 final 近乎全量]** S1–S3 改的 `slice-gate.py` 被绝大多数用例加载，增量也近乎全选；以 lint 实际报告为准。

## Migration Plan

- **升级**：合入后，已装仓库执行 `./install.sh --upgrade` 即获得新机制。无 submodule 的仓库零变化。在飞的 change 用的是自己分支里的旧 `.claude`，不受影响。
- **afa**（Q8-A）：`raw-file-viewer` 按它自己会话里的混合路线继续。升级后，下一个改 viewer 的 change 实测，重点看三项：
  - 隔离 worktree 填充；
  - 执行体 `git -C` 提交是否被拦；
  - 两片并行合回。
- **回退**：revert 本 change，回到「含 submodule 用 `--gate=per-task`」。单个 change 也可以继续显式走 `--gate=per-task`，门禁展开对它照样生效。

## Open Questions

- 无须 supersede 的在役 ADR。新增 `DRAFT-submodule-slices-borrow-home-worktree`，作为 `DRAFT-apply-as-flight` 原则 3 在多仓下的补充。
- Claude Code 对含 submodule 的隔离 worktree 如何清扫，以及执行体 `git -C <P>` 是否被隔离检查放行，这两点只能在真实会话里验证（见 Risks）。
