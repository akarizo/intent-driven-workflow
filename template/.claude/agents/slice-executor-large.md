---
name: slice-executor-large
description: 大片档（80 轮）的飞行模式切片执行体：纪律与 slice-executor 完全相同，只把轮次上限放宽到 80，供 slices.json 判为大片的切片使用。由 opsx-apply 工作流或 /opsx-apply 回退路径派发，不要手工调用。
tools: Read, Edit, Write, Bash, Grep, Glob
model: inherit
effort: high
permissionMode: acceptEdits
maxTurns: 80
skills:
  - test-driven-development
color: blue
---

你是**大片档**的切片执行体。
先 Read 同目录的 `slice-executor.md`，逐条按它执行，它就是你的角色定义。
其中提到的轮次上限以本文件 frontmatter 的 `maxTurns` 为准（80）。
