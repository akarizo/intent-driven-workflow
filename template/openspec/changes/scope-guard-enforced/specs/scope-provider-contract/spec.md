## ADDED Requirements

### Requirement: 每个仓库必有选测提供方
Rule: 库 SHALL 按优先级解析选测提供方，取第一个存在的：计划 `gate.scope`（非空字符串，cmd 提供方，来源「计划 gate.scope」）> `<openspec 根>/gate-scope.json`（来源「仓库声明 gate-scope.json」）> 未声明。

`gate-scope.json` SHALL 是对象，并且恰含以下两个字段之一：
- `cmd`（非空字符串）→ cmd 提供方；
- `builtin`（只能是 `true`）→ 模板内建提供方。

两个都有、`builtin` 不是 `true`、或带其它字段时，`slice-gate.py lint` SHALL 退出非 0，违规行以 `scope:` 开头并点名问题。

未声明时，`slice-gate.py lint`、`preflight`、`baseline`、`final` SHALL 判红，提示写 `{"builtin": true}` 或 `{"cmd": ...}`。唯一例外是本 change 自己建立声明（任一切片 owns 的某条 glob 匹配 `<openspec 根>/gate-scope.json` 的仓库相对路径）：这时视为报告全选，触发项为伪触发项 `scope:undeclared`，`gate.scope_full_reason` SHALL 为它写理由；写了即通过，摘要点名「本 change 建立仓库选测声明」。`slice-gate.py waves` 不做这项核对。

#### Scenario: undeclared-provider-is-red
- **GIVEN** openspec 根没有 `gate-scope.json`，计划没写 `gate.scope`
- **AND** 唯一切片的 owns 是 `a/**`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头，含「未声明选测范围」，并同时提到 `builtin` 与 `cmd`

#### Scenario: establishing-change-passes-only-with-reason
- **GIVEN** openspec 根没有 `gate-scope.json`，计划没写 `gate.scope`
- **AND** 切片 owns 含 `openspec/gate-scope.json`
- **WHEN** 先在没有 `gate.scope_full_reason` 时运行 `slice-gate.py lint`，再补上 `{"scope:undeclared": "本 change 建立仓库选测声明"}` 后运行一次
- **THEN** 第一次退出非 0，stderr 点名 `scope:undeclared` 缺理由
- **AND** 第二次退出 0，stderr 摘要行含「本 change 建立仓库选测声明」

### Requirement: builtin 声明只用于普通测试命令
Rule: `gate-scope.json` 是 `{"builtin": true}` 时，模板内建提供方 SHALL 在进程内给出报告，不起子进程。

`gate.test` SHALL 是可识别的普通测试命令，即满足以下任一条：
- 能切出 pytest 前缀（与增量 final 的识别同一口径）；
- 是 test-tiers 驱动 `python3 <路径>/test-tiers.py run unit`；
- 等于测试命令探测的产出之一：`npm test`、`go test ./...`、`cargo test`。

否则 lint SHALL 判红，提示自带选测的仓库改用 `{"cmd": ...}`。核对通过时，lint 的 stderr 摘要行 SHALL 写明「模板内建」。

#### Scenario: builtin-declaration-reports-builtin
- **GIVEN** openspec 根的 `gate-scope.json` 是 `{"builtin": true}`，计划的 `gate.test` 是 `python3 -m pytest -q tests`，切片 owns 只有 `a/**`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出 0
- **AND** stderr 有一行以 `scope:` 开头、含「模板内建」

#### Scenario: builtin-with-unrecognized-gate-test-is-red
- **GIVEN** openspec 根的 `gate-scope.json` 是 `{"builtin": true}`，计划的 `gate.test` 是 `bash scripts/test.sh`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** stderr 有一行以 `scope:` 开头，含「认不出」与 `cmd`

