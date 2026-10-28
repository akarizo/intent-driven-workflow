## Context

- **现状**：`cmd_final`（`slice-gate.py`）只要 G7 绿，就跑以下全部：
  - lint / typecheck，按基线差分；
  - `gate.test` 全量：有分层时是单元层加探针，再加已选区域；
  - 每项 `gate.checks` 的 `final`。

  增量复用只在 `cmd_baseline` 里（`_try_reuse` / `_delta` / 基线池），而且只在「代码树之差只有测试文件」时复用。final 一律全量。
- **实测代价**：
  - 本仓库全量约 130 秒。
  - afa 的 `gate.test` 是 `verify/full_suite.sh`（`exec pytest -n auto`），全量 193–249 秒；三项 checks 各自跑 executor 全量，一次完整 final 观测到 29–42 分钟。
- **重复 final**：
  - fix 子代理修完自跑 final（`opsx-apply.js:212`），final-gate 再跑一次（`:233`），主会话还常在后台再跑。
  - `ship` 只认对齐 HEAD 的 final；`_final_fresh` 只放过记账文件的 commit，而且要求 final commit 是 HEAD 的祖先。
- **计数不一致的根因（已查清）**：`run_test_gate` 经 `PYTEST_ADDOPTS` 注入 `--junitxml`。afa 的预算插件在会话结束时起一个复测子进程，它继承了这个变量，把父会话已写好的 junit 覆盖成自己的 0 失败。afa 在 `e59e0e0c8`（2026-10-28 16:20 +0800）修了自己的插件。库侧任何嵌套 pytest 都可能重演；探针插件同样经 `PYTEST_ADDOPTS -p` 注入，嵌套会话会把幽灵 nodeid 混进探针记录（PR #5 切片评审的 deferred MEDIUM）。
- **可复用的零件**：
  - `_snapshot`：未提交改动快照；
  - `_delta`：两棵树按 blob 比较，排除计划工件与其他 change；
  - `cmd_key`：命令指纹；
  - `_pool_write` / `_pool_candidates`：git common dir 下的池，原子写、只留最新 N 条；
  - `_pytest_outcomes`：G7 的直接 pytest 实跑，带结果插件；
  - `TIER_PROBE_PLUGIN`：审计钩子探针；
  - `_check_env`：检查命令的运行契约。
- **约束**：
  - 本仓库没有 CI，final 是唯一的全量关口。
  - 基线复用 ADR（`DRAFT-baseline-reuse-by-content-fingerprint`）的盲区论证写着「final 跑全量时……会判红。所以最坏是收口多出一条红，不会把红判成绿」。这个前提要被修订。
  - 本 change 叠在 test-tiers（PR #5）之上，那里的 design 写着「final 按分层运行」。

## Goals / Non-Goals

**Goals:**
- final 默认增量：只重跑改动真正影响到的测试文件，其余沿用锚点结论；改一行代码的 final 从分钟级降到秒级。
- 同一棵树的 final 只跑一次，重复调用秒回。
- 嵌套 pytest 不再覆盖 junit、不再污染探针与依赖图。
- checks 能拿到 Δ，自行收窄范围。
- 仓库可用自己的选测命令代替内建选测。
- `/pr-ship` 评审出 CRITICAL/HIGH 时自动修复，不问询。

**Non-Goals:**
- 不改 G7：scenario 用例每次照跑，它是验收本身。
- 不改 baseline 的复用规则：baseline 只多记锚点与 `failed_nodes`。
- 不加 CI，不改 afa 仓库，不改工作流脚本 `opsx-apply.js`（Q3 选了「工作流不改」）。
- 不做函数级选测：粒度是测试文件。
- 非 pytest 仓库不做内建依赖图，只能用 `gate.impacted`，否则全量。

## Decisions

