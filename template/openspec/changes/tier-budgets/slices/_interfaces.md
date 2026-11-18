# 切片之间的接口（tier-budgets）

各片只按这里写的签名与形状互相调用。规则原文在 `specs/tier-budgets/spec.md`，取舍在 `design.md`。

## S1 · `test-ledger.py`

```python
budget(final, base, budgets, scope_of, allow=None, phase="final") -> dict
budget_changes(old_budgets, new_budgets, old_allow, new_allow) -> [str]
```

- `final` / `base`：账本（`build` 的产物）；`base` 可为 `None`。
- `budgets`：`tier_budgets(tiers)` 的返回（见 S2）。
- `scope_of(用例 id, 账本里的层 t) -> 范围 | None`：`budget_scope_of(tiers)` 的返回（见 S2）。
- `allow`：`allow_view(...)` 的返回（见 S2），键是 nodeid；账本 `id_form` 为 `junit` 时由 `budget` 内部用 `_to_junit` 换算键。
- `phase`：`"baseline"`（全部超线计老债，不看 `base`）或 `"final"`。
- 纯函数：不读文件、不取时间、不抛出可预期的异常（形状意外由调用方的 `try` 兜住）。

`budget` 的返回：

```python
{
  "judged": bool,            # 集成层单条能否判红；final 阶段基线账本缺失或不完整 → False
  "why": str | None,         # judged 为 False 的原因
  "failed": [str],           # 以 "G13 slow integration test" / "G14 tier budget" 开头，调用方原样并入 failed / reasons
  "warnings": [str],
  "new_n": int,  "new":   [[用例 id, 秒, 范围, 线], …],   # 本 change 新增且超线（明细至多 TOP_N 条，下同）
  "debt_n": int, "debt":  [[用例 id, 秒, 范围, 线], …],   # 基线时已超线
  "cross_n": int, "cross": [[用例 id, 秒, 范围, 线], …],  # 基线时未超线、本次超线
  "allowed_n": int,          # 超过区域的线、但在有效放行之内的条数
  "totals": {范围: {"kind": "unit" | "region", "cases": int, "sec": float, "no_sec": int,
                    "budget": float | None, "over": True | False | None,   # None = 没有预算或未判
                    "added_sec": float | None,                              # 不在 base 里的用例耗时之和；没有 base → None
                    "top": [[用例 id, 秒], …]}},                            # 该范围耗时最大的至多 3 条
  "allow": {"total": int, "expired": [用例 id], "soon": [[用例 id, 到期日]], "unlimited": int},
}
```

- `totals` 的键 = `budgets` 里出现的全部范围（没写预算的范围 `budget` 为 `None`、`over` 为 `None`）。
- `allow` 统计的是整份放行名单（不只是这次超线的），`unlimited` = 未过期且没有上限的条数。
- 调用方（S4）会在返回值上再加一个键 `"changes": [str]`（`budget_changes` 的结果），`render` 认这个键。

`budget_changes` 的入参：两版 `tier_budgets` 的返回，与两版分层文件里**原样**的 `slow_allow` 对象（不是 `allow_view`）。

`render(d)`：`d.get("budget")` 为真时在原有输出**之后**追加预算段；否则输出与现在逐字相同。

## S2 · `slice-gate.py`

```python
UNIT_MAX_SEC = 3.0        # 保留：单元层单条上限的缺省值
ALLOW_SOON_DAYS = 14      # 草案值

tier_budgets(tiers) -> {范围: {"kind": "unit" | "region", "case_sec": float | None, "total_sec": float | None, "part": str | None}}
budget_scope_of(tiers) -> (用例 id, 层) -> 范围 | None
allow_view(allow, today=None) -> {用例 id: {"limit": float | None, "expires": str | None, "expired": bool, "soon": bool,
                                            "approved": str, "reason": str}}
tier_verdicts(probe, probe_why, rerun, allow, case_sec=UNIT_MAX_SEC, today=None) -> (failed, warnings)
part_tier_verdicts(name, res, rerun, allow, case_sec=UNIT_MAX_SEC, today=None) -> (failed, warnings)
slow_candidates(probe, case_sec=UNIT_MAX_SEC) -> [nodeid]
```

- 范围：简写形态 `"unit"` 与各区域名；部件形态 `"<部件>/unit"` 与各区域名。`tiers` 为 `None` → `{}`。
- 单元层范围的 `case_sec` 没写时是 `3.0`；区域没写时是 `None`。`part`：部件形态下所属部件名，简写形态为 `None`。
- `allow`（两个判定函数的入参）仍是分层文件里原样的 `slow_allow`；`today` 是 `datetime.date`，缺省取 UTC 当天。
- `allow_view` 的 `expired`：`today > expires`；`soon`：未过期且 `(expires - today).days <= ALLOW_SOON_DAYS`。

## S4 · `slice-gate.py`

```python
_budget_judge(root, name, tiers, led, phase, lock_info, base=None, base_commit=None, tiers_file=None) -> (failed, warnings, 摘要 | None)
_final_budget(root, name, change_dir, tiers, led, baseline, lock_info) -> (failed, warnings, 摘要 | None)   # final 阶段取基线 commit 的分层文件与预算变更比较
_tiers_has_budget(tiers) -> bool
_tiers_at(root, commit, tiers_file) -> tiers | None
```

- 没有任何范围写 `budget` → `([], [], None)`，不调用账本模块。
- 摘要 = `budget()` 的返回去掉 `failed` / `warnings`，final 阶段另加 `changes`。
- 已经过 `_time_verdicts`：返回的 `failed` 可直接并入。
- 任何异常 → `([], ["预算未判：<原因>"], None)`。

输出位置：final 的 `result["tests"]["budget"]` 与 `delta.json` 的 `budget`；baseline 的 `bl["ledger"]["budget"]`。摘要为 `None` 时都不出现这个键。

## S3 · `test-tiers.py`

```
test-tiers.py allow-slow NODEID --reason TEXT [--limit-sec SEC] [--expires YYYY-MM-DD] [--openspec-root DIR] [--session PATH]
```

- `--limit-sec` 须大于 0，写入条目 `limit_sec`（整数值写成 int）；`--expires` 须为不早于今天（UTC）的真实日期，写入条目 `expires`。不合法 → 退出 2。
- 两者都没给 → 照常写入，stderr 提示一行「没有上限也没有到期日」。

## S5 · `flight-doctor.py`

```python
_tests_budget(path, tl, best) -> 预算与放行的 [tests] 展示行
```

- `[tests]` 段列出各范围预算与放行条目；只读展示，不改判定。