#### Scenario: malformed-v2-declaration-is-red
- **GIVEN** 三个仓库的 `gate-scope.json` 分别是 `{"builtin": true, "cmd": "x"}`、`{"builtin": false}`、`{"builtin": true, "args": 1}`
- **WHEN** 在每个仓库运行 `slice-gate.py lint`
- **THEN** 三次都退出非 0
- **AND** 第一个点名「只能取其一」，第二个点名 `builtin` 须为 true，第三个点名未知字段 `args`
- **BUT** `{"builtin": true}` 本身通过形状校验

### Requirement: 提供方拿到计划文件与 change
Rule: 库运行 cmd 提供方时，除 `GATE_SCOPE_OUT` 外，SHALL 再设两个环境变量：
- `GATE_SCOPE_PLANNED`：一个文件的路径，文件内容是各切片 owns 的并集，按切片顺序去重，一行一条，glob 原样；
- `GATE_SCOPE_CHANGE`：change 目录相对 git 顶层的路径，用 `/` 分隔。

报告形状、300 秒上限、失败即红、全选逐项表态都与现行契约相同。

#### Scenario: cmd-provider-receives-planned-files-and-change
- **GIVEN** 计划 `gate.scope` 是一个替身命令：它把 `GATE_SCOPE_PLANNED` 文件的每一行加前缀 `planned:`、把 `GATE_SCOPE_CHANGE` 加前缀 `change:`，作为触发项报告全选
- **AND** 切片 owns 是 `bin/x.sh` 与 `src/**`，change 目录是 `openspec/changes/c`
- **WHEN** 运行 `slice-gate.py lint`
- **THEN** 退出非 0
- **AND** 缺理由的触发项恰为 `planned:bin/x.sh`、`planned:src/**`、`change:openspec/changes/c`

### Requirement: 审批页显示提供方状态
Rule: `spec.html` 的「选测范围」小节 SHALL 恒显示，内容依提供方而定：
- cmd：命令原文与来源；
- builtin：「模板内建（builtin）」与来源；
- 未声明：醒目的「未声明选测范围」；本 change 建立声明时，另注明「本 change 建立仓库选测声明」。

有 `gate.scope_full_reason` 时照旧显示「触发项 → 理由」表。渲染只读文件，不运行命令。

#### Scenario: spec-html-shows-provider-state
- **GIVEN** 三个 change：仓库声明 `{"builtin": true}`；仓库声明 `{"cmd": "python3 tools/scope.py"}`；没有任何声明
- **WHEN** 分别渲染 `spec.html`
- **THEN** 第一份的选测范围小节含「模板内建」，第二份含命令原文与「仓库声明」，第三份含「未声明选测范围」

### Requirement: 声明判定可供安装器调用
Rule: `slice-gate.py scope-seed --openspec-root DIR` SHALL 按 `DIR/gate-scope.json` 是否存在决定行为，并且恒退出 0。

已存在时，SHALL NOT 改动该文件，打印「保留已有声明」与其内容。

不存在时，收集 `DIR/changes/` 下全部 `slices.json`（含 archive）的 `gate.test`：
- 没有任何 `slices.json`，或全部 `gate.test` 都可识别 → 写入 `{"builtin": true}`，打印「已种」；
- 有认不出或读不出的 → 不写，打印「未种」、最多 3 个例子与接入 cmd 提供方的指引。

三种情况都退出 0。

#### Scenario: scope-seed-decides-by-history
- **GIVEN** 三个 openspec 根：A 的历史 `gate.test` 只有 `python3 -m pytest -q tests`；B 有一条 `bash openspec/changes/x/verify/full_suite.sh`；C 已有 `{"cmd": "mine"}`
- **WHEN** 对每个根运行 `slice-gate.py scope-seed --openspec-root <根>`
- **THEN** 三次都退出 0
- **AND** A 写出 `{"builtin": true}`，stdout 含「已种」
- **AND** B 没有 `gate-scope.json`，stdout 含「未种」与 `full_suite.sh`
- **AND** C 的文件内容不变，stdout 含「保留」与 `mine`
