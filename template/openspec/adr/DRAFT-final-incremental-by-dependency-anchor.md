# DRAFT. final 以锚点为基准、按实测依赖图增量运行

- Status: accepted
- Date: 2026-10-28
- 关联：DRAFT-baseline-reuse-by-content-fingerprint（修订其盲区论证的前提，原 ADR 不改）· DRAFT-test-gate-baseline-diff · DRAFT-test-tiers-unit-baseline-by-audit-probe · DRAFT-gate-paired-checks-by-exit-code
- 来源 change：incremental-final（design D1–D10）

## Context

final 每次都全量跑 `gate.test` 与每项 `gate.checks`，改一行代码也要重跑全量。

- **afa 实测**（change `test-tiering-unit-integration`，2026-10-28）：一次完整 final 要 29–42 分钟。起过的 7 次 final 里，约 5 次尝试全量，4 次被中断或失败。人类两次要求「只跑增量局部，不跑全量 final」。
- **本仓库**：全量约 130 秒；PR #5 修 1 条 HIGH 后又全量跑了一次。
- **重复 final**：同一棵树上的 final 会被反复调用，fix 子代理一次、final-gate 一次、主会话后台还有一次。

同时，库经 `PYTEST_ADDOPTS` 注入的 `--junitxml` 与探针插件，会被用例里起的嵌套 pytest 继承。afa 的「计数不一致（汇总行 14，junit 0）」就是嵌套会话在会话结束后覆盖了父 junit，让唯一跑完的那次全量白跑。

基线复用 ADR 的盲区论证写着「final 跑全量时……会判红。所以最坏是收口多出一条红，不会把红判成绿」。本决定让 final 不再总是全量，这条前提需要修订。原 ADR 的决定本身（baseline 按内容指纹复用）不变，文件不改。

test-tiers change（PR #5，未归档）的 design 规定 final 全跑单元层加已选区域。本决定在配置了分层时同样走增量：只重跑选中的单元层文件并挂探针，只运行涉及到的区域。

## Decision

1. **锚点**：每次全量运行（baseline 全量、final 全量）与每次增量 final，都把一条锚点写进 `<git common dir>/flight-anchors/`（不入库，跨 worktree、跨 change 共用）。锚点含：
   - 代码树（commit 与未提交改动快照）；
   - 命令与分层指纹；
   - 逐用例的失败清单（仓库相对 nodeid）；
   - 以测试文件为单位的依赖图；
   - 盲文件清单。
2. **依赖图实测，不靠推断**：依赖图来自三处：
   - 静态 import 闭包；
   - 审计钩子记下的 open / exec（字节码映射回源文件）；
   - 经门禁注入的 `sitecustomize` 记下的 Python 子进程加载与读取。

   剥了 env、录不到的 Python 子进程，把所在测试文件标为「盲」，每次都重跑。
3. **final 默认增量**：取 Δ 最小的可用锚点。重跑以下测试文件，其余用例沿用锚点结论，新增失败按基线逐条差分：
   - 依赖与 Δ 相交的；
   - Δ 里的测试文件；
   - 锚点里失败的；
   - 盲文件。
4. **何时仍全量**：下列任一成立时全量：
   - `--full`；
   - 没有可用锚点；
   - 基线缺逐用例记录；
   - 全局文件（`conftest.py`、pytest / 打包配置、依赖清单、分层文件）变动；
   - Δ 含锚点时已存在、依赖图从未见过的非 Python、非文档文件。

   依赖图未见过的 `.py` 只警告，因为全量也测不到它。
5. **同树只跑一次**：上一次 final 是绿的，代码树、计划、命令指纹都没变时，直接沿用上次结论。`ship` 按两棵树的差判 final 是否过期，不再要求祖先关系。
6. **嵌套会话不得污染度量**：门禁注入的 pytest 运行都带防护插件，嵌套会话不写 junit、不写探针与依赖图记录。
7. **扩展点**：
   - `gate.impacted` 让仓库用自己的选测命令代替内建选测；
   - 检查命令经 `GATE_FINAL_MODE` / `GATE_DELTA_FILE` / `GATE_ANCHOR_COMMIT` 拿到 Δ，自己决定范围。

## Consequences

- **更易**：
  - 改几行代码后 final 从分钟级降到秒级，修复循环不再反复全量；
  - 同树重复调用秒回；
  - afa 这类仓库可接上已有的选测工具；
  - junit 覆盖与幽灵 nodeid 不再发生。
- **更难**：
  - 判定器的可信计算基多了依赖图插件、`sitecustomize`、锚点池与选测逻辑；
  - 排查「为什么这个用例没跑」要看 `incremental` 段与锚点。
- **盲区**（接受）：
  - 依赖图看不见环境变量、网络、C 扩展直接读的文件、非 Python 子进程内部读的文件（非 Python 文件未见即全量，能兜住其中一部分）；
  - 锚点只在本机。

  这取代了基线复用 ADR 里「final 跑全量兜底」的论证。最坏情况从「收口多一条红」变为「依赖图漏记的回归在本次收口没被测到」。缓解：
  - 锚点里的失败用例必重跑；
  - 盲文件必重跑；
  - `--full` 随时可用。
- **兼容**：
  - 锚点池为空、或基线缺 `failed_nodes` 且有预存红时，第一次 final 全量，之后自动转为增量；
  - 非 pytest 的 `gate.test` 没有依赖图，照旧全量，除非配了 `gate.impacted`。
