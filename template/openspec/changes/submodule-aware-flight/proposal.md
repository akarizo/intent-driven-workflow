## Why

含 git submodule 的仓库飞不起来。2026-11-07 afa change `raw-file-viewer` 有 9 片，其中 6 片改 submodule `admin/viewer`。飞行模式在三处实测失败，只能退化为 `--gate=per-task` 串行：

1. 隔离 worktree 里 submodule 是空目录。`submodule update --init` 去远端 clone，本地未 push 的 gitlink 报 `not our ref`。执行体自己也不能从 change 家取：Claude Code 的隔离检查会拦 `git -C <家>`。
2. 执行体在隔离 worktree 自己的子仓里提交，家里的子仓看不到这个提交，合回后 gitlink 指向一个不存在的提交。
3. 同一 wave 两片都改 gitlink，合回时出现 `CONFLICT (submodule)`。integrator 按纪律只能 abort。

读代码又定位到三处同根问题：

4. 切片门禁只看父仓 diff（`slice-gate.py:2429` `changed_files`、`:2443` `added_lines`），只拿到 `admin/viewer` 这一条 gitlink，于是 G6 判它在 owns 外、G3 看不到测试、G8 漏掉 ceiling 行。afa 那 6 片写不出门禁记录，ship 只能判 draft。
5. 快照（`:2960` `_checkpoint`）只看父仓 porcelain，submodule 内的半成品不进快照。
6. preflight（`:3857`）不校验 submodule 是否就绪，问题要到合回时才暴露。

根因在模板：飞行模式从隔离、提交、合回到门禁，全程按单仓设计。决策页 `template/openspec/superpower/2026-11-07-submodule-aware-flight-decisions.html` 列了 Q1–Q8，用户 2026-11-07 全部采纳推荐项。

## What Changes

- **隔离 worktree 自带 submodule**：
  - `slice-gate.py start` 通过 G0 基点校验后，为隔离 worktree 填充 change 家里已初始化的每个 submodule。做法是从家子仓借出 linked worktree，检出到 HEAD 的 gitlink，不访问远端。
  - 家子仓未初始化、gitlink 不在家子仓的对象库 → 以 `G0 submodule` 拒绝起跑，并给出修法。
  - 已填充的子仓不被改动。
  - 新增子命令 `sub-sync`，供 fix 执行体用（slices.json 没有 fix 条目，不能靠 start 填充）。
- **门禁按文件判**：
  - `gate` 把 gitlink 展开为 submodule 内的文件：已提交部分取 gitlink 前后的子仓 diff，未提交部分取子仓 status。
  - 新增 `G6 gitlink`：子仓检出未记录进父仓 HEAD 即红。
  - `added_lines` 带上 `--submodule=diff`，G8 能看到子仓内的 ceiling 行。
  - 门禁绿时在子仓写 `refs/flight-sub/<change>/<S>`，锚住本片的子仓提交，防 gc。
- **快照与恢复覆盖子仓**：`checkpoint` 与 `start --resume-checkpoint` 对每个有 owns 落在其中的 submodule，各做一份同名 ref 的快照与恢复。
- **preflight 就绪校验**：计划 owns 落在某个 submodule 内时，家里该子仓必须已初始化、检出等于父仓 HEAD 的 gitlink，否则拒绝起飞。这一项排在基线检查之前。
- **合回脚本化**：新增子命令 `merge <S>=<sha> ...`，integrator 第 1 项一律调用它。
  - 逐片执行 `git merge --no-ff`。
  - gitlink 是快进时直接钉；分叉时先在家子仓内合并，再用 `update-index` 钉。
  - 合回后家子仓的分支和检出都与 gitlink 一致。
  - 非 gitlink 冲突，或子仓内容冲突 → 父仓与子仓都回滚，返回 `ok:false`。
  - 无 submodule 的仓库与原来逐条 `merge --no-ff -m "integrate: <S>"` 等价。
- **编排与文档**：
  - `opsx-apply.js`：integrator 与 finalize 改调 `merge`；fix 在基点校验后跑 `sub-sync`；评审改用 `git show --submodule=diff`。
  - `integrator.md`、`slice-executor.md` 补上子仓提交纪律：先 `git -C <P>` 提交，再把 gitlink 并入同一个切片 commit。
  - `opsx-apply.md` 与同名 skill 同步改；`openspec-git-discipline` 新增 Submodule 小节；README、WORKFLOW_zh 补一句。
- **不变**：
  - final 增量选测不认识 gitlink：gitlink 变动按「未被用例触及的非 Python 文件」触发全量，记为天花板。
  - 不支持嵌套 submodule、新增或删除 submodule 的切片：前者给 warning，后者由 G6 点名伪路径，提示改走 `--gate=per-task`。
  - `--gate=per-task` 照旧可用，也同样受益于门禁展开。

## Capabilities

### New Capabilities

- `submodule-gate-expansion`：切片门禁把 gitlink 展开成子仓内文件判 G3 / G6 / G8 / GWT，gitlink 未记录判红，门禁绿锚定子仓提交。
- `submodule-worktree-sync`：隔离 worktree 从 change 家借出子仓 linked worktree（`start` / `sub-sync`），基点校验先于填充，重派续跑，快照恢复覆盖子仓，preflight 就绪校验。
- `submodule-merge`：`slice-gate.py merge` 逐片合回，gitlink 冲突在家子仓内合并后钉，失败全回滚，无 submodule 时与 `merge --no-ff` 等价。
- `submodule-flight-orchestration`：工作流与回退路径的 integrator / fix / 评审接上上述命令，agent 定义与命令文档写明子仓纪律。

### Modified Capabilities

（无）飞行模式的现行规格在未归档的 change `apply-flight` 等目录里，`openspec/specs/` 下没有对应主 spec，所以本 change 只用 ADDED。integrator 第 1 项的执行方式由新 ADR 记录。

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py` 一个文件。
  - 新增：`_gitlinks`、`_home_root`、`_sub_sync`、gitlink 展开、`G6 gitlink`、子仓锚定 ref、`sub-sync` / `merge` 子命令。
  - 改动：快照与恢复按仓分别进行，preflight 加就绪校验。
- **编排与文档**：
  - 代码与 agent 定义：`template/.claude/workflows/opsx-apply.js`、`agents/integrator.md`、`agents/slice-executor.md`。
  - 命令与 skill：`commands/opsx-apply.md`、`skills/openspec-apply-change/SKILL.md`、`skills/openspec-git-discipline/SKILL.md`。
  - 说明文档：`README.md`、`docs/WORKFLOW_zh.md`。
- **测试**：
  - 新增夹具 `tests/submodule_helpers.py`（父仓 + 本地子仓 + change 家 + 隔离 worktree）。
  - 新增 `tests/test_submodule_gate.py`、`tests/test_submodule_sync.py`、`tests/test_submodule_merge.py`、`tests/test_submodule_docs.py`。
  - 既有用例 `test_integrator_agent_contract` 断言正文含 `git merge`，S4 须保留该措辞。
- **ADR**：新增 `DRAFT-submodule-slices-borrow-home-worktree`。它不取代现行决策，补充 `DRAFT-apply-as-flight` 的原则 3（确定性调度）。
- **已装仓库**：
  - 无 submodule 的仓库零变化。
  - 含 submodule 的仓库升级后可以飞行：在飞的 change 用的是自己分支里的旧 `.claude`，不受影响。
  - afa `raw-file-viewer` 按决策 Q8-A 继续走它自己的混合路线，新机制在下一个改 viewer 的 change 上实测。
- **无**新依赖、部署或数据变化。
