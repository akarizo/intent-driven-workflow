## Why

C3（`mechanical-command-layer`，#28）把 `/clean-after-merged` 改成在 fork 子 agent 里运行，路由键 `cleanup.runner` 由 `model-routing.py frontmatter` 渲染进命令文件。PR 评审留下两条 MEDIUM 与若干 LOW，合并时未处理：

- **汇报缺内容**：fork 里只有子 agent 的最后一条回复会到用户手里，而命令只要求它带 step 4 的结果。step 2 的清理计划（safe / manual / keep 三段，含 keep 的原因）与 step 5 的验证输出，用户都看不到。
- **漂移不可见**：改了 `openspec/model-routing.json` 却没重跑 `frontmatter` 时，`show` 报的是配置里的值，`/clean-after-merged` 实际用的却是 frontmatter 里的旧值。只有手跑 `frontmatter --check` 才能发现。
- **起始 CWD 前提未验证**：`--protect "<起始 CWD>"` 假定子 agent 的起点就是主会话当前所在目录。2026-11-20 的探针已证实这一点：主会话 `cd` 进子目录后，普通子 agent 与 fork 子 agent 的首条 `pwd` 都是该子目录。文档还没有写明这个依据。
- **LOW**：
  - CRLF 换行的命令文件被整份改成 LF；
  - 文件以收尾的 `---` 结束（后面没有换行）时，被误判为非 fork 形态；
  - 退出码说明缺 `frontmatter --check` 的 exit 1；
  - `install.sh` 的补救提示只指向配置文件；
  - 测试文件里有孤儿 `import pytest`、过时的 docstring 与多余空行。

## What Changes

- `/clean-after-merged` 的最后一条回复改为依次包含：step 2 的计划原文、step 4 的 `done` / `failed` 与 manual 档代码块、step 5 的验证输出。
- 文档写明起始 CWD 的依据（探针结论与日期）；`--protect` 须传绝对路径，保护只覆盖传入的路径。
- `flight-doctor.py doctor` 新增 `[routing]` 段：调用 `model-routing.py frontmatter --check`，一致时打印一致，漂移时逐条点名；只报告，恒 exit 0。`install.sh --upgrade` 结束时的体检自然带上这一段。
- `model-routing.py frontmatter` 保留命令文件原有的换行风格（LF / CRLF）；收尾的 `---` 后面没有换行也能识别。
- `install.sh` 渲染失败时的补救提示同时给出两条出路：修好 `openspec/model-routing.json`，或用 `install.sh --upgrade` 刷新 `.claude/`。
- 顺手清掉 C3 自己留下的问题：退出码说明补 exit 1，删孤儿 import，修过时的 docstring 与多余空行，`merged-cleanup.py` 头注释注明 `--protect` 须传绝对路径。

## Capabilities

### New Capabilities
- `routing-frontmatter-hardening`：fork 命令 frontmatter 渲染保留换行风格、识别文件末尾的收尾 `---`，doctor 暴露漂移，安装补救提示给出升级出路。
- `cleanup-fork-report`：`/clean-after-merged` 在 fork 子 agent 里运行时，最后一条回复包含计划、结果与验证三部分；起始 CWD 的依据写进文档。

### Modified Capabilities
（无：`openspec/specs/` 下没有已归档的同名 spec）

## Impact

- `template/.claude/hooks/model-routing.py`：`FRONTMATTER_RE`、`render_frontmatter`、`cmd_frontmatter` 的读写方式，文件头退出码说明。
- `template/.claude/hooks/flight-doctor.py`：`doctor` 新增 `[routing]` 段，头注释同步。
- `template/.claude/commands/clean-after-merged.md`：运行方式与汇报约定。
- `template/.claude/hooks/merged-cleanup.py`：只改头注释。
- `install.sh`：补救提示一行。
- `README.md`：路由一节补一句 doctor 会报漂移。
- 测试：新增 `tests/test_routing_followups.py`；改 `tests/test_install_routing.py`、`tests/test_fork_commands_docs.py`、`tests/test_routing_frontmatter.py`。
- ADR 不动：`DRAFT-mechanical-commands-run-in-isolated-subagent` 的措辞问题只能 supersede，不在本 change 范围。
