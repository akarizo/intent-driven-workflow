# DRAFT. 执行层模型按派发用途由仓库配置显式路由，规划期继承主会话

- Status: accepted, supersedes DRAFT-model-routing-defaults-for-template（仅决策第 2 条中的「需推理的 subagent 保留 inherit」；第 1、3、4 条在役）
- Date: 2026-11-19
- Supersedes: DRAFT-model-routing-defaults-for-template（合并时回填真实号；只取代上述一条）
- 来源 change：model-routing-config（design D1–D9）

## Context

`DRAFT-model-routing-defaults-for-template` 规定需推理的 subagent 保留 inherit，也就是随会话主模型。后来铁律 11 把它机械化了：执行体与评审员 = `session-model.py` 判定出的 `<main>` · high，integrator = sonnet · low。

2026-11-19 用户提出四点要求：
- 执行层用 opus · medium，评审保留 high；
- 每个仓库有自己的默认配置；
- 起飞前确认；
- 配置「不写 main，必须是直接模型名称」。

用户同时明确：「最终的解决方案和规划还是要继承主会话」。

随主会话做不到上面这些：
- 执行体与评审员共用一个 `<main>`，effort 写死在文档和 frontmatter 里；
- 下游仓库没有可配的地方；
- bulk-apply 与 legacy 的实现 / 修复派发漏写 `model`，实际落到了 env 默认的 sonnet。

审批页 `docs/flight-routing-config.html` v4，用户回复「全按推荐」。

## Decision

1. **执行层每个派发用途一个键**，共 10 个：flight 5 个（executor / executor-large / fixer / reviewer / integrator）、ship 2 个（reviewer / followup）、archive.sync、claudemd.evidence、bulk.apply。值只写模型名（opus / sonnet / haiku / fable）与 effort，禁 `main` / `inherit`。配置放在 openspec 根下的 `model-routing.json`；缺失的键走内建默认：推理类 opus · high，机械类 sonnet · low，bulk.apply opus · medium。
2. **规划期确认**：flight 与 ship 两组在规划期钉进 `slices.json.routing`，人类批准计划即确认路由。之后改动会让批准过期。起飞时只认钉住的值，缺失即停飞。
3. **环境覆盖时停飞**：设了 `CLAUDE_CODE_EFFORT_LEVEL` 或 `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`，起飞前停飞，因为它们会覆盖派发时传入的值。
4. **收口机械对账 model 与 effort**：effort 取子 agent 转录 assistant 行的 `effort` 字段。
5. **规划期不进路由配置**：explore / new / continue / propose / mini 的产出只来自主会话或 fork。注册表拒收规划期组名，规划类命令与 skill 不写 `model` / `effort`，也不做非 fork 的派发；由测试机械检查。

## Consequences

- **更易**：每个仓库按派发用途调模型与 effort，只改一份 JSON，飞行前在 spec.html 上看得见；路由不符会在收口时被机械发现，PR 判 draft。
- **更难 / 代价**：
  - 没有配置的下游，执行体与评审员从「随主会话」变为固定 opus · high；
  - 在途 change 要先 pin，并重新批准一次；
  - 执行体降到 medium 的效果没有数据，需要先跑几次飞行观察。
- **约束后续变更**：
  - 新增执行层派发点，必须登记一个键并经 `model-routing.py get` 取值，不得写死模型名；
  - 规划期的提速只能用 fork 或主会话串行，不得进入路由配置；
  - 改注册表要新立 ADR。