### D1 嵌套会话防护插件 `flight_guard`
- **装载**：`run_test_gate` 与增量重跑时写进临时目录，和 `--junitxml` 一起经 `PYTEST_ADDOPTS` 的 `-p flight_guard` 加载。
- **判外层**（`pytest_configure`，`tryfirst=True`）：
  - 环境里没有 `FLIGHT_GUARD_OWNER`、也没有 `workerinput` 的会话是外层。外层设 `os.environ["FLIGHT_GUARD_OWNER"] = str(os.getpid())`，子进程会继承。外层再用 `pytest_configure_node`（`optionalhook=True`，有 xdist 才生效）给自己的 worker 写 `workerinput["flight_outer"] = 1`。
  - worker 带 `flight_outer` 就算外层的一部分。
  - 其余是嵌套会话：设 `config.option.xmlpath = None`，抢在 junitxml 插件读它之前，并设 `os.environ["FLIGHT_GUARD_NESTED"] = "1"`。
- **生效范围**：探针插件与依赖图插件在写记录前检查 `FLIGHT_GUARD_NESTED`，嵌套时什么都不写。
- **为什么用 worker 标记而不是比 ppid**：嵌套会话自己的 xdist worker 也有 `workerinput`，但嵌套的 controller 已判为嵌套，不会给它们写 `flight_outer`。显式标记比进程关系可靠。
- **加载失败**：泛化现有的 `TIER_PLUGIN_FAIL` 检测，按「`-p` 的模块导入失败」的输出特征识别。识别到就去掉防护、探针、依赖图三个插件，只带 junit 重跑一次，用这次的结果，再给警告「防护插件加载失败（包装命令覆写了 PYTHONPATH？），依赖图未测」。
- **备选**：只在 `_read_probe` 里取第一段 start、或和 junit cases 取交集（评审 deferred 给的退路）。只能治探针，治不了 junit 覆盖，否决。

### D2 依赖图插件 `flight_deps` 与 `sitecustomize`
- **粒度**：测试文件，用仓库相对路径。由 `item.path`（3.8 下用 `item.fspath`）对 `FLIGHT_ROOT` 求相对路径。不用 nodeid 的文件部分，因为 afa 这类在子目录运行的仓库，rootdir 不是仓库根。
- **静态闭包**：会话结束时，对每个测试文件解析 AST，取全部 `Import` / `ImportFrom`（含函数体内的），按模块搜索根解析到仓库内的 `.py`，求传递闭包。模块搜索根是 rootdir、测试文件所在目录链，以及 `sys.path` 里落在仓库内的项。
  - 理由：同进程里模块有 `sys.modules` 缓存，第二个 import 同一模块的测试文件运行时观察不到加载。静态闭包补上这一块。
- **运行时**：审计钩子在两类窗口里记 `open` 事件：收集窗口（`pytest_pycollect_makemodule` 的 hookwrapper）与用例窗口（setup / call / teardown）。
  - `__pycache__/<stem>.<tag>.pyc` 映射回 `<dir>/<stem>.py`。
  - `subprocess.Popen` / `os.exec*` / `os.posix_spawn` 的 argv 里，落在仓库内的路径记为依赖。
  - 只收仓库内的文件，排除 `.git/`、门禁临时目录与字节码。
- **Python 子进程**：
  - 每个用例窗口开始时，设 `os.environ["FLIGHT_DEPS_FILE"] = <该测试文件>`，子进程会继承。
  - 门禁临时目录里放一个 `sitecustomize.py`，经 `PYTHONPATH` 生效。它装同样的审计钩子；`atexit` 时把 `sys.modules` 里仓库内模块的 `__file__` 与 open 过的文件，按 `FLIGHT_DEPS_FILE` 追加进 `FLIGHT_DEPS_OUT`。
  - `FLIGHT_GUARD_NESTED` 为真时不写。嵌套 pytest 进程本身也是 Python 子进程，它在外层用例窗口里加载的东西照样归外层那个测试文件。这是正确的归属：嵌套会话用到的文件，确实是外层用例的依赖。
- **盲**：`subprocess.Popen` 的审计参数含 `env`。如果 `executable` 或 `argv[0]` 的文件名像 Python 解释器（以 `python` 开头），而 `env` 不是 None 且其 `PYTHONPATH` 不含门禁临时目录，或者 argv 带 `-I` / `-S` / `-E`，就把当前测试文件记为盲。
- **逐用例结论**：插件同时在 `pytest_runtest_logreport` 记 `[仓库相对 nodeid, outcome]`，与 G7 插件同一口径。基线据此得到 `failed_nodes`，锚点据此得到失败用例。junit 形式的 `test.failed` 照旧保留，供现有差分使用。
- **备选**：
  - coverage.py：新依赖，子进程要 `COVERAGE_PROCESS_START`，否决。
  - 只用静态 import 图：看不见子进程与数据文件，本仓库大部分测试是子进程跑 hook 脚本，否决。

