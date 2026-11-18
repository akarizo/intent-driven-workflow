## ADDED Requirements

### Requirement: 切片的测试留痕写在 git 共用目录
`test-evidence.py` 在工作树根有切片标记时 SHALL 把留痕写到 `<git common dir>/flight-evidence/<change>/<切片>.log`（`<change>` 为标记里 change 目录的目录名），行格式不变：`ISO 时间\t切片\tPASS|FAIL\t命令前 120 字符`；此时 MUST NOT 写工作树里的 `<change>/evidence.log`。有标记时任何 Bash 事件都 SHALL 确保该文件存在（没有可记的行时是空文件）。命令被认作测试运行的条件 SHALL 是：命中原有的运行器名字，或命令执行位置上的脚本路径记号与本片 `verify` 或计划 `gate.test` 执行位置上的记号相同（命令按 `;` `&&` `||` `|` `&` 换行与括号切段；执行位置是段首词，或紧跟 `bash`、`sh`、`zsh`、`python`、`python3`、`node`、`npx`、`tsx` 的那个词；记号含 `/` 且以 `.sh`、`.py`、`.js`、`.mjs`、`.ts` 结尾；命中运行器名字的段不出记号，只是读写这些文件的命令不算）；读不到计划时只按运行器名字认。没有切片标记时行为 MUST 不变。hook 任何异常 MUST 静默并以 0 退出。
Feature: 同一仓库的任何 worktree 都读得到切片的留痕
Rule: 留痕按切片分文件放在共用目录；文件在就说明 hook 在工作

#### Scenario: hook-writes-slice-rows-to-common-dir
- **GIVEN** 工作树根有指向切片 S1 的标记
- **WHEN** 先后收到一条 pytest 通过的 Bash 事件与一条 pytest 失败的事件
- **THEN** 共用目录里 S1 的留痕文件有两行，依次为 PASS 与 FAIL，切片列是 S1，命令列含 pytest
- **AND** 工作树里的 `<change>/evidence.log` 没有出现

#### Scenario: hook-leaves-heartbeat-on-any-bash
- **GIVEN** 工作树根有指向切片 S1 的标记
- **WHEN** 收到一条不是测试运行的 Bash 事件（`git status`）
- **THEN** hook 以 0 退出，共用目录里 S1 的留痕文件存在且没有任何行
- **AND** 工作树里的 `<change>/evidence.log` 没有出现

#### Scenario: hook-recognizes-verify-script-runs
- **GIVEN** 切片 S1 的 `verify` 是 `bash openspec/changes/c/verify/viewer.sh test src`，`gate.test` 是 `bash tools/full.sh`
- **WHEN** 先后收到三条 Bash 事件：运行 verify 脚本（输出通过）、运行 `bash tools/full.sh`（输出失败）、`ls tools`
- **THEN** 前两条各记一行，依次为 PASS 与 FAIL，命令列分别含 `viewer.sh` 与 `tools/full.sh`
- **AND** `ls tools` 不记

### Requirement: 门禁跨 worktree 读留痕，记录时并回分支
切片门禁判 G5 时，本片的留痕行 SHALL 取「所在工作树 `<change>/evidence.log` 里本片的行」与「共用目录里本片文件的行」之和；工作树那份 MUST 只计时间不早于本片首轮 `start` 时刻的行（首轮 `start` 把该时刻记在共用目录本片的 `.since` 文件里，读不到时不过滤），上一次飞行并回分支的行不算本轮的。两处都不存在时判为 hook 未触发：只留警告，`hooks_missing` 为 true。至少一处存在而没有本片的行时 MUST 判红，`failed` 含 `G5 evidence` 并写明 hook 在工作而本片没跑过测试；此时 `hooks_missing` 为 false。有行时「先红后绿」的判定不变。`record` SHALL 在写门禁结论之前把共用目录里该片的行追加进 `<change>/evidence.log`（已有的行不重复追加，原有内容不动），随后删除共用目录里该片的文件；重复执行 MUST 是空操作。首轮 `start`（不带 `--continue`、不带 `--resume-checkpoint`、没有同片标记）SHALL 删除共用目录里该片的留痕文件；两种接续 MUST 保留它。`flight-evidence/` 下只保留最近 30 个 change 的目录。
Feature: 留痕跟着切片走，不跟着 worktree 走
Rule: 上一轮留下的算数；合回之后分支上读得到

#### Scenario: gate-reads-rows-written-from-another-worktree
- **GIVEN** 共用目录里有切片 S1 先红后绿的两行留痕
- **AND** 本轮门禁跑在另一间新开的 worktree 里，那里的 change 目录没有 `evidence.log`
- **WHEN** 在该 worktree 里运行 `gate S1`
- **THEN** 门禁通过，`hooks_missing` 为 false
- **AND** `failed` 与 `warnings` 里都没有 G5 项

#### Scenario: gate-fails-when-hook-alive-but-no-test-run
- **GIVEN** 共用目录里切片 S1 的留痕文件存在但没有任何行
- **WHEN** 运行 `gate S1`
- **THEN** 门禁判红，`failed` 含以 `G5 evidence` 开头并写明「没跑过测试」的一项
- **AND** `hooks_missing` 为 false

#### Scenario: record-merges-slice-rows-into-branch-log
- **GIVEN** 分支工作树的 `evidence.log` 已有一行主会话的记录
- **AND** 共用目录里有 S1 的两行与 S2 的一行
- **WHEN** 连续两次运行 `record --json <S1 的门禁 JSON>`
- **THEN** `evidence.log` 的内容恰为原有那一行后接 S1 的两行，没有重复，没有 S2 的行
- **AND** 共用目录里 S1 的文件已删除，S2 的文件原样还在

#### Scenario: gate-ignores-branch-rows-from-previous-flight
- **GIVEN** 分支工作树的 `evidence.log` 留着上一次飞行 S1 先红后绿的两行
- **AND** 本次飞行首轮 `start S1` 之后执行体一次测试都没跑
- **WHEN** 运行 `gate S1`
- **THEN** 门禁判红，`failed` 含以 `G5 evidence` 开头并写明「没跑过测试」的一项，`hooks_missing` 为 false
- **AND** 工作树 `evidence.log` 再追加首轮 `start` 之后的先红后绿两行后，`gate S1` 通过

#### Scenario: first-round-start-clears-stale-evidence
- **GIVEN** 共用目录里留着上一次飞行的 S1 留痕，当前 worktree 没有切片标记
- **WHEN** 分别以首轮（不带接续参数）、`--continue`、`--resume-checkpoint` 运行 `start S1`（每次之前恢复那份残留）
- **THEN** 首轮之后残留被删除
- **AND** 两种接续之后残留都还在
