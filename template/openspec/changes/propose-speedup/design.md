## Context

现状（main @ 03a2077，C1 已合入）：

- propose 的 step 3 要求逐个工件调用 `openspec instructions <id> --change <name> --json`。openspec 1.3.1 一次只出一个工件，5 个工件就是 5 次工具往返；输出里有 `instruction` / `template` / `rules` 等字段。
- 切片包、`tasks.md`、测试骨架全由模型逐字写，没有生成器。`tasks.md` 的格式见 `schemas/intent-driven/templates/tasks.md`：一片一行，`- [ ] S<n> <标题> （deps: … · verify: \`…\`）`。
- 现有 G4 检查是 `slice-gate.py` 的 `gwt_violations(root, test_files)`，切片门禁时才运行；G7 用 `scenario_status` 判 xfail 标记与实跑结果。
- baseline 的复用候选依次是：本 change 旧基线 → 锚点 → 基线池（`_baseline_candidates`）。
  - **本 change 旧基线**（`_try_reuse(own=True)`）的条件：`ok` 或 `test_ok` 为真；`cmd_key` 相同；Δ 只有 `test_*.py`。计划工件不算进 Δ（`PLAN_FILES` / `PLAN_DIRS`）；本 change 目录里在 gate.test 闭包内、且内容没变的脚本也不算。满足时只补跑 Δ 里的测试文件，允许有预存红，只要改动的测试文件不在预存红里。
  - **有 `test-tiers.json` 时**没有任何候选，恒走全量（`nocand = args.full or tiers is not None`，原设计 D5：G10 / G11 要单元层探针）。
- `cmd_key` 把命令文本与命令直接引用的仓库内文件（含 shell 闭包）的内容做指纹；本 change 的目录名会被归一成 `<change>`。所以只要文件内容按词边界替换后相同，在另一个 change 目录下的同名包装脚本也算同一个指纹。
- `cmd_baseline` 在取锁之前读旧基线；旧基线是运行标记（`running: true`）时按 None 处理。preflight 用 pid 判断运行标记是「仍在跑」还是「已中断」。
- afa 的 `gate.test` 是每个 change 自带的包装脚本（`bash openspec/changes/<name>/verify/full_suite.sh`），没有分层文件。本仓库是 `python3 -m pytest -q tests`，也没有分层文件。

在役 ADR：
- `DRAFT-baseline-reuse-by-content-fingerprint`：本 change 旧基线复用；
- `DRAFT-baseline-reuse-via-dependency-anchor`：锚点；
- `DRAFT-execution-routing-by-config`：规划期只用主会话或 fork。

本 change 只是给这些规则多提供一个候选、多一种派发方式，不改其中任何一条。

## Goals / Non-Goals

**Goals**
- 机械搬运的部分改由脚本生成：instruction 汇总、tasks.md、切片包的机械区、测试骨架。
- 补断言这一步按测试文件用 fork 并行，fork 不可用时由主会话串行补，语义与现状一致。
- baseline 的全量提前到规划开始时在后台跑，正式 baseline 能复用就只补跑骨架。
- 骨架没补完不能起飞（机械红线）。

**Non-Goals**
- 不改 baseline 的复用规则；分层仓库不预热。
- 不改 `/opsx-continue`、schema 的 tasks instruction 与 spec.html。
- 不让 fork 写 proposal / design / specs / ADR / slices.json（Q8-A）。
- 不预估提速分钟数，合入后用探针实测。

## Decisions

### D1 · 新工具放进两个新脚本，预热放进 slice-gate.py

- **`plan-kit.py`**（instructions / tasks / packets）与 **`plan-scaffold.py`**（scaffold / gwt）都是新文件。两个文件能在同一个 wave 里并行实现，也不会把 6000 多行的 `slice-gate.py` 再撑大。
- **`warm`** 要复用 `cmd_baseline` 的整套机制：快照、指纹、锁、锚点、账本、运行期间改动检测，所以只能放进 `slice-gate.py`。
- **`gwt`** 按路径加载 `slice-gate.py`，复用 `gwt_violations`，不复制判据。

### D2 · instructions：一次运行，按工件分节打印

- 先运行 `openspec status --change <name> --json`，取 `artifacts`；对其中每个 `status != "done"` 的工件，再运行 `openspec instructions <id> --change <name> --json`。
- 按工件依次打印一节：`## <id> → <outputPath>`，下面依次是 instruction、template、rules（rules 为空就省略）。
- `--all` 时 done 的工件也打印。
- 命令在当前目录运行（与 openspec CLI 一致），任一次失败 → exit 2，stderr 写出失败的命令与它的 stderr。