### D3 锚点池 `<git common dir>/flight-anchors/`
- **条目**：
  - `change`、`commit`、`at`、`snapshot`、`byproducts`；
  - `cmd_key`（`gate.test`）、`tiers_key`（分层文件的 blob，无分层为 null）；
  - `files`：全部测试文件；
  - `failed`：仓库相对 nodeid；
  - `deps`：`{测试文件: [仓库文件...]}`；
  - `blind`；
  - `measured`；
  - `source`：`baseline` / `final-full` / `final-incremental`。
- **写入**：复用 `_pool_write` 的原子写与只留最新 N 条（锚点单独一个目录与上限，`ANCHOR_KEEP = 20`）。写入时机：
  - baseline 跑全量后；
  - final 全量后；
  - 增量 final 后：旧锚点的 deps / failed 去掉重跑过的文件，再并入本次结果。
- **选取**：对 `cmd_key` 与 `tiers_key` 都匹配、`measured` 为真的最新 10 条，逐条算 `_delta(root, cand, cur_snap, head, change_rel, same_change)`（返回 None 即不可用），取 |Δ| 最小者，同样小取最新。
- **跨 change 共用**：锚点不必来自本 change。Δ 按两棵树的真实内容差算，正确性不依赖锚点的来源。锚点的失败用例总会被重跑，所以别的 change 留下的红不会被当成绿沿用。
- **为什么放 git common dir、不入库**：afa 有上万个用例，依赖图体积大，入库会让每次飞行记录 commit 变重；放在 git common dir 里，跨 worktree 共用，与基线池一致。代价：换一台机器就没有锚点，第一次 final 全量（D5 的「没有可用锚点」）。

### D4 Δ 与自动全量
- **算 Δ**：Δ 用 `_delta(...)`，strict=False：排除本 change 的计划工件与其他 change 目录，忽略字节码。
- **全量触发**：任一成立即全量，`full_why` 写明第一条命中的原因：
  - `--full`；
  - 没有可用锚点；
  - 基线 `test.failed` 非空但缺 `failed_nodes`；
  - Δ 含全局文件（清单见 spec）；
  - Δ 含「锚点时已存在（旧 blob 非空）、不在任何 deps 里、不是测试文件、扩展名不是 `.py`、不是文档」的文件。
- **为什么 `.py` 例外**：Python 进程（含继承了 sitecustomize 的子进程）加载过的 `.py` 一定会被记下。依赖图里没有某个 `.py`，说明全量运行时也没有任何用例加载它，再跑一次全量照样测不到它，白花时间，所以只给警告。非 Python 文件可能被看不见的读者读取（例如 shell 脚本 `source` 另一个脚本），这时全量能让间接用到它的用例重跑，所以触发。
- **新文件**：锚点时不存在的新文件不触发全量。能用到它的唯一途径是某个已存在的文件引用了它，而那个文件本身也在 Δ 里，依赖它的测试文件会被选中。

### D5 选测、判红与前移
- **选中**：依赖与 Δ 相交的测试文件 ∪ Δ 里现存的测试文件 ∪ 锚点 `failed` 所在的测试文件 ∪ `blind`。选中集合为空时不运行 pytest，记「增量：0 个文件需要重跑」。
- **重跑**：扩展 `_pytest_outcomes`：可选参数 `deps_out`，同时加载防护与依赖图插件；分层叠加时还有 `probe_out`。用 `gate.pytest`（缺省从 `gate.test` 推导，与 G7 同一个 runner）、`--rootdir <仓库根>`，对选中文件实跑。
- **判红**：
  - 重跑结果里 FAILED / ERROR 的仓库相对 nodeid，不在基线 `failed_nodes` 里的，记 `G2 test：新增失败 n 条：...`；
  - 超时记 `G2 test：增量重跑超时`；
  - rc 不在 {0, 1, 5}，或输出里有收集错误，记 `G2 test：增量重跑 exit <rc>`，附输出末尾。
