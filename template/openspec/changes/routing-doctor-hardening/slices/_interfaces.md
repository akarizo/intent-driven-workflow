# 公开接口摘要

## S1

- `template/.claude/hooks/flight-doctor.py` `doctor_routing(openspec_root)`：[routing] 段，调用 model-routing.py frontmatter --check；崩溃或不可读报「不可用」，stdout/stderr 按 UTF-8 宽松解码。
- `template/.claude/hooks/model-routing.py` `cmd_frontmatter(args)`：frontmatter 读写失败走退出码 2；非 UTF-8 命令文件被拒绝。
- `tests/test_routing_followups.py`：S1 场景测试。

## S2

- `template/.claude/commands/clean-after-merged.md`：文档，注明 context: fork 命令未单独实测。
- `tests/test_fork_commands_docs.py`：起点依据断言改为整句。
