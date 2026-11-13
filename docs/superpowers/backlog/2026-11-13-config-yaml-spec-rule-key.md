# backlog · `template/openspec/config.yaml` 的 rules 用了不存在的工件 id `spec`（2026-11-13）

## 现象（本轮 1 次，未达 E 类门槛，先记 backlog）

`template/openspec/config.yaml` 的 `rules:` 下有一个 `spec:` 键（`- Must use gherkin-authoring skill`），但 schema `intent-driven` 的工件 id 是 `specs`。`openspec instructions <artifact> --change <name>` 每次在输出最前面打印：

```
Unknown artifact ID in rules: "spec". Valid IDs for schema "intent-driven": adr, design, proposal, specs, tasks
```

影响：

- 这条规则从未生效，生成 specs 时不会注入「Must use gherkin-authoring skill」；
- 这行警告混在 stdout 里，`openspec instructions ... --json` 的输出不能直接按 JSON 解析（change `grill-glossary` 的 propose 阶段就因此解析失败，改为直接读 `schema.yaml`）。

## 修法

把 `spec:` 改成 `specs:`。按 mini change 处理，`tests/` 里先 grep 有没有断言钉住 `config.yaml` 原文，有就并入同片 owns。

## 防线（Q4 ✓：可机械判定）

加一条测试：读 `template/openspec/config.yaml` 的 `rules` 键集合，断言它是 `schema.yaml` 里 `artifacts[].id` 集合的子集。