- **沿用数**：锚点里不在选中文件里的用例数。
- **前移**：无论绿红都写新锚点，`source` 为 `final-incremental`。红也写，因为失败用例下次一定会被重跑，不会被沿用成绿。
- **为什么用 `gate.pytest` 而不是给 `gate.test` 追加参数**：`gate.test` 可能是包装脚本，追加参数不安全。G7 已经约定用 `gate.pytest` 直接跑指定用例（afa 配了 `verify/pytest.sh`），这里沿用同一约定。

### D6 同树沿用与 `ship` 新鲜度
- **记录**：final 结束时写 `<git common dir>/flight-final/<change>.json`（原子写），内容是 `{commit, snapshot, fps, result}`。`fps` 包括：
  - `plan_sha(data)`；
  - `scenario_tests` 的 sha；
  - `cmd_key` 分别对 `gate.test` / `lint` / `typecheck` / `impacted` 与每项 check 的 `final`；
  - 分层文件 blob。
- **沿用**：final 开始时，记录 `result.ok` 为真、`fps` 全等，且 `_delta(root, rec, cur_snap, head, change_rel, True, strict=True)` 去掉记账文件后为空，就沿用。不运行 G7，不跑任何测试、lint、typecheck、检查。照常 `append_report` 与 `timeline_record`。
- **红不沿用**：红往往来自环境或偶发，人修了环境就会重跑，沿用红会让人困惑；绿的沿用没有这个问题。
- **`_final_fresh`**：去掉「final commit 是 HEAD 的祖先」这一条，改为 `git diff --name-only <final> HEAD`。成功且只含记账文件（或为空）就算新鲜；git 失败（commit 不存在等）仍判过期。
- **工作流不改**：重复的 final 由沿用自动变成秒回。

### D7 checks 注入
- `_check_env(phase, change, base_commit, cdir, final_ctx=None)`：`final_ctx` 是 `{"mode", "delta", "anchor"}`。
- 只在 final 传入 `final_ctx`：把 Δ 写进 `<cdir>/.gate-delta.txt`，再加三个变量：`GATE_FINAL_MODE`、`GATE_DELTA_FILE`、`GATE_ANCHOR_COMMIT`。
- 全量且没有锚点时，后两个为空串。
- baseline 不变。

### D8 `gate.impacted`
- **运行**：存在时，增量路径改为 `run_test_gate(gate.impacted, root)`，env 里加 D7 的三个变量。按基线 junit 形式的 `test.failed` 差分，复用 `_diff_verdict`。
- **锚点**：本 change 最近一次绿的 final 记录（D6）的 commit；它不是 HEAD 的祖先时，取 `gate-baseline.json` 的 commit 与快照。
- **触发条件**：全局文件与 `--full` 照旧触发全量；不要求依赖图。
- **lint**：`gate.impacted` 存在但不是非空字符串时判红；它进 `plan_sha`，作为 gate 命令之一。
- **为什么还保留内建选测**：afa 有自己的选测工具，其他仓库（含本仓库）没有。两者并存，`gate.impacted` 优先。

### D9 与测试分层叠加（修订 test-tiers design 的 final 行为）
- **单元层**：选中文件 ∩ `unit.paths` 用 `_pytest_outcomes(..., probe_out=...)` 重跑，按探针结果对这些用例跑 `tier_verdicts` 的同一套判定（G10 候选单独重跑一次、放行名单、G11）。
- **集成区域**：只在选中文件落在某个已选区域的 `paths` 里时，才按现有逻辑运行该区域 `cmd` 并差分；否则记进 `regions_skipped`。
- **区域运行也记依赖图**：区域的 `run_test_gate` 同样加载依赖图插件，锚点的 deps 覆盖单元层与已选区域。
- **全量时**：与 test-tiers 现状完全相同，单元层加探针，再加全部已选区域。
- **`tier_sec`**：只计实际运行的部分。

### D10 输出
- **JSON**：final 的 JSON 加 `incremental`：
  - 增量：`{"mode": "incremental", "source": "builtin"|"impacted", "anchor": {"change", "commit"}, "delta": n, "rerun_files": a, "rerun_tests": b, "inherited_tests": c, "regions_skipped": [...]}`；
  - 全量：`{"mode": "full", "full_why": "..."}`；
  - 沿用：`{"mode": "reused", "from": "<commit>"}`。
