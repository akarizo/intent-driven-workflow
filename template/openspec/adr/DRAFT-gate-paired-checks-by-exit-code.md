# DRAFT. 仓库自定义的成对检查只按退出码判定，数据放 git common dir

- Status: accepted
- Date: 2026-10-17
- 关联：DRAFT-gate-evidence-not-self-reported · DRAFT-baseline-reuse-by-content-fingerprint · DRAFT-test-gate-baseline-diff（均保持在役）
- 来源 change：slice-gate-paired-checks（design D2–D8、D11）

## Context

afa 仓重构测试体系时要两类门禁：覆盖对拍（merge-base 与分支头各量一次覆盖再对齐比较）与共用包联动回归（按改动触发，在另一个子项目环境跑，按它自己的基线差分）。两者都要「两次测量 + 比较」，`gate.test` / `lint` / `typecheck` 的单次运行加失败集差分装不下。afa 的 CI 不跑 executor 的测试，飞行流程的 slice-gate 是唯一生效的门禁。

测量方式与比较规则都和仓库强相关。模板若去理解它们，会变成每个仓库的定制代码。

## Decision

slice-gate 提供一个通用扩展点 `gate.checks`：每个检查给出 `baseline`（可空）与 `final` 两条命令。

- **只看退出码**：0 为绿，非 0 或超时为红。slice-gate 不解析检查的输出，只把完整输出落盘、在红的提示里带末尾若干行。
- **时机固定**：baseline 在全量、lint / typecheck、每片 verify 之后运行 `baseline` 命令，红即基线红；final 在 G7 绿时、全量判定之后运行 `final` 命令，红记 G9。切片门禁不跑。
- **环境契约**：工作目录是 git toplevel；注入 `GATE_PHASE`、`GATE_CHANGE`、`GATE_BASE_COMMIT`（基线的 commit）、`GATE_CHECK_DIR`。
- **数据交接放 git common dir**：`flight-gate-checks/<change>/<name>/`，同仓各 worktree 可见、不进 commit；baseline 实跑前清空。
- **沿用与 lint / typecheck 同口径**：只沿用本 change 自己的旧基线，严格差异为空且命令与指纹不变时才沿用；跨 change 一律实跑。
- **仓库默认检查显式抄写**：openspec 根目录的 `gate-checks.json` 列出的检查，每个 change 要么写进 `gate.checks`，要么在 `gate.checks_skip` 写理由，由 lint 机械校验；不做隐式合并。

否决的方案：

- **把覆盖对拍做进模板**：测量方式、对齐规则、数据仓指纹都是 afa 特有，进模板就成了单仓库的定制代码。
- **让 slice-gate 解析检查输出**（如读一个结果 JSON）：每加一种检查就要改模板的解析代码；退出码已足够表达红绿。
- **数据放 change 目录**：覆盖数据很大，会被提交，也会被 baseline 的运行期间改动判定当成改动。
- **仓库默认检查自动并入每个计划**：评审在计划里看不到实际会跑什么，与「判据可见、人类审批」相悖。
- **跨 change 沿用检查结果**：检查测的往往正是本 change 的代码与它自己目录里的数据，借别人的会错。

## Consequences

- **更易**：仓库可以挂任意「两次测量 + 比较」的门禁，不改模板；红绿判定仍是零 token。
- **更易**：未配置检查的仓库与 change 行为、输出、`plan_sha` 都不变。
- **更难**：检查的正确性全在仓库脚本里，模板只保证它被运行、结果被尊重；脚本写错（该红时退出 0）模板看不出来。
- **更难**：检查脚本若被划进某个切片的 `owns`，执行体可以改弱它；信任模型与 `gate.test` 指向仓内脚本时相同，靠计划审批与 G6 所有权兜住。
- **代价**：`.git/flight-gate-checks/` 下的数据没有自动回收，按 change 目录手动清理。
- **代价**：沿用看不出仓外状态的变化（数据仓、解释器环境），要靠 `baseline --full`。
