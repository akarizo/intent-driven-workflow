## ADDED Requirements

### Requirement: /pr-ship 评审出 CRITICAL/HIGH 时直接自动修复
`/pr-ship` 的独立评审（首审或复核）给出 CRITICAL / HIGH 时，命令 SHALL 直接进入自动修复，不问「自动修还是只贴评论」：

1. 主会话按 finding 的修法修代码，每个独立修复点一个 commit，然后 push；
2. 派一个新的 code-reviewer 以 follow-up 模式复核，复核报告同样贴成 PR 评论；
3. 至多 2 轮，跑满 2 轮仍有 CRITICAL / HIGH 就停下交人，列出仍阻断的 finding；
4. 收尾复裁照旧。

命令全程 SHALL 不使用 AskUserQuestion。MEDIUM / LOW 仍只写进评论、不自动修。不代用户合并、不推 main 等既有边界不变。

#### Scenario: pr-ship-autofixes-without-asking
- **GIVEN** 本 change 合入后的 `template/.claude/commands/pr-ship.md`
- **WHEN** 检查其文本
- **THEN** 全文不含 `AskUserQuestion`，也不含「只贴评论交人」
- **AND** 自动修复一步写明 CRITICAL/HIGH 直接修复并 push、不询问，并保留「至多 2 轮」与停下交人
- **AND** Guardrails 写明全程不问询
