## Context

本 change 命中「跨模块」触发器：`model-routing.py`（渲染）、`flight-doctor.py`（体检）、`install.sh`（安装提示）与 `/clean-after-merged` 命令文档各改一处，彼此通过 `frontmatter --check` 的输出与退出码相连。

**现状**：

- **frontmatter 渲染**（`model-routing.py`）：
  - `FRONTMATTER_RE = r"^---\n(.*?)\n---\n"`，要求收尾 `---` 后面紧跟 `\n`。
  - `cmd_frontmatter` 用 `Path.read_text` / `write_text` 读写，两者走 universal newlines：CRLF 读入即被归一成 LF，只要有一个值要改，写回时整份文件变成 LF。
  - `--check` 发现漂移时 exit 1，但文件头的退出码说明只列了 0 / 2 / 3。
- **漂移的可见性**：`show` / `get cleanup.runner` 报配置里的值；`/clean-after-merged` 实际运行用 frontmatter 里的值。两者不一致只能靠手跑 `frontmatter --check` 发现。`flight-doctor.py doctor` 现有 `[runner] [anchors] [gate.test] [declare] [checks] [lock] [tests]` 七段，`install.sh --upgrade` 结束时会运行一次（只读、恒 exit 0）。
- **fork 汇报**（`clean-after-merged.md`）：运行方式一节写「最后一条回复就是交给用户的全部汇报（step 4 的 `done` / `failed` 与 manual 档代码块）」。step 2 要求计划「原样展示」，step 5 要求输出 `git worktree list`；在 fork 里这两处都到不了用户手里。
- **起始 CWD 探针**（2026-11-20，本会话实测）：

  | 步骤 | 结果 |
  |---|---|
  | 主会话 `cd` 进 `.worktrees/baseline-inherit-fixes/template/openspec` | 环境的 primary working directory 随之更新为该目录 |
  | 派普通子 agent（general-purpose），首条 Bash 是 `pwd` | 输出上面的子目录 |
  | 派 fork 子 agent，首条 Bash 是 `pwd` | 输出同一个子目录 |

  结论：子 agent 的起点是主会话 `cd` 之后的当前目录，不是会话最初的启动目录。`--protect "<起始 CWD>"` 的前提成立。PR #28 复核提出的「由主会话把 `pwd` 作为参数传入」因此不必做。
  - 限制：探针用的是 Agent 工具派发；`context: fork` 命令走同一套子 agent 机制，但没有单独实测。

## Goals / Non-Goals

**Goals:**
- 用户在 fork 运行的 `/clean-after-merged` 里看到的内容，与改 fork 之前一样完整：计划、结果、验证。
- frontmatter 漂移由脚本发现，不靠人记得跑 `--check`。
- `frontmatter` 只改 `model` / `effort` 两行的值，文件其余字节（含换行符）不变。
- 补救提示覆盖与配置无关的失败原因。

**Non-Goals:**
- 不改 `merged-cleanup.py` 的判定逻辑与 `--protect` 的语义，只改头注释。
- 不让 `show` 标出 frontmatter 实际值（用户 2026-11-20 选定只在 doctor 里报）。
- 不改 ADR `DRAFT-mechanical-commands-run-in-isolated-subagent` 的措辞：ADR 只能 supersede，措辞问题不值得为此新开一份。
- doctor 不改退出码；`[routing]` 段只报告。

## Decisions

### D1 fork 汇报的组成

最后一条回复依次包含三部分，主会话不再复述：

