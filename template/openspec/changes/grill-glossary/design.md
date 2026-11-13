## Context

**现状**：

- `grill-me`（`template/.claude/skills/grill-me/SKILL.md`）只有 4 句：追问每个设计分支、一次一问、每问附推荐、能查代码就不问。它不读也不写任何文档。
- `template/openspec/config.yaml` 规定 proposal 阶段必须用 `grill-me`；schema（`template/openspec/schemas/intent-driven/schema.yaml`）的 proposal / specs instruction 不涉及用词。
- 仓库没有术语表。`openspec/` 下现有的持久工件只有 `adr/`；`install.sh` 只按清单下发 `openspec/` 种子（`.gitignore` · `config.yaml` · `changes/.gitkeep` · `adr/.gitkeep` · `superpower/.gitkeep`），其余一律算用户数据，不覆盖。
- `spec_html.py` 按模板 `spec.html.tmpl` 的 `<!-- block:NAME -->…<!-- /block:NAME -->` 占位整段替换，内容为 `None` 的块保留模板原样（`substitute_block`）。审批时要人参考、但不阻断的提示（选测范围、测试成本预告）目前都放在 `flight` 块里。

**用户决策**（2026-11-13，`grill-me` 访谈 Q1–Q4，AskUserQuestion）：

- **Q1 位置**：`openspec/glossary.md`。
- **Q2 范围**：`grill-me` + schema 的 proposal / specs instruction。
- **Q3 写入**：定下即写；当前分支是默认分支时先列出、问过再写。
- **Q4 检查**：spec.html 列出避用词命中，只提示。

**在役 ADR**：没有约束术语或 `grill-me` 的 ADR。`DRAFT-repo-selector-reports-scope-at-plan-time` 决策 6 的「审批页可见、由人放行」与本设计的 D5 同一思路；`DRAFT-memory-as-fifth-resident-carrier` 的「软判断只提醒、不阻断」与 D5 一致。本设计不偏离任何在役 ADR。

```
C4 · 容器图（轻量 C4 风格；★ 新增，◆ 修改）

 [人类] ──回答访谈问题──▶ ◆ grill-me skill ──读 / 写──▶ ★ openspec/glossary.md
                                                            │ 读
                 ┌──────────────────────────────────────────┤
                 ▼                                          ▼
 ◆ schema.yaml（proposal / specs instruction）      ◆ spec_html.py ──扫──▶ proposal.md · design.md · specs/**
     ↳ 模型写工件时用规范词                              │ 命中
                                                         ▼
                                              ◆ spec.html「术语对照」一节 ──看──▶ [人类批准]
```

- **边界**：术语表是项目数据，模板只给规则和格式，不给词条。
- **写方唯一**：只有 `grill-me` 写术语表（人也可以手改）；schema 和 `spec_html.py` 只读。
- **强制力**：没有阻断点。schema 是对模型的指令；spec.html 给人看，人决定改不改。
- **假设**：下游项目的工件主要用中文写，别名常是规范词的一部分（「计划」之于「飞行计划」），所以误报控制是 D4 的重点。

## Goals / Non-Goals

**Goals**：

- 一个概念一个规范词，记在一处，访谈当场维护。
- 写 proposal / specs 时模型有表可依。
- 人批准时能看到工件里哪些地方用了避用词，不用自己逐行找。

**Non-Goals**：

- 多上下文（`CONTEXT-MAP.md`）。
- `grill-me` 提议 ADR（schema 的 adr 工件已有触发器）。
- 模板预置词条；`install.sh` 不改。
- 执行体（slice-executor）写代码、起名时对照术语表。
- 任何阻断：不进 `slice-gate.py lint`，不加 hook，不改 spec.html 渲染退出码。
- 把术语表登记进 `claudemd-standard.md` §12b 的载体表：它和 `adr/` 一样是 `openspec/` 下按需读的意图工件，不是常驻载体。

## Decisions

### D1 · 位置：`openspec/glossary.md`

和 `adr/`、`changes/` 并列，是 `openspec/` 下又一份持久工件。

- **为什么**：意图工件集中在 `openspec/`；schema 可以照引用 `<repo>/openspec/adr/` 的方式引用它；`spec_html.py` 已有 `project_root(change_dir)` 定位 `openspec/adr/`，同法定位术语表；`install.sh` 不在种子清单里的文件都算用户数据，升级不覆盖，不用改安装器。
- **备选**：
  - 根目录 `CONTEXT.md`（mattpocock 约定）：放在 `openspec/` 之外，和 CLAUDE.md 同级，容易被当成另一种记忆文件；
  - CLAUDE.md 的一节：每会话常驻，有行数预算，违反「有正式归宿只留指针」。
- **懒建**：模板仓库自己的 `template/openspec/` 兼作本仓库的工作区，将来这里建 `glossary.md` 也不会下发给下游（不在种子清单）。

### D2 · 词条格式是脚本契约

```markdown
# 术语表

<可选：一两句说明本项目>

## <可选分组>

**<规范词>**：<一两句定义：它是什么，不写怎么实现>
避用：<别名>、<别名>
```

- **词条行**：`**规范词**：定义`，冒号中英文都认。正则 `^\*\*([^*]+)\*\*\s*[：:]\s*\S`。
- **避用行**：紧跟在词条之后（中间可以隔其他行，归属最近的上一个词条），`避用：` 开头，冒号中英文都认；别名按 `、` `，` `,` `/` 拆开，去掉首尾空白，空的丢掉。
- **其余行**一律忽略（标题、说明、空行）。避用行出现在第一个词条之前也忽略。
- **为什么**：比 `grill-with-docs` 的 `_Avoid_:` 少一层 Markdown 斜体，标签用中文；一个词条两行，人手改也不容易写坏。去掉原版的「示例对话」与「Flagged ambiguities」：前者是噪音，后者在访谈里当场解决。
- **备选**：YAML / JSON 结构化文件——解析更稳，但人读起来不像术语表，`grill-me` 当场追加也更容易写坏缩进。

