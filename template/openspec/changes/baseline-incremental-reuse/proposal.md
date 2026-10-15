## Why

`/opsx-propose` 每次都跑一遍完整基线；改了计划要不要重跑、重跑多少，全靠模型判断。原仓（Mod 版 `akarizo/intent-driven-claude-code`）2026-10-15 合入 #65（`855b834`，change `baseline-incremental-reuse`），按内容指纹增量复用基线。本仓 `slice-gate.py` 里没有对应实现（2026-10-15 检索 fingerprint / 指纹 / 基线池 / 复用，无结果）。

本仓实测（2026-10-15，main `3f98011`，用 change `workflow-edition` 的 4 片计划按 `cmd_baseline` 的顺序串行计时）：

| 段 | 耗时 |
|---|---|
| 全量 `python3 -m pytest -q tests` | 50.6 秒 |
| lint（`compileall`） | 0.1 秒 |
| 4 片 verify 串行 | 49.0 秒（S2 36.6 · S4 11.8 · S1 0.5 · S3 0.1） |
| 合计 | 约 100 秒 |

4 片 verify 跑的测试文件都在全量的 `tests` 里，全量刚跑过一遍。#65 只省「改计划后重跑」那一遍，第一次全量基线里的这 49 秒省不掉。

#65 合入时独立评审留了 13 条 deferred（原仓 `template/openspec/changes/baseline-incremental-reuse/review-findings.json`），其中 MEDIUM 4 条：

- **红判成绿**：跨 change 复用会整份沿用对方的预存红名单。名单里如果混进指纹之外的差异造成的红，本 change 把这些用例改坏时，final 会当预存红放过。原仓 ADR 写的「不会把红判成绿」不成立。
- **副产物死循环**：全量测试写出的未跟踪副产物，第二次全量时已经在开始快照里，被改写就判红，重跑仍红。人删掉它，preflight 又判过期。
- **软链崩溃与假差异**：`git hash-object --stdin-paths` 跟随软链。断链直接 traceback 并留下运行标记；有效软链算出的是目标内容的 blob，与 git 树里的链接文本 blob 对不上。
- **重复补跑**：同一组差异测试文件对最多 11 个候选各补跑一次，补跑红时还要按超时上限重复 11 遍，才回到全量。

LOW 6 条：
- 不复用的理由被丢弃；
- 池里有孤儿临时文件；
- 指纹为空的条目也会写进池；
- 运行期改动判定与差异的排除口径不一致；
- 文档漏写一条复用条件；
- 池的保留与容错没有测试。

本仓没有账本，#65 用「账本有无 takeoff」决定 preflight 是否按内容判过期，这里要改用本仓自己的起飞事实（ADR `DRAFT-workflow-edition-repo` 第 3 条：依赖插件的部分在本仓重新设计）。

用户决策（2026-10-15，会话内逐项问答，代替 grill-me 访谈）：
- 移植 #65；
- 跨 change 只复用全绿（`test.exit == 0`）的全量；
- 一并修掉 #65 的 deferred 问题；
- 代码树没变时 lint / typecheck 也沿用；
- 全量可度量时 verify 从全量结果推导；
- 不做「lint / typecheck 与全量并行」。

## What Changes

- **移植 #65 的内容指纹与增量复用**（`slice-gate.py baseline` / `preflight`）：
  - `gate-baseline.json` 记 `change`、`mode`、`snapshot`、`cmd_key`、每片 verify 的 `cmd`；
  - 差异 Δ 按 git blob 比较；
  - Δ 只有 `test_*.py`、不涉预存红、补跑不红 → 增量；verify 只重跑受影响的片；
  - 基线池放 git common dir，跨 change 复用；
  - `--full` 强制全量；
  - preflight 在首次起飞前按内容判过期。
- **起飞判据换成本仓事实**：preflight 是否按内容判过期，看本 change 的 `timeline.md` 有没有 `approve` 事件（`/opsx-apply` 第 4 步写入，在 preflight 之后），不读账本。
- **跨 change 只复用全绿**：别的 change 的全量只在 `test.exit == 0` 时复用；池只收全绿的全量。同一 change 内仍可沿用自己的预存红。
- **修 #65 遗留问题**：
  - 副产物登记进 `byproducts`，再次改写只警告，不计入差异；
  - 软链按链接文本取 blob；
  - 同一组差异文件只补跑一次，补跑红或超时就不再试别的候选；
  - 走全量时在 `reuse_skipped` 记下每个候选不复用的理由；
  - 池清理时删掉超过一小时的临时文件；指纹为空不入池；写池失败只警告；
  - 运行期改动判定排除其他 change 的目录。
- **代码树没变时 lint / typecheck 沿用上次**：本 change 自己的上一次基线与当前代码树按严格口径（只排除本 change 的计划工件、字节码、pytest 缓存与副产物）完全相同，且命令与命令指纹不变时，不再运行。
- **verify 从全量结果推导**：全量是可度量的直接 pytest 调用，且某片 verify 只是同一 pytest 前缀加白名单选项与测试文件路径时，按全量 junit 判，不单独运行。本仓首次基线约省下 verify 的 49 秒。
- **记录与文档**：
  - timeline 的 baseline 行标出「增量」与复用来源；
  - `opsx-propose` 命令与同名 skill 的基线步骤写明增量、跨 change、`--full`、推导与沿用；
  - README 同步。

## Capabilities

### New Capabilities
- `baseline-incremental-reuse`：基线内容指纹、同一 change 与跨 change 的增量复用（含副产物、软链、补跑去重、不复用理由、池卫生）、verify 按需重跑、preflight 按内容判过期（以 `approve` 事件为起飞判据）、记录与文档。
- `baseline-redundant-run-skip`：代码树没变时 lint / typecheck 沿用上次结论；全量可度量时 verify 从全量 junit 推导。

### Modified Capabilities
<!-- 无：template/openspec/specs/ 不存在，基线行为此前没有归档的 capability -->

## Impact

- `template/.claude/hooks/slice-gate.py`：
  - 改 `cmd_baseline`、`cmd_preflight`、`run_test_gate`（多返回 junit 用例集）；
  - 新增指纹、Δ、池、推导相关函数；
  - 新增 `baseline --full`。
- `template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md`（同改）、`README.md`。
- 测试：
  - 新增 `tests/test_baseline_incremental.py`、`tests/test_baseline_pool.py`、`tests/test_baseline_skip.py`、`tests/test_baseline_incremental_docs.py`；
  - `tests/test_slice_gate.py` 里对 verify 的完全相等断言放宽为只比 `exit`，对 lint 的完全相等断言放宽为只比 `exit` 与 `lines`。
- ADR：
  - 新增 `DRAFT-baseline-reuse-by-content-fingerprint`、`DRAFT-baseline-verify-derived-from-full-suite`；
  - `DRAFT-test-gate-baseline-diff` 继续有效，不 supersede。
- 兼容：
  - 旧格式 `gate-baseline.json`（没有 `snapshot`）不作候选，preflight 对它保持原四项校验；
  - `--full` 恒等于旧行为；
  - `opsx-apply` 不用改：它已在第 3 步跑 preflight，过期报错照常停飞。
- 已知边界：
  - 仓外漂移（数据仓、解释器环境）和被 source 的门禁脚本不在指纹里，用 `--full` 兜底；
  - lint 扫描本 change 计划工件目录时，沿用可能过时，也用 `--full`；
  - verify 推导看不出「单独运行才红」的顺序依赖用例，要到飞行中 G1 才暴露（用户已接受）。
