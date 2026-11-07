# DRAFT. 选测提供方必有、计划文件可见、baseline / final 开跑前复核

- Status: accepted, supersedes ADR-DRAFT-repo-selector-reports-scope-at-plan-time（仅决策 1、2、3、5；决策 4、6、7 在役，决策 7 补充 approve 绑定）
- Date: 2026-11-07
- Supersedes: DRAFT-repo-selector-reports-scope-at-plan-time（合并时回填真实号；只取代上述四条）
- 关联：DRAFT-installer-versioned-with-template · DRAFT-gate-evidence-not-self-reported（均保持在役）
- 来源 change：scope-guard-enforced（design D1–D4、D8–D12、D14）

## Context

`DRAFT-repo-selector-reports-scope-at-plan-time` 让项目自带选测在计划期报告范围，但有四处让它形同虚设：

- **可选**：仓库不声明，契约就不运行，lint 照绿，审批页也什么都不显示。安装器（新装和升级）都不种声明。
- **看不到计划**：选测命令只拿到 `GATE_SCOPE_OUT`，只能看到 propose 时的 diff，看不到切片 owns 里将改的文件。
- **只在 lint / preflight 跑**：baseline 和 final 开跑前不复核。lint 被跳过或计划后改，baseline 照样全量。
- **理由不进 `plan_sha`**：批准后再改理由，没有人知道。

2026-11-07 afa change `export-xlsx-aparam-override` 正好落在这几个洞里：

- afa 的 `slice-gate.py` 已具备契约，但没有 `gate-scope.json`；
- 登记表改动让 baseline 全选集成层，跑了 683.8 s，跑完才被发现；
- S2、S3 计划改 `executor/bin/*`，final 还会再全选一次，计划期即使开着契约也看不到。

用户要求新装与升级都不再犯（决策页 Q1–Q9 全取推荐）。

## Decision

1. **提供方必有**：
   - 提供方按优先级解析：计划 `gate.scope`（cmd）> `<openspec 根>/gate-scope.json`（`{"cmd": …}` 或 `{"builtin": true}`，二者取一）> 未声明。
   - 未声明时，lint、preflight、baseline、final 判红。
   - 唯一例外：本 change 的 owns 覆盖声明文件，这时视为全选，触发项为伪触发项 `scope:undeclared`，须写理由。
2. **builtin 只配普通测试命令**：`gate.test` 须能切出 pytest 前缀、是 test-tiers 驱动，或是探测产出的标准命令；否则判红，要求改用 cmd。
3. **提供方拿到计划**：契约新增 `GATE_SCOPE_PLANNED`（各片 owns 的并集）与 `GATE_SCOPE_CHANGE`（change 目录）。
4. **开跑前复核**：
   - baseline 写运行标记之前、final 运行测试之前，按同一套规则复核；
   - 未表态的全选不跑，baseline 退出非 0，final 记 `G2 scope` 红；
   - `final --full` 是显式要求，豁免。
5. **理由以 approve 提交为准**：final 复核时，当前 `gate.scope_full_reason` 须等于最近一次新增 approve 行的提交里的那份。理由仍不进 `plan_sha`。
6. **安装器负责种声明**：
   - 新装与升级都调用 `slice-gate.py scope-seed`：没有历史 change，或历史 `gate.test` 全部可识别 → 种 `{"builtin": true}`；否则不种，醒目提示接入 cmd；已有声明不动。
   - 不新增参数，不交互。

否决的方案：

- **未声明不阻断、每个 change 写理由**：理由由模型写，静默只是换成了套话。
- **安装器一律种 builtin**：afa 这类自带选测的仓库会因此得到假安全。
- **复核只警告、记入飞行记录**：全量的代价已经付出，与「计划期表态」的初衷相反。
- **用 `{"cmd": "python3 .claude/hooks/slice-gate.py scope"}` 表示内建**：路径因仓库而异，而且白起子进程。

## Consequences

- **更易**：
  - 装了模板的任何仓库，全量都不会再没人知情：计划期点名，开跑前复核；
  - 计划要改的文件进入报告，final 的退化在 propose 时就能看到；
  - 审批页恒显示提供方状态。
- **更难**：
  - 自带选测的仓库升级后，要先实现只算范围的命令，否则新 change 判红；
  - 每次 lint、preflight、baseline、final 多一次范围计算（builtin 在进程内，cmd 量级约 10 s）。
- **边界**（接受）：
  - cmd 提供方报告的真伪模板仍无法核验；
  - builtin 识别靠命令形态，带选测插件的 pytest 会被当成普通命令。
- **与在役 ADR**：
  - 原 ADR 决策 4（失败即拦）、6（审批页可见）、7（不进 `plan_sha`）继续有效，决策 7 补充 approve 绑定；
  - `DRAFT-installer-versioned-with-template` 的「不交互、新增参数只能可选」得到遵守。
