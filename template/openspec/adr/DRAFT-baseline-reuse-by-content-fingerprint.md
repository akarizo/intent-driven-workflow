# DRAFT. 基线按内容指纹复用全量结果

- Status: accepted
- Date: 2026-10-15
- 关联：DRAFT-test-gate-baseline-diff · DRAFT-gate-evidence-not-self-reported · DRAFT-workflow-edition-repo
- 来源 change：baseline-incremental-reuse（design D1–D10；摘自原仓 #65 `855b834`，按本仓改写）

## Context

起飞前的基线（`slice-gate.py baseline`）每次都跑全量、lint / typecheck 与每片 verify。本仓一遍约 100 秒；原仓 afa 一遍约 10 分钟，其中全量 447 秒。改计划之后要不要重跑全靠模型判断，而 preflight 的 `plan_sha` 只认命令字符串，看不出测试文件与门禁脚本的内容变化。

全量预存红集只取决于代码树与全量命令。同一仓库的各 worktree 共享 git 对象库，不同 change 对同一棵代码树跑全量，结论相同。

原仓 #65 已按这个思路实现。它的独立评审 deferred 了 13 条问题，其中一条指出 ADR 原文「不会把红判成绿」不成立：跨 change 整份沿用对方的预存红名单时，名单可能混进指纹外差异造成的红。本 change 移植时修正。另外，本仓没有账本，「是否已起飞」要换用本仓自己的事实。

## Decision

- **代码树按内容判同**：
  - 基线记录 `snapshot`（未提交改动的 git blob id；软链取链接文本的 blob）与 `cmd_key`（命令文本把本 change 路径归一成占位符，加上命令里直接写出的仓库内文件内容）；
  - 比较两棵代码树时逐路径比 blob id，不比 commit；
  - 运行副产物登记在 `byproducts`，未跟踪时不计入差异。
- **只有测试文件变了才复用全量**：差异只有 `test_*.py`、不涉及候选的预存红、补跑差异文件不红 → 复用候选的全量结果；同一组差异文件只补跑一次，补跑红即回全量。其余一律跑全量；`--full` 强制全量。
- **跨 change 只复用全绿**：
  - 全绿且指纹非空的全量写进 git common dir 下的基线池，同仓各 worktree 共享，按 `cmd_key` 匹配；
  - 别的 change 的结果只在 `test.exit == 0` 时复用；
  - 同一 change 内可沿用自己的预存红。
- **代码树完全没变时 lint / typecheck 也沿用**：只限本 change 自己的上一次基线，用不排除其他 change 目录的严格差异判断，且命令与命令指纹不变。
- **不计入差异**：各 change 的计划与门禁脚本目录（`<changes 根>/**`，同一 change 内的门禁脚本除外）、字节码、pytest 缓存、未跟踪的副产物；仓外内容（数据仓、解释器环境）不检测。
- **preflight**：本 change 的 `timeline.md` 还没有 `approve` 事件时按内容判过期；之后保持原四项校验。

否决的方案：

- **按 commit 相等复用**：起飞提交工件、预合并、pull 只带进范围外的提交，都会让它失效。
- **由模型判断是否重跑**：违反「判据不自证」；而且实际出现过多跑。
- **跨 change 带预存红也复用、只把风险写进文档**：留着把红判成绿的窗口（用户 2026-10-15 否决）。
- **计入被 source 的门禁脚本**：各 change 的 `_env.sh` 各不相同，跨 change 永远不命中。
- **池放 refs**：refs 放门禁结论与快照，不放缓存。
- **以账本 takeoff 判起飞**：本仓没有账本（DRAFT-workflow-edition-repo）。

## Consequences

- **更易**：改计划后重跑基线只要秒级到分钟级；同一 main commit 上全绿的多个 change 只跑一次全量；preflight 能看出测试内容变了；不复用时 `reuse_skipped` 写明理由。
- **更难**：判定器的可信计算基多了差异计算、副产物登记与池；按文件名主干匹配预存红是保守近似，有测试覆盖。
- **盲区**：
  - 仓外漂移与被 source 的门禁脚本不在指纹里。因为跨 change 只复用全绿，最坏是本 change 上本来红的用例被当成绿：final 跑全量时它不在本 change 的预存红名单里，会判红。所以最坏是收口多出一条红，不会把红判成绿。
  - 需要时用 `--full`。lint 扫描计划工件目录时也用 `--full`。
- **兼容**：旧格式基线不作候选，下一次 baseline 跑全量后升级为新格式；新字段对旧代码透明。
