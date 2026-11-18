## ADDED Requirements

### Requirement: 只改 CLAUDE.md 的提交不该换来一遍全量，除非别无依据
final 绿之后只提交了 `CLAUDE.md` 的改动时，收口行为 SHALL 按仓库的配置分三种：
- 依赖图已测、没有声明 `inert`：`ship` 判 final 过期，重跑 final 走增量、重跑 0 个文件（既有行为，由守卫测试钉住）；
- 声明了 `inert` 且含该文件：`ship` 仍判 final 新鲜，不需要重跑；
- 依赖图未测、也没有声明：重跑 final 走全量，全量原因 SHALL 点名该文件，成本预告与 `ship` 的「final 过期」理由 SHALL 事先说明这次是全量并点名该文件。
Feature: 记忆沉淀提交之后的收口
Rule: 能不跑就不跑，要全量就事先说清为什么

#### Scenario: claude-md-commit-with-inert-keeps-ship-fresh
- **GIVEN** 仓库声明 `inert` 为 `["CLAUDE.md"]`，final 已绿
- **AND** 之后只提交了 `CLAUDE.md` 的改动
- **WHEN** 运行 `slice-gate.py ship`
- **THEN** reasons 里没有含「过期」的条目

#### Scenario: claude-md-commit-without-graph-or-inert-runs-full-and-names-file
- **GIVEN** 依赖图测不到、也没有声明 `inert` 的仓库，final 已绿
- **AND** 之后只提交了 `CLAUDE.md` 的改动
- **WHEN** 依次运行 `flight-doctor.py forecast --json`、`slice-gate.py ship`、`slice-gate.py final`
- **THEN** 预告的 `final.mode` 为 `full`，`final.why` 含 `CLAUDE.md`
- **AND** ship 有一条理由同时含「final 过期」「补跑将是全量」与 `CLAUDE.md`
- **AND** final 的 `incremental.mode` 为 `full`，`full_why` 含 `CLAUDE.md`

### Requirement: /pr-ship 先裁决再决定是否重跑 final
`/pr-ship` 在记忆沉淀提交之后 SHALL 先运行 `slice-gate.py ship`：reasons 里没有 `final 过期` 时 MUST NOT 重跑 final；有时才重跑。要不要重跑 MUST 由 `ship` 的输出决定，模型不自行判断。评审修复之后的重跑规则不变。
Feature: 重跑由脚本裁决
Rule: 零 token 优先

#### Scenario: pr-ship-asks-ship-before-rerunning-final
- **GIVEN** 本 change 合入后的 `template/.claude/commands/pr-ship.md`
- **WHEN** 读 step 2b（记忆层沉淀）
- **THEN** `slice-gate.py ship` 出现在 `slice-gate.py final` 之前
- **AND** 写明 reasons 含 `final 过期` 才重跑，否则「不重跑 final」
- **AND** 不再有「沉淀 commit 之后重跑：」这句无条件说法
