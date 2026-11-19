## ADDED Requirements

### Requirement: 审批面板显示钉住的路由
`spec_html.py` 渲染飞行区块时 SHALL 按 `routing` 是否存在分两种输出：
- `slices.json` 有 `routing` → SHALL 输出一张「模型路由」表，flight 组与 ship 组的每个键各占一行，列出键、模型、effort，并写明来源；
- 没有 `routing` → SHALL 显示一条提示：起飞会被拒绝，需先运行 `model-routing.py pin --change-dir`。

Feature: 审批面板路由表
Rule: 人类在批准前看见本次飞行用什么模型

#### Scenario: spec-html-shows-pinned-routing
- **GIVEN** 一个 `slices.json` 含 `routing`，其中 `flight.executor` 为 opus · medium、`flight.integrator` 为 sonnet · low
- **WHEN** 渲染 spec.html
- **THEN** 页面有「模型路由」标题，表里有 `flight.executor` 一行写着 opus 与 medium，`flight.integrator` 一行写着 sonnet 与 low

#### Scenario: spec-html-warns-missing-routing
- **GIVEN** 一个没有 `routing` 的 `slices.json`
- **WHEN** 渲染 spec.html
- **THEN** 页面含 `model-routing.py pin` 的提示
