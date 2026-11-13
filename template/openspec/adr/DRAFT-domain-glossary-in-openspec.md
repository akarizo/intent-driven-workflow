# DRAFT. 项目术语表是 openspec 下的持久工件，格式由脚本解析，检查只提示不阻断

- Status: accepted
- Date: 2026-11-13
- 来源 change：grill-glossary（design D1 · D2 · D5）

## Context

同一个概念在 proposal、specs、代码里换着说法写，会让 scenario 措辞和测试钉错东西。模板此前没有任何术语载体，`grill-me` 只追问设计、不管用词。

外部的 `grill-with-docs` 用根目录 `CONTEXT.md` 当术语表，并顺带在 `docs/adr/0001-*` 写 ADR。本仓库的意图工件集中在 `openspec/`，ADR 走 `openspec/adr/DRAFT-*` 与合并时定号，两套直接并存会让术语与决策散在两处。

2026-11-13 用户在 `grill-me` 访谈里定下：术语表放 `openspec/glossary.md`；`grill-me` 与 schema 的 proposal / specs instruction 使用它；spec.html 列出避用词命中，只提示。

## Decision

1. **位置**：项目术语表是 `<repo>/openspec/glossary.md`，与 `adr/`、`changes/` 并列的持久工件，属用户数据：不进 `install.sh` 种子清单，升级不覆盖，第一次定下术语时才建。模板只给规则与格式，不预置词条。
2. **格式是契约**：每个词条一行 `**规范词**：定义`，可选紧跟一行 `避用：别名、别名`；其余行忽略。`grill-me` 按它写，`spec_html.py` 按它读；改格式等于改契约，要另立 ADR。
3. **强制力只到「人看得见」**：避用词命中只在 spec.html 里列出，由人批准时决定；不进 `slice-gate.py lint`，不加 hook，不改任何退出码。术语表读不出时等于没有，不报错。
4. **写方唯一**：只有 `grill-me` 访谈（或人手改）写术语表；schema 与脚本只读。

## Consequences

- **更易**：一个概念一个规范词、记在一处；访谈时当场纠偏；批准时一眼看到工件里用错的词。
- **更难**：中文没有词边界，命中按子串判，靠「长者先占」与跳过代码压误报，仍会有少量误中；格式写错时功能静默关闭，没有报错提示。
- **中性**：不做多上下文（`CONTEXT-MAP.md`），单仓库一份表；`grill-me` 不再提议 ADR，ADR 仍由 schema 的 adr 工件按「长期架构承诺」触发。
