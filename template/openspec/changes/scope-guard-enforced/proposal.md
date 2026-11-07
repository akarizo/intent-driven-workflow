## Why

装上模板的仓库仍然可能**没人知情地跑全量**。2026-11-07 afa change `export-xlsx-aparam-override` 的 baseline 跑了 683.8 s，原因是门禁范围算成了 11343 条（单元 9416 + 集成 1927），集成层全选；直到 baseline 跑完才有人发现。S2、S3 计划改 `executor/bin/*`，所以 final 还会再全选一次。

起因是 afa 自己的选测器退化，但模板有 5 个断点，才让它变成「没人知情」。这 5 个断点对**任何**新装或升级的仓库都成立：

1. **安装器不种选测声明**：`install.sh:382` 只种 `.gitignore`、`config.yaml` 和三个 `.gitkeep`，新装与 `--upgrade` 之后都没有 `gate-scope.json`。
2. **没有声明时 lint 静默跳过**：`slice-gate.py:1566` 在没有命令时直接 `return errors, None`。afa 这次 lint 是绿的，审批页上什么也没有。
3. **契约看不到切片计划改的文件**：`slice-gate.py:1511` 只给选测命令传 `GATE_SCOPE_OUT`。计划期只看得到 propose 时的 diff（骨架 + 登记表），看不到 owns 里将改的 bin。
4. **baseline / final 开跑前不复核范围**：`slice-gate.py:3416` 写完运行标记就直接跑 `gate.test`。lint 被跳过或计划后改，baseline 照样全量。
5. **模板内建增量自己也会退回全量**：`_full_why` 有一条「Δ 含依赖图没见过的非 Python 文件 → 全量」（`slice-gate.py:4294-4306`）。bash 子进程 `source` 的文件测不到，工作流自己的声明文件（`gate-scope.json`、`.claude/**`）也会被算进去。这与 afa 的 `executor/bin/*` 是同一类错误。

用户要求（2026-11-07）：**新装与升级都必须不再犯这个错误，目标是可靠的模板工作流**。决策页 `template/openspec/superpower/2026-11-07-scope-guard-enforced-decisions.html` 共 Q1–Q9，用户全取推荐（grill-me 以该决策页完成）。

## What Changes

- **契约 v2：每个仓库必有选测提供方**（**BREAKING**：「没有声明 → 静默跳过」改为「没有声明 → 红」）。
  - 提供方按优先级解析：计划 `gate.scope` > `<openspec 根>/gate-scope.json` > 未声明。
  - `gate-scope.json` 新增 `{"builtin": true}`（模板内建）一种形态，与 `{"cmd": "..."}` 二选一。
  - 未声明 → lint / preflight / baseline / final 红。唯一例外是本 change 自己建立声明（owns 含 `gate-scope.json`）：这时须为伪触发项 `scope:undeclared` 写理由，审批页标出。
  - `builtin` 配上认不出的 `gate.test`（不是 pytest、test-tiers 驱动或探测出的标准命令）→ 红，提示改用 cmd 提供方。
- **计划文件交给提供方**：新增 `GATE_SCOPE_PLANNED`（各片 owns 的并集，一行一条，glob 原样）和 `GATE_SCOPE_CHANGE`（change 目录的仓库相对路径）。计划期报告因此能覆盖 final 会改的文件。
- **内建提供方**（`slice-gate.py` 内置，不起子进程）：预测模板内建增量 final 会不会退回全量，包括全局文件、依赖图没见过的非 Python 文件、`gate.test` 无法等价复现、没有可用锚点。lint 用锚点池里最新的锚点预测；preflight 用刚跑完的基线锚点精确预测。非 pytest 运行器和部件形态的 final 本来就恒全量，属于设计边界：只注明，不要求写理由。
- **运行期守卫**：
  - baseline 开跑前复核范围：未表态的全选不跑 `gate.test`，基线红，不写运行标记。
  - final 开跑前复核：内建看 `_full_why`，cmd 重跑提供方。未表态 → 不跑测试，final 红。`--full` 是显式要求，豁免。
  - 理由以 approve 提交里的 `gate.scope_full_reason` 为准，批准后再改 → 红。
