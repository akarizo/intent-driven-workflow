## ADDED Requirements

### Requirement: grill-me 访谈对照并维护术语表
`grill-me` SHALL 在访谈开始时读 `openspec/glossary.md`（存在时），用户用词与表里定义冲突、用了避用词或用词含糊时 SHALL 当场指出并提出规范词；用户回答后 SHALL 当场把定下的术语按文档写明的格式写进 `openspec/glossary.md`，但当前分支是仓库默认分支（如 `main`）时 MUST NOT 直接写文件，改为访谈末尾列出待写词条、问过再写。术语表 MUST 只收本项目特有的概念、只写定义。
Feature: 访谈顺手把词定准，并留在一个地方
Rule: 用户的回答就是确认；默认分支上不弄脏工作区

#### Scenario: grill-me-challenges-against-glossary
- **GIVEN** `template/.claude/skills/grill-me/SKILL.md` 与 `README.md`
- **WHEN** 阅读 grill-me 的术语表一节
- **THEN** 它写明先读 `openspec/glossary.md`，不存在时等第一个术语定下再建
- **AND** 写明用户用词与表里定义冲突或用了避用词时当场指出，用词含糊时提出规范词
- **AND** 原有的「一次问一个问题」与「能查代码就不问」两句仍在
- **AND** `README.md` 里 grill-me 那一行提到 `openspec/glossary.md`

#### Scenario: grill-me-writes-resolved-term-except-on-main
- **GIVEN** `template/.claude/skills/grill-me/SKILL.md` 的术语表一节
- **WHEN** 阅读其中关于写入的规则与格式说明
- **THEN** 它写明用户回答后当场写入，不攒到最后
- **AND** 写明当前分支是默认分支（如 `main`）时不写文件，访谈末尾列出待写词条、问过再写
- **AND** 写明词条格式为 `**规范词**：定义`，可选紧跟一行 `避用：`，别名用 `、` 分隔
- **AND** 写明只收本项目特有的概念、不写实现细节

### Requirement: proposal 与 specs 按术语表用词
schema 的 proposal 与 specs 两个 instruction SHALL 各自写明：`openspec/glossary.md` 存在时用其中的规范词，不用 `避用：` 行列出的别名；schema MUST 保持 `openspec schema validate intent-driven` 通过。
Feature: 访谈后写的工件也照着同一张表用词
Rule: 引用写在 schema 里，不写在用户的 config.yaml 里

#### Scenario: schema-proposal-and-specs-use-glossary
- **GIVEN** `template/openspec/schemas/intent-driven/schema.yaml`
- **WHEN** 分别切出 proposal 工件与 specs 工件的 instruction
- **THEN** 两段都提到 `openspec/glossary.md` 与 `避用`
- **AND** design、adr、tasks 三个工件的 instruction 不提 `glossary`

### Requirement: 审批面板列出工件里的避用词（只提示）
`spec_html.py` 渲染时 SHALL 读项目的 `openspec/glossary.md`，扫本 change 的 `proposal.md`、`design.md` 与 `specs/**/*.md`，命中避用词时在面板里输出「术语对照」一节，逐条列出 `文件:行`、避用词与规范词；命中位置落在任一规范词的出现范围内、或在代码块与行内代码里时 MUST NOT 算命中；同一处被长短两个词同时覆盖时只按较长的那个算；纯 ASCII 的避用词 SHALL 按整词、不分大小写匹配。没有术语表或没有命中时 MUST NOT 输出这一节。这一节只提示，渲染退出码 MUST 不受影响。
Feature: 人在批准时一眼看到哪里用错了词
Rule: 只提示不阻断；误报宁少

#### Scenario: spec-html-lists-avoided-term-hits
- **GIVEN** 项目的 `openspec/glossary.md` 有词条「切片」（避用：任务、子任务）与「起飞」（避用：上线）
- **AND** change 的 `proposal.md` 第 3 行写着「本次上线拆成三个任务」，`specs/x/spec.md` 第 5 行写着「每个子任务独立门禁」
- **WHEN** 运行 `spec_html.py --change-dir <change>`
- **THEN** 退出码为 0，面板里有「术语对照」一节
- **AND** 列出 `proposal.md:3` 的「上线 → 起飞」与「任务 → 切片」，以及 `specs/x/spec.md:5` 的「子任务 → 切片」
- **BUT** `specs/x/spec.md:5` 只有这一条，不另报「子任务」里面的「任务」

#### Scenario: spec-html-omits-glossary-section-without-hits
- **GIVEN** 两个项目：一个没有 `openspec/glossary.md`；另一个有术语表，但 change 工件里一个避用词都没用
- **WHEN** 分别运行 `spec_html.py --change-dir <change>`
- **THEN** 两次退出码都为 0
- **AND** 两份面板都没有「术语对照」一节，只留下模板里空的 `glossary` 占位

#### Scenario: spec-html-skips-canonical-and-code-hits
- **GIVEN** 术语表有词条「飞行计划」（避用：计划）与「切片」（避用：task）
- **AND** change 的 `proposal.md` 里，「飞行计划」出现在正文里，「计划」只出现在行内代码 `` `计划` `` 与一个代码块里，`tasks.md` 只作为文件名出现在正文里
- **WHEN** 运行 `spec_html.py --change-dir <change>`
- **THEN** 面板里没有「术语对照」一节
- **AND** 同一份 `proposal.md` 再加一行正文「这个 Task 很急」后重新渲染，面板列出这一行的「task → 切片」
