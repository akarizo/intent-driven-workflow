## Why

PR #30（`mechanical-layer-followups`）的干净评审留下 2 条 MEDIUM 与 4 条 LOW：

- doctor 会把 `model-routing.py` 自己的崩溃误报成漂移，并给出错误的修法；
- 两个 doctor 用例绑在仓库真实的命令文件上，有人改本仓库 `cleanup.runner` 的路由就会误红；
- 另有若干 LOW：doctor 解码兜底、文档措辞、断言强度。

另外，用户（2026-11-20）要求 `openspec/model-routing.json` 默认就存在，便于直接调整，并且每个键自带说明。现状是：

- 下游仓库装完没有这个文件，11 个键里有几个、各管哪个派发点，只能去翻 README；
- 本仓库的文件也只写了 2 个键。

## What Changes

- **frontmatter 渲染**：`model-routing.py frontmatter` 读写命令文件失败时（不是 UTF-8、读不了、写不了），以退出码 2 点名文件，不再带 traceback 以 1 退出。退出码 1 只表示漂移。
- **doctor `[routing]` 段**：
  - 退出码 1 但 stdout 没有漂移条目时，报「不可用」加 stderr 末行，不给修法；
  - 子进程输出按 UTF-8 宽松解码，解码失败不再吞掉整份 doctor 报告。
- **doctor 用例隔离**：两个 doctor 用例改为在临时目录里运行复制出来的 hooks 与命令文件，不再读仓库真实的 `clean-after-merged.md`。
- **`/clean-after-merged` 文档**：
  - 运行方式一节注明 `context: fork` 命令本身未单独实测；
  - step 1 注释措辞与运行方式一节对齐；
  - 相应断言改为整句匹配。
- **新增 `model-routing.py init`**：
  - openspec 根没有 `model-routing.json` 时，写出全部 11 个键：内建默认值，每键带 `desc`，顶层带 `$comment`；
  - 文件已存在时只补缺失的键与缺失的 `desc`，不改已有的 `model` / `effort`；
  - 配置非法时以退出码 2 报错，不动文件。
- **校验器**：接受每键的 `desc` 字段与顶层 `$comment`。
- **安装**：`install.sh` 安装与 `--upgrade` 都运行 `init`，失败不改变 install 的退出码。
- **本仓库配置**：本仓库的 `template/openspec/model-routing.json` 用 `init` 补全为 11 键，`flight.executor` 两档保持 opus · medium。

## Capabilities

### New Capabilities
- `routing-doctor-hardening`：frontmatter 渲染对命令文件读写失败的报错，以及 doctor `[routing]` 段对崩溃与解码失败的报告。
- `cleanup-doc-precision`：`/clean-after-merged` 文档对起点依据的限定与措辞一致。
- `routing-config-seeded`：`model-routing.json` 默认存在、全键显式、每键自带说明，以及安装 / 升级时的补全规则。

### Modified Capabilities
- 无。前序 change 的 capability 尚未归档进 `openspec/specs/`。

## Impact

- **代码**：
  - `template/.claude/hooks/model-routing.py`：frontmatter 报错、`init` 子命令、校验放宽 `desc` / `$comment`；
  - `template/.claude/hooks/flight-doctor.py`：`doctor_routing`；
  - `install.sh`：运行 `init` 与收尾提示措辞。
- **文档**：
  - `template/.claude/commands/clean-after-merged.md`；
  - `README.md` 模型路由一节。
- **配置**：`template/openspec/model-routing.json` 补全为 11 键。
- **测试**：
  - `tests/test_routing_followups.py`
  - `tests/test_fork_commands_docs.py`
  - `tests/test_install_routing.py`
  - 新增 `tests/test_routing_seed.py`
- **下游**：
  - `install.sh --upgrade` 后，目标仓库多出（或补全）`openspec/model-routing.json`；
  - 已有的值不变；
  - 以后模板改内建默认，已装仓库里写好的值不会跟着变（用户 2026-11-20 选定全写显式值）。