### D3 · tasks：生成、保留勾选

- **格式**与 `templates/tasks.md` 逐字一致：
  - 文件头是注释行 `<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->`；
  - 然后是 `## 切片`；
  - 每片一行 `- [ ] <id> <title> （deps: <逗号分隔或 -> · verify: \`<verify>\`）`。
- 旧 `tasks.md` 里已勾选（`[x]`）的切片 id 保持勾选。

### D4 · packets：机械区由标记包住，标记外原样保留

`slices/<S>.md` 的机械区放在 `<!-- plan-kit:begin -->` 与 `<!-- plan-kit:end -->` 之间，内容依次为：
- 标题行 `# <S> · <title>`；
- `## owns`；
- `## 依赖的切片`：每个 dep 一行「`<dep>` · 标题 · 包路径」，没有依赖时写「无」；
- `## scenario`：每个 scenario 一个小节，含能力名、scenario 名、映射的测试 `path::func`，以及取自 `specs/<能力>/spec.md` 的 GIVEN / WHEN / THEN / AND / BUT 原文；
- `## verify`。

文件不存在 → 只写机械区；已存在 → 只替换标记之间的内容，标记之外的文字一个字节不动。已存在但没有标记 → 把机械区插到文件最前面，原内容整体保留在后面。

备选：审批页设想的 `slices.json` 里加 `brief` / `notes` 字段，否决。长段 markdown 写进 JSON 字符串要转义换行，写起来更贵，也更容易出错；标记区让主会话照常写 markdown。

### D5 · scaffold：只补缺的函数，占位断言带固定标记

对 `scenario_tests` 的每一项 `path::func`：
- `path` 不是 `.py` → 记进 `skipped`，不动文件；
- 函数已存在（与 G7 同样的 `def <func>(` 匹配）→ 不动；
- 否则追加：
  ```python
  @pytest.mark.xfail(strict=True, reason="<切片 id> 未实现")
  def <func>():
      # Given: <GIVEN 原文>；<AND 原文>…
      # When: <WHEN 原文>
      # Then: <THEN 原文>；<AND / BUT 原文>…
      assert False, "PLAN-SCAFFOLD-PLACEHOLDER：换成真实断言"
  ```
  - AND / BUT 并入它前面那个关键字所在的行；
  - 函数参数为空，需要 fixture 由补断言的人改；
  - 新文件写入 docstring：「<能力名> 的 scenario 骨架（strict xfail；切片 <S> 实现后去掉标记即解锁）」，再加 `import pytest`；已有文件缺 `import pytest` 时，插在最后一条顶层 import 之后（没有 import 就插在 docstring 之后）。
- **输出**：stdout 打印 JSON `{"created": [path::func…], "existing": […], "skipped": […]}`，exit 0。scenario 在 specs 里找不到 → exit 2，点名。
- **占位标记**：固定字符串 `PLAN-SCAFFOLD-PLACEHOLDER`，`plan-scaffold.py` 与 `slice-gate.py` 各自定义同名常量。两边一致由 S4 的端到端 scenario 机械保证。

### D6 · gwt 与 lint 红线

- **`plan-scaffold.py gwt --change-dir`**：对 `scenario_tests` 涉及的测试文件跑 `gwt_violations`，只报映射到的函数；再找函数体里残留的占位标记。逐条打印，有任何一条 → exit 1。
- **`slice-gate.py lint`**：给了 `--change-dir` 时，对 `.py` 的 scenario 测试函数查占位标记，命中 → 判红：`skeleton: <path::func> 仍是 scaffold 占位断言`。现有夹具不含这个标记，不会扩散。

### D7 · warm：写成本 change 的旧基线，正式 baseline 按原规则复用

`slice-gate.py warm --change-dir D [--cmd CMD]`：

1. **定命令**：
   1. `--cmd` 显式给出时用它；
   2. openspec 根有 `test-tiers.json` → 打印「跳过预热：分层仓库的 baseline 恒走全量」，exit 0，不写任何文件；
   3. 否则在 `<changes 根>`（不含 `archive/`）里，找 `slices.json` mtime 最新、且不是本 change 的那个，取它的 `gate.test`（同时带上 `gate.pytest`）；
   4. 找不到 → 打印「跳过预热：没有可沿用的 gate.test」，exit 0。
