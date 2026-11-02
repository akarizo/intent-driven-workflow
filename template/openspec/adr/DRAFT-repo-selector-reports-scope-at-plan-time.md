# DRAFT. 项目自带选测须在计划期报告范围，退化为全选须逐项表态

- Status: accepted
- Date: 2026-11-02
- 关联：DRAFT-final-incremental-by-dependency-anchor（决策 7 扩展点，保持在役）· DRAFT-gate-evidence-not-self-reported · DRAFT-gate-paired-checks-by-exit-code（均保持在役）
- 来源 change：scope-fallback-guard（design D5–D10）

## Context

模板的 `gate.test` 对项目是黑盒。有的仓库在 `gate.test` 里自带选测：按相对主干的改动只跑受影响的测试，遇到「基础设施」改动就保守地全选。

afa 2026-11-02 的 change `cpdb-lru-position`：propose 期按 ADR 把 3 个真实库测试登记为集成用例，改动了登记表 `executor/tests/tiering_registry.json`；afa 的选测把该文件列为基础设施，于是 888 条登记集成用例（240 个文件）全选，baseline 跑了 474.7 秒，而只拿掉登记表时受影响的集成文件只有 3 个。直到 baseline 跑完都没有人看见「全选」这件事。

模板改不到项目自己的选测代码，但能定一个契约，让退化在计划期就被机械发现。用户选择「计划期表态」，而不是只在 baseline / final 告警。

## Decision

1. **声明**：计划可写 `gate.scope`（只算范围、不跑测试的命令）；仓库可在 openspec 根放 `gate-scope.json`（`{"cmd": "..."}`）作为默认，计划没写时使用它。
2. **契约**：在 git 顶层运行，超时 300 秒；库经环境变量 `GATE_SCOPE_OUT` 给出文件路径，命令写入 `{"full": bool, "triggers": [..], "count": int?}`。
3. **运行时机**：`slice-gate.py lint` 与 `preflight` 实跑一次；`waves` 不跑。
4. **失败即拦**：命令非 0、超时、报告缺失或不合法 → lint / preflight 红。
5. **逐项表态**：报告全选时，计划须在 `gate.scope_full_reason` 为每个触发项写理由，键集合与本次触发项完全相等；未全选却写了理由、没有选测命令却写了理由，同样红。
6. **审批页可见**：spec.html 显示选测命令原文、来源与「触发项 → 理由」表。
7. **不进 `plan_sha`**：两个字段不影响 baseline 的测试结论。

否决的方案：

- **只在 baseline / final 告警**：baseline 已经跑完才看见，代价已经付出；用户选了计划期表态。
- **理由写一段自由文字**：审批页看不到具体触发项，也无法核对理由是否过期。
- **报告走 stdout 最后一行**：选测命令的日志会挤掉它。
- **不设仓库级默认、只靠 propose 文档提醒**：模型忘写就完全没有保护，正是 afa 这次的情形。
- **选测命令失败只警告**：保护会悄悄失效；与 afa 自己「算不出范围就抛错、不静默退回全量」的取向一致。

## Consequences

- **更易**：选测退化为全选时，propose 的 lint 当场点名触发项；人类在 spec.html 里看着触发项与理由决定是否起飞。仓库声明一次，之后每个 change 都受保护。
- **更难**：配了选测命令的仓库，每次 lint / preflight 多跑一次（afa 量级约 10 秒）；仓库要自己实现一个遵守契约的只算范围命令。
- **边界**（接受）：报告的真伪模板无法核验——命令报 `full: false` 而实际全选，模板看不出。缓解：命令在仓库内可审，`gate.scope` 原文显示在审批页，`gate-scope.json` 只能经 PR 修改（DRAFT-gate-evidence-not-self-reported 的「判据从哪来、谁能伪造」）。
- **范围外**：`gate.impacted` 在 final 的退化、baseline / final 侧的范围记录留给后续 change。
