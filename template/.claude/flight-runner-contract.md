# 飞行门禁 · 运行器契约

> 项目侧接入飞行门禁测试运行的唯一依据。门禁实现在 `.claude/hooks/slice-gate.py`，体检在 `.claude/hooks/flight-doctor.py`。

门禁跑 `gate.test` 时往环境里注入一组变量；项目的包装脚本按本文转发，增量 final、锚点复用与检查读结果才能工作。直接调 pytest 的项目零改动（`PYTEST_ADDOPTS` / `PYTHONPATH` 注入照旧），本文只约束会重建子进程环境的包装脚本。

## 1. 包装脚本要转发的两个变量

| 变量 | 内容 | 转发方法 |
|---|---|---|
| `FLIGHT_PLUGIN_PATH` | flight 插件与 `sitecustomize.py` 所在目录 | 被测进程的 `PYTHONPATH` 以它开头 |
| `FLIGHT_PYTEST_ARGS` | 本次要传给 pytest 的 `-p` 插件参数与 `--junitxml=<path>`，按 shell 规则引号 | 按 shell 拆词后原样传给 pytest |

- **两者都为空**（去插件重跑）→ 什么也不加，与不转发一致。
- **其余 `FLIGHT_*` 变量**（插件靠它们定位输出）须留在被测进程环境里；按白名单重建环境时，白名单要放行 `FLIGHT_` 前缀。

```bash
#!/usr/bin/env bash
# 包装脚本示例：清掉项目自己不要的 PYTEST_ADDOPTS / PYTHONPATH，仍让依赖图测到
set -eo pipefail
unset PYTEST_ADDOPTS
eval "args=($FLIGHT_PYTEST_ARGS)"            # 为空时 args=()
export PYTHONPATH="${FLIGHT_PLUGIN_PATH:+$FLIGHT_PLUGIN_PATH:}src"
exec python3 -m pytest -q tests "${args[@]}"
```

## 2. `GATE_PHASE` / `GATE_CHANGE`

- **注入范围**：baseline 与 final 运行 `gate.test`、`gate.impacted` 与增量重跑时都设。
- **`GATE_PHASE`**：`baseline` 或 `final`。
- **`GATE_CHANGE`**：change 目录名。包装脚本用 `$GATE_CHANGE` 取 change 名，不写死；`cmd_key` 会把脚本里的本 change 名归一成 `<change>`，两个只差 change 名的脚本指纹相同，跨 change 复用才成立。

## 3. 检查可读的 `GATE_TEST_RESULT`

- **何时有**：只在 final 运行 `gate.checks` 的 `final` 命令时设，值为结果文件绝对路径 `<git common dir>/flight-gate-checks/<change>/.gate-test-result.json`；baseline 阶段为空。同树沿用的 final 不跑检查，也不写结果文件。
- **字段**：

| 字段 | 含义 |
|---|---|
| `change` / `commit` / `at` | 本次 final 的 change、commit、时间 |
| `mode` | `full` / `incremental` / `impacted` |
| `cmd` / `cmd_key` | gate.test 命令与它的指纹 |
| `nodes` | `{仓库相对 nodeid: outcome}`，outcome 取 `passed` / `failed` / `error` / `skipped` / `xfailed` / `xpassed`；`impacted` 或依赖图未测时为 `null` |
| `inherited` | 沿用锚点结论的用例数；全量为 0；`impacted` 为 `null` |
| `failed_nodes` | 本次判为失败（`failed` / `error`）的 nodeid，排序 |
| `junit` | 本次 junit 副本（同目录 `.gate-test-junit.xml`）绝对路径；增量时只含重跑部分；取不到为 `null` |
| `complete` | `nodes` 覆盖锚点与本次重跑的全部用例时为真 |

- **用法**：
  - 只要实跑结果的检查（例如统计真实耗时、只信本次执行的结局）看 `mode == "full"`，否则跳过或降级；
  - 要逐用例结局的检查读 `nodes`，先看 `complete` 为真；`inherited > 0` 表示其中有沿用锚点的结论；
  - 不要再从项目缓存或 junit 自行拼结局——增量时 junit 不完整。

## 4. 易变变量与项目缓存键

- ⚠ **`FLIGHT_` 与 `GATE_` 前缀的变量每次运行都变，项目侧任何按环境做键的缓存都必须从缓存键剔除它们，建议直接改用白名单（只列真正影响结果的变量）。**
- 黑名单挡不住新变量：实测还见过 `CLAUDE_EFFORT` 混进缓存键，白名单才是根治。

## 5. 依赖图未测的四类原因与修法

基线写 `deps_unmeasured: {kind, why}`，warning 为 `依赖图未测（<kind>）：<why>`；锚点写 `deps_kind`。

