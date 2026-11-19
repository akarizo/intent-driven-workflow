## Why

执行层的模型是写死的：执行体与评审员 = 会话主模型 · high，integrator = sonnet · low（铁律 11，`opsx-apply.md` 路由表）。这带来三个问题：

- 用户要执行体用 opus · medium、评审保留 high，现在做不到：执行体与评审员共用 `<main>`，effort 写死在文档和 agent frontmatter 里；
- 仓库之间没法各配各的：路由只存在于模板文本，没有一份按仓库生效的配置；
- 起飞前没有一处让人类看见并确认本次飞行用什么模型；收口只对账模型，不对账 effort。

另外有两处派发漏写了 `model`，实际落到 `CLAUDE_CODE_SUBAGENT_MODEL` 的默认值 sonnet：bulk-apply 派发的子 agent，以及 legacy 逐 task 模式的实现 / 修复派发。

意图访谈以四轮审批页代替：`docs/flight-routing-config.html` v1–v4（主仓库工作区，未入库）。用户 2026-11-19 回复「全按推荐」，C1 相关：Q1-A 无配置文件走内建默认、Q3-A 一个派发用途一个键共 10 个、Q4-A 规划期确认后钉进 slices.json、Q5-A 旧 change 缺 routing 停飞并提示 pin、Q6-A 本仓库按第 05 节取值、Q7-A 评审类不设下限、Q13-A 修复不属于规划期。另有两条用户原话约束：「不写 main，必须是直接模型名称」；「最终的解决方案和规划还是要继承主会话」。

## What Changes

- **新增路由配置 `openspec/model-routing.json`**：只写模型名（`opus | sonnet | haiku | fable`）与 effort（`low | medium | high | xhigh | max`），`main` / `inherit` 判红。按派发用途登记 10 个键：
  - `flight`：`executor` / `executor-large` / `fixer` / `reviewer` / `integrator`；
  - `ship`：`reviewer` / `followup`；
  - `archive.sync` · `claudemd.evidence` · `bulk.apply`。
  
  规划期的组名（propose / explore / new / continue / mini）出现即判红。没有配置文件或缺某个键时走内建默认：推理类 opus · high，机械类 sonnet · low，`bulk.apply` opus · medium。本仓库的配置：`flight.executor` 与 `flight.executor-large` 为 opus · medium，其余取内建默认。
- **新增 `.claude/hooks/model-routing.py`**，四个子命令：
  - `show`：打印生效的路由表及每个键的来源；
  - `pin --change-dir`：把 flight 与 ship 两组键钉进 `slices.json.routing`；
  - `resolve --change-dir`：起飞时读钉住的路由，输出工作流用的 `models` / `efforts`；缺 routing 时停飞并提示 pin；设了 `CLAUDE_CODE_EFFORT_LEVEL` 或 `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` 时停飞；
  - `get <组.键>`：其他派发点取单个键，change 钉过的优先。
- **`opsx-apply.js` 按 5 个角色派发**：大片档执行体走 `executor-large`，批量修复与 wave 跨片修复走 `fixer`；两者缺省时同 `executor`，兼容旧调用；effort 值不在允许集合内时拒绝起飞。
- **收口对账加 effort**：`session-decompose.py` 新增 `--expect-efforts`，读子 agent 转录 assistant 行的 `effort` 字段对账；`fix` 开头的标签判为 `fixer`；`--turns` 把大片档切片判为 `executor-large`；`fixer` 与 `executor-large` 没派发时不算零覆盖。
- **spec.html 显示钉住的路由表**；缺 routing 时显示「起飞会被拒绝」的提示。
- **文档（命令与 skill 同改）**：
  - `/opsx-apply`：step 4 改为 `model-routing.py resolve`，打印路由表；回退路径的 Agent 派发显式传 `model` 与 `effort`；收口加 `--expect-efforts`；去掉 `<main>` / `--model=`。
  - `/opsx-propose`：tasks 阶段运行 `pin`。
  - `/pr-ship`、`/opsx-archive`、`/claudemd-standardize`、`/opsx-bulk-apply`、legacy 逐 task 模式：派发都改用 `model-routing.py get <键>`，补上 bulk 与 legacy 漏写的 `model`。
- **铁律 11 改写**（根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet`）：执行层按派发用途从配置显式路由，只写模型名；规划期产出只来自主会话或 fork，不进路由配置，规划类命令与 skill 不写 `model` / `effort`。README、`docs/WORKFLOW_zh.md`、`install.sh` 说明同步。
- **新 ADR**：取代 `DRAFT-model-routing-defaults-for-template` 决策第 2 条中的「需推理的 subagent 保留 inherit」。
- **BREAKING（下游行为）**：没有配置文件的下游仓库，执行体与评审员从「随会话主模型」改为固定 opus · high（Q1-A）。旧 change 起飞前要先 `pin`，并重新批准一次（Q5-A）。

## Capabilities

### New Capabilities
- `execution-model-routing`：路由配置的形状与校验、内建默认、钉进 slices.json、起飞解析与环境覆盖检查、单键查询。
- `flight-role-routing`：飞行工作流按 5 个角色派发（大片档执行体、修复执行体单独路由），以及 effort 校验。
- `route-audit-efforts`：收口对账覆盖 effort 与新增的两个角色。
- `spec-html-routing`：审批面板显示钉住的路由。
- `routing-docs`：apply / propose / ship / archive / claudemd / bulk / legacy 各派发点从配置取值；规划期不变式由测试机械检查。
- `iron-rule-routing`：铁律 11 与对外文档的措辞。

### Modified Capabilities
（无：`openspec/specs/` 目前为空）

## Impact

- **新增**：`template/.claude/hooks/model-routing.py`、`template/openspec/model-routing.json`（本仓库配置）、`tests/test_model_routing.py`、`tests/test_workflow_routing_roles.py`、`tests/test_route_audit_efforts.py`、`tests/test_spec_html_routing.py`、`tests/test_routing_docs.py`。
- **修改**：
  - 代码：`template/.claude/workflows/opsx-apply.js`、`template/.claude/hooks/session-decompose.py`、`template/.claude/hooks/spec_html.py`；
  - 命令与 skill：apply、propose、pr-ship、archive、claudemd-standardize、bulk-apply、legacy；
  - 文档与安装：根 `CLAUDE.md`、`template/CLAUDE.md.snippet`、README、`docs/WORKFLOW_zh.md`、`install.sh`；
  - 钉住旧措辞的测试：`tests/test_template_docs.py`、`tests/test_docs_iron_rules.py`、`tests/test_agents_workflow.py`。
- **不变**：
  - `session-model.py` 保留，`session-decompose` 仍用它的 `alias_of` 把模型 id 归一成别名；
  - agent frontmatter 不改，派发时显式传的 `model` / `effort` 优先于 frontmatter；
  - takeoff-gate 的新鲜度规则不改：`slices.json` 本来就是计划工件，pin 改了它，批准自然过期。
- **下游**：install 不种配置文件，下游缺省走内建默认；升级后在途的 change 起飞前要先 pin。