### D3 · `grill-me` 怎么用术语表

在 `SKILL.md` 原有 4 句之后新增「术语表」一节，原文一字不动：

- **开场先读**；文件不存在不新建，第一个术语定下时再建。
- **对照**：用户用词与定义冲突、用了避用词时当场指出；用词含糊时提出规范词，作为一个问题来问（仍附推荐答案）。
- **对照代码**：用户描述的行为与代码矛盾时先指出。
- **定下即写**：用户回答即确认，当场写入。
- **默认分支例外**：`git branch --show-current` 是仓库默认分支（如 `main`）时不写文件，访谈末尾列出待写词条，问过再写——避免在主工作区留下未提交改动。走 `/opsx-propose` 时会话已在 change worktree 里，这条不触发。
- **准入**：只收本项目特有的概念；通用编程概念不收；只写定义，不写实现细节，不当草稿本。
- **格式**照 D2 原样写进 skill，注明 `spec_html.py` 按它解析。

### D4 · 命中判定（`spec_html.py`）

**扫哪些文件**：本 change 目录下的 `proposal.md`、`design.md`、`specs/**/*.md`，按路径排序。`tasks.md`、`slices/` 不扫：前者由 `slices.json` 生成，后者是给执行体的施工说明，不是意图。

**每行怎么判**：

1. **去掉代码**：围栏代码块（```` ``` ```` 之间）整段跳过；行内代码 `` `…` `` 先换成等长空白，保持列位置。
2. **候选词**：全部规范词 + 全部避用词，按长度从长到短。
3. **占位**：依次在这一行里找每个候选词，跳过与已占位置重叠的匹配；找到就占住这一段。规范词占住不报；避用词占住就记一条命中。
4. **ASCII 别名**：只含 ASCII 字符的词按整词匹配（前后不是 `[A-Za-z0-9_]`），不分大小写；含非 ASCII 字符的词按子串匹配（中文没有词边界）。
5. **去重**：同一行同一个避用词只记一条。

- **为什么要「长者先占」**：别名常是规范词的一部分（「计划」⊂「飞行计划」），或别名之间互相包含（「任务」⊂「子任务」）。不先占，每一处规范词都会被报成命中，提示就没人看了。
- **备选**：分词库——引入新依赖，且对项目自造词无效。

### D5 · 面板怎么显示

- **新块** `glossary`：加进 `BLOCK_NAMES`；模板里在 `capabilities` 与 `specs` 两节之间放一个**空的**占位 `<!-- block:glossary --><!-- /block:glossary -->`，不进侧栏导航。
- **有命中**：块内容是一整节 `<section id="glossary">`，标题「术语对照（只提示）」，一张表：`位置`（`proposal.md:3`，相对 change 目录）· `避用词` · `规范词`。
- **没有术语表 / 没有命中**：块内容为 `None`，模板的空占位原样保留，页面上什么都不出现；不计入 footer 的 section 数。
- **容错**：读或解析术语表时出任何异常都按「没有术语表」处理，不影响面板其他部分，不改退出码（铁律 10：脚本失效时保留占位）。
- **为什么不放进 `flight` 块**：`flight` 块只在有 `slices.json` 时才渲染；术语对照在只写了 proposal 时（`/opsx-continue`）也该能看到。
- **备选**：写入时 hook 警告（反馈最早，但要新增 hook、改 settings.json 与 `install.sh` 的 hook 合并，Q4 已否决）；`slice-gate.py lint` 判红（lint 只管 `slices.json`，且误报会锁死起飞）。

### D6 · schema 两处 instruction

- **proposal**：在 Capabilities 段之后加一段：`<repo>/openspec/glossary.md` 存在时先读，用每个词条的规范词，不用 `避用：` 行列出的别名；新术语在 `grill-me` 访谈里定下并写回。
- **specs**：在 Gherkin-style content requirements 段里加一条：requirement 与 scenario 文字必须用规范词，不用避用词；spec.html 会列出命中。
- **design / adr / tasks** 不加：design 也会被 D4 扫到，但它不是对外契约，不额外加指令，免得每个 instruction 都膨胀。
- **约束**：`cd template && openspec schema validate intent-driven` 必须绿，用 `gate.checks` 在 baseline 与 final 各跑一次。

## Risks / Trade-offs

- **[常见词作别名，误报多]** → D4 的长者先占 + 跳过代码；只提示不阻断；词条由人在访谈里定，别名选得太宽是人看得见、改得了的。
- **[中文子串误中]**（别名「上线」命中「上线程池」这类拼接）→ 接受。只提示；要彻底解决得引入分词，不值得。
- **[模型不照 schema 用词]** → 正是 D5 存在的原因：漏掉的会在面板上被人看到。
- **[`grill-me` 在默认分支上被调用，人没回应待写词条]** → 词条丢失，下次访谈再定。比弄脏 `main` 好。
- **[下游项目改了 `glossary.md` 格式]**（比如用 `_Avoid_:`）→ 解析不到避用行，面板不出这一节，等于功能关闭，不出错。

## Migration Plan

- 下游跑 `./install.sh --upgrade` 拿到新的 `grill-me`、schema、`spec_html.py` 与模板；不需要迁移任何用户文件。
- **回退**：把这三处恢复到旧版即可；`glossary.md` 留在项目里无害。

## Open Questions

- 无。四个分叉已在访谈里定下；本 change 不改任何在役 ADR。
