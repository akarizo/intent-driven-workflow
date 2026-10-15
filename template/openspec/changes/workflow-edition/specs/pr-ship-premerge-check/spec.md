## ADDED Requirements

### Requirement: 预合并冲突检查按 merge-tree 退出码判断
`/pr-ship` 第 4 步 SHALL 用 `git merge-tree --write-tree --name-only HEAD origin/<target>` 预演合并并按退出码处理：退出 0 = 无冲突进入下一步；退出 1 = 有冲突，报告输出里的冲突文件后停下交人；其他退出码报告错误并停下。SHALL NOT 再用 `grep -c "^<<<<<<<"` 统计旧版 merge-tree 的输出（那里的冲突标记前带 `+`，统计恒为 0）；文档 SHALL 写明需要 git ≥ 2.38。
Feature: pr-ship-premerge-check

#### Scenario: pr-ship-premerge-uses-merge-tree-exit-code
- **GIVEN** `template/.claude/commands/pr-ship.md`
- **WHEN** 取第 4 步「预合并冲突检查」到第 5 步之间的内容
- **THEN** 含 `git merge-tree --write-tree --name-only`、「退出 0」「退出 1」与 2.38
- **AND** 不含 `grep -c "^<<<<<<<"`
