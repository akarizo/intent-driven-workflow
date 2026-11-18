# DRAFT. 没有依赖图时，只改了测试文件的 final 只重跑这些文件

- Status: accepted
- Date: 2026-11-18
- 关联：DRAFT-final-incremental-by-dependency-anchor（修订其决策 4「没有可用锚点即全量」，加一个例外，原 ADR 不改）· DRAFT-baseline-reuse-by-content-fingerprint（同一条「只改测试文件」判据）· DRAFT-gate-test-result-handoff-and-runner-contract（结果文件 `mode` 新增取值）· DRAFT-unmeasured-deps-need-plan-statement
- 来源 change：ship-rerun-hardening（design D5–D7）

## Context

`DRAFT-final-incremental-by-dependency-anchor` 让 final 以锚点为基准按依赖图增量运行，并规定「没有可用锚点」时全量。依赖图没接通的仓库因此每次 final 都全量，包括评审修复只改了一个测试文件的那一次。

baseline 早有一条不靠依赖图的复用路（`DRAFT-baseline-reuse-by-content-fingerprint`）：自上次基线以来只改了 `test_*.py`，就复用上次的全量结论、只补跑这些文件。final 没有对应的路。

final 每次实跑都在 git 共用目录留一份记录，含当时的树、指纹与结论；红的记录带着最近一次绿的树。`gate.impacted` 已经把它当锚点用。

C1 之后，依赖图未测的仓库必须在计划里表态才能起飞。表态接受全量，不等于连「只改了一个测试文件」也要全量。

## Decision

1. **例外条件**：final 没有可用锚点（不含锚点链到上限的情形）、没配 `gate.impacted`、不是 `--full` 时，若本 change 有一次绿 final，且其后的改动去掉记账文件与生效的 `inert` 路径后只含 `test_*.py`，就只重跑这些测试文件，其余用例沿用那次绿 final 的结论。
2. **从严的四个前提**：没有测试分层文件；增量重跑能等价复现 `gate.test`；那次绿 final 的测试命令与分层指纹同当前；改动的测试文件不含基线的预存红、不命中 `global`。任一不成立即全量。
3. **重跑红即红**：重跑里的失败、超时、异常退出都直接判 final 红，不退回全量。
4. **不写锚点、不设链长上限**：这条路没有依赖图可记；沿用的集合只会因重跑而缩小。
5. **如实标注**：结果里来源记为 `tests-only`；交给检查的结果文件 `mode` 为 `tests-only`，逐用例结局与沿用数为空、`complete` 为假。
6. **预告与实际同一个判定**：成本预告与 `ship` 的「final 过期」理由用同一个函数；因为有非测试文件而走不了这条路时，全量原因点名这些文件。

否决的方案：

- **没有绿 final 时拿基线当起点**：基线到当前树的改动是整个 change，本来就不只有测试文件。
- **补跑红时退回全量**（baseline 的做法）：baseline 需要一份完整的基线，final 只需要一个结论。
- **不要求可等价复现**：补跑会用门禁自己的解释器而不是仓库的运行器，final 是最后一道，不接受这个差异。

## Consequences

- **更易**：依赖图没接通的仓库，评审修复只改测试时不再整跑一遍；仍要全量时原因里写明是哪些文件造成的。
- **更难**：final 多了一条运行路径；检查若枚举了结果文件 `mode` 的全部取值，需要认新取值。
- **盲区**（接受，与基线复用相同）：被别的测试文件 import 的 `test_*.py` 改了，只重跑它自己；`conftest.py` 是全局文件，不走这条路。
- **兼容**：有可用锚点的仓库不受影响；包装脚本类仓库要配 `gate.pytest` 才用得上。