- **summary / timeline**：写法见 spec；timeline 备注的结论词仍在末尾，`timeline.py` 不改。
- **警告**：「Δ 中 n 个 .py 文件未被任何用例加载」进 `warnings`。

### D11 `/pr-ship` 自动修复不询问
- **改法**：step 10 删掉唯一一次 AskUserQuestion 与「只贴评论交人」分支，改为 CRITICAL/HIGH 直接按原流程自动修复（至多 2 轮）。description 与 Guardrails 改为「全程不问询」。
- **为什么不违背铁律**：人类审批的第二处是 PR review，不在这一步；自动修复的 commit 照样经 follow-up 评审与 `ship` 复裁。

## Risks / Trade-offs

- **[依赖图漏记 → 漏测，红被判绿]** 例如环境变量、网络、非 Python 子进程内部读的文件，或 C 扩展直接读文件。
  → 对策：
  - 非 Python 子进程的 argv 路径记为依赖；
  - 剥 env 的 Python 子进程把所在文件标为盲，每次都重跑；
  - 非 Python 文件未见即全量；
  - 全局文件变动即全量；
  - `--full` 随时可用；
  - 新 ADR 写明这是接受的盲区。
- **[锚点只在本机]** 换机器或 git common dir 被清，第一次 final 全量。
  → 跑完即有锚点；全量本就是今天的行为，不会更差。
- **[`sitecustomize` 遮蔽仓库自己的 sitecustomize]** 门禁临时目录在 `PYTHONPATH` 最前。
  → 门禁版本先 import 记录逻辑，再按 `sys.path` 去掉自身目录后尝试 import 下一个 `sitecustomize`（`importlib`），找不到就忽略。
- **[`-p flight_guard` 在剥了 `PYTHONPATH`、却保留 `PYTEST_ADDOPTS` 的嵌套 pytest 里导入失败]** 嵌套会话会因此报错，导致该用例失败。探针今天已有同样的风险。
  → 防护模块名带 `flight_` 前缀并写进文档。与 D1 的外层退回不同，嵌套报错会表现为用例红，人能看见，不会静默。
- **[静态闭包解析不准]** 例如 `sys.path` 魔改、命名空间包。
  → 解析不到的 import 忽略，运行时记录兜底；解析出的路径不存在也忽略。
- **[同树沿用掩盖偶发绿]** 上次绿是偶发。
  → 与今天「绿了就收口」等价，没有更差。
- **[叠在未合入的 PR #5 上]** #5 改动会导致本分支 rebase。
  → 本 change 只在 #5 合入前后 rebase 一次；冲突集中在 `slice-gate.py`，由人决定。

## Migration Plan

- **无需迁移**：
  - 旧 `gate-baseline.json` 没有 `failed_nodes` 时：无预存红照常增量，有预存红则第一次 final 全量（D4）；
  - 锚点池为空时第一次 final 全量；
  - 没有 `gate.impacted` / `gate.checks` 的仓库不受新字段影响。
- **回退**：final 带 `--full` 即今天的行为；删掉 `<git common dir>/flight-anchors/` 即回到「每次全量」，下一次全量又会自动重建锚点。
- **afa**：合入后升级 afa 的安装版，下一次 baseline 或 final 全量后即开始增量；afa 可把 `tools/testgate --scope impacted` 配成 `gate.impacted`。afa 仓库内的动作不在本 change。

## Open Questions

- **基线复用 ADR 的盲区论证**：`DRAFT-baseline-reuse-by-content-fingerprint` 依赖「final 跑全量」。它的决定本身（baseline 按内容指纹复用）不变，只是盲区的兜底换成了 D4 的触发条件与 D5 的「锚点失败用例必重跑」。由新 ADR `DRAFT-final-incremental-by-dependency-anchor` 记录这一修订，原 ADR 不改。
- **test-tiers 的 final 行为**：test-tiers 的 ADR 写的是「基线只跑单元层」，与本 change 不冲突。它的 design 里「final 按分层全跑单元层」被 D9 改写；该 change 尚未归档，不另立 ADR，记在新 ADR 的 Context 里。
