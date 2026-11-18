## ADDED Requirements

### Requirement: 轮次档由脚本按切片的现存文件数算
`slice-gate.py turns --change-dir DIR` SHALL 打印一个 JSON 对象，把每个切片 id 映射到 `"standard"` 或 `"large"`，退出 0；计划不合法时与 `lint` 一样在 stderr 点名并以 2 退出。档位的算法：取切片 owns 展开后的现存文件数，超过 8 个为 `large`，否则为 `standard`。文件在 `gate-baseline.json` 记录的 `commit` 的树上数；没有基线、或该 commit 不在对象库时，在 HEAD 的树上数。只数已提交的文件。owns 落在 submodule 里的条目，按那棵树记录的 gitlink 在子仓对象库里数，取不到时按 0。`lint`、`waves`、`preflight` 的 stdout 形状 MUST 不变。脚本 MUST NOT 把档位写进任何计划文件。
Feature: 大切片拿到更多轮次
Rule: 档位看计划时的规模，飞行中途不漂移

#### Scenario: turns-computed-from-owned-files
- **GIVEN** 切片 S1 的 owns 展开后在 HEAD 有 8 个现存文件，S2 有 1 个，没有基线
- **WHEN** 运行 `turns`；给 S1 的 owns 范围再提交第 9 个文件后重新运行
- **THEN** 第一次输出 `{"S1": "standard", "S2": "standard"}`，第二次输出 `{"S1": "large", "S2": "standard"}`
- **AND** 工作树里未提交的文件不改变结果

#### Scenario: turns-measured-at-baseline-commit
- **GIVEN** 基线记录的 commit 上 S1 有 8 个现存文件，之后又提交了 3 个落在 S1 owns 内的新文件
- **WHEN** 运行 `turns`；再把基线的 commit 换成对象库里没有的值后重新运行
- **THEN** 第一次 S1 是 `standard`（按基线那个 commit 数）
- **AND** 第二次 S1 是 `large`（退回按 HEAD 数）

### Requirement: 计划可以升档，不能降档
切片 MAY 带 `"turns": "large"`，把按规模是 `standard` 的切片升为 `large`；`turns` 子命令的输出 SHALL 反映升档后的结果。切片写了 `"turns": "standard"` 而按规模是 `large` 时，`lint`、`waves`、`preflight`、`turns` MUST 判计划不合法并点名该切片与 `turns`；`turns` 取其他值同样不合法。不写 `turns` 时按规模。
Feature: 小而难的切片可以多要轮次，大切片不能少报
Rule: 人能把档位往上调，往下调由规模说了算

#### Scenario: turns-upgrade-declared-in-plan
- **GIVEN** S1 按规模是大片档；S2 只有 1 个现存文件，计划里写了 `"turns": "large"`
- **WHEN** 运行 `turns` 与 `waves`；再分别把 S1 写成 `"turns": "standard"`、把 S2 写成 `"turns": "huge"` 后运行 `waves`
- **THEN** `turns` 输出 `{"S1": "large", "S2": "large"}`，第一次 `waves` 退出 0
- **AND** 后两次 `waves` 都以 2 退出，stderr 分别点名 S1 与 S2，并都含 `turns`

### Requirement: 工作流按档位选执行体定义
`opsx-apply` 工作流 SHALL 接受可选参数 `args.turns`（`turns` 子命令的输出）：值为 `large` 的切片，首轮与重派都派给 `slice-executor-large`，其余派给 `slice-executor`；没传 `turns` 时全部按标准档。`useAgentTypes` 为 false 时，prompt SHALL 让执行体先读对应的那份定义文件。`template/.claude/agents/slice-executor-large.md` SHALL 是一份薄定义：frontmatter 的 `name` 为 `slice-executor-large`、`maxTurns` 为 80，`tools` / `model` / `effort` / `permissionMode` / 预加载 skill 与 `slice-executor.md` 相同；正文只指向 `slice-executor.md`，MUST NOT 复制其纪律条目。`slice-executor.md` 的 `maxTurns` 保持 40。
Feature: 轮次上限来自定义文件，定义文件按档位选
Rule: 纪律只有一份，两档只差一个数字

#### Scenario: workflow-picks-definition-by-tier
- **GIVEN** `args.turns` 把 S2 标为 `large`，S2 首轮门禁红、重派后绿
- **WHEN** 分别在 agent 类型已注册与未注册两种配置下跑工作流；再跑一次不传 `turns` 的
- **THEN** 已注册时 S2 与 S2 的重派派给 `slice-executor-large`，其余切片派给 `slice-executor`
- **AND** 未注册时 S2 的 prompt 让执行体先读 `slice-executor-large.md`，其余切片读 `slice-executor.md`
- **AND** 不传 `turns` 时所有切片都派给 `slice-executor`

