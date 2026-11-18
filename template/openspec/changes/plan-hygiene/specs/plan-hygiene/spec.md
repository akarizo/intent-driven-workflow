## ADDED Requirements

### Requirement: baseline 不改计划文件
`slice-gate.py baseline` MUST NOT 写 `slices.json`，也 MUST NOT 写本 change 的任何其他计划工件（`proposal.md` / `design.md` / `specs/**` / 切片包）；它只写 `gate-baseline.json` 与飞行记录。`gate.test` 缺失时 baseline SHALL 在写运行标记之前以非 0 退出并点名 `gate.test`，MUST NOT 探测测试命令后写回。「运行期间 gate / verify 被修改」的判定 SHALL 保留。
Feature: 批准之后，测量不让批准过期
Rule: 计划文件的内容全部来自人批准的那一版；脚本测出来的东西不往里写

#### Scenario: baseline-leaves-plan-file-untouched
- **GIVEN** 一个已提交的 change，`gate.test` 是直接的 pytest 调用，`slices.json` 里没有 `full_suite_sec`
- **AND** `slices.json` 的修改时间被钉在过去的某一刻
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出码为 0
- **AND** `slices.json` 的字节与修改时间都没有变
- **AND** `gate-baseline.json` 顶层的 `full_suite_sec` 是一个数值

#### Scenario: approval-survives-baseline-rerun
- **GIVEN** 一个跑过一次 baseline 的 change，计划工件的修改时间早于人类在会话里说「起飞」的时间
- **WHEN** 在批准之后再运行一次 `slice-gate.py baseline --full`，然后运行 `takeoff-gate.py --change-dir <change> --session <转录>`
- **THEN** 起飞门禁退出码为 0，stdout 是那条批准证据

#### Scenario: baseline-stops-without-gate-test
- **GIVEN** 一个已提交的 change，`slices.json` 的 `gate.test` 为空，仓库里有 `tests/` 目录（探测得出 pytest 命令）
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出码非 0，stderr 点名 `gate.test`
- **AND** 没有生成 `gate-baseline.json`，`slices.json` 的字节没有变

### Requirement: 全量耗时记在基线里，读取方都从基线取
全量基线 SHALL 把本次全量测试的墙钟秒数写进 `gate-baseline.json` 顶层的 `full_suite_sec`；增量基线 SHALL 沿用本 change 上一份基线的值（没有时依次取旧计划的 `gate.full_suite_sec`、候选的 `full_suite_sec`、候选的 `test.sec`）。运行标记 SHALL 带上开跑前已知的 `full_suite_sec`。`slice-gate.py` SHALL 提供 `suite_sec(change_dir, data=None)`：先取 `gate-baseline.json`（含运行标记）里的数值，取不到再取计划里旧的 `gate.full_suite_sec`，都没有返回 `None`，布尔值不算数值；G7 超时推算、「基线仍在跑」的提示与成本预告 SHALL 都经它取值。
Feature: 耗时换个地方记，用它的地方照常工作
Rule: 新字段优先，旧字段只作回退；已安装仓库的在途 change 不用重跑 baseline

#### Scenario: incremental-baseline-keeps-suite-sec
- **GIVEN** 一个 change 跑过一次全量基线，`gate-baseline.json` 的 `full_suite_sec` 为某个数值
- **AND** 之后只改了一个测试文件并提交
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 新基线的 `mode` 为 `incremental`
- **AND** 它的 `full_suite_sec` 与第一次相同

#### Scenario: running-marker-carries-last-suite-sec
- **GIVEN** 一个 change 跑过一次基线，`gate.test` 是一个在运行期间读取 `gate-baseline.json` 的脚本
- **WHEN** 再运行 `slice-gate.py baseline --full`，脚本在运行期间检查该文件
- **THEN** 脚本看到的是运行标记（`running` 为真），且其中 `full_suite_sec` 等于上一份基线的值

#### Scenario: running-baseline-hint-shows-last-suite-sec
- **GIVEN** change 的 `gate-baseline.json` 是一个进程仍在的运行标记，`full_suite_sec` 为 12.5，`slices.json` 里没有 `full_suite_sec`
- **WHEN** 运行 `slice-gate.py preflight`
- **THEN** 退出码非 0，stderr 含「仍在跑」与「12.5 秒」

#### Scenario: suite-sec-resolver-prefers-baseline
- **GIVEN** 一个 change 目录，计划里旧的 `gate.full_suite_sec` 为 816
- **WHEN** 分别在四种状态下调用 `suite_sec`：没有基线；基线的 `full_suite_sec` 为 300.5；基线的 `full_suite_sec` 为布尔值 `true`；没有基线且计划里也没有该字段
- **THEN** 依次得到 816、300.5、816、`None`

### Requirement: 子仓 gitlink 计入内容快照
基线的内容快照 SHALL 对有未提交改动的 gitlink 路径记录子仓当前 HEAD 的 commit（子仓未就绪时记索引里的值），使「gitlink 已暂存」与「同一 gitlink 已提交」按内容判为相同。其他目录 MUST 照旧不记。
Feature: 带子仓的 change 提交工件后不必重跑基线
Rule: 快照里 gitlink 的取值与 git 树里的表示同口径

#### Scenario: staged-gitlink-commit-keeps-baseline-fresh
- **GIVEN** 一个带子仓的仓库，change 的计划已提交
- **AND** 子仓里新增了一个提交，父仓把新的 gitlink 暂存但还没提交
- **WHEN** 运行 `slice-gate.py baseline`，随后把 gitlink 与基线文件一起提交，再运行 `slice-gate.py preflight`
- **THEN** preflight 退出码为 0，不报「基线过期」

### Requirement: propose 文档写明 baseline 不改计划文件
`opsx-propose.md` 与 `openspec-propose/SKILL.md` SHALL 用同一句话写明 baseline 的耗时记在 `gate-baseline.json`、不改计划文件；SHALL 用同一句话写明子仓 gitlink 的改动与计划工件同一次提交；MUST NOT 再出现「耗时写回 `slices.json`」的说法。
Feature: 文档与脚本说同一件事
Rule: 命令与同名 skill 同改

#### Scenario: propose-docs-say-baseline-leaves-plan-alone
- **GIVEN** `template/.claude/commands/opsx-propose.md` 与 `template/.claude/skills/openspec-propose/SKILL.md`
- **WHEN** 阅读两份文档的基线步骤与硬交接
- **THEN** 两处都不含 `full_suite_sec`，也不含「`slices.json` 的耗时」
- **AND** 两处有同一行同时含 `gate-baseline.json`、「耗时」与「不改」「计划文件」
- **AND** 两处有同一行同时含 `gitlink` 与「同一次提交」
