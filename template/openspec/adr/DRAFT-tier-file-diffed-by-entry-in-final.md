# DRAFT. 分层文件按条目参与增量 final，只有单元层改动才全量

- Status: accepted, supersedes ADR-DRAFT-final-incremental-by-dependency-anchor（仅决策 4 中「分层文件」一项，及决策 1 里「分层指纹」的口径）
- Date: 2026-11-02
- Supersedes: DRAFT-final-incremental-by-dependency-anchor（合并时回填真实号；只取代上述两处，其余决策在役）
- 关联：DRAFT-test-tiers-unit-baseline-by-audit-probe（保持在役）
- 来源 change：scope-fallback-guard（design D1–D4）

## Context

`DRAFT-final-incremental-by-dependency-anchor` 决策 4 把分层文件 `test-tiers.json` 列为全局文件，决策 1 让锚点带「分层指纹」（实现为整个文件的 blob 哈希）。当时的考虑是：分层文件变了，单元层与区域的范围都可能变，锚点里的结论不再可信。

但分层文件里大部分条目与单元层范围无关，apply 期又恰好会改到它们：

- 门禁报 G10 后人类放行慢单测，`allow-slow` 往 `slow_allow` 写一条；
- 区域的 `covers` / `paths` 随模块调整。

2026-11-02 在临时仓库实证：baseline 后只加一条 `slow_allow`、或只给区域 `covers` 加一个 glob，再改一行源码，final 都退回全量（「没有可用锚点」）；不碰分层文件的对照组走增量。

同一天 afa 出现同一类问题：工作流自己写的分类登记表被选测逻辑整体当成基础设施，baseline 全选 888 条集成用例。用户要求模板侧先把自己的这一处修好。

## Decision

1. **分层指纹只取单元层**：简写形态下，锚点与 final 指纹里的分层指纹由 `unit`（`paths` 与 `cmd`）的规范 JSON 算出。单元层变了，锚点照旧不可用，final 全量。部件形态不变（其 final 恒全量）。
2. **锚点记录区域与放行**：每条锚点另记各区域条目指纹与 `slow_allow` 的用例 id 清单。
3. **final 按块收窄**：
   - 已选区域的条目与锚点不同（或锚点没有它）→ 该区域本次必跑；未选区域的改动不影响 final；
   - `slow_allow` 新增或删除的用例 → 其所在测试文件（落在单元层的）并入重跑，G10 按当前名单判定；理由文字不参与比较。
4. **分层文件不再是全局文件**：Δ 里的 `test-tiers.json` 不命中「全局文件」与「未被任何用例触及的非 Python 文件」两条全量条件；它的影响全部由上面三条决定。

否决的方案：

- **只给 `slow_allow` 开白名单，其余改动仍全量**：覆盖最常见的场景，但区域调整照样全量；用户选了三块分别比对。
- **按 JSON 文本 diff 判断**：格式化、键序变化都会误判；按解析后的条目比较更稳。
- **维持整文件哈希、靠 `--full` 以外的手段跳过**：没有机械依据，等于把判断交给模型。

## Consequences

- **更易**：apply 期放行慢单测、调整区域后，final 仍走增量；放行的用例所在文件会被重跑，G10 按新名单重判。
- **更难**：锚点多了 `tiers_detail` 一段，排查「为什么这个区域跑了」要看它与当前条目的比对。
- **代价**：锚点格式变化，升级后各仓库第一次 final 全量一次。
- **盲区**（接受）：区域 `paths` 改动只让该区域重跑，不追究被移出该区域的文件；单元层 `paths` 不变时这些文件不会悄悄进入单元层，不属于任何层的文件由 G12 与 `/test-tiers check` 拦。
- **与在役 ADR**：`DRAFT-final-incremental-by-dependency-anchor` 的其余决策（锚点、依赖图实测、默认增量、其它全量条件、同树沿用、扩展点）继续有效；`DRAFT-test-tiers-unit-baseline-by-audit-probe` 不受影响。
