# DRAFT. 与测试无关的路径由仓库声明，并与依赖图对账

- Status: accepted
- Date: 2026-11-18
- 关联：DRAFT-final-incremental-by-dependency-anchor（修订其决策 5「`ship` 按两棵树的差判 final 是否过期」里「差」的口径，原 ADR 不改）· DRAFT-baseline-reuse-by-content-fingerprint · DRAFT-baseline-reuse-via-dependency-anchor · DRAFT-gate-test-result-handoff-and-runner-contract
- 来源 change：ship-rerun-hardening（design D1–D4）

## Context

`ship` 只认对齐 HEAD 的 final，final 之后只容忍记账文件。`/pr-ship` 的记忆沉淀提交改的是 CLAUDE.md，不在其列，于是每次收口都要重跑一次 final。

重跑走增量还是全量取决于依赖图。本仓有依赖图，重跑是「增量、重跑 0 个文件」；afa 的依赖图没接通，2026-11-18 统计它收口阶段的 final 全量 49 次，原因全部是「没有可用锚点」。基线复用同理：`CLAUDE.md`、`.claude/skills/…`、迁移脚本这类改动被算成「有非测试文件改动」，退回全量。

门禁已有两项仓库声明：`global`（一改就全量）与 `blind`（每次都重跑），都是「依赖图看不见、所以要多跑」。没有反方向的声明：「这些路径改了也不影响测试结论」。

不能按文件类型替仓库判断：本仓就有读 `CLAUDE.md`、README 与命令文档的测试。

## Decision

1. **`inert` 是仓库声明**：`<openspec 根>/gate-scope.json` 的可选字段，仓库相对路径 glob 数组。模板不给缺省、不按扩展名推断。
2. **只放宽测试结论的复用**：匹配的路径在三处与记账文件同等看待——`ship` 的新鲜度；final 的同树沿用与取锚点的 Δ；baseline 的复用判定。起飞前的「基线过期」判定、lint / typecheck 结论的沿用、`gate.impacted` 的 Δ 都不看它。
3. **五类路径永不生效**：测试路径、全局文件、`global` 命中的路径（`global` 赢）、`changes/` 下的路径、三份声明文件。
4. **能机械判定的错在起飞前拦**：选测复核里，glob 匹配到已跟踪的测试路径、全局文件或 `global` 路径即判红；锚点池里有同指纹且测到依赖图的锚点时，取最新一条对账，有测试文件依赖了声明的路径即判红。
5. **运行时依赖图优先**：final 与 baseline 用到的锚点显示某路径被测试文件依赖时，该路径不按 `inert` 处理，照常选测并警告。
6. **没有依赖图就没有对账**：这种仓库里声明对不对只靠人在 PR 里审，契约文档写明这一点。
7. **`/pr-ship` 的重跑由 `ship` 裁决**：记忆沉淀提交之后先跑 `ship`，理由里没有「final 过期」就不重跑。

否决的方案：

- **按扩展名把文档 / 配置当无关**：会让读文档的测试漏跑。
- **只在运行时兜、不判红**：声明错了没人知道，换到没有依赖图的环境就真的漏测。
- **做进内容比对函数本身**：它的调用方里有不该放宽的判定（基线过期、lint 结论沿用）。
- **把沉淀挪到 apply 的 final 之前**：沉淀要读评审结论与整段对话，属于收口之后的工作。

## Consequences

- **更易**：
  - 声明之后，记忆沉淀提交不再让 final 过期，收口少一次重跑；
  - 没有依赖图的仓库，文档类改动不再把基线拖回全量；
  - 有依赖图的仓库，「没有任何用例触及的非 Python 文件」不再触发全量，前提是把它声明出来。
- **更难**：
  - 门禁的可信计算基多了一份人写的声明；
  - 排查「为什么没重跑」要多看一处 `gate-scope.json`。
- **盲区**（接受）：依赖图测不到的仓库里，错误的 `inert` 声明会让改动不触发重跑。缓解：不做缺省；五类路径永不生效；`doctor` 注明「无法对账」；`final --full` 随时可用。
- **兼容**：没写 `inert` 的仓库行为不变。旧版脚本读到这个字段会报「未知字段」，回退模板时要同时删掉它。
