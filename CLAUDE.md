这是一个面向最佳工程实践的intent-driven库，所有的思考都从如何打造最适合AI工程实践的第一性原理出发。


!!当前说的pr都是提到本仓库，不是指fork上游。

## 仓库铁律（零容忍：任何提速手段不得破坏）
1. 先意图后代码：中级+ 变更无工件不写源码；intent-gate 只能加严不能绕过。
2. 规格即验收：每个 scenario 有测试骨架与映射；apply 完成 = 全部 scenario 测试 pass 且骨架标记已去。
3. TDD 与留痕：生产代码前必有先失败的测试；测试运行由 hook 留痕，不接受自述。
4. 独立评审必有：每个 change 至少一次不带主会话立场的 reviewer；CRITICAL/HIGH 未闭环不得非 draft PR。
5. 门禁红不收口：slice-gate / final gate 红时禁止勾选、禁止声明完成、禁止 PR。
6. Git 边界：每 change 一间 worktree；不自动 merge、不推 main、不删 worktree；ADR 不可改只 supersede。显式跑 `/opsx-apply` / `/pr-ship` = 授权该命令文档内的 commit · push feature 分支 · 建 PR · 贴 review 评论 · draft↔ready 转换。显式跑 `/clean-after-merged` = 授权其 safe 档；`branch -D` / `push --delete` 永远交人。
7. 两处人类审批不可省：飞行计划批准（运行 /opsx-apply）与 PR review；第一处由 `.claude/hooks/takeoff-gate.py` 机械校验（人类消息证据 + 新鲜度），模型不得自证。
8. 度量必打印：每次 apply 收口打印飞行记录；无数据不得声称提速。
9. 零 token 优先：能用脚本 / hook 判定的不交给模型。
10. 回退必存在：新机制失效时回退路径语义一致（Workflow → Agent 派发；脚本渲染 → 保留占位）。
11. 模型按角色显式路由：执行体 / 评审员 = 会话主模型 high，机械角色 = sonnet low；派发不留空 `model`、模板禁设 `_FORCE`；`<main>` 由 `.claude/hooks/session-model.py` 判定，**禁自述**（判不出停飞，人工 `--model=`）；收口 `--expect-models` 机械对账各角色实际模型。

## 本仓库开发纪律
- 命令与同名 skill 同改，禁漂移；`python3 -m pytest -q tests` 全绿；`cd template && openspec schema validate intent-driven` 绿；`.claude/hooks/*.py` 可 compileall。
- 回复与文档禁日文假名 / 韩文谚文。
- change 工件落 `template/openspec/changes/<name>/`，实现在 `.worktrees/<name>/`；PR 前预合并 main。

