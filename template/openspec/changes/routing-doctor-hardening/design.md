## Context

本 change 命中「跨模块」触发器：`model-routing.py`（渲染 / 初始化 / 校验）、`flight-doctor.py`（体检）、`install.sh`（种子）、`/clean-after-merged` 命令文档与本仓库路由配置各改一处，彼此通过 `model-routing.py` 的退出码与 `model-routing.json` 的形状相连。

**现状（main 851183a）**：

- **frontmatter 渲染的退出码**：`cmd_frontmatter` 用 `path.read_bytes().decode("utf-8")` 读命令文件。
  - 文件不是 UTF-8 时抛 `UnicodeDecodeError`，Python 带 traceback 以 1 退出，与「`--check` 发现漂移」的 exit 1 撞号。
  - PR #30 评审的定向抽查证实了这一点。
- **doctor `[routing]` 段**：`doctor_routing` 认定退出码 1 就是漂移。它原样打印 stdout 各行，再追加「修法：…frontmatter」。
  - 崩溃时 stdout 为空，用户只看到一行错误的修法。
  - `subprocess.run(..., text=True)` 按 locale 严格解码。子进程输出解码失败时异常越过 `doctor_routing`，被 `main()` 的兜底吞掉，整份 doctor 报告只剩一行「flight-doctor doctor 失败」。
- **doctor 用例**（`tests/test_routing_followups.py`）：
  - drift 与 in-sync 两个用例运行仓库真实的 `flight-doctor.py`，后者调用的 `model-routing.py` 读的是仓库真实的 `template/.claude/commands/clean-after-merged.md`；
  - drift 用例硬断言该文件是 sonnet · low，in-sync 用例要求它等于内建默认。
- **路由配置文件**：
  - `install.sh` 的 openspec 种子是显式清单（`.gitignore config.yaml changes/.gitkeep adr/.gitkeep superpower/.gitkeep`），没有 `model-routing.json`，下游装完没有这个文件；
  - 本仓库的 `template/openspec/model-routing.json` 只写 `flight.executor` / `flight.executor-large` 两键；
  - 校验器 `validate()` 拒绝未登记的顶层键（`$comment` 会判红）。`check_value()` 不检查额外字段（`desc` 目前就能过）。
- **文档**：
  - `clean-after-merged.md` 第 16 行写「普通子 agent 与 fork 子 agent 的首条 `pwd` 都是该子目录」，但探针（2026-11-20）用的是 Agent 工具派发，没有直接跑 `context: fork` 命令；
  - 第 26 行注释仍是「主会话所在目录」。

## Goals / Non-Goals

**Goals:**
- `model-routing.py frontmatter` 的退出码 1 只表示漂移；读写失败点名文件、以 2 退出。
- doctor 的 `[routing]` 段：崩溃或解码异常时报「不可用」，不给错误修法，也不吞掉其他段。
- doctor 用例不读仓库真实的命令文件与配置。
- `openspec/model-routing.json` 默认存在：11 键全写显式值，每键带 `desc`，用户直接改值即可（用户 2026-11-20 选定）。
- 安装与升级只补缺，不改用户写过的值。

**Non-Goals:**
- 不改「文件缺失 / 缺键走内建默认」的语义，`effective()` 照旧。老仓库没跑 `init` 也照常工作。
- 不改 `show` / `pin` / `resolve` 的输出形状。`show` 的 `source` 列在补全后会显示 `repo`，这是如实反映。
- 不随升级刷新已有键的值或已有的 `desc`：用户可能改过。
- 不处理 #29 的 LOW（用户 2026-11-20 只要 #30 遗留）。
- 不改 ADR。

## Decisions

### D1 frontmatter 读写失败走退出码 2

- `cmd_frontmatter` 对每个命令文件：
  - `read_bytes()` 抛 `OSError` → `die(EXIT_INVALID, ["<键>：读不了命令文件 <路径>：<错误>"])`；
  - `decode("utf-8")` 抛 `UnicodeDecodeError` → `die(EXIT_INVALID, ["<键>：<路径> 不是 UTF-8 文本"])`；
  - `write_bytes()` 抛 `OSError` → `die(EXIT_INVALID, ["<键>：写不了命令文件 <路径>：<错误>"])`。
- 文件头退出码说明的 exit 2 一行补上「命令文件读不了 / 不是 UTF-8 / 写不了」。
- 备选：只在 doctor 侧兜。被否：exit 1 仍然二义，`install.sh` 等其他调用方照样分不清（用户 2026-11-20 选定两端都修）。

### D2 doctor `[routing]` 段按 stdout 内容区分漂移与崩溃

