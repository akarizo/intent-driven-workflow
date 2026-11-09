## Why

PR 送出前后各有一个收尾动作没有闭环。两处都在 2026-11-07 至 11-09 的 `submodule-aware-flight` 中实际出过问题。

**合并后清理靠手写命令，判错就失败或丢数据。**
- PR #11 合并后要清理 9 个 worktree、9 个分支。按人工给出的命令清单执行，6 个已合并分支的 `git branch -d` 报 `not fully merged`。
- 根因：这些分支没有 upstream。`git branch -d` 此时按本地 HEAD 判断是否已合并，而本地 `main` 还没同步 `origin/main`。
- 要不要 `--force`、要不要 `-D`，都靠人和模型临场判断。`openspec-git-discipline` 只写了「由人确认后在主仓库根手动 `git worktree remove`」。
- 本仓库刚支持 submodule，又多了一处隐患（2026-11-09 用玩具仓实测）：
  - 在 linked worktree 里初始化的子仓，仓库本体在 `<主仓>/.git/worktrees/<id>/modules/<P>`；
  - 不加 `--force` 时，`git worktree remove` 拒绝删除含子仓的 worktree；
  - 加 `--force` 会连同这个子仓库一起删掉，其中未推送的子仓提交随之丢失，主 checkout 的子仓和子仓远端都没有它。

**知识沉淀依赖人记得跑 `/claudemd-commit`，反复出现的错误没有去处。**
- `/pr-ship` 的「典型使用顺序」要求先跑 `/claudemd-commit`，但它是一个独立命令，要逐条问用户确认，与飞行收口「全程不问询」接不上。`submodule-aware-flight` 就跳过了它。
- 本轮有两条反复出现的错误：
  - 自举飞行时文档切片先合回，导致后续两次门禁红；
  - 合并后清理 `-d` 失败。
- 这两条只记进了个人 auto-memory，模板的载体体系里没有。
- `/claudemd-commit` 在 2026-08-25 废除了 C 类「本轮发现的工程偏差」，理由是它没有上限。结果连有证据、反复出现的错误也只能进 backlog。

## What Changes

- **新增判定脚本 `template/.claude/hooks/merged-cleanup.py`**（零 token，`plan` / `apply` 两个子命令）。它在主 worktree 根运行，检测以下四类对象：
  - 所有 linked worktree；
  - 本地 `worktree-*` 分支；
  - 远端 `<remote>/worktree-*` 分支；
  - 已落地 change 留下的 `refs/flight/<change>/*` 快照。

  每项判定以下几点，并给出确切命令：
  - **合并状态**：
    - `ancestor`：tip 是 target 的祖先；
    - `content`：squash 等方式合入，`merge-tree` 结果与 target 树相同；
    - `fresh`：tip 落在 target 主线上，没有独有提交；
    - `unmerged`：未合并。
  - **是否需要 `--force`，及原因**：
    - 只剩飞行记录（`timeline.md` / `gate-report.md` / `evidence.log` / `.openspec-slice`）；
    - 含已填充的子仓；
    - 有其他未提交改动。
  - **执行档位**：`safe` / `manual` / `keep`。

  `branch -d` 的可行性按 git 自身规则推算（有 upstream 按 upstream 判，否则按 HEAD 判）。target 落后时，先 `--ff-only` 同步，再判。
  子仓提交只存在于将被删除的子仓库时，判 `manual`，并写明「先推送子仓」。
- **新增命令 `/clean-after-merged`**：
  - 先跑 `plan --markdown` 展示结果，再跑 `apply` 执行 `safe` 档：
    - `fetch --prune`；
    - `--ff-only` 同步 target；
    - `worktree remove`，脚本判定后可带 `--force`；
    - `worktree prune`，包括家子仓里借出的 linked worktree；
    - 删除已落地 change 的 `refs/flight/*`；
    - `branch -d`。
  - `manual` 档原样输出成命令清单交给用户执行，包括：
    - `branch -D`；
    - `push --delete`；
    - 含其他改动、被锁定、位于仓库约定目录之外的 worktree。
