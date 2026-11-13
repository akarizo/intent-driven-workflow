## Why

同一个概念在 proposal、specs、代码里换着说法写，是 spec 漂移的源头：scenario 措辞会变成测试和验收，词一歧义，测试就钉错东西。现在的 `grill-me` 只追问设计分支，不管用词；仓库里也没有任何术语表，模型每次都按自己的理解起名。

外部的 `grill-with-docs`（mattpocock 风格）多了两件事：访谈时对照术语表纠正用词、当场把定下的词写回；以及提议写 ADR。前者正是本仓库缺的，后者与本仓库已有的 adr 工件和 `architectural-decision-records` skill 重复，且目录、编号格式冲突（`docs/adr/0001-*` 对 `openspec/adr/DRAFT-*`）。

2026-11-13 用 `grill-me` 访谈定下四点（Q1–Q4）：

- **位置**：`openspec/glossary.md`，不用根目录 `CONTEXT.md`，也不写进 CLAUDE.md。
- **使用范围**：`grill-me` 访谈时读写；schema 的 proposal 与 specs instruction 也引用它。
- **写入时机**：术语定下就写；当前分支是默认分支（如 `main`）时先列出、问过再写。
- **机械检查**：`spec.html` 审批面板列出工件里的避用词命中，只提示、不阻断。

## What Changes

- **`grill-me` 新增术语表一节**（`template/.claude/skills/grill-me/SKILL.md`，原有段落不动）：
  - 开场先读 `openspec/glossary.md`；文件不存在不新建，第一个术语定下时才建。
  - 用户用词与表里定义冲突、或用了避用词时当场指出；用词含糊时提出规范词，作为一个问题来问。
  - 用户回答后当场写入；当前分支是默认分支时不写文件，访谈末尾列出待写词条，问过再写。
  - 只收本项目特有的概念，只写定义、不写实现细节。
  - 写明词条格式：`**规范词**：定义`，可选紧跟一行 `避用：别名、别名`。
- **schema 引用术语表**（`template/openspec/schemas/intent-driven/schema.yaml`）：proposal 与 specs 两个 instruction 各加一段——有 `openspec/glossary.md` 时用其中的规范词，不用 `避用：` 行列出的别名。
- **审批面板列出避用词命中**（`template/.claude/hooks/spec_html.py` 与模板 `spec.html.tmpl`）：
  - 渲染时读 `openspec/glossary.md`，扫本 change 的 `proposal.md`、`design.md`、`specs/**/*.md`。
  - 命中就在面板里多出一节「术语对照（只提示）」，逐行列出 `文件:行 · 避用词 → 规范词`。
  - 不算命中：落在规范词本身里的（如规范词「飞行计划」、避用词「计划」）、代码块与行内代码里的；纯 ASCII 别名按整词、不分大小写匹配。
  - 没有术语表或没有命中时，面板不出现这一节。
  - 只提示，不改退出码，不进 slice-gate，不加 hook。
- **说明**：`README.md` 的 `grill-me` 一行与 `spec-html-render/SKILL.md` 的 block 清单补上术语表。
- **不做**：
  - 多上下文（`CONTEXT-MAP.md`）；
  - `grill-me` 里提议 ADR（schema 的 adr 工件已有「长期架构承诺」触发器）；
  - 模板预置词条（`glossary.md` 不进 `install.sh` 种子清单，属用户数据）；
  - 执行体写代码时对照术语表。

## Capabilities

### New Capabilities

- `domain-glossary`：项目术语表 `openspec/glossary.md` 的格式；`grill-me` 访谈对照并维护它；proposal / specs 按它用词；spec.html 列出工件里的避用词命中（只提示）。

### Modified Capabilities

- 无。`openspec/specs/` 不存在，`grill-me` 与 spec.html 原有行为不变，本 change 的增量以 ADDED 写在新 capability 里。

## Impact

- **代码**：`template/.claude/hooks/spec_html.py`。
- **模板**：`template/.claude/skills/spec-html-render/templates/spec.html.tmpl`（新增一个空的 `glossary` 块，默认不显示）。
- **文档**：`template/.claude/skills/grill-me/SKILL.md`、`template/.claude/skills/spec-html-render/SKILL.md`、`template/openspec/schemas/intent-driven/schema.yaml`、`README.md`。
- **ADR**：新增 `template/openspec/adr/DRAFT-domain-glossary-in-openspec.md`。
- **测试**：新增 `tests/test_spec_html_glossary.py`、`tests/test_glossary_docs.py`；钉住 schema / README / 审批面板文本的现有测试不改，须保持绿。
- **下游**：已安装的仓库跑 `./install.sh --upgrade` 拿到新 skill 与 schema；`install.sh` 不改。
- **顺带发现（不在本 change 范围）**：`template/openspec/config.yaml` 的 rules 用了键 `spec`，schema 的工件 id 是 `specs`，`openspec instructions` 每次都报 `Unknown artifact ID in rules: "spec"`，`gherkin-authoring` 这条规则从未生效。
