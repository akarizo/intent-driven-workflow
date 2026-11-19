## ADDED Requirements

### Requirement: 按 scenario 映射生成 strict-xfail 骨架
`.claude/hooks/plan-scaffold.py scaffold --change-dir D` SHALL 对 `scenario_tests` 的每一项 `path::func` 按以下规则处理：
- `path` 不是 `.py` → 列入 `skipped`，不改文件；
- 函数已存在 → 列入 `existing`，不改文件；
- 否则追加一个函数，列入 `created`，形式如下：
  - 带 `@pytest.mark.xfail(strict=True, reason="<切片 id> 未实现")`；
  - 函数体是 `# Given:` / `# When:` / `# Then:` 三行注释，内容取自对应 scenario 的 Gherkin 原文，AND / BUT 并入它前面那个关键字所在的行；
  - 最后一行是 `assert False, "PLAN-SCAFFOLD-PLACEHOLDER：换成真实断言"`。

文件缺 `import pytest` 时 SHALL 补上。stdout 输出 `{"created", "existing", "skipped"}`。映射里的 scenario 在 specs 中找不到时 MUST 以 exit 2 退出，并点名该 scenario。

Feature: 测试骨架生成
Rule: 只补缺的函数，GWT 取 Gherkin 原文

#### Scenario: scaffold-creates-strict-xfail-skeletons
- **GIVEN** 一个计划：S1 有一个 scenario，映射到尚不存在的 `tests/test_new.py::test_alpha`
- **AND** 该 scenario 的 spec 原文是 GIVEN「已有订单」、AND「订单已付款」、WHEN「用户申请退款」、THEN「订单变为退款中」
- **WHEN** 运行 `plan-scaffold.py scaffold --change-dir`
- **THEN** `tests/test_new.py` 含 `import pytest` 与带 `strict=True` 的 xfail 函数 `test_alpha`
- **AND** 它的 Given 行含「已有订单」与「订单已付款」，When 行含「用户申请退款」，Then 行含「订单变为退款中」，函数体含 `PLAN-SCAFFOLD-PLACEHOLDER`
- **AND** stdout 的 `created` 是 `["tests/test_new.py::test_alpha"]`

#### Scenario: scaffold-leaves-existing-functions
- **GIVEN** `tests/test_old.py` 已有写好断言的 `test_beta`，计划同时映射 `test_beta` 与尚不存在的 `test_gamma`
- **WHEN** 运行 `scaffold`
- **THEN** `test_beta` 的源码逐字不变，文件末尾多出 `test_gamma`
- **AND** stdout 的 `existing` 含 `test_beta`，`created` 含 `test_gamma`

#### Scenario: scaffold-skips-non-python
- **GIVEN** 一个 scenario 映射到 `web/a.test.js::renders`
- **WHEN** 运行 `scaffold`
- **THEN** 退出 0，stdout 的 `skipped` 含 `web/a.test.js::renders`，`web/a.test.js` 没有被创建

### Requirement: 规划期自查 GWT 与占位残留
`plan-scaffold.py gwt --change-dir D` SHALL 只针对 `scenario_tests` 映射到的函数做两项检查，逐条打印问题，有任何一条即 exit 1，全部通过时 exit 0：
- 用与切片门禁 G4 相同的判据，检查 GWT 注释；
- 检查函数体里有没有残留 `PLAN-SCAFFOLD-PLACEHOLDER`。

Feature: 规划期 G4 自查
Rule: 骨架补完才算规划完成

#### Scenario: gwt-reports-missing-steps-and-placeholders
- **GIVEN** 一个映射函数缺 `# When:` 注释，另一个映射函数仍含 `PLAN-SCAFFOLD-PLACEHOLDER`
- **WHEN** 运行 `plan-scaffold.py gwt --change-dir`
- **THEN** exit 1，输出分别点名这两个函数
- **AND** 把两处都修好后再运行，退出 0