1. step 2 `plan --markdown` 的输出原文（safe / manual / keep 三段）；
2. step 4 的 `done` / `failed`，与 manual 档命令的 ```` ```bash ```` 代码块（按原因逐条中文说明）；
3. step 5 的 `git worktree list` 与 `git branch --list 'worktree-*'` 输出。

step 2 的「原样展示」改为「原样放进最后一条回复」，step 5 同理。

- **备选**：只报结果，外加 keep 档每条一行原因。被否：看不到 safe 档删了哪些的计划原文，与 fork 之前不一致（用户 2026-11-20 选定全量汇报）。

### D2 起始 CWD 写进文档

- 运行方式一节：起始 CWD 是主会话当前所在目录（主会话 `cd` 过也一样，2026-11-20 探针实测）。
- `--protect` 传绝对路径，即 step 1 `pwd` 的输出；保护只覆盖传入的路径。
- 原因表 `session-cwd` 一行补「只保护 `--protect` 传入的路径」。
- `merged-cleanup.py` 头注释注明 P 应为绝对路径：相对路径会按脚本的 CWD（主 worktree 根）解析。

### D3 doctor 新增 `[routing]` 段

- 位置：`doctor` 的最后一段，排在 `[tests]` 之后。
- 做法：用子进程运行同目录的 `model-routing.py frontmatter --check --openspec <openspec 根>`。命令目录取它的缺省值（`<hooks>/../commands`），和 `install.sh` 渲染的是同一份。
- 输出按退出码分三种：

  | 退出码 | `[routing]` 段内容 |
  |---|---|
  | 0 | 原样打印它的一行「frontmatter 与路由一致」 |
  | 1 | 原样打印每条漂移，再加一行修法：在仓库根运行 `python3 .claude/hooks/model-routing.py frontmatter` |
  | 其他（配置非法 / 命令文件缺失或不是 fork 形态 / 脚本不存在） | 打印「不可用：」加 stderr 首行 |

- 恒 exit 0，与其他段一致。
- **为什么用子进程，不 import**：`model-routing.py` 的 `die()` 会 `sys.exit`。子进程把判定逻辑留在原脚本，doctor 只转述结果，符合「判定逻辑不复制」的头注释约定。

### D4 frontmatter 保留换行风格

- **读写**：按字节读写，`path.read_bytes().decode("utf-8")` 与 `path.write_bytes(new.encode("utf-8"))`，关掉换行转换。
- **识别**：`FRONTMATTER_RE` 改为 `^---(\r?\n)(.*?)\r?\n---(\r?\n|\Z)`（`re.S`）。
  - 首行换行符记为文件的换行风格 `eol`；
  - 收尾 `---` 后面的换行可以没有（文件末尾）。
- **拼接**：块内各行按 `eol` 切分与拼接；收尾 `---` 后面沿用原文的那段（可能为空），不硬补换行；块外内容 `text[m.end():]` 原样保留。
- **效果**：没有值要改时 `new == text`，不写文件（现有行为）；有值要改时，只有 `model` / `effort` 两行的值变了，其余字节不变。
- **备选**：只支持 LF，遇到 CRLF 就 exit 2。被否：CRLF 仓库的安装渲染会失败（用户 2026-11-20 选定保留原换行）。

### D5 安装补救提示

`install.sh` 渲染失败分支的第二行 `log_err` 改为给出两条出路：修好 `openspec/model-routing.json`，或用 `install.sh --upgrade` 刷新 `.claude/`；两者之后都在目标仓库根重跑 `python3 .claude/hooks/model-routing.py frontmatter`。失败分支照旧不改 install 的退出码。

### 动态图（C4 dynamic，ASCII）

```
 install.sh --upgrade        model-routing.py                       .claude/commands/clean-after-merged.md
 ────────────────────        ────────────────                       ──────────────────────────────────────
 渲染 ─────────────────────▶ frontmatter ─── 按字节读，保留 eol ─────▶ 只改 model / effort 两行
   失败 → 提示：修配置 或 --upgrade
 体检 ──▶ flight-doctor.py doctor
            [routing] ─────▶ frontmatter --check（子进程，只读）──── 读 frontmatter ──▶ 一致 / 漂移逐条 / 不可用
 主会话 /clean-after-merged ─▶ fork 子 agent（起点 = 主会话当前目录）
            plan → apply --protect <起始 CWD> → 最后一条回复 = 计划 + 结果 + 验证
```

- **边界**：`model-routing.py` 是 frontmatter 唯一的写方；doctor 只读；命令文档约束子 agent 的汇报。
- **假设**：`context: fork` 命令与 Agent 工具派发的子 agent 起点规则相同（见 Context 中的限制）。

## Risks / Trade-offs

- **[风险] fork 命令的起点规则与 Agent 派发不同**：探针没有直接跑 `context: fork` 命令。→ **缓解**：
  - 文档写明依据与日期；
  - 真不同时，`--protect` 保护的是子 agent 自己 `pwd` 出来的目录，最坏情况就是现状（复核所说的残余边界）；
  - `merged-cleanup.py` 的判定不变。
- **[风险] doctor 的子进程开销**：多一次 Python 启动，约百毫秒级；doctor 只在升级结束与人工体检时运行，可接受。
- **[权衡] 汇报变长**：计划原文可能有几十行。换来的是用户能看到 keep 档的原因与 safe 档删了什么，这是 fork 之前就有的信息。

## Migration Plan

- 不迁移数据。下游执行 `install.sh --upgrade` 即拿到新命令文档与脚本；升级结束的体检会显示 `[routing]` 段。
- 回滚：revert 本 change 的代码 commit。

## Open Questions

- 无。三项决策已在 2026-11-20 定下：全量汇报、doctor 加一节、保留原换行。
- 与在役 ADR 一致：`DRAFT-mechanical-commands-run-in-isolated-subagent` 规定机械命令在不继承对话的子 agent 里运行，本 change 只补汇报约定与文档依据，不需要 supersede。
