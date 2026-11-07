## ADDED Requirements

### Requirement: 内建提供方在计划期预测 final 是否退化
Rule: 模板内建提供方的报告 SHALL 针对**预测的 final Δ**：tracked 文件中匹配任一切片 owns glob 的那些。报告的触发项取以下各条命中的全部，`full` = 有触发项。

- **全局文件**：预测 Δ 里的全局文件（与增量 final 同一清单），触发项是该文件路径。
- **无法等价复现**：`gate.test` 无法被增量 final 等价复现（pytest 之后带白名单外选项，且 `gate.pytest` 没配或没覆盖）时，触发项是 `final:gate-test-unreproducible`。
- **依赖图没见过的文件**：预测 Δ 里现存的、依赖图（含 shell 静态闭包）没见过的文件，触发项是该文件路径。排除以下几类：
  - 测试文件；
  - `.py` 文件，与 final 一样只警告；
  - 文档；
  - 工作流声明文件。
- **锚点**：
  - lint 用锚点池里命令指纹与分层指纹都匹配的最新锚点；
  - preflight 用当前树能取到的锚点，通常就是刚跑完的基线锚点；
  - lint 或 baseline 取不到锚点时，不报这一类触发项，而是把预测 Δ 里现存的、上述排除项以外的非 Python 文件列为**待定**。为待定项预写的理由不算多余；摘要注明「final 精确预测在 preflight」；
  - preflight 取不到锚点时，触发项是 `final:no-anchor`。
- **库外**：不在 git 仓库里时，只做 `gate.test` 识别与全局文件检查。全局文件检查按 owns 条目的文件名判定；这种情况不会出现在真实仓库里。
- **基线缺逐用例记录**：preflight 时基线有失败、但缺 `failed_nodes`，触发项是 `final:baseline-missing-failed-nodes`。

`gate.test` 不是 pytest（`npm test`、`go test ./...`、`cargo test`），或分层文件是部件形态时，final 恒全量属于设计边界：报告不全选，摘要注明「final 恒全量（设计边界）」。

#### Scenario: planned-global-file-is-trigger
- **GIVEN** 仓库声明 `{"builtin": true}`，`gate.test` 是 pytest 命令
- **AND** 切片 owns 含 `pyproject.toml`，该文件已被跟踪
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** 缺理由的触发项含 `pyproject.toml`

#### Scenario: planned-unseen-non-python-file-is-trigger
- **GIVEN** 仓库声明 `{"builtin": true}`，基线已跑并写下依赖图；`scripts/helper.sh` 从未被任何用例触及
- **AND** 切片 owns 含 `scripts/helper.sh`
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0
- **AND** 缺理由的触发项含 `scripts/helper.sh`

#### Scenario: preflight-reports-missing-anchor
- **GIVEN** 仓库声明 `{"builtin": true}`，基线绿，但锚点池随后被清空
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出非 0
- **AND** 缺理由的触发项含 `final:no-anchor`

#### Scenario: non-pytest-runner-is-by-design
- **GIVEN** 仓库声明 `{"builtin": true}`，计划的 `gate.test` 是 `npm test`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0
- **AND** stderr 摘要行含「设计边界」

### Requirement: 工作流声明文件不触发全量
Rule: 增量 final 的「Δ 含依赖图没见过的非 Python 文件 → 全量」一条 SHALL 跳过以下工作流声明文件：
- `<openspec 根>/gate-scope.json`；
- `<openspec 根>/gate-checks.json`；
- `<openspec 根>/test-tiers.json`（与现行相同）；
- git 顶层 `.claude/` 下的一切。

这些文件只被 Claude Code 与门禁工具读取。若有测试在运行时触及它们，照常按依赖选中这些测试。全局文件规则不受影响。

#### Scenario: declaration-files-do-not-force-full
- **GIVEN** 基线已跑并写下依赖图
- **WHEN** 随后只改了 `openspec/gate-scope.json`（内容仍合法）并新增 `.claude/settings.json`，然后运行 `slice-gate.py final`
- **THEN** final 走增量，不是全量
- **AND** 输出没有 `full_why`

### Requirement: shell 静态闭包计入依赖
Rule: 一个测试文件的实测依赖里有 shell 脚本时（后缀 `.sh` / `.bash`，或首行 `#!` 指向 sh、bash、zsh、dash），库 SHALL 静态解析这些脚本，把解析到的仓库文件并入该测试文件的依赖。并入的结果既用于增量选中，也用于「依赖图没见过」判定。

解析规则：
- 跳过注释行；
- `$(dirname "${BASH_SOURCE[0]}")`、`$(dirname "$0")`、`${BASH_SOURCE%/*}`、`${0%/*}`（含引号变体）视为脚本所在目录；
- 被赋予这些形式（含 `$(cd … && pwd)` 包裹）的变量，其引用 `$V` / `${V}` 同样视为脚本所在目录；
- 路径记号先按脚本所在目录解析，再按 git 顶层解析，只保留存在的仓库文件；
- 文件名含未解析的 `$`、但目录能解析时，取该目录下同后缀的全部文件；
- 新到达的 shell 脚本递归解析。

解析不到的引用不补依赖，现行规则照旧生效，即仍判全量。

#### Scenario: sourced-shell-file-selects-its-tests
- **GIVEN** `tests/test_run.py` 用子进程运行 `bash scripts/run.sh`，`run.sh` 用 `source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"` 引入 `scripts/lib.sh`；基线已跑
- **WHEN** 随后只改了 `scripts/lib.sh`（行为不变），然后运行 `slice-gate.py final`
- **THEN** final 走增量
- **AND** 重跑的测试文件恰为 `tests/test_run.py`

#### Scenario: shell-closure-resolves-common-forms
- **GIVEN** `scripts/run.sh` 依次写了：
  - `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`；
  - `source "$SCRIPT_DIR/lib/common.sh"`；
  - `. "${BASH_SOURCE%/*}/env.sh"`；
  - 对 `a`、`b` 循环调用 `"$SCRIPT_DIR/units/$u.sh"`；
  - `bash tools/x.sh`。
- **AND** `scripts/lib/common.sh` 又 `source ./scripts/lib/deep.sh`；相关文件都存在，`tools/x.sh` 位于仓库根
- **WHEN** 对 `{"scripts/run.sh"}` 求 shell 静态闭包
- **THEN** 结果含 `scripts/lib/common.sh`、`scripts/lib/deep.sh`、`scripts/env.sh`、`scripts/units/a.sh`、`scripts/units/b.sh`、`tools/x.sh`

#### Scenario: unresolvable-shell-reference-stays-full
- **GIVEN** `tests/test_run.py` 运行 `bash scripts/run.sh`，`run.sh` 写的是 `source "$(lib_dir)/lib.sh"`（目录由函数算出，静态解析不到）；基线已跑
- **WHEN** 随后只改了 `scripts/lib.sh`，然后运行 `slice-gate.py final`
- **THEN** final 走全量
- **AND** `full_why` 含 `scripts/lib.sh`
