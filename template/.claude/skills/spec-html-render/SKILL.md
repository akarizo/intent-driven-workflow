---
name: spec-html-render
description: 把 OpenSpec change 工件渲染为单文件 HTML 审批面板 `openspec/changes/<change>/spec.html`。当 /opsx-propose 完成所有工件、/opsx-continue 创建一个工件、或用户运行 /spec-html 时调用。HTML 用于用户在浏览器一屏审批意图，不参与 OpenSpec merge。
---

# spec-html-render

把 OpenSpec change 下的 markdown 工件 (proposal / specs / design / tasks)、in-force ADR，以及飞行计划 (slices.json / timeline.md / gate-report.md) 渲染为一份**单文件 self-contained** 的 HTML 审批面板，让用户双击在浏览器里一眼审批 AI 即将做的事。

> **零 token**：渲染由 `spec_html.py` 脚本确定性完成，不需要模型读工件或拼 HTML。

## 何时触发

下面三种情况**全部**应当触发本 skill：

1. **/opsx-propose 全部工件创建完成后** — 命令第 4.5 步会调用本 skill (全量首次渲染)。
2. **/opsx-continue 创建完一个工件后** — 命令第 3.5 步会调用本 skill (按当前已存在的工件**全量重渲**，不增量补)。
3. **用户手动 /spec-html `<change-name>`** — 兜底 / 离线刷新。

不触发的情况：

- `/opsx-new` (只 scaffold change 目录，没有内容可渲染)
- `/opsx-explore` (探索阶段没有工件)
- `/opsx-archive` (归档不需要刷新 HTML)
- `/opsx-apply` (实施期间 tasks.md 勾选状态会变；如需重新出 HTML 让用户主动 /spec-html)

## 用法

```bash
python3 .claude/hooks/spec_html.py --change-dir openspec/changes/<change-name>
```

- 输出路径缺省 `<change-dir>/spec.html`，`--out PATH` 可覆盖；直接覆盖旧文件，不产生中间件。
- 模板缺省 `.claude/skills/spec-html-render/templates/spec.html.tmpl`，`--template PATH` 可覆盖。
- `--now ISO时间`（或环境变量 `SPEC_HTML_NOW`）固定 footer 时间戳；不传则取当前时间。
- 脚本按模板的 `<!-- block:NAME -->…<!-- /block:NAME -->` 占位契约整段替换：`title` / `change-name` / `meta-chips`（读 `openspec status --change <name> --json`，读不到则按工件文件是否存在判 done/blocked）/ `why` / `what` / `capabilities` / `glossary`（读 `openspec/glossary.md`，列出 proposal / design / specs 里的避用词命中；没有术语表或没有命中时保留空占位，页面不显示）/ `specs`（Requirement → `.requirement`，Scenario → `.scenario` + GIVEN/WHEN/THEN steps）/ `design` / `diagrams`（```mermaid 块）/ `adrs`（扫 `openspec/adr/`，含未定号的 `DRAFT-*.md`）/ `flight`（slices.json 切片表 + scenario↔test 状态 + timeline.md 事件）/ `tasks` / `footer`。`mockups` 块不生成，保留模板占位。未涉及或工件缺失的块保留原始 placeholder。
- **失败只 warn，不阻塞主流程**：change-dir 不存在、模板缺失等异常时脚本非 0 退出；调用方（/opsx-propose、/opsx-continue、/spec-html）应捕获后只提示，不让主流程失败。

## 设计原则

- **单文件 self-contained**：除 `https://cdn.jsdelivr.net/npm/mermaid@10/...` 外不引任何外部资源。
- **离线兼容**：Mermaid CDN 失败或 10s 超时时模板自动给 `<body>` 加 `.offline`，图的纯文本降级版以 `<pre>` 显示，不留白屏。
- **HTML 是 render layer**：事实来源是 markdown 工件与 slices.json/timeline.md/gate-report.md；脚本不发明工件里没有的事实，也不修改任何输入文件。
- **幂等**：同一份工件状态 + 同一个 `--now` 重跑 → 产物字节级一致（跨越 --now 的时间戳除外）。
- **不主动改 .gitignore**：spec.html 是否提交由用户决定。

## Guardrails

- **找不到模板时报错**：`templates/spec.html.tmpl` 不存在 → 脚本非 0 退出并在 stderr 报错，让用户检查 skill 是否完整安装。
- **不修改 markdown / slices.json 工件**：所有输入只读。
- **Mermaid 脚本段原样保留**：模板尾部的 `<script type="module">` 由模板固定，脚本不改写。其中 `startOnLoad` 恒为 `false` + 显式 `await mermaid.run()` —— 动态 import 落地时 window 的 `load` 事件早已触发，改回 `startOnLoad: true` 会让所有图**静默不渲染**。