#### Scenario: large-definition-is-thin
- **GIVEN** `template/.claude/agents/` 下的两份执行体定义
- **WHEN** 解析 `slice-executor-large.md` 的 frontmatter 与正文
- **THEN** `name` 为 `slice-executor-large`、`maxTurns` 为 80，`tools`、`model`、`effort`、`permissionMode` 与标准档相同，预加载 `test-driven-development`
- **AND** 正文提到 `slice-executor.md`，非空行不超过 6 行，不含标准档的纪律条目原文
- **AND** 标准档的 `maxTurns` 仍为 40

### Requirement: 大片档执行体受同样的起飞门禁与模型对账
`takeoff-gate.py` SHALL 把 Agent / Task 工具对 `slice-executor-large` 的派发与 `slice-executor` 一样当作起飞类派发判定（没有人类批准时拒绝）。`session-decompose.py` SHALL 把 agent 类型 `slice-executor-large` 归为 executor 角色参与模型对账。
Feature: 多一份定义文件不多一条绕过门禁的路
Rule: 凡是按 agent 类型名判定的地方，两档同等对待

#### Scenario: large-executor-is-gated-and-audited
- **GIVEN** 一次用 Agent 工具派 `slice-executor-large` 的派发，prompt 指向某个 change，转录里没有人类批准
- **WHEN** 起飞门禁以 hook 模式判定这次派发；另读收口对账脚本的 agent 类型映射
- **THEN** 起飞门禁拒绝，理由点名该 change 目录
- **AND** 对账脚本把 `slice-executor-large` 与 `slice-executor` 都记为 executor 角色

### Requirement: 未交回的 blocked 理由写明档位与快照位置
执行体首轮与重派都没有交回结果时，工作流记下的 blocked（`kind` 为 `infra`）理由 SHALL 含：「未返回」与「已重派一次」、该片的档位名（「标准档」或「大片档」）与该档的轮次上限、半成品快照所在的 ref `refs/flight/<change>/<S>`，并说明重新起飞的首轮会清掉这份快照、要保留须先用 `start <S> --resume-checkpoint` 接续。理由里的上限数字 MUST 与对应定义文件的 `maxTurns` 一致。
Feature: 撞上限之后知道下一步做什么
Rule: 理由里只写脚本确知的事实

#### Scenario: noreturn-blocked-reason-names-tier-and-snapshot
- **GIVEN** S1 是大片档、S2 是标准档，两片的首轮与重派都没有交回结果
- **WHEN** 工作流跑完
- **THEN** 两片都记 blocked，`kind` 为 `infra`，理由含「未返回」与「已重派一次」
- **AND** S1 的理由含「大片档」「80」与 `refs/flight/<change>/S1`，S2 的理由含「标准档」「40」与 `refs/flight/<change>/S2`

### Requirement: 审批页与文档显示档位
`spec_html.py` 渲染的切片表 SHALL 多一列「轮次档」，每片显示「标准档」或「大片档」（取自 `slice-gate.py turns`）；算不出档位时该列显示「—」，页面 MUST 照常生成并以 0 退出。`README.md` 与 `install.sh` 的 agent 清单 SHALL 列出 4 个 agent 并点名 `slice-executor-large`；`README.md` SHALL 说明两档的轮次上限、档位由 `slice-gate.py turns` 按规模算、切片留痕经 `flight-evidence` 共用目录并回分支、合回后回收临时 worktree。
Feature: 批准计划的人看得到每片的档位
Rule: 展示可以缺，不能挡住页面

#### Scenario: spec-html-shows-turn-tier
- **GIVEN** git 仓库里的一个 change：S1 的 owns 展开后有 9 个现存文件，S2 有 1 个；另有一份不在 git 仓库里的同样的 change
- **WHEN** 分别渲染 `spec.html`
- **THEN** 两次都退出 0，切片表都有「轮次档」一列
- **AND** git 仓库里 S1 那行是「大片档」、S2 那行是「标准档」
- **AND** 不在 git 仓库里的那份不出现「大片档」

#### Scenario: readme-and-installer-list-four-agents
- **GIVEN** `README.md` 与 `install.sh`
- **WHEN** 查找 agent 清单与留痕说明
- **THEN** 两处都写「4 个 agent」并点名 `slice-executor-large`，不再出现「3 个 agent」
- **AND** `README.md` 含 `flight-evidence`、`slice-gate.py turns`、「大片档」、80 与「回收」
