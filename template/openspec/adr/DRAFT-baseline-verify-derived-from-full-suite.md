# DRAFT. 基线上的 verify 可由全量 junit 推导

- Status: accepted
- Date: 2026-10-15
- 关联：DRAFT-test-gate-baseline-diff · DRAFT-gate-evidence-not-self-reported · DRAFT-baseline-reuse-by-content-fingerprint
- 来源 change：baseline-incremental-reuse（design D11）

## Context

#32（`a88a97b`）要求每片 verify 在基线上绿，用来在起飞前抓出「verify 在改动前就不可运行或含既有错误」。`slice-gate.py baseline` 因此在全量之后把每片 verify 再串行跑一遍。

在 verify 只是用同一个 pytest 跑若干测试文件的项目里，这是重复执行。本仓实测（2026-10-15）：全量 50.6 秒，4 片 verify 串行 49.0 秒，后者跑的测试文件全在全量里。全量运行时已经经 `PYTEST_ADDOPTS` 注入 `--junitxml`（DRAFT-test-gate-baseline-diff），逐条用例的结果就在手边。

## Decision

全量可度量（exit 0，或可度量的 exit 1）时，满足以下全部条件的 verify 不单独运行，按全量 junit 判为绿，记 `derived: "full"`：

- **同一前缀**：`gate.test` 与 verify 是同一个 pytest 启动前缀的直接调用（前缀之前没有 `cd`、环境变量赋值、管道），前缀之后都只含白名单选项与路径；
- **路径**：verify 的路径都是仓库内存在的测试文件，不带 `::` 选择；
- **全量里有、且都通过**：每个文件在 junit 里都有用例，全量的失败与错误里没有它的用例。

只推导绿；范围内有失败、或任一条件不满足，照旧单独运行。`gate.pytest` 不参与前缀匹配：包装脚本设置的环境 verify 不一定具备，推导会掩盖「verify 单独不可运行」。

「verify 在基线上必须绿」这条要求不变，变的只是取证方式。证据来自判定器自己运行的全量（junit 文件），不来自被门禁方的叙述。

否决的方案：

- **继续每片单独运行**：本仓首次基线一半时间在重复跑测试。
- **用 `gate.pytest` 前缀匹配**：包装脚本场景会掩盖 verify 的环境问题，正是 #32 要在起飞前抓的那一类。
- **verify 之间并行运行**：一般项目的测试共享端口、数据库、固定路径，并发会互相干扰。

## Consequences

- **更易**：直接用 pytest 的项目，首次基线省去大部分 verify 时间；推导结果在 `gate-baseline.json` 与 timeline 里可见。
- **更难**：判定器多了一段命令词法判断与 junit 用例集，属于可信计算基，要有测试覆盖。
- **盲区**：顺序依赖的用例（全量里绿、单独运行才红）推导不出来，要到飞行中 G1 运行 verify 时才暴露，按门禁红处理（用户 2026-10-15 已接受）。
- **安全方向**：classname 对不上、junit 不可解析、命令里有任何白名单外的词，都退回单独运行；推导只会让 verify 少跑，不会把红判成绿。
