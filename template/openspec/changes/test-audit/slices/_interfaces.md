# 切片之间的接口（test-audit）

各片只按这里写的签名与形状互相调用。规则原文在 `specs/test-audit/spec.md`，取舍在 `design.md`。

## S1 · `test-ledger.py`

```python
violations(ledger, budgets, scope_of, allow=None) -> [dict]
```

- `ledger`：账本形状的字典，只用到 `cases`（`{用例 id: {"s", "t", …}}`）与 `id_form`；
- `budgets`：`slice-gate.py` 的 `tier_budgets(tiers)`；`scope_of`：`budget_scope_of(tiers)`；`allow`：`allow_view(...)`（键是 nodeid）；
- 返回每条 `{"case", "scope", "kind": "unit" | "region", "sec", "line", "by": "budget" | "allow"}`，按 `(-sec, case)` 排序；
- 纯函数。`budget()` 的签名、返回、文本都不变。

## S2 / S3 · `test-tiers.py`

模块常量（S2 一次定全，含 S3 才产出的类别）：

```python
AUDIT_RULES = {
  "<类别>": {"rule": "R1".."R8" | None, "level": "violation" | "advice" | "unjudged", "fix": [去向…], "title": 中文名},
}
```

类别共 16 个：十个不合规（`no-tiers` `layering` `unit-impure` `unit-slow` `no-case-limit` `region-slow` `total-over` `allow-stale` `allow-expired` `allow-unbounded`）、五个提示（`allow-soon` `allow-unneeded` `pure-in-region` `purity-unchecked` `gwt-missing`）、一个 `unjudged`。各自的 `rule` / `fix` 见 spec「体检的不合规类别」的表；提示里 `allow-unneeded` 的 `fix` 是 `["drop-allow"]`，`pure-in-region` 是 `["move", "split"]`，其余为空。

命令行：

```
test-tiers.py audit [--openspec-root DIR] [--change-dir DIR | --ledger PATH | --no-ledger] [--probe PATH]...
                    [--scope 范围]... [--category 类别]... [--top N] [--json] [--out PATH]
                    [--compare 之前的体检JSON [--plan 整改稿JSON]]
```

体检 JSON（`--json` 的 stdout 与 `--out` 的文件是同一个对象）：

```python
{
  "v": 1, "at": ISO 时间, "head": HEAD commit | None,
  "form": "none" | "shorthand" | "parts",
  "verdict": "compliant" | "violations" | "unjudged",
  "source": {"ledger": {"change", "phase", "commit", "at", "mode", "complete", "id_form"} | None,
             "probes": 份数, "cases": 用例数, "dropped": 丢弃数},
  "counts": {"violation": N, "advice": N, "unjudged": N, "by_category": {类别: N}},   # --top 截断之前
  "items": [{"id": "<类别>:<键>", "category", "rule", "level", "scope", "case", "file", "sec", "line", "text", "fix"}],
  "scopes": {范围: {"kind", "cases", "sec", "no_sec", "case_sec", "total_sec", "over", "p50", "p95", "max"}},
  "allow": budget() 返回的 allow 段 | None,
  "compare": {...}                      # 只在 --compare 时有（S3）
}
```

- 条目里用不上的字段为 `None`；`gwt-missing` 另带 `"count"`。
- 键：用例类取用例 id，`layering` / `pure-in-region` 取文件路径，`no-case-limit` / `total-over` 取范围名，放行类取放行的键；`no-tiers` / `purity-unchecked` / `gwt-missing` 的键为空串（id 以冒号结尾）；未判的 id 是 `unjudged:no-measure` / `unjudged:ledger` / `unjudged:scope:<范围>`。
- 退出码：0 合规 / 1 有不合规项 / 3 没有不合规项但有未判项 / 2 输入不可用。带 `--compare` 时见 spec「体检前后对比」。

## S4 / S5 · `test-audit.py`

```python
ACTIONS = {"move": "mechanical", "split": "mechanical", "retier": "mechanical", "budget": "mechanical",
           "drop-allow": "mechanical", "allow": "human", "speedup": "change", "purify": "change",
           "delete": "change", "keep": "keep"}
```

```
test-audit.py render --audit 体检JSON --plan 整改稿JSON --out HTML [--openspec-root DIR]
test-audit.py verify --plan 整改稿JSON --base COMMIT [--openspec-root DIR] [--json]
```

整改稿：

```python
{"items": {"<条目 id>": {"action": 去向, "dest": 目标文件（move / split）, "note": 备注（keep 必填）}},
 "tiers": 拟写入的分层文件（可选）, "support": [随迁文件 glob]（可选）}
```

- `render` 的 stdout 末行：`{"tracks": {"mechanical", "human", "change", "keep", "unplanned"}, "problems": N, "out": 路径}`；问题逐条进 stderr；退出码 0 / 1 / 2。
- `verify --json` 的 stdout：`{"ok", "violations": [文本], "unchecked": [路径], "changed": {"tests": N, "support": [路径], "tiers": bool}, "budget_changes": [文本]}`；退出码 0 / 1 / 2。
- `test-audit.py` 不依赖 `test-tiers.py`：它只读体检 JSON 里每条的 `fix`，不引用 `AUDIT_RULES`。两个常量的一致性由 S7 的对账测试守。

## S6 · 文档（已合回）

- `template/.claude/flight-runner-contract.md` 新增「测试套件合规标准」一节；`template/.claude/commands/test-tiers.md` 加体检指针。无代码符号；测试从 `tests/test_audit_standard_docs.py` 的 `standard_section` / `TITLE` 取节。

> 已合回核对：S1 `violations(ledger, budgets, scope_of, allow=None)`（test-ledger.py:394）、S4 `cmd_render(args)` / `main(argv=None)`（test-audit.py:152/206），与上文签名一致。

> 已合回核对（wave 2）：S2 `AUDIT_RULES`（test-tiers.py:485）/ `audit_report(top, tiers, led, probes)`（:597）/ `cmd_audit(args)`（:701）/ `main(argv=None)`（:721）；S5 `ACTIONS`（test-audit.py:27）/ `cmd_verify(args)`（:313）/ `main(argv=None)`（:359），均与上文一致。