- **铁律 6 加一条授权例外**（根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`）：显式运行 `/clean-after-merged` = 授权它文档内的 `safe` 档。`branch -D` 与 `push --delete` 仍只交人执行。`openspec-git-discipline` 的清理条款同步改写。
- **`/claudemd-commit` 改为自动识别与录入**：
  - 只有「与已有认知有较大差异」的条目才和用户对齐。较大差异包括：删除或反转既有规则、与既有条目或在役 ADR 矛盾、改动铁律或核心约束段、写到仓库外的全局 `~/.claude/CLAUDE.md`。
  - 新增有上限的 **E 类「反复错误」**：本轮至少出现 2 次，且每次都有证据指针才收。证据可以是门禁红记录、`review-findings.json` 条目、fix commit，或用户原话纠正。
  - E 类能写成测试、lint 或 hook 的，进 backlog 立项，常驻层只留一行过渡条目。只出现 1 次的照旧进 backlog。
  - C 类维持废除。
- **`/pr-ship` 新增 step 2b「记忆层沉淀」**（不问询）：
  - 巡视三处来源：本会话对话（含 compact 摘要）、分支 diff、飞行记录与评审。
  - 按 `/claudemd-commit` 的自动模式产出一个独立的 `docs(memory)` commit。
  - 需要对齐的条目不落盘，列进 PR 正文「记忆层：需与你对齐」，由用户在 PR review 时裁决。
  - 飞行模式下，沉淀 commit 之后重跑 `slice-gate.py final`，让 ship 裁决的 final 行对齐新 HEAD。
  - 收尾提示合并后跑 `/clean-after-merged`。

**不改**：
- `slice-gate.py` 的门禁、合回与 ship 判据；
- `claudemd-lint` / `memory-lint` 的判据与阈值；
- `/claudemd-commit` 的准入四问与预算中性规则；
- `/pr-ship` 的评审与自动修复流程。

## Capabilities

### New Capabilities
- `merged-cleanup-plan`：合并后清理的判定与执行脚本。包括合并状态、是否需要 `--force` 及原因、档位、按 git 规则推算 `-d` 可行性、target 同步、子仓提交存活校验、`apply` 只执行 `safe` 档。
- `clean-after-merged-command`：`/clean-after-merged` 命令、铁律 6 的授权例外、git-discipline 与 README / WORKFLOW_zh / install.sh 的同步。
- `ship-memory-sedimentation`：`/claudemd-commit` 自动录入与差异对齐、E 类反复错误、`/pr-ship` step 2b 记忆层沉淀。

### Modified Capabilities
（无：`openspec/specs/` 尚无已归档的 spec）

## Impact

- **新增**：
  - `template/.claude/hooks/merged-cleanup.py`
  - `template/.claude/commands/clean-after-merged.md`
  - 三个测试文件：`tests/test_merged_cleanup.py`、`tests/test_clean_after_merged_docs.py`、`tests/test_ship_memory_docs.py`
- **修改**：
  - `template/.claude/commands/pr-ship.md`
  - `template/.claude/commands/claudemd-commit.md`
  - `template/.claude/claudemd-standard.md`（§13 合约表）
  - `template/.claude/skills/openspec-git-discipline/SKILL.md`
  - `template/CLAUDE.md.snippet`
  - 根 `CLAUDE.md`
  - `README.md`
  - `docs/WORKFLOW_zh.md`
  - `install.sh`（命令计数）
- **依赖**：只用 git（≥ 2.38，`merge-tree --write-tree`，与 `/pr-ship` 的要求一致）。不调用 `gh` / `glab`，不访问网络，`fetch` 除外。
- **兼容**：
  - 没有 linked worktree 或 `worktree-*` 分支的仓库，`plan` 输出空清单，`apply` 什么都不做。
  - 已安装模板的仓库重新安装后获得新命令。