| 类别 | 判定 | 修法 |
|---|---|---|
| `not-pytest` | 既没有 junit 输出，也没有 pytest 汇总行 | 依赖图只认 pytest：改用 pytest，或配 `gate.impacted` 由仓库自己选测 |
| `plugins-dropped` | pytest 跑了，但外层防护标记没写、也没有插件导入错误——包装脚本没把 `-p` 参数传给 pytest | 按第 1 节转发 `$FLIGHT_PYTEST_ARGS`（连同 `$FLIGHT_PLUGIN_PATH`） |
| `plugin-import-failed` | 输出里有 flight 插件导入错误（门禁随即去插件重跑） | 包装脚本覆写了 `PYTHONPATH`：让它以 `$FLIGHT_PLUGIN_PATH` 开头 |
| `incomplete` | 依赖图记录有开始、没有结束，或已损坏 | 被测进程中途退出或记录写入被中断；查清后重跑 baseline |

体检：`python3 .claude/hooks/flight-doctor.py doctor` 的 `[runner]` 节按类别统计在途 change 的基线。

## 6. `gate-scope.json` 的可选字段

`<openspec 根>/gate-scope.json` 恰含 `cmd` 或 `builtin` 之一，另可选：

| 字段 | 形状 | 作用 |
|---|---|---|
| `global` | 仓库相对路径 glob 的字符串数组 | Δ 中有路径匹配 → final 与经锚点的基线都自动全量，原因点名该 glob；内建选测把它当全选触发项 |
| `blind` | 测试文件 glob 的字符串数组 | 匹配的现存测试文件每次增量都重跑（依赖图看不见的依赖） |
| `anchor_max_hops` | 正整数，缺省 5 | 锚点链上限：由增量推出的锚点 `hops` 逐代 +1，`hops` ≥ 上限的锚点不再作候选，下一次回到全量 |

形状不合法时 lint 与 preflight 判红并点名字段。

## 7. 接入步骤

1. **改包装脚本**：按第 1 节转发两个变量，用 `$GATE_CHANGE` 代替写死的 change 名；项目缓存键按第 4 节剔除 `FLIGHT_` / `GATE_`。
2. **跑 baseline，确认依赖图测到**：`slice-gate.py baseline --full` 后基线 warnings 没有「依赖图未测」，或 `flight-doctor.py doctor` 的 `[runner]` 为 0。
3. **对账**：baseline 之后提交一处改动，跑 `slice-gate.py final`（增量）留下结果文件副本，再在同一棵树上跑 `slice-gate.py final --full`，两份结果文件的 `nodes` 逐条一致才算接通。
4. **声明 global / blind**：对账不一致的来源（依赖图看不见的配置、数据、插件目录）写进 `gate-scope.json` 的 `global`；只能靠每次重跑兜住的测试写进 `blind`；必要时调 `anchor_max_hops`。
5. **检查改读结果文件**：`gate.checks` 的 `final` 命令改读 `$GATE_TEST_RESULT`，不再自己重跑测试或拼 junit。

## 8. 全机测试锁

同一台机器同一时刻只让一套全量测试在跑：门禁的测试运行先取锁再开跑，取不到就排队。

- **是什么**：用户级目录（缺省 `~/.claude/flight-lock/`）下的一把读写锁，跨仓库、跨 worktree 共用；持有进程退出即释放。
- **谁用哪种**：

  | 方式 | 命令 |
  |---|---|
  | **独占** | `slice-gate.py baseline` · `slice-gate.py final` · `test-tiers.py run` / `probe` |
  | **共享** | 切片 `slice-gate.py gate`（verify 到 G7） |

  共享方之间可同时持有；独占方排队时，后来的共享方不插队。
- **环境变量**：

  | 变量 | 作用 |
  |---|---|
  | `FLIGHT_LOCK=off` | 关闭锁，门禁直接开跑 |
  | `FLIGHT_LOCK_DIR` | 锁目录；主目录在网络盘时指到本机路径 |
  | `FLIGHT_LOCK_MAX_HOLD_SEC` | 持有上限：某次运行持锁超过它，排队方不再等；缺省为上次全量耗时的 3 倍、不低于 300 秒，没有记录时 1800 秒 |
  | `FLIGHT_LOCK_HELD` | 重入标记，门禁自己设，持锁期间的子进程不再排队；包装脚本按白名单重建环境时须随 `FLIGHT_` 前缀放行（第 1、4 节），否则被测进程里再调门禁会排到持有上限 |

- **CI**：容器已经隔离时设 `FLIGHT_LOCK=off`。
- **门禁之外的测试运行**想一起排队：`python3 .claude/hooks/flight-lock.py run exclusive -- <命令>`；看谁在占：`python3 .claude/hooks/flight-lock.py status`。
- **放弃等待**：排队方发现持有者超过持有上限即放弃（状态 `timeout`），这一次不加锁继续跑，G10 慢单测降为警告（原文保留并注明原因）；`off` 与平台不支持（`unavailable`）时同样不加锁，但 G10 照常判。
- **留痕**：输出 JSON 的 `lock` 字段；时间线备注里的「排队 Ns · 负载 起→止/核数」；final 备注里的「测试 Ns · 检查 <名> Ns」；`flight-doctor.py cost` 归因排队与收口秒数，`doctor` 的 `[checks]` `[lock]` 两段体检。排队期间 stderr 打印「排队中」与在等谁，不是卡死。
- **已知限制**：共享方之间不限流；不保证先来先到；多用户之间互不可见（锁目录在各自主目录下）。
