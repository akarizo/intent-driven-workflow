# DRAFT. 脚本测出来的东西不写进计划文件

- Status: accepted
- Date: 2026-11-18
- 来源 change：plan-hygiene（design D1 · D2）

## Context

飞行计划要过两道人类审批，第一道由 `takeoff-gate.py` 机械校验：人类批准的时间不得早于计划工件（`proposal.md` / `design.md` / `slices.json` / `specs/**`）的最后修改时间。

`slice-gate.py baseline` 却在结束时重写 `slices.json`，把全量测试耗时回填到 `gate.full_suite_sec`。baseline 在后台跑，人在它结束前批准，或批准后重跑 baseline，批准就过期。afa 的 `key-features-keyft` 飞行为此多要了一轮「起飞」；同一次飞行里，子仓 gitlink 在 baseline 时只是暂存、之后提交，基线又被判过期，再重跑 baseline，再回写，再过期。

根子在于同一个文件里混着两种东西：人批准的内容，和脚本每次运行都会变的测量值。

## Decision

1. **计划文件只承载人批准的内容**。脚本（baseline、final、门禁、体检）MUST NOT 往 `slices.json`、`proposal.md`、`design.md`、`specs/**`、切片包里写任何东西。
2. **测量值的归宿是 `gate-baseline.json` 与飞行记录**（`timeline.md` / `gate-report.md`）。全量耗时记在 `gate-baseline.json` 顶层的 `full_suite_sec`；增量基线沿用上一份的值；运行标记带上开跑前已知的值。
3. **读取经一个函数**：`slice-gate.py` 的 `suite_sec(change_dir, data=None)`，基线优先，计划里旧的 `gate.full_suite_sec` 只作回退。以后新增的测量字段照此办理：写进基线，读取方不直接碰计划文件里的同名旧字段。
4. **内容快照覆盖 gitlink**：有未提交改动的 gitlink 路径记子仓当前 HEAD 的 commit，与 git 树里的表示同口径；「已暂存」与「已提交」按内容判为相同。
5. **`gate.test` 须由人显式写出**：baseline 不探测、不代填。

否决的方案：

- **起飞门禁排除纯度量字段**：要在两个脚本里各维护一份「哪些字段不算计划」，写入方仍在改文件。
- **起飞门禁改比内容指纹**：改动大，且不解决「脚本写计划文件」本身；修改时间判据在第 1 条成立后已经稳定。
- **靠 propose 文档规定提交顺序绕开 gitlink 问题**：顺序靠模型照做，缺口仍在脚本里；而且工件先于 baseline 提交会让 `gate-baseline.json` 把工作树弄脏，被 `/opsx-apply` 的干净检查拦下。

## Consequences

- **更易**：批准之后重跑 baseline 不再需要重新批准；带子仓的 change 提交工件后不必重跑基线；「计划文件变了」重新等于「人改了计划」。
- **更难**：外部脚本若读 `slices.json` 的 `gate.full_suite_sec`，升级后读到的是不再更新的旧值，要改读 `gate-baseline.json`。
- **中性**：`DRAFT-baseline-reuse-by-content-fingerprint` 的快照规则不变，只是多了 gitlink 这一种取值；旧基线没有 `full_suite_sec` 时回退读旧字段，不需要迁移。
