# DRAFT. 门禁与项目之间的两份运行契约：测试结果交给检查，依赖图插件经包装脚本转发

- Status: accepted
- Date: 2026-11-09
- 关联：DRAFT-gate-paired-checks-by-exit-code（扩展其环境契约，判定仍只看退出码，保持在役）· DRAFT-final-incremental-by-dependency-anchor（依赖图插件与锚点，保持在役）· DRAFT-baseline-reuse-via-dependency-anchor（同一 change）
- 来源 change：unified-test-result-reuse（design D1–D5、D12、D14）

## Context

模板经 `PYTEST_ADDOPTS` 注入 `-p flight_guard -p flight_deps` 与 `--junitxml`，经 `PYTHONPATH` 注入 `sitecustomize`，借此测依赖图、取逐用例结局。项目只要直接调 pytest，这条路就是通的：stc-foundation 有 19 次增量 final、6 次同树沿用。

项目一旦用包装脚本重建被测进程的环境，这条路就断了。afa 的 testgate 有意这样做（冷启动、结局、签名），丢掉了插件与 `sitecustomize`。afa 锚点池 20 条里只有 2 条测到依赖图，final 因"没有可用锚点"全量 33 次。门禁这边只留下一句"依赖图未测：没有依赖图输出（不是 pytest？）"，误导了排查。

另一边，检查（`gate.checks`）拿不到门禁刚跑出的测试结果。项目只能自建按环境做键的缓存，而 gate.test 的环境里有每次运行都变的 `FLIGHT_*` 临时路径，键永远对不上：afa 25 次，每次 final 多跑一遍全量。

这两件事都发生在模板与项目的边界上。模板不能改项目代码（用户决策 Q5：项目侧适配由用户在各项目自己做），只能把边界写成契约。

## Decision

1. **检查结果契约**：
   - final 跑完 gate.test 之后、运行检查之前，把本次测试结果写进 git common dir 下本 change 检查目录的父目录，经 `GATE_TEST_RESULT` 交给检查；
   - 结果包含模式（全量 / 增量 / 选测命令）、逐用例结局、沿用条数、是否完整、junit 副本；
   - 检查的判定仍只看退出码，模板不解析检查输出。
2. **运行器契约**：
   - 除现有注入外，另外导出 `FLIGHT_PLUGIN_PATH`（插件目录）与 `FLIGHT_PYTEST_ARGS`（插件与 junit 参数）；
   - 会重建环境的包装脚本，把前者放进被测进程的 `PYTHONPATH`、把后者传给 pytest，依赖图即可测到；
   - gate.test 的环境另带 `GATE_PHASE` / `GATE_CHANGE`。
3. **易变变量**：`FLIGHT_` 与 `GATE_` 前缀的变量每次运行都会变，项目侧按环境做键的缓存必须剔除它们，建议改用白名单。
4. **可诊断**：依赖图未测时给出四类机读原因（`not-pytest` / `plugins-dropped` / `plugin-import-failed` / `incomplete`）与修法。
5. **契约随模板下发**：`template/.claude/flight-runner-contract.md` 随 `.claude/` 安装到项目，是项目侧接入的唯一依据。

否决的方案：
- **由模板识别并改写项目的包装脚本**：侵入项目代码，而且每种包装各不相同。
- **改用 `PYTEST_PLUGINS` 注入**：会被同样的环境清洗丢掉。
- **只交 junit 给检查**：增量时 junit 不完整，nodeid 与 classname 也对不齐。
- **让检查自己读锚点池**：锚点的选取、沿用与链长规则在模板里，交给项目等于要它们重写一遍。
- **模板在 gate.test 环境里不设 `FLIGHT_*`**：插件靠这些变量定位输出，不设就测不到依赖图。

## Consequences

- **更易**：
  - 项目改几行包装脚本就能接上增量 final；
  - 检查不必再跑一遍全量；
  - 依赖图为什么没测到，一眼可见。
- **更难**：模板多了两份要长期保持兼容的对外契约，变量名与结果文件字段一经发布，就只能做向后兼容的扩展。
- **风险**：
  - 增量 final 交出的结局里有沿用的条目，检查若误当作实跑会出错：结果文件写明 `mode` / `inherited` / `complete`，由检查自己决定；
  - 包装脚本接入 `sitecustomize` 会改变项目的冷启动约定：接不接入由项目决定，不接入就保持全量，但会被预告。
- **中性**：不转发契约的项目行为完全不变。
