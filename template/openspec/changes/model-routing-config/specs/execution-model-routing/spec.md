## ADDED Requirements

### Requirement: 路由配置只登记执行层的 10 个键，只写模型名
`.claude/hooks/model-routing.py` SHALL 读取 openspec 根下的 `model-routing.json`。注册表固定为 10 个键：`flight.executor` / `flight.executor-large` / `flight.fixer` / `flight.reviewer` / `flight.integrator` / `ship.reviewer` / `ship.followup` / `archive.sync` / `claudemd.evidence` / `bulk.apply`。

每个写出的键 MUST 同时有 `model` 与 `effort`：
- `model` ∈ `opus | sonnet | haiku | fable`；
- `effort` ∈ `low | medium | high | xhigh | max`。

出现以下任一情况时，`show` / `pin` / `get` MUST 以 exit 2 退出，并在 stderr 点名出错的键：
- 未登记的组或键；
- 组名是 `propose` / `explore` / `new` / `continue` / `mini`，提示「规划期不进路由配置」；
- 模型写成 `main` / `inherit` 等非模型名，提示「只写模型名」；
- effort 不在允许集合内。

没有配置文件或缺某个键时，SHALL 取内建默认：`flight.integrator` / `archive.sync` / `claudemd.evidence` 为 sonnet · low，`bulk.apply` 为 opus · medium，其余为 opus · high。

Feature: 执行层路由配置
Rule: 只收执行层的键与模型名，缺省走内建默认

#### Scenario: routing-builtin-defaults-without-config
- **GIVEN** 一个 openspec 根下没有 `model-routing.json` 的仓库
- **WHEN** 运行 `model-routing.py show --json`
- **THEN** 退出 0，输出 10 个键
- **AND** `flight.executor` 是 opus · high，`flight.integrator` 是 sonnet · low，`bulk.apply` 是 opus · medium，每个键的来源都是 `builtin`

#### Scenario: routing-config-overrides-per-key
- **GIVEN** `model-routing.json` 只写了 `flight.executor` 为 opus · medium
- **WHEN** 运行 `show --json`
- **THEN** `flight.executor` 是 opus · medium，来源为 `repo`
- **AND** `flight.reviewer` 仍是 opus · high，来源为 `builtin`

#### Scenario: routing-rejects-planning-keys
- **GIVEN** `model-routing.json` 含组 `propose`（如 `propose.skeleton`）
- **WHEN** 运行 `show`
- **THEN** exit 2，stderr 含「规划期不进路由配置」并点名 `propose.skeleton`

#### Scenario: routing-rejects-non-model-names
- **GIVEN** `model-routing.json` 里 `flight.reviewer` 的 model 写成 `main`
- **WHEN** 运行 `show`
- **THEN** exit 2，stderr 含「只写模型名」并点名 `flight.reviewer`

### Requirement: 规划期把 flight 与 ship 两组钉进 slices.json，起飞只认钉住的值
`model-routing.py pin --change-dir D` SHALL 把生效配置里 flight 组的 5 个键与 ship 组的 2 个键，写进 `D/slices.json` 顶层的 `routing`，形如 `{source, flight, ship}`；其余顶层键 MUST 原样保留。

`resolve --change-dir D` SHALL 只读钉住的 `routing.flight`，stdout 输出 `{"models": {5 个角色}, "efforts": {5 个角色}}`。以下情况 MUST 以 exit 3 退出：
- `routing` 缺失或不合法：stderr 给出 `model-routing.py pin --change-dir D` 的命令，并说明 pin 之后要重新批准；
- 环境变量 `CLAUDE_CODE_EFFORT_LEVEL` 或 `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` 非空：stderr 点名该变量。

Feature: 钉住与解析
Rule: 起飞用的路由来自计划工件，环境覆盖时停飞

#### Scenario: routing-pin-writes-flight-and-ship
- **GIVEN** 一个 change 的 `slices.json`（含 gate 与 slices），仓库配置把 `flight.executor` 设为 opus · medium
- **WHEN** 运行 `pin --change-dir`
- **THEN** `slices.json` 多出 `routing`，其中 `flight` 有 5 个键、`flight.executor` 为 opus · medium，`ship` 有 2 个键
- **AND** 原有的 `gate` 与 `slices` 不变

#### Scenario: routing-resolve-requires-pin
- **GIVEN** 一个没有 `routing` 的 `slices.json`
- **WHEN** 运行 `resolve --change-dir`
- **THEN** exit 3，stderr 含 `model-routing.py pin --change-dir` 与「重新批准」

#### Scenario: routing-resolve-outputs-workflow-args
- **GIVEN** 一个已 pin 的 change
- **WHEN** 运行 `resolve --change-dir`
- **THEN** 退出 0，stdout 的 JSON 有 `models` 与 `efforts`，各含 executor / executor-large / fixer / reviewer / integrator 5 个角色，取值等于钉住的值

#### Scenario: routing-resolve-refuses-env-override
- **GIVEN** 一个已 pin 的 change，环境变量 `CLAUDE_CODE_EFFORT_LEVEL=high`
- **WHEN** 运行 `resolve --change-dir`
- **THEN** exit 3，stderr 点名 `CLAUDE_CODE_EFFORT_LEVEL`

### Requirement: 其他派发点按键取值，钉住的优先
`model-routing.py get <组.键> [--change-dir D]` SHALL 在 stdout 输出 `{"model", "effort", "source"}`。取值顺序：
1. D 的 `slices.json.routing` 里钉住的值（`source` 为 `pinned`）；
2. 仓库配置（`repo`）；
3. 内建默认（`builtin`）。

未登记的键 MUST 以 exit 2 退出。

Feature: 单键查询
Rule: 钉住 > 仓库配置 > 内建默认

#### Scenario: routing-get-prefers-pinned
- **GIVEN** 仓库配置把 `ship.reviewer` 设为 sonnet · medium，而 change 钉住的 `ship.reviewer` 是 opus · high
- **WHEN** 分别运行 `get ship.reviewer --change-dir D` 与不带 `--change-dir` 的 `get ship.reviewer`
- **THEN** 前者输出 opus · high、来源为 `pinned`
- **AND** 后者输出 sonnet · medium、来源为 `repo`
