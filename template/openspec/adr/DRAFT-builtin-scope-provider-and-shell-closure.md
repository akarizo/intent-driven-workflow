# DRAFT. 内建选测提供方与 final 的依赖补全：声明文件不触发全量、shell 静态闭包计入依赖

- Status: accepted, supersedes ADR-DRAFT-final-incremental-by-dependency-anchor（仅决策 4 中「Δ 含依赖图从未见过的非 Python、非文档文件」一项）
- Date: 2026-11-07
- Supersedes: DRAFT-final-incremental-by-dependency-anchor（合并时回填真实号；只取代上述一项，其余决策在役；分层文件一项早已由 DRAFT-tier-file-diffed-by-entry-in-final 取代）
- 关联：DRAFT-scope-provider-mandatory-with-runtime-guard（同一 change）· DRAFT-tier-file-diffed-by-entry-in-final（保持在役）
- 来源 change：scope-guard-enforced（design D5–D7）

## Context

增量 final 有一条规则：Δ 含依赖图从未见过的非 Python、非文档文件 → 全量。依赖图来自运行时审计（Python 进程的 `open`、子进程 argv、Python 子进程的 sitecustomize）和静态 import 闭包。这条规则在两类情况下误报：

- **bash 子进程读的文件看不见**：测试运行 `bash scripts/run.sh` 时，`run.sh` 在依赖图里，但它 `source` 的 `lib/_common.sh` 不在。改 `_common.sh` → final 全量。这与 afa 2026-11-07 的 `executor/bin/*` 全选是同一类错误。afa 侧用只读脚本推演过，静态解析就能反查到绝大多数引用：252 个文件解析出 194 条引用边。
- **工作流声明文件也被算进去**：`gate-scope.json`、`gate-checks.json`、`.claude/**` 只被门禁工具与 Claude Code 读取，改它们也会让 final 全量。

同时，新 ADR `DRAFT-scope-provider-mandatory-with-runtime-guard` 要求模板内建提供方在计划期预测 final 是否退化，预测规则须与 final 实际判定同源。

## Decision

1. **触发项单一出处**：final 的全量判定与内建提供方的计划期预测，共用同一套规则，得到全部触发项。
   - 文件类触发项用仓库相对路径；
   - 其它类用稳定代码：`final:no-anchor`、`final:baseline-missing-failed-nodes`、`final:gate-test-unreproducible`。
   - final 的原因文字取第一条触发项。
2. **计划期预测**：
   - 预测的 final Δ = tracked 文件中匹配任一 owns glob 的那些；
   - lint 用锚点池里最新的匹配锚点；preflight 用当前树取到的锚点（通常是刚写的基线锚点）；
   - lint 取不到锚点时只做静态检查，preflight 取不到锚点时报 `final:no-anchor`；
   - 非 pytest 运行器与部件形态的 final 恒全量，属于设计边界，只注明，不要求写理由。
3. **声明文件不触发「没见过」全量**：
   - 排除 `<openspec 根>/gate-scope.json`、`<openspec 根>/gate-checks.json`、git 顶层 `.claude/**`，并保留分层文件的排除；
   - 不排除整个 `openspec/**`，因为种子文件可能被 bash 子进程消费（本仓库 `install.sh` 正是如此），整个排除会漏选。
4. **shell 静态闭包计入依赖**：
   - 测试依赖里的 shell 脚本，静态解析以下几类引用：
     - `source` / `.` / 字面路径；
     - dirname 形态，以及由 dirname 赋值的变量；
     - 文件名含变量时，取该目录下同后缀的全部文件；
   - 递归求闭包，结果并入该测试文件的依赖，既用于增量选中，也用于「没见过」判定；
   - 解析不到的引用不补依赖，现行规则照旧（全量）。

否决的方案：

- **整个排除 `openspec/**`**：会漏选，理由见决策 3。
- **运行期追踪 bash 读文件**（`BASH_ENV` 注入或系统调用追踪）：侵入性大、平台相关，而且拖慢每个测试。
- **在计划期用「池锚点 vs 当前树」的 Δ 预测**：池里的锚点可能很旧，会混进别的 change 的文件。

## Consequences

- **更易**：
  - 新装仓库改脚本库、改工作流配置，final 不再退回全量；
  - 内建提供方的计划期预测与 final 实际判定同源，不会漂移。
- **更难**：shell 解析是启发式的，排查「为什么选中这个测试」时要看闭包。
- **边界**（接受）：
  - 其它语言子进程（node、make 等）读到的文件仍看不见，按现行规则全量，并在计划期被点名；
  - 由函数或命令替换算出的路径解析不到。
- **与在役 ADR**：`DRAFT-final-incremental-by-dependency-anchor` 的其余决策（锚点、依赖图实测、默认增量、其它全量条件、同树沿用、扩展点）继续有效。
