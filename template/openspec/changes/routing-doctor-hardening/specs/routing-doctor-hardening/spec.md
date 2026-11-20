## ADDED Requirements

### Requirement: frontmatter 渲染读写失败时报配置不可用
`model-routing.py frontmatter`（含 `--check`）在命令文件读不了、不是 UTF-8 文本或写不了时 SHALL 以退出码 2 退出，并在 stderr 点名路由键与文件路径。它 SHALL NOT 带 traceback 以退出码 1 退出：退出码 1 只表示 `--check` 发现漂移。命令文件 SHALL 保持不变。

Feature: fork 命令 frontmatter 渲染
Rule: 退出码 1 只留给漂移

#### Scenario: frontmatter-rejects-non-utf8-command
- **GIVEN** 命令目录里的 `clean-after-merged.md` 含 `context: fork`，frontmatter 里夹着一段不是 UTF-8 的字节；openspec 根没有 `model-routing.json`
- **WHEN** 运行 `model-routing.py frontmatter --check`
- **THEN** 退出 2，stderr 点名 `cleanup.runner` 与 `clean-after-merged.md`，并说明它不是 UTF-8 文本
- **AND** stderr 里没有 traceback，命令文件的字节不变

### Requirement: doctor 把崩溃报成不可用
`flight-doctor.py doctor` 的 `[routing]` 段 SHALL 只在 `frontmatter --check` 退出 1 且 stdout 有漂移条目时报漂移并给出修法。退出 1 但 stdout 没有漂移条目时，SHALL 报「不可用」并附 stderr 的最后一个非空行，SHALL NOT 给出修法。doctor SHALL 恒 exit 0。

Feature: 路由漂移体检
Rule: 修法只给真正的漂移

#### Scenario: doctor-reports-unreadable-command-as-unavailable
- **GIVEN** 一份独立安装的 hooks，命令目录里的 `clean-after-merged.md` 含 `context: fork` 但夹着不是 UTF-8 的字节
- **WHEN** 运行该 hooks 的 `flight-doctor.py doctor --openspec-root <根>`
- **THEN** 退出 0，`[routing]` 段报「不可用」并说明命令文件不是 UTF-8 文本
- **AND** `[routing]` 段没有「修法」行

#### Scenario: doctor-reports-crash-as-unavailable
- **GIVEN** 一份独立安装的 hooks，其中的 `model-routing.py` 一运行就抛出未捕获的 `RuntimeError: boom`
- **WHEN** 运行该 hooks 的 `flight-doctor.py doctor --openspec-root <根>`
- **THEN** 退出 0，`[routing]` 段报「不可用：RuntimeError: boom」
- **AND** `[routing]` 段没有「修法」行

### Requirement: doctor 不因子进程输出解码失败丢掉报告
`flight-doctor.py doctor` 读取 `frontmatter --check` 的输出时 SHALL 按 UTF-8 宽松解码。输出含不是 UTF-8 的字节时，doctor SHALL 照常输出包括 `[routing]` 在内的全部段落，SHALL NOT 退化为一行失败提示。

Feature: 路由漂移体检
Rule: 一段的异常不拖垮整份报告

#### Scenario: doctor-survives-undecodable-output
- **GIVEN** 一份独立安装的 hooks，其中的 `model-routing.py` 往 stdout 写一段不是 UTF-8 的字节和「frontmatter 与路由一致」后退出 0
- **WHEN** 运行该 hooks 的 `flight-doctor.py doctor --openspec-root <根>`
- **THEN** 退出 0，输出同时含 `[runner]` 段与 `[routing]` 段
- **AND** 输出里没有「flight-doctor doctor 失败」