| 退出码 | stdout 有非空行 | `[routing]` 段内容 |
|---|---|---|
| 0 | — | 首行（「frontmatter 与路由一致」） |
| 1 | 有 | 原样各行 + 修法行（现状） |
| 1 | 无 | 「不可用：」+ stderr 最后一个非空行（traceback 的异常行），不给修法 |
| 其他 | — | 「不可用：」+ stderr 首个非空行（现状） |

- `subprocess.run` 改为 `encoding="utf-8", errors="replace"`：解码不再抛异常，其他段照常输出。
- 备选：在 `doctor()` 里给 `doctor_routing` 包 `except (Exception, SystemExit)`。被否：异常会让 `[routing]` 段整段丢失；宽松解码更直接，且保留输出内容。

### D3 doctor 用例在临时目录里跑复制的 hooks

- 测试 helper 把仓库的 `template/.claude/hooks/` 复制到 `tmp/.claude/hooks/`（忽略 `__pycache__`），在 `tmp/.claude/commands/` 写一份命令文件，openspec 根取 `tmp/openspec/`，再运行复制出来的 `flight-doctor.py doctor --openspec-root tmp/openspec`，cwd 为 `tmp`。
- `model-routing.py` 的命令目录缺省值是 `<自身目录>/../commands`，复制后自然指向 `tmp/.claude/commands`，产品代码不用为测试加参数。
- in-sync 用例：命令文件的 `model` / `effort` 取复制出来的 `model-routing.py get cleanup.runner --openspec <空根>` 的输出，不在测试里写死内建默认。
- 崩溃 / 解码类场景：把复制出来的 `model-routing.py` 换成桩脚本（抛异常 / 输出非 UTF-8 字节）。
- 备选：从真实文件当前值推导期望。被否：仍读真实文件；in-sync 的前提会从「内建默认」变成「当前值」（用户 2026-11-20 选定复制 hooks）。

### D4 `model-routing.py init`：种下并补全配置

- **说明文本的唯一来源**：`model-routing.py` 里新增 `DESC = {"组.键": "<一句话>"}`，键集合与 `BUILTIN` 相同（测试校验）。文本依据 README 模型路由表的「派发点」列：

  | 键 | desc |
  |---|---|
  | `flight.executor` | 飞行中实现切片的 slice-executor（标准档） |
  | `flight.executor-large` | 飞行中实现大片档切片的 slice-executor-large |
  | `flight.fixer` | 飞行中的修复派发（评审后的批量修复 fix、wave 跨片修复 fix:w<i>） |
  | `flight.reviewer` | 飞行中的 code-reviewer（切片评审 / 复核） |
  | `flight.integrator` | 飞行中的 integrator（合回切片 · wave 集成检查 · final 门禁） |
  | `ship.reviewer` | /pr-ship 对整个 PR 的干净评审 |
  | `ship.followup` | /pr-ship 自动修复后的复核评审 |
  | `archive.sync` | /opsx-archive 选择同步时，把 delta spec 同步进主 specs 的子 agent |
  | `claudemd.evidence` | /claudemd-standardize 的证据调查子 agent（读文件核验真实路径） |
  | `bulk.apply` | /opsx-bulk-apply 为每个 change 派的执行子 agent |
  | `cleanup.runner` | /clean-after-merged 的 fork 子 agent（不继承对话）；改后在仓库根运行 python3 .claude/hooks/model-routing.py frontmatter |

- **顶层 `$comment`**：一个字符串，写明：
  - 每个「组.键」是一个派发用途；
  - model 只写模型名（`MODELS`），effort 取 `EFFORTS`；
  - 删掉某键 = 走内建默认；
  - `desc` 只作说明；
  - 改 `cleanup.runner` 后要运行 `frontmatter`。
- **`init [--openspec DIR]`**，按文件状态分三种：

  | 文件状态 | 动作 | 退出码 |
  |---|---|---|
  | 不存在 | 写出 `$comment` + 11 键（`BUILTIN` 值 + `DESC`），按 `REGISTRY` 的组 / 键顺序 | 0，打印「已写入 11 个键」 |
  | 存在且合法 | 只补缺失的键（内建值 + desc）、缺失的 `desc`、缺失的 `$comment`；已有的 `model` / `effort` / `desc` 不动；没有要补的就不写文件 | 0，打印「补 N 个键 · 补 M 条说明」或「已完整」 |
  | 存在但非法（JSON 坏 / `validate` 报错） | 不写文件，stderr 逐条点名 | 2 |

