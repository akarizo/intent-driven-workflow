# DRAFT. 测试分两层：单元层是基线，纯度与耗时由审计钩子探针机械判定

- Status: accepted
- Date: 2026-10-28
- 关联：DRAFT-test-gate-baseline-diff · DRAFT-baseline-reuse-by-content-fingerprint · DRAFT-gate-evidence-not-self-reported · DRAFT-gate-paired-checks-by-exit-code（均保持在役）
- 来源 change：test-tiers（design D1–D7、D10、D12）

## Context

飞行的 baseline 与 final 每次都跑 `gate.test` 全量。本仓 2026-10-28 实测：323 个用例里 312 个碰了真实文件或起了子进程，全量 84 秒；没有任何机制阻止单元测试变慢、变脏。

用户要求：单元测试（纯函数、不碰真实文件）是基线；集成测试只在判断确实影响到真实文件时按模块 / package / library 分区域发起；每个单元测试必须 <3 秒，超线要人工放行；新用例设计先按分层定位置。

「纯函数」与「耗时」若靠模型自报或静态扫描，分类会随时间漂移，基线悄悄变慢——典型的静默失败。Python 的审计钩子（`sys.addaudithook`）能在运行时看到文件、子进程、网络事件，可以逐用例取证。

## Decision

- **两层**：单元层 = 运行时不碰真实文件、子进程、网络，且每个用例 setup + call + teardown < 3 秒；其余都是集成层，按区域划分。
- **按路径归层**：仓库级 `openspec/test-tiers.json` 用路径 glob 声明单元层与各区域，各带运行命令；混合文件拆开。
- **单元层就是基线**：分层文件存在时 `gate.test` 必须等于单元层命令，由 lint 校验。
- **区域显式选择**：每个 change 在 `gate.integration` 选区域、在 `gate.integration_skip` 写跳过理由；区域 `covers` 与切片 `owns` 相交时必须二选一，由 lint 校验；未选区域不跑。
- **纯度与耗时由探针判定**：baseline / final 跑单元层时注入临时 pytest 插件，用审计钩子逐用例记录触碰与耗时；排除 import 机制与断言重写；碰了即 G11；≥3 秒且单独重跑仍 ≥3 秒即 G10。阈值不可配置。
- **放行要人类原话**：慢单测只有在最新一条人类消息含该用例名与放行词时才写进 `slow_allow`（判据同起飞批准）。
- **降级**：探针不可度量（非 pytest、插件加载失败）时 G10 / G11 只警告；插件加载失败时去掉探针重跑，失败用例差分不受影响。
- **配置了分层时 baseline 不复用**：单元层本来就快，复用会跳过探针。

否决的方案：

- **pytest marker 分层**：只适用 Python；区域要靠 marker 组合，lint 无法只看路径判定。
- **静态扫描测试源码判定纯度**：间接调用看不见，误报多，结论仍会漂移。
- **只在 `/test-tiers` 命令里检测、门禁不查**：分类只在运行命令那一刻成立。
- **按 `covers` 自动选区域 / final 兜底全跑**：前者把「判断」交给路径重叠，后者违背「按需发起」。
- **阈值用环境变量可调**：被门禁的一方能在命令前缀里改判据（DRAFT-gate-evidence-not-self-reported）。
- **一次超线即红**：并行切片的负载抖动会让飞行误停。
- **放行名单人手随意编辑、只靠 PR review**：「人工审核」没有机械证据；保留为已知缺口而非主路径。

## Consequences

- **更易**：基线从全量降到单元层（本仓预计 84 秒降到 1 秒内，大多数 change 还会选上 slice-gate 区域）；纯度与耗时有逐用例证据，分类不再漂移。
- **更易**：未配置分层文件的仓库与 change，行为、输出、`plan_sha` 都不变。
- **更难**：仓库要维护分层文件与目录布局；新测试写错层会被 lint / G12 拦下，需要挪文件。
- **更难**：未选区域里的回归在本 change 内跑不到，靠表态规则与计划审批兜住；定期全跑留给仓库自己（CI 等）。
- **代价**：探针只认 pytest；`os.stat` 类调用与 C 扩展 I/O 是盲区。
- **代价**：放行名单可被直接编辑绕过脚本，靠 G6 所有权与 PR diff 兜住。
- **与在役 ADR**：失败差分仍按 DRAFT-test-gate-baseline-diff（探针不承担差分，该 ADR 否决 `-p` 插件的顾虑由回退重跑化解）；复用规则仍按 DRAFT-baseline-reuse-by-content-fingerprint，分层仓库不复用属新情形。均不 supersede。