- **内建精度**：
  - 工作流声明文件（`<openspec 根>/gate-scope.json`、`<openspec 根>/gate-checks.json`、git 顶层 `.claude/**`）不再触发「依赖图没见过的非 Python 文件」这条全量规则。
  - 实测依赖里的 shell 脚本做静态闭包：`source` / `.` / 字面路径、`$(dirname "${BASH_SOURCE[0]}")` 及由它赋值的变量、文件名含变量时取整个目录的同后缀文件。闭包结果计入依赖，用于增量选中和全量判定。
- **安装器**：
  - 新装和 `--upgrade` 缺声明时都调用 `slice-gate.py scope-seed`。没有历史 change，或历史 `gate.test` 全部可识别 → 种 `{"builtin": true}`；否则不种，并在安装摘要醒目提示接入 cmd 提供方。
  - 已有声明不动，只打印出来。
  - 不新增参数、不交互（遵守 `DRAFT-installer-versioned-with-template` 决策 2）。
- **文档**：schema、`/opsx-propose`、`/opsx-apply`、`/opsx-verify` 及各自同名 skill、README 同步契约 v2。本仓库自己声明 `template/openspec/gate-scope.json` = `{"builtin": true}`。
- **不变**：`gate.scope` / `gate.scope_full_reason` 仍不进 `plan_sha`；报告形状 `{full, triggers, count?}`、300 秒上限、失败即红都不变；`gate.impacted`、部件形态 final 的判定不变。

## Capabilities

### New Capabilities

- `scope-provider-contract`：选测提供方的声明与解析（builtin / cmd / 未声明）、未声明判红与「本 change 建立声明」例外、builtin 误用判红、`GATE_SCOPE_PLANNED` / `GATE_SCOPE_CHANGE`、审批页显示提供方状态、`scope-seed` 判定。
- `builtin-scope-precision`：内建提供方在 lint / preflight 预测 final 是否退化；工作流声明文件不触发全量；shell 静态闭包计入依赖。
- `scope-runtime-guard`：baseline / final 开跑前复核，未表态的全选不跑、判红；理由以 approve 提交为准；`--full` 豁免。
- `install-scope-seed`：新装与升级时种选测声明、醒目提示、保留已有声明；文档描述契约 v2。

### Modified Capabilities

（无）选测范围契约的现行规格还在未归档的 change `scope-fallback-guard`（capability `gate-scope-report`）里，`openspec/specs/` 下没有主 spec，所以本 change 只用 ADDED。行为上的取代关系由新 ADR 记录。

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`（提供方解析、内建预测、shell 闭包、baseline / final 守卫、`scope-seed` 子命令）、`template/.claude/hooks/spec_html.py`（选测范围小节恒显示提供方状态）、`install.sh`（调用 `scope-seed`、摘要打印）。
- **测试**：新增 `tests/test_scope_contract_v2.py`、`tests/test_builtin_scope_precision.py`、`tests/test_scope_runtime_guard.py`；追加 `tests/test_spec_html_scope.py`、`tests/test_install.py`、`tests/test_scope_docs.py`。`tests/conftest.py` 的 `git_repo` 默认带一份「恒报未全选」的 cmd 声明，避免既有用例因「未声明 → 红」整体失效。⚠ `conftest.py` 是全局文件，所以本 change 自己的 final 必然全量，已在计划 `gate.scope` 如实声明。另顺带修了一个既有的不稳定用例：`tests/final_helpers.py::change_and_commit` 写完后把修改时间推后 2 秒，避免同一秒内的等长改写命中旧的字节码缓存与 pytest 断言改写缓存，并由新增的 `tests/test_final_helpers.py` 锁住。它曾让前三次基线变红；用户 2026-11-07 授权在起飞前、propose 期完成，见 design D15。
- **文档**：schema、3 个命令及各自同名 skill、README；2 份新 ADR，部分 supersede `DRAFT-repo-selector-reports-scope-at-plan-time` 与 `DRAFT-final-incremental-by-dependency-anchor`。
- **已装仓库**：升级后，历史 `gate.test` 可识别的仓库自动受保护。像 afa 这样自带选测的仓库，要先接入 cmd 提供方，否则新 change 会判红。afa 的接入 change 与本 change 并行推进，两边合入后再升级 afa。在飞的 change 用的是自己分支里的旧 `.claude`，不受影响。
- **无**新依赖、部署或数据变化。
