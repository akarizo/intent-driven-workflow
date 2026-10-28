## Why

final 每次都全量跑 `gate.test` 和每项 `gate.checks`，没有任何增量或复用：改一行代码就要重跑全量。业务仓库 afa 的 change `test-tiering-unit-integration`（2026-10-28）里，一次完整 final 实测 29–42 分钟。这个 change 一共起了 7 次 final，约 5 次尝试全量，其中 4 次被中断或失败；人类两次明确说「修复了 6 条，为何要跑全量」「只跑增量局部，不跑全量 final」。本仓库也一样：PR #5 修 1 条 HIGH 后又全量跑了一次 final（约 130 秒）。

查下来根因有三条：
1. `cmd_final` 没有增量机制。
2. 同一棵代码树会反复跑 final：fix 子代理一次，final-gate 一次，主会话还会在后台再跑一次。
3. 全量跑完却判「不可度量」。afa 唯一跑完的那次 final 报「计数不一致（汇总行 14，junit 0）」，根因是测试里起的嵌套 pytest 继承了库经 `PYTEST_ADDOPTS` 注入的 `--junitxml`，在会话结束后覆盖了父会话的 junit。afa 侧已在 `e59e0e0c8` 修掉自己的插件，库侧至今没有防护。

同日人类追加：`/pr-ship` 的独立评审出 CRITICAL/HIGH 时直接自动修复并 push，不再询问。

## What Changes

- **嵌套会话防护**：库注入的 pytest 运行（全量、区域、增量重跑）都带一个防护插件。用例里起的嵌套 pytest 会话不写 junit，也不写探针 / 依赖图记录，父会话的度量不会再被覆盖或混入幽灵用例。插件加载失败时退回不带插件的运行，只给警告。
- **依赖图与锚点**：每次全量运行（baseline 全量、final 全量）顺带记录每个测试文件实际用到的仓库文件，即依赖图。依赖图来自三处：静态 import 闭包、运行时 open / exec、Python 子进程。子进程经 `sitecustomize` 记录；env 被剥掉、录不到的子进程，把所在测试文件标为「盲」。同时记逐用例结论。这些连同代码树指纹写进 git common dir 下的**锚点池**，跨 worktree、跨 change 共用。
- **增量 final（默认）**：在锚点池里取一个可用锚点，算出锚点树与当前树的差 Δ。只重跑以下测试文件，其余用例沿用锚点结论，再按基线差分判红：
  - 依赖图与 Δ 相交的；
  - Δ 里的测试文件；
  - 锚点里失败的；
  - 被标为盲的。

  结果写明重跑多少、沿用多少、锚点是哪个 commit，并把锚点前移到本次。
- **自动全量的触发条件**：
  - `--full`；
  - 没有可用锚点（池空、命令指纹变了、锚点不是 HEAD 的祖先、依赖图没测到）；
  - 基线缺逐用例记录；
  - Δ 含全局文件（`conftest.py`、`pytest.ini`、`pyproject.toml`、`setup.cfg`、`tox.ini`、`setup.py`、依赖清单、`test-tiers.json`）；
  - Δ 含锚点时已存在、依赖图从没见过、且不是 Python 也不是文档的文件。

  没见过的 Python 文件只给警告。
- **同树沿用**：final 记树指纹与命令指纹。代码树、计划、命令都没变且上次 final 是绿的，就直接沿用上次结论，不跑任何测试。`ship` 判 final 是否过期时，改为比较两边的树：内容相同就算新鲜，不再要求 final commit 是 HEAD 的祖先。
- **checks 注入 Δ**：final 运行 `gate.checks` 时新增三个环境变量：`GATE_FINAL_MODE`（`incremental` / `full`）、`GATE_DELTA_FILE`（Δ 清单）、`GATE_ANCHOR_COMMIT`。由检查命令自己决定跑多大范围；不认这些变量的检查行为不变。
- **`gate.impacted`（可选）**：仓库已有自己的选测命令时配上它，增量时由它代替内建选测，库只把 Δ 交给它，按基线差分判红。
- **与测试分层叠加**：配置了 `test-tiers.json` 时：
  - 单元层只重跑选中的文件，并挂探针判 G10 / G11；
  - 集成区域只在选中的文件落在该区域时才运行，否则沿用。
- **`/pr-ship` 评审自动修复**：CRITICAL/HIGH 直接自动修复并 push（至多 2 轮），不再问「自动修还是只贴评论」。全程不问询；跑满 2 轮仍阻断就停下交人。
- **文档**：`/opsx-verify`、`/opsx-apply` 与同名 skill、`/pr-ship`、schema 的 tasks instruction（`gate.impacted`）、README。

## Capabilities

### New Capabilities
- `incremental-final`：final 以锚点为基准增量运行。涵盖嵌套会话防护、依赖图与锚点池、选测与判红、自动全量的触发条件、同树沿用、checks 注入 Δ、`gate.impacted` 与分层叠加。
- `pr-ship-review-autofix`：`/pr-ship` 评审出 CRITICAL/HIGH 时自动修复并 push，不询问。

### Modified Capabilities
（`openspec/specs/` 尚无已归档规格；对 test-tiers change 里 final 行为的改写见 design D9。）

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`
  - 新增防护 / 依赖图插件与 `sitecustomize` 的注入；
  - `run_test_gate` 与 `_pytest_outcomes` 可选记录依赖图；
  - 新增锚点池与 final 记录；
  - `cmd_final` 走增量 / 全量 / 沿用三条路径；
  - `_final_fresh` 改按树比较；
  - `_check_env` 在 final 阶段新增三个变量；
  - lint 校验 `gate.impacted`。
- **计划格式**：`slices.json` 新增可选字段 `gate.impacted`。`gate-baseline.json` 的 `test` 段新增 `failed_nodes`（仓库相对 nodeid）。final JSON 新增 `incremental` 段。
- **新存储**：`<git common dir>/flight-anchors/`（锚点池）与 `<git common dir>/flight-final/<change>.json`（同树沿用的 final 记录），都不入库。
- **测试**：`tests/test_final_guard.py`、`tests/test_final_deps.py`、`tests/test_final_incremental.py`、`tests/test_final_reuse.py`、`tests/test_final_checks_env.py`、`tests/test_final_impacted.py`、`tests/test_final_tiers.py`、`tests/test_incremental_final_docs.py`。
- **文档**：`template/.claude/commands/pr-ship.md`、`opsx-verify.md`、`opsx-apply.md`、同名 skill、`template/openspec/schemas/intent-driven/schema.yaml`、`README.md`。
- **ADR**：新增 `DRAFT-final-incremental-by-dependency-anchor.md`，修订基线复用 ADR 里「final 跑全量兜底」的安全论证前提（原 ADR 不改）。
- **兼容**：
  - 旧的 `gate-baseline.json` 没有 `failed_nodes`：带预存红时第一次 final 走全量。
  - 锚点池为空时第一次 final 走全量，跑完即有锚点。
  - 没有 `gate.impacted` / `gate.checks` 的仓库不受新字段影响。
  - 非 pytest 的 `gate.test` 没有依赖图，final 照旧全量，并给警告。
- **叠放**：本 change 从 `worktree-test-tiers`（PR #5）分出，依赖其中的探针与分层代码。PR 先指向该分支，#5 合入后改指 main。
- **afa 落地**：库合入后再升级 afa 的安装版。那是 afa 仓库里的动作，不在本 change 内。
