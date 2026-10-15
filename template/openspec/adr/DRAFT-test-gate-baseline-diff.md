# DRAFT. 全量测试门禁按基线逐条差分

- Status: accepted
- Date: 2026-10-10
- 关联：DRAFT-gate-evidence-not-self-reported · DRAFT-flight-orchestrator-state-machine
- 来源 change：flight-gate-speedup（design D2）

## Context

slice-gate 的 lint / typecheck 门禁早已按基线差分：把基线上的输出行规范化记下来，只有新增行才判红。全量测试（`gate.test`）却只看退出码，基线上有任何失败就判红、不能起飞。

有预存红的仓库只能绕开：afa 每个 change 都先跑一遍全量收集失败，写 deselect 脚本，再跑 baseline。afa 全量单进程 32–37 分钟，这一步每个 change 多花约 33 分钟，而且 deselect 清单靠模型临场写，不是机械判定（2026-10-10 `dlib-recorder-param-patch` 实测）。

可行性已实测：在 `PYTEST_ADDOPTS` 里追加 `--junitxml=<f>`，包装脚本里的 `pytest.main()`、bash 包装且覆写 `PYTHONPATH` 两种形态都会写出逐条结果。

## Decision

当 `gate.test` 是 pytest、并且本次结果可度量时，全量测试门禁按基线逐条差分：

- **记录**：baseline 运行 `gate.test` 时经 `PYTEST_ADDOPTS` 注入 `--junitxml`，把失败与错误的测试按 `classname::name` 记入 `gate-baseline.json` 的 `test.failed`；有可度量的预存红时 baseline 判 ok。
- **判定**：final 只对不在基线 `test.failed` 里的失败判红；失败全在基线里时判绿，并在警告里写明排除条数。
- **可度量条件**（全部满足）：退出码为 1、junit 存在且可解析、输出里 pytest 汇总行恰好一行、汇总行的 failed 与 error 合计等于 junit 的 failures 与 errors 合计。
- **不满足时**：按退出码判，红的原因写明「按退出码」与不可度量的理由。非 pytest 的 `gate.test` 一律按退出码判。
- **范围**：差分只用于 `gate.test`；切片 `verify` 仍要求在基线上绿。

否决的方案：
- **继续只看退出码，由各仓库手写 deselect**：每个 change 多跑一遍全量；清单由模型临场生成，不是机械判定。
- **自写 pytest 插件经 `-p` 加载**：依赖 `PYTHONPATH`，被测仓库的包装脚本常会覆写它（afa 就是），插件会找不到。
- **解析终端输出里的 FAILED 行**：依赖报告参数与输出格式，参数化 id 里可能有空格。

## Consequences

- **更易**：有预存红的仓库 baseline 一遍即可，不再手写 deselect；预存红数量进入基线与 final 的警告，可审计；与 lint / typecheck 的差分口径统一。
- **更难**：可度量条件属于门禁的可信计算基，汇总行识别与计数比对都要有测试覆盖；pytest 汇总行格式若变化，会退回按退出码判红（fail-closed，不会误判为绿）。
- **放宽**：基线有可度量的预存红时允许起飞（原先判红）。「本来就红、又被改坏」的测试会被掩盖，这与手写 deselect 的盲区相同，不新增。
- **兼容**：旧格式的 `gate-baseline.json` 没有 `test.failed`，视为空集，语义与原先一致。
