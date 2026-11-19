## ADDED Requirements

### Requirement: 一次取全部待建工件的 instruction
`.claude/hooks/plan-kit.py instructions --change <name>` SHALL 按以下步骤工作：
1. 运行一次 `openspec status --change <name> --json`；
2. 对每个状态不是 `done` 的工件，运行 `openspec instructions <id> --change <name> --json`；
3. 按工件依次打印一节，节标题为 `## <id> → <outputPath>`，内容依次是 instruction、template，以及非空的 rules。

带 `--all` 时，`done` 的工件也打印。任一次 openspec 调用失败时 MUST 以 exit 2 退出，并在 stderr 写出失败的命令。

Feature: 汇总 instruction
Rule: 一次运行拿全待建工件的写作要求

#### Scenario: kit-instructions-prints-pending-artifacts
- **GIVEN** 一个 openspec 桩命令：proposal 已 done，design 与 tasks 待建，每个工件的 instruction 与 template 各不相同
- **WHEN** 运行 `plan-kit.py instructions --change c`
- **THEN** 退出 0，输出有 `## design → design.md` 与 `## tasks → tasks.md` 两节，各含自己的 instruction 与 template
- **AND** 输出没有 proposal 那一节

#### Scenario: kit-instructions-fails-loud
- **GIVEN** 一个 openspec 桩命令，`instructions design` 以非 0 退出
- **WHEN** 运行 `plan-kit.py instructions --change c`
- **THEN** exit 2，stderr 含 `openspec instructions design`

### Requirement: 由 slices.json 生成 tasks.md
`plan-kit.py tasks --change-dir D` SHALL 生成 `D/tasks.md`：
- 第一行是生成声明注释，接着是 `## 切片`；
- 每片一行：`- [ ] <id> <title> （deps: <逗号分隔的依赖或 -> · verify: \`<verify>\`）`，与 `templates/tasks.md` 的格式一致；
- 旧 `tasks.md` 里已勾选的切片 id MUST 保持 `[x]`。

Feature: 生成 tasks.md
Rule: 格式与模板一致，勾选状态不丢

#### Scenario: kit-tasks-generates-from-slices
- **GIVEN** 两片计划：S1 无依赖，S2 依赖 S1，各有 verify
- **WHEN** 运行 `plan-kit.py tasks --change-dir`
- **THEN** `tasks.md` 有 `- [ ] S1 <S1 标题> （deps: - · verify: \`<S1 verify>\`）` 与 `- [ ] S2 <S2 标题> （deps: S1 · verify: \`<S2 verify>\`）` 两行

#### Scenario: kit-tasks-keeps-checked-state
- **GIVEN** 旧 `tasks.md` 里 S1 已勾选
- **WHEN** 再次运行 `plan-kit.py tasks --change-dir`
- **THEN** S1 那一行仍是 `- [x]`，S2 那一行是 `- [ ]`

### Requirement: 切片包的机械区由脚本渲染，说明原样保留
`plan-kit.py packets --change-dir D` SHALL 为每个切片渲染 `slices/<S>.md` 的机械区，放在 `<!-- plan-kit:begin -->` 与 `<!-- plan-kit:end -->` 之间。机械区依次包含：
- 标题行 `# <S> · <title>`；
- owns 列表；
- 依赖切片（id、标题、包路径）；
- 每个 scenario 的能力名、scenario 名、映射的测试，以及取自 `specs/<能力>/spec.md` 的 GIVEN / WHEN / THEN / AND / BUT 原文；
- verify。

已存在的包 MUST 只替换标记之间的内容，标记之外的文字保持不变。已存在但没有标记时，机械区插到最前面，原内容整体保留。

Feature: 渲染切片包
Rule: 机械部分由脚本写，判断部分由主会话写

#### Scenario: kit-packets-renders-mechanical-region
- **GIVEN** 两片计划：S2 依赖 S1，S2 有一个 scenario，其 spec 原文含 GIVEN / WHEN / THEN 各一行
- **WHEN** 运行 `plan-kit.py packets --change-dir`
- **THEN** `slices/S2.md` 的标记之间含标题行、S2 的每个 owns、S1 的标题、该 scenario 的 GIVEN 原文与映射的测试，以及 S2 的 verify

#### Scenario: kit-packets-preserves-notes
- **GIVEN** `slices/S1.md` 已有机械区，标记之后有主会话写的一段说明
- **AND** 之后 `slices.json` 里 S1 的 owns 多了一个文件
- **WHEN** 再次运行 `plan-kit.py packets --change-dir`
- **THEN** 机械区出现新文件，标记之后的说明逐字不变
