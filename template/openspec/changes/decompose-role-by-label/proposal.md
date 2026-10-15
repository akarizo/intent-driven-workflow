## Why

`/opsx-apply` 收口时，`session-decompose.py --expect-models` 对每个 Workflow agent 先判角色，再拿实际模型与路由表比对（铁律 11）。角色只认两样：meta 里的 `agentType`；没有时退回按阶段判（`template/.claude/hooks/session-decompose.py:23-25`、`:216`）。

`useAgentTypes=false`（agent 定义没注册时的回退路径）下派发不带 `agentType`。wave integrator 在 **Implement 阶段**派发（`template/.claude/workflows/opsx-apply.js:180`），于是被判成 executor。2026-10-15 change `baseline-incremental-reuse` 的两轮飞行里，`integrate:w1`、`integrate:w2` 实际按路由表跑在 sonnet 上，却被判成「期望 opus，实际 sonnet」，HIGH 写进 blocking，PR #2 被强制 draft，最后由人类放行。

这个缺陷两个方向都错：
- **误报**：路由正确的 integrator 被判不符。本仓根目录不注册 `template/.claude/agents`，dogfood 每次都走回退路径，每次都会误报。
- **漏报**：integrator 真被错路由到 opus 时，被当成 executor，判为一致，违规被放过。

`session-decompose.py:22` 的注释已经点出「只看阶段会误判成 executor」，但只修了带 `agentType` 的主路径。铁律 10 要求回退路径语义一致，现在不满足。

## What Changes

- `session-decompose.py` 判角色改为三级：`agentType` → **label** → 阶段。
  - label 就是 Workflow agent meta 的 `description`，由 `opsx-apply.js` 派发时写入，格式固定。
  - 只认两类显式格式：`integrate:*`、`final-gate*` → integrator；`review:*` → reviewer。
  - 其余 label（切片 id、`fix` 等）不认，退回按阶段判，与现在相同。
- 新增测试锁住两个方向：无 `agentType` 的 `integrate:w1` 跑 sonnet 判一致、跑 opus 判不符。
- 新增契约测试：`opsx-apply.js` 里 integrator / reviewer 的 label 模板，与 `session-decompose.py` 认的格式一一对应。脚本改 label 而不改对账，测试会红。
- 不改 `opsx-apply.js`，不改路由表，不改 `--expect-models` 的输出格式与退出码。

## Capabilities

### New Capabilities
- `route-audit-role-resolution`：收口模型对账如何确定每个 Workflow agent 的路由角色（`agentType` → label → 阶段），以及 label 格式与工作流脚本的契约。

### Modified Capabilities
（无。`openspec/specs/` 尚无已归档规格。）

## Impact

- 代码：`template/.claude/hooks/session-decompose.py`（角色判定一处）。
- 测试：`tests/test_evidence_timeline.py`（对账行为）、`tests/test_agents_workflow.py`（label 契约）。
- 行为：只影响没有 `agentType` 的 Workflow agent。带 `agentType` 的路径与既有测试不变。
- 不在范围：仓库根 `.claude/` 是否接入 `template/.claude` 的 agents / commands（独立的结构决定）；回退用 Agent 派发路径的对账（它不经过 `--workflow`）。
