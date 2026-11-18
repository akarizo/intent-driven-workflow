## ADDED Requirements

### Requirement: 脚本列出已落地的切片
`slice-gate.py landed --change-dir DIR` SHALL 打印一个 JSON 对象，把每个已落地的切片 id 映射到它最新门禁行里的 commit，退出 0；计划不合法时与 `lint` 一样以 2 退出。一个切片已落地须同时满足：`gate-report.md` 里它的最新一行是绿的；那一行的 commit 能解析且是 HEAD 的祖先；从那个 commit 到当前工作树，该片的切片包与本 change 的 `specs/` 没有改动，且 `slices.json` 里该片的条目除 `owns` 与 `owns_wide` 外与那个 commit 上的相同。没有任何门禁行时输出空对象。
Feature: 重新起飞时知道哪些切片不用再做
Rule: 门禁绿、提交在分支上、计划里这一片没再改过，三条都满足才算

#### Scenario: landed-lists-green-merged-slices
- **GIVEN** 三个切片：S1 的最新门禁行是绿的且 commit 在分支历史里；S2 的最新门禁行是红的；S3 的门禁行是绿的但 commit 不在对象库
- **WHEN** 运行 `slice-gate.py landed`
- **THEN** 退出 0，输出只有 S1，值是它门禁行里的 commit

#### Scenario: landed-excludes-slice-whose-plan-changed
- **GIVEN** S1、S2 的门禁行都是绿的且 commit 在分支历史里
- **WHEN** 改了 S1 的切片包后运行 `landed`；还原后只改 S2 的 owns 再运行；再改 S2 的 verify 后运行
- **THEN** 第一次输出没有 S1、有 S2
- **AND** 第二次 S1、S2 都在
- **AND** 第三次输出没有 S2

### Requirement: 工作流不重做已落地的切片
`opsx-apply` 工作流 SHALL 接受可选参数 `args.landed`（`landed` 子命令的输出）：其中的切片 MUST NOT 派执行体，返回值的 `slices` 里记 `{slice, ok: true, commit, landed: true}`；评审照派，审的是 `landed` 给出的 commit。一个 wave 只要有已落地或本次合回的切片就 SHALL 做集成检查；整个 wave 都已落地时 integrator 的派发 MUST NOT 含 `slice-gate.py merge`，只运行 `wave-check` 并带回 `check`。没传 `landed` 时行为与没有本功能时相同。
Feature: 补完计划重新起飞，只花没落地那几片的钱
Rule: 执行体不重派，评审与集成检查不省

#### Scenario: workflow-skips-landed-slices
- **GIVEN** `args.landed` 含 S1（commit 为 1…1）；另一次飞行的 `args.landed` 含第一个 wave 的全部切片
- **WHEN** 各跑一遍工作流
- **THEN** 第一次没有 S1 的执行体派发，有 `review:S1` 且 prompt 含 1…1，返回值的 `slices` 里 S1 带 `landed: true`
- **AND** 第二次第一个 wave 的合回 prompt 含 `wave-check`、不含 `slice-gate.py merge`，第二个 wave 的切片照常派发
