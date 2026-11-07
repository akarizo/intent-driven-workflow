# Gate Report

## 天花板

| 时间 | 切片 | 位置 | 限制 | 升级路径 |
|---|---|---|---|---|
| 2026-11-07T05:16:32Z | S2 | template/.claude/hooks/slice-gate.py:4531 | 逐行正则启发式，不处理续行 / heredoc / 函数返回值 | 漏解析的引用照旧触发全量；误判多时改用 shell 语法树 |

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-11-07T05:07:47Z | S1 | ok | 89f96d471a | - | G5 evidence: 无 evidence.log（test-evidence hook 未安装或未触发），本切片留痕无法核对 |
| 2026-11-07T05:16:32Z | S2 | ok | cf3f741066 | - | G5 evidence: 无 evidence.log（test-evidence hook 未安装或未触发），本切片留痕无法核对 |
| 2026-11-07T05:16:32Z | S4 | ok | 1acbbfe739 | - | G5 evidence: 无 evidence.log（test-evidence hook 未安装或未触发），本切片留痕无法核对 |
