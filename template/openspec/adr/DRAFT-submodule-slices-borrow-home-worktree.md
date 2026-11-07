# DRAFT. 含 submodule 的飞行：隔离 worktree 借用家子仓的 linked worktree，gitlink 随切片提交、由合回脚本合并

- Status: accepted
- Date: 2026-11-07
- 关联：DRAFT-apply-as-flight（补充原则 2、3、4 在多仓下的落地，不取代）· DRAFT-gate-evidence-not-self-reported（展开判定同样机械）
- 来源 change：submodule-aware-flight（design D1–D6）

## Context

飞行模式的执行体跑在 Claude Code 的隔离 worktree 里，由 integrator 在 change 家合回。整条链路默认单仓。2026-11-07，afa change `raw-file-viewer` 的 9 片里有 6 片改 submodule。实测三处失败，change 只能退化为逐 task 串行：

- 隔离 worktree 的 submodule 是空目录，去远端 clone 时报 `not our ref`；
- 执行体在隔离 worktree 自己的子仓里提交，家看不到；
- 并行两片改同一 gitlink，合回冲突。

另有三处同根问题：门禁只看父仓 diff、快照不含子仓、preflight 不校验子仓。

约束：执行体直接 `git -C <家>` 会被 Claude Code 的隔离检查拦下（官方文档 worktrees · Git redirects）。`WorktreeCreate` hook 会整体替换默认的 worktree 创建，代价过大。

## Decision

1. **借出而不是 clone**：
   - `slice-gate.py start`（G0 通过之后）和 `sub-sync`，对未填充的子仓执行 `git -C <家>/<P> worktree add --detach <隔离>/<P> <HEAD:P>`。
   - 家定位：用 `--expect-branch` 在 `git worktree list --porcelain` 中查找。
   - 这样与家共享对象库，不访问远端。
   - 已填充的子仓不改动。
   - 这一步由 hook 脚本代办，写入只发生在共享 `.git` 内：登记、对象、per-worktree HEAD、`refs/flight*`。不改家的分支和工作区文件。
2. **gitlink 随切片 commit**：执行体先 `git -C <P>` 提交子仓，再把 gitlink 与父仓 owns 文件并入一个切片 commit。门禁、评审、重派都只认这一个父仓 commit。
3. **合回脚本化**：integrator 一律运行 `slice-gate.py merge <S>=<sha> ...`。
   - gitlink 快进直接钉；分叉时在家子仓内 `merge --no-ff` 后，用 `update-index` 钉。
   - 合回后家子仓的分支和检出与 gitlink 一致。
   - 任何真冲突都全回滚并停止。
   - 无 gitlink 时与逐条 `git merge --no-ff -m "integrate: <S>"` 等价。
4. **门禁、快照、preflight 按子仓内文件判**：
   - gitlink 展开为 `<P>/<文件>`；
   - 子仓检出未记录进父仓即 `G6 gitlink` 红；
   - 快照与恢复按仓分别进行，ref 同名；
   - preflight 校验家子仓已初始化且检出等于 gitlink；
   - 门禁绿时用 `refs/flight-sub/<change>/<S>` 锚住子仓提交。
5. **边界**：
   - final 增量不展开 gitlink，gitlink 变动 → 全量；
   - 不支持嵌套 submodule 与新增或删除 submodule 的切片，这类改走 `--gate=per-task`。

## Consequences

- **更易**：含 submodule 的 change 可以 wave 并行；子仓切片能写出门禁记录，ship 不再因「无门禁记录」落 draft；per-task 路径同样受益于门禁展开。
- **更易**：无 submodule 的仓库零变化；integrator 少了一项靠模型判断的步骤（合回与检出同步都由脚本完成）。
- **更难**：hook 脚本多了一类「在文本检查之外写家子仓元数据」的操作，后续改动须守住「只写共享 `.git`、不碰家的分支与工作区」这条边界。
- **约束后续变更**：
  - 新增任何在隔离 worktree 里运行、需要子仓内容的步骤，都应复用 `sub-sync`，不能各自 clone。
  - 任何合回都经 `slice-gate.py merge`，不得由模型手工 merge。
- **不影响**：评审离路径、批准门、模型路由、ADR 不可改。
