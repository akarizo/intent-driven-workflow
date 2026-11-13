---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
---

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase, explore the codebase instead.

## 术语表

本项目的术语表是 `openspec/glossary.md`。访谈时按下面的规则读它、对照它、维护它。

- **开场先读**：访谈开始先读 `openspec/glossary.md`。文件不存在时不新建，等第一个术语定下时再建。
- **对照用词**：用户的用词与表里的定义冲突，或用了某个词条的避用词时，当场指出。用词含糊时提出规范词，作为一个问题来问（仍附推荐答案）。
- **对照代码**：用户描述的行为与代码矛盾时，先指出矛盾再问。
- **定下即写**：用户回答后术语就算定下，当场写入 `openspec/glossary.md`，不攒到最后。
- **默认分支例外**：`git branch --show-current` 是仓库默认分支（如 `main`）时不写文件，访谈末尾列出待写词条，问过用户再写。
- **准入**：只收本项目特有的概念，通用编程概念不收。只写定义，不写实现细节，不当草稿本。

格式：

```markdown
# 术语表

<可选：一两句说明本项目>

## <可选分组>

**<规范词>**：<一两句定义：它是什么，不写怎么实现>
避用：<别名>、<别名>
```

每个词条一行 `**规范词**：定义`，可选紧跟一行 `避用：`，别名用 `、` 分隔。`spec_html.py` 按这个格式解析，审批面板据此列出工件里的避用词。
