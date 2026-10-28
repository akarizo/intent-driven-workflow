## REMOVED Requirements

### Requirement: pr-ship 自动修代码之前必须问一次
**Reason**: 与本 change 的 `pr-ship-review-autofix`「/pr-ship 评审出 CRITICAL/HIGH 时直接自动修复」直接冲突：新语义是评审给出 CRITICAL / HIGH 时直接自动修复并 push、全程不使用 AskUserQuestion，修前不再问询。
**Migration**: 改以 `specs/pr-ship-review-autofix/spec.md` 为准（scenario `pr-ship-autofixes-without-asking`）。旧 scenario `pr-ship-asks-before-autofix` 的映射用例 `tests/test_template_docs.py::test_pr_ship_asks_before_autofix` 保留函数名（旧 change `flight-preflight-and-retry` 的映射仍引用它），断言已按新语义改为「修前不问询」。