- **写出格式**：`json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"`。补全已有文件时会重排格式，这是可接受的代价：只在确实有缺项时才写。
- **校验放宽**：
  - `validate()` 跳过顶层 `$comment`（值须是字符串）；
  - `check_value()` 接受可选的 `desc`（须是字符串）。
  - 其余未登记字段照旧不检查（不收紧，避免打破已有配置）。
- **备选**：只写说明与只读的 `default`，写了值才覆盖。被否：要分清哪些是提示、哪些是覆盖，用户选定「所见即所用」。
- **代价**：模板以后改内建默认，已装仓库里写好的值不跟着变（用户 2026-11-20 接受）。

### D5 安装与升级运行 `init`

- `install.sh` 在 fork 命令渲染（`frontmatter`）之前运行 `python3 "$TARGET/.claude/hooks/model-routing.py" init --openspec "$TARGET/openspec"`，安装与 `--upgrade` 都跑：
  - 成功 → `log_add` / `log_info` 打印它的一行输出；
  - 失败 → `log_err` 点名，并提示修好 `openspec/model-routing.json` 后在目标仓库根重跑 `init`，不改变 install 的退出码；
  - 没有 python3 → 与现有分支一致，只打印提示。
- 收尾说明（第 521 行一带）的「缺省内建默认，仓库可写 openspec/model-routing.json 覆盖」改为「安装时种下 openspec/model-routing.json（11 键全写、每键带 desc），直接改值」。
- 本仓库：`template/openspec/model-routing.json` 由 S3 运行一次 `init` 补全。`flight.executor` 两档的 opus · medium 不变，所以已钉进 `slices.json.routing` 的值与生效值一致。
- README 模型路由一节同步：「文件缺失或缺键走内建默认」后补一句「安装与升级时 `model-routing.py init` 种下完整文件（11 键、每键带 `desc`），只补缺、不改已有值」。

### 动态图（C4 dynamic，ASCII）

```
 install.sh（安装 / --upgrade）
   ├─▶ model-routing.py init ──▶ openspec/model-routing.json   不存在→写 11 键+desc；存在→只补缺；非法→exit 2 不动
   └─▶ model-routing.py frontmatter ──▶ .claude/commands/clean-after-merged.md
                                         读写失败 / 非 UTF-8 → exit 2（点名文件）；漂移(--check) → exit 1
 flight-doctor.py doctor
   └─▶ [routing] ─▶ frontmatter --check（子进程，UTF-8 宽松解码）
                     exit 0 → 一致；exit 1 且有漂移行 → 漂移+修法；exit 1 无漂移行 / 其他 → 不可用：<stderr>
```

- **边界**：
  - `model-routing.py` 是 `model-routing.json`（init）与 fork 命令 frontmatter（frontmatter）唯一的写方；
  - doctor 只读；
  - install 只调用、不判定。
- **假设**：`init` 运行在 `frontmatter` 之前，所以首次安装渲染出的 frontmatter 等于种下的值（与内建默认相同）。

## Risks / Trade-offs

- **[风险] 补全时重排了用户手写的格式（缩进、键顺序）** → **缓解**：只在确实有缺项时写；值与 `desc` 逐字保留。
- **[风险] `show` 的 `source` 列在补全后全是 `repo`，看不出哪些等于内建默认** → **缓解**：如实反映「值来自文件」；用户要回到内建默认就删掉该键。不在本 change 加标记（Non-Goals）。
- **[权衡] 内建默认不再自动传到已装仓库**：用户选定「所见即所用」的代价，写进 README。
- **[风险] doctor 用例复制整个 hooks 目录变慢** → **缓解**：hooks 目录是几十个小文件，复制在毫秒级；测试仍是单元层。

## Migration Plan

- 下游执行 `install.sh --upgrade`：
  - 拿到新脚本；
  - `init` 种下或补全 `openspec/model-routing.json`；
  - 已有值不变，frontmatter 随后按它渲染。
- 回滚：revert 本 change 的代码 commit。已种下的 `model-routing.json` 内容等于内建默认（或用户原值），留着不影响旧脚本：旧校验器对 `$comment` 会判红，回滚时需一并删掉 `$comment` 键或整个文件。

## Open Questions

- 无。已在 2026-11-20 定下的决策：
  - 误报两端都修；
  - 用例复制 hooks 隔离；
  - 文档补「未单独实测」；
  - 种子并进本 change；
  - 11 键全写显式值；
  - 说明用每键 `desc`。
- 与在役 ADR 一致：
  - `DRAFT-execution-routing-by-config` 规定执行层路由由配置驱动、缺键走内建默认，本 change 只让配置文件默认存在，不改这一语义；
  - `DRAFT-mechanical-commands-run-in-isolated-subagent` 不受影响。
