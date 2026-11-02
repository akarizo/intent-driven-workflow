## Why

工作流自己写的分类元数据一改动，选测逻辑就把整个文件当成「基础设施」，范围退回全量，而且没有任何人在计划期看得到。

- **afa 实测**（2026-11-02，change `cpdb-lru-position`）：propose 期按 ADR 把 3 个真实库测试登记为集成用例，改了 `executor/tests/tiering_registry.json`（+23 行，全是新文件的条目）。该文件在 afa 选测的 `INFRA_PATTERNS` 里，888 条登记集成用例（240 个文件）全选，baseline 跑了 474.7 秒；只拿掉登记表，受影响的集成文件只有 3 个。final 还会再全选一次。
- **模板自身同类缺陷**（临时仓库实证）：baseline 之后只在 `test-tiers.json` 的 `slow_allow` 加一条（等同 apply 期跑 `allow-slow`），或只给某区域的 `covers` 加一个 glob，final 都退回全量（`full_why` 为「没有可用锚点」）；不碰分层文件的对照组走增量。原因是锚点按整个分层文件的 blob 哈希过滤（`slice-gate.py:3967`、`:3982`），且 `GLOBAL_FILES` 含 `test-tiers.json`（`:3977`）。

模板改不到项目自己的选测代码，但能做两件事：把自己的分层文件改成按条目判定；给项目自带选测定一个范围报告契约，让「退化为全选」在计划期就被机械发现、由人类看着放行。用户决策（2026-11-02，决策页 `openspec/superpower/2026-11-02-scope-fallback-guard-decisions.html`，6 题全取推荐）。

## What Changes

- **A · 分层文件按条目参与增量 final**（简写形态）：
  - 锚点的分层指纹只由单元层（`unit.paths` / `unit.cmd`）算出；单元层变了照旧全量；
  - 已选区域的条目变了 → 该区域本次必跑；未选区域的改动不影响 final；
  - `slow_allow` 按用例 id 比对，新增或删除的条目所在测试文件并入重跑、G10 按新名单重判；
  - Δ 里的分层文件本身不再命中两条全量条件（全局文件、未被用例触及的非 Python 文件）；
  - 锚点额外记录各区域条目指纹与 `slow_allow` 清单。部件形态 final 恒全量，不变。
- **B · 项目自带选测的范围报告契约（计划期表态）**：
  - 计划可写 `gate.scope`，或仓库在 openspec 根放 `gate-scope.json`（`{"cmd": "..."}`）作默认；
  - `lint` 与 `preflight` 实跑选测命令（`waves` 不跑，超时 300 秒），库经 `GATE_SCOPE_OUT` 给出文件路径，命令写入 `{"full", "triggers", "count"}`；
  - 报告全选时，计划须在 `gate.scope_full_reason` 为每个触发项写理由，键与本次触发项必须完全一致；
  - 选测命令失败（非 0 / 超时 / 报告不合法）即 lint 红；
  - `spec.html` 显示选测命令、来源与「触发项 → 理由」表；
  - 两个新字段不进 `plan_sha`。
- **文档**：schema tasks instruction、`/opsx-propose` 与同名 skill、`/opsx-verify` 与同名 skill、`/test-tiers` 的「放行慢单测」、README。

## Capabilities

### New Capabilities
- `tier-file-incremental`: 分层文件按单元层 / 区域 / `slow_allow` 三块参与增量 final，不再整体触发全量
- `gate-scope-report`: 项目自带选测的范围报告契约，全选须在计划里逐项表态并显示在审批页

### Modified Capabilities
<!-- openspec/specs/ 尚无已归档的 spec；被取代的「分层文件 → 全量」条款来自未归档 change incremental-final，由新 ADR supersede -->

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`（锚点写入、`_tiers_key`、`GLOBAL_FILES`、final 增量选择、lint / preflight 的选测范围核对）、`template/.claude/hooks/spec_html.py`（选测范围小节）。
- **文档**：`template/openspec/schemas/intent-driven/schema.yaml`、`template/.claude/commands/{opsx-propose,opsx-verify,test-tiers}.md`、`template/.claude/skills/{openspec-propose,openspec-verify-change}/SKILL.md`、`README.md`。
- **ADR**：新增两份 DRAFT；其一 supersede `DRAFT-final-incremental-by-dependency-anchor` 决策 4 中「分层文件」一项（原文件不改）。
- **兼容**：锚点格式变化，升级后各仓库第一次 final 全量一次；未配分层、未配选测命令的仓库行为不变。
- **不在范围**：afa 侧 `tiering_select.py` 的登记表按条目差分、afa 输出范围报告的子命令（afa 自己的 change）；`gate.impacted` 在 final 的退化；baseline / final 侧的范围记录。