2. **沿用包装脚本**：命令里引用的文件（含 shell 闭包）落在来源 change 目录下的，复制到本 change 目录的同一相对位置（已存在就不覆盖），并把命令文本里的来源目录换成本 change 目录。
3. **跑全量**：与 `cmd_baseline` 同一条路径，用只含 `gate.test`（以及 `gate.pytest`）的计划。没有切片、检查、lint / typecheck，不做选测范围复核，不复用任何候选，恒全量。
   - 运行标记与结果都带 `"warm": true`；
   - 结果的 `plan_sha` 为 null；
   - 锚点、基线池、账本照常写（它就是一次合法的全量）；
   - 运行期间的改动检测照旧：主会话在预热期间改了已有文件或测试文件 → 结果 `ok: false`、`test_ok: false`，不会被复用。
4. **记录**：时间线记 `warm` 事件；stdout 打印结果 JSON，打印的命令就是建议的 `gate.test`；退出码按 ok。

**正式 baseline 的配合**：`cmd_baseline` 在读旧基线之前，如果 `gate-baseline.json` 是 `warm: true` 的运行标记，且 pid 还活着 → 往 stderr 打一行「等待预热结束」，每 2 秒检查一次，直到它不再是运行标记或进程退出，然后照常读旧基线。之后由现有 `_try_reuse(own=True)` 判断能否复用，规则一个字不改。

**命中条件**（未改规则的推论，写进 propose 文档）：
- 计划的 `gate.test` 与 warm 打印的命令相同；
- 预热之后除计划工件外只改了 `test_*.py`。

新写 ADR 这类非测试文件会让复用落空，回退到锚点、池或全量，与现状一致。

备选：在临时 worktree 里预热，否决。afa 一间 worktree 约 1G，建得慢；运行期间改动检测已经能挡住预热期间被改过的情况。

### D8 · propose 流程与 fork 补断言（命令与 skill 同改）

1. step 2 建 change 目录之后，立即后台运行 `slice-gate.py warm --change-dir …`，不等它结束。
2. step 3 改为运行一次 `plan-kit.py instructions --change <name>`。
3. tasks 阶段写完 `slices.json` 之后：
   1. `plan-kit.py packets`：在每个切片包标记区之后写接口约定与注意事项；
   2. `plan-scaffold.py scaffold`；
   3. **补断言**：按测试文件分组。
      - 多于 1 组：同一条消息里为每组派一个 fork（Agent 工具，`subagent_type: "fork"`）。prompt 写明「只改这些文件：把 `PLAN-SCAFFOLD-PLACEHOLDER` 那行换成真实断言，保留 GWT 注释与 xfail 标记；不碰其他文件；完成后运行 `plan-scaffold.py gwt --change-dir …`，回报改了哪些函数」。
      - fork 报错或不可用 → 由主会话串行补完剩下的组。
      - 只有 1 组 → 主会话自己写。
   4. `plan-scaffold.py gwt` 必须 exit 0；
   5. `plan-kit.py tasks`；
   6. `slice-gate.py lint`；
   7. `model-routing.py pin`。
4. fork 不进路由配置（C1 不变式）。`test_routing_docs.py` 的规划期扫描改为：正文里每个 `subagent_type` 都必须是 `"fork"`；`model: "` 仍然禁止。

## Risks / Trade-offs

- **[风险] 多个 fork 同时写测试，写法各自为政** → 按文件分组避免互相覆盖；gwt 与 lint 机械验收；不合格的组由主会话接手。
- **[风险] fork 在非交互会话里是否默认开启，文档没写** → 每处都有主会话串行回退（铁律 10）。
- **[取舍] 预热与规划争 CPU** → 预热与正式 baseline 一样持全机测试锁；锁被别人持有时预热排队，不会叠两套全量。
- **[风险] 预热期间改了被测代码** → 运行期间改动检测把结果判为不可复用，正式 baseline 回退到原路径，不会误用。
- **[取舍] 有新 ADR 的 change 命不中复用** → 与现状一致，不放宽规则；是否把 `openspec/adr/` 声明为 inert 由各仓库决定，留作后续。
- **[未验证] 提速幅度** → 合入后用审批页第 02 节同一套探针重测 3 次 propose。

## Migration Plan

- 合入后：下游 `install.sh --upgrade` 拿到新的 hooks 与文档即可生效，不需要迁移数据。
- 回滚：revert 即可。预热写的 `gate-baseline.json` 一定会被正式 baseline 覆盖；packets 的标记是注释，旧流程会忽略它。

## Open Questions

- 无阻断项。不立新 ADR：工具化归铁律 9（零 token 优先），fork 规则已在 `DRAFT-execution-routing-by-config`，预热不改任何复用规则。
