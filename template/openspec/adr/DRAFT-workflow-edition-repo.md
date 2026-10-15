# DRAFT. Workflow 版独立成仓：以 stable-v2.0 为起点，按需摘取 Mod 版的通用改进

- Status: accepted
- Date: 2026-10-15
- 关联：DRAFT-apply-as-flight · DRAFT-gate-evidence-not-self-reported（均保持在役）
- 来源 change：workflow-edition

## Context

`akarizo/intent-driven-claude-code` 在 `stable-v2.0`（PR #34）之后，从 #35 起把飞行控制面迁进 flight 插件（Mod）；#49 删除了 Workflow 引擎，铁律 10 改为「失效即停飞、不回退第二实现」。

2026-10-15 用户决定：Mod 版留在原仓继续演进，Workflow 版另起独立仓库维护；不在原仓回滚，也不在原仓开长期分支。

原仓 #35–#63 里有 12 个 PR 带不依赖插件的通用改进（G7 按实际结果判、执行体抛错重派、执行体一律隔离、全量测试按基线差分、安装器修复等），v2.0 用户同样需要。两个版本今后会分叉，同一个问题可能要在两边各修一次。

## Decision

1. **本仓 = Workflow 版**：飞行的唯一实现是 Workflow 引擎（`template/.claude/workflows/opsx-apply.js`）；Workflow 不可用时按铁律 10 原文回退到 Agent 派发。不引入 flight 插件及其批准带、账本、计划指纹、测量协议、能力包络。
2. **起点**：本仓 main 以原仓 `stable-v2.0`（`49533dd`）为起点，保留完整历史与 `stable-v1.0`、`stable-v2.0` 两个 tag。
3. **与原仓不做同步**：原仓的改进按需以本仓的 change 摘取，每次在 proposal 里写明原仓 PR 与 commit；只摘不依赖插件的部分，依赖插件的思路要在本仓重新设计、另立 change。
4. **分发**：`install.sh` 缺省从本仓下载；两个版本之间的切换走 `--upgrade`；安装器检测到仍启用的 flight 插件时只提示、不代卸载。
5. **带入的 ADR**：原仓的 `DRAFT-installer-versioned-with-template`、`DRAFT-test-gate-baseline-diff` 随本 change 原样带入、在本仓生效；它们正文里提到的 Mod 侧 ADR 与 flight 插件只存在于原仓。

## Consequences

- **更易**：v2.0 用户拿到经过实战修复的 Workflow 引擎与判定器，不需要插件；原仓 Mod 版的演进不受影响；fail-soft 的回退语义保留。
- **更难**：两个版本分叉，通用修复要分别落地；摘取时要识别插件依赖（本次的做法：以 Workflow 引擎删除前的最后一版为底做减法）。
- **中性**：本仓不是 GitHub fork，`gh pr create` 只会投到本仓；原仓文档不提本仓，下游从本仓 README 获知两个版本的关系。
