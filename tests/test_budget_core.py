"""test-ledger.py 的预算判定（集成层棘轮 G13、层总量 G14）、预算变更比较、「测试变更」的预算段、对账噪声项收窄
（scenario: tier-budgets#new-integration-case-over-line-is-red 等 11 条）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。只调纯函数，不碰真实文件、不起子进程。"""
from conftest import load_hook

H = "tests/integration/hooks/test_h.py::"
OLD, NEW, BIG = H + "test_old", H + "test_new", H + "test_big"
DEBT, DRIFT = H + "test_debt", H + "test_drift"


def case(sec, m=1, tier=None, outcome="passed"):
    return {"o": outcome, "s": sec, "t": tier, "m": m}


def ledger(cases, mode="full", form="nodeid", commit="f" * 40, phase="final", complete=True):
    return {"v": 1, "change": "c", "commit": commit, "at": "2026-11-18T00:00:00Z", "phase": phase, "mode": mode,
            "lock": "held", "id_form": form, "tiered": True, "complete": complete, "cases": cases}


def base_ledger(cases, form="nodeid", complete=True):
    return ledger(cases, form=form, commit="b" * 40, phase="baseline", complete=complete)


def scope(kind, case_sec=None, total_sec=None):
    return {"kind": kind, "case_sec": case_sec, "total_sec": total_sec, "part": None}


def budgets(hooks_case=30.0, hooks_total=None, unit_total=None):
    """tier_budgets 的返回形状：单元层缺省 3 秒；区域 hooks 按参数；区域 docs 什么都没写。"""
    return {"unit": scope("unit", 3.0, unit_total), "hooks": scope("region", hooks_case, hooks_total),
            "docs": scope("region")}


def scope_of(cid, tier):
    return tier


def allowed(limit=None, expired=False):
    """allow_view 里一条放行的形状。"""
    return {"limit": limit, "expires": "2000-01-01" if expired else None, "expired": expired, "soon": False,
            "approved": "2026-11-18T03:12:00Z · 放行 test_big", "reason": "读 40MB 真实样本"}


def test_new_integration_case_over_line_is_red():
    # Given: 区域 hooks 单条上限 30 秒；收口账本里 test_new 实测 42.0 秒，基线账本里没有它
    tl = load_hook("test-ledger")
    base = base_ledger({OLD: case(1.0, tier="hooks")})
    final = ledger({OLD: case(1.0, tier="hooks"), NEW: case(42.0, tier="hooks")})

    # When: 判预算
    b = tl.budget(final, base, budgets(), scope_of)

    # Then: 恰有一条 G13 失败，点名用例、耗时与区域；新增超线 1 条
    assert len(b["failed"]) == 1 and b["failed"][0].startswith("G13 slow integration test"), b["failed"]
    assert NEW in b["failed"][0] and "42.0" in b["failed"][0] and "hooks" in b["failed"][0], b["failed"]
    assert (b["new_n"], b["judged"]) == (1, True), b


def test_existing_cases_over_line_only_warn():
    # Given: 基线账本里 test_debt 50 秒、test_drift 20 秒；收口账本里两条都是实测，分别 55 秒与 35 秒
    tl = load_hook("test-ledger")
    base = base_ledger({DEBT: case(50.0, tier="hooks"), DRIFT: case(20.0, tier="hooks")})
    final = ledger({DEBT: case(55.0, tier="hooks"), DRIFT: case(35.0, tier="hooks")})

    # When: 判预算
    b = tl.budget(final, base, budgets(), scope_of)

    # Then: 没有失败；老债 1 条、本次量到超线 1 条，各有一条警告点名
    assert b["failed"] == [], b["failed"]
    assert (b["debt_n"], b["cross_n"], b["new_n"]) == (1, 1, 0), b
    assert any("老债" in w and DEBT in w for w in b["warnings"]), b["warnings"]
    assert any("未判红" in w and DRIFT in w for w in b["warnings"]), b["warnings"]


def test_unmeasured_and_unbudgeted_cases_not_judged():
    # Given: 三条不在基线的 90 秒用例：hooks 里沿用的、hooks 里实测但无耗时的、没写单条上限的区域 docs 里实测的
    tl = load_hook("test-ledger")
    base = base_ledger({OLD: case(1.0, tier="hooks")})
    final = ledger({OLD: case(1.0, tier="hooks"), H + "test_inherited": case(90.0, m=0, tier="hooks"),
                    H + "test_nosec": case(None, tier="hooks"),
                    "tests/integration/docs/test_d.py::test_doc": case(90.0, tier="docs")})

    # When: 判预算
    b = tl.budget(final, base, budgets(), scope_of)

    # Then: 一条都不判
    assert b["failed"] == [], b["failed"]
    assert (b["new_n"], b["debt_n"], b["cross_n"]) == (0, 0, 0), b


def test_allow_entry_moves_integration_case_line():
    # Given: 区域 hooks 单条上限 30 秒；新增用例 test_big 实测 74 秒；放行名单里有它
    tl = load_hook("test-ledger")
    base = base_ledger({OLD: case(1.0, tier="hooks")})
    final = ledger({OLD: case(1.0, tier="hooks"), BIG: case(74.0, tier="hooks")})
    jbase = base_ledger({"tests.integration.hooks.test_h::test_old": case(1.0, tier="hooks")}, form="junit")
    jfinal = ledger({"tests.integration.hooks.test_h::test_old": case(1.0, tier="hooks"),
                     "tests.integration.hooks.test_h::test_big": case(74.0, tier="hooks")}, form="junit")

    # When: 放行未过期且上限 90 / 上限 60 / 没有上限 / 已过期；另以 junit 形式的账本配上限 90
    b90 = tl.budget(final, base, budgets(), scope_of, {BIG: allowed(limit=90.0)})
    b60 = tl.budget(final, base, budgets(), scope_of, {BIG: allowed(limit=60.0)})
    bnone = tl.budget(final, base, budgets(), scope_of, {BIG: allowed()})
    bexp = tl.budget(final, base, budgets(), scope_of, {BIG: allowed(limit=90.0, expired=True)})
    bj = tl.budget(jfinal, jbase, budgets(), scope_of, {BIG: allowed(limit=90.0)})

    # Then: 上限之内与没有上限的不判红；超过上限或放行过期的判红；junit 形式的账本同样认得这条放行
    assert b90["failed"] == [] and b90["allowed_n"] == 1, b90
    assert bnone["failed"] == [] and bnone["allowed_n"] == 1, bnone
    assert len(b60["failed"]) == 1 and b60["failed"][0].startswith("G13") and "放行上限" in b60["failed"][0], b60
    assert len(bexp["failed"]) == 1 and bexp["failed"][0].startswith("G13"), bexp
    assert bj["failed"] == [] and bj["allowed_n"] == 1, bj


def test_missing_baseline_ledger_degrades_to_warning():
    # Given: 区域 hooks 单条上限 30 秒；收口账本里一条实测 42 秒的用例；基线账本缺失，或不完整
    tl = load_hook("test-ledger")
    final = ledger({NEW: case(42.0, tier="hooks")})
    partial = base_ledger({OLD: case(1.0, tier="hooks")}, complete=False)

    # When: 以 final 阶段判预算
    results = [tl.budget(final, None, budgets(), scope_of), tl.budget(final, partial, budgets(), scope_of)]

    # Then: 不判红，说明原因，超线只进警告
    for b in results:
        assert b["failed"] == [], b["failed"]
        assert b["judged"] is False and b["why"], b
        assert any("未判" in w and "hooks" in w for w in b["warnings"]), b["warnings"]


def test_unit_total_over_budget_is_red():
    # Given: 单元层总量预算 10 秒；账本里单元层 30 条各 0.5 秒，其中 20 条是沿用的
    tl = load_hook("test-ledger")
    cases = {"tests/unit/test_u.py::test_u%02d" % i: case(0.5, m=1 if i < 10 else 0, tier="unit") for i in range(30)}
    led = ledger(cases, mode="incremental")

    # When: 分别以 10 秒与 20 秒的预算判
    over = tl.budget(led, base_ledger(cases), budgets(unit_total=10.0), scope_of)
    under = tl.budget(led, base_ledger(cases), budgets(unit_total=20.0), scope_of)

    # Then: 超预算时恰有一条 G14 失败，写明合计与预算；预算够时不红
    assert len(over["failed"]) == 1 and over["failed"][0].startswith("G14 tier budget"), over["failed"]
    assert "15.0" in over["failed"][0] and "10" in over["failed"][0], over["failed"]
    assert (over["totals"]["unit"]["sec"], over["totals"]["unit"]["over"]) == (15.0, True), over["totals"]
    assert under["failed"] == [] and under["totals"]["unit"]["over"] is False, under


def test_region_total_over_budget_only_warns():
    # Given: 区域 hooks 总量预算 100 秒；收口账本里 4 条共 130 秒，其中 12 秒的那条不在基线账本里
    tl = load_hook("test-ledger")
    top = H + "test_a"
    old = {top: case(60.0, tier="hooks"), H + "test_b": case(40.0, tier="hooks"), H + "test_c": case(18.0, tier="hooks")}
    final = ledger(dict(old, **{NEW: case(12.0, tier="hooks")}))

    # When: 判预算（该区域没写单条上限）
    b = tl.budget(final, base_ledger(old), budgets(hooks_case=None, hooks_total=100.0), scope_of)

    # Then: 不判红；警告写明合计、预算、本 change 新增的秒数与最慢的用例
    assert b["failed"] == [], b["failed"]
    warn = [w for w in b["warnings"] if w.startswith("G14") and "hooks" in w]
    assert len(warn) == 1, b["warnings"]
    assert "130.0" in warn[0] and "100" in warn[0] and "新增 12.0s" in warn[0] and top in warn[0], warn
    assert (b["totals"]["hooks"]["over"], b["totals"]["hooks"]["added_sec"]) == (True, 12.0), b["totals"]


def test_total_not_judged_for_impacted_partial_ledger():
    # Given: 单元层总量预算 10 秒；基线单元层 30 条各 1 秒；选测（gate.impacted）的收口账本只量到其中 2 条
    tl = load_hook("test-ledger")
    full = {"tests/unit/test_u.py::test_u%02d" % i: case(1.0, tier="unit") for i in range(30)}
    part = {k: full[k] for k in sorted(full)[:2]}
    led = ledger(part, mode="impacted")

    # When: 判预算
    b = tl.budget(led, base_ledger(full), budgets(unit_total=10.0), scope_of)

    # Then: 部分合计不可比，G14 不判红也不判绿，只警告「G14 未判」点名选测
    assert not any(f.startswith("G14") for f in b["failed"]), b["failed"]
    assert any(w.startswith("G14 未判") and "unit" in w and "impacted" in w for w in b["warnings"]), b["warnings"]
    assert b["totals"]["unit"]["over"] is None, b["totals"]


def test_total_not_judged_when_seconds_missing():
    # Given: 单元层总量预算 1 秒；10 条用例里 2 条无耗时、其余合计 5 秒；另一份账本耗时齐全但不完整
    tl = load_hook("test-ledger")
    gaps = {"tests/unit/test_u.py::test_u%02d" % i: case(None if i < 2 else 0.625, tier="unit") for i in range(10)}
    whole = {k: case(0.5, tier="unit") for k in gaps}

    # When: 判预算
    b1 = tl.budget(ledger(gaps), base_ledger(gaps), budgets(unit_total=1.0), scope_of)
    b2 = tl.budget(ledger(whole, complete=False), base_ledger(whole), budgets(unit_total=1.0), scope_of)

    # Then: 都不判，各有一条说明
    for b in (b1, b2):
        assert b["failed"] == [], b["failed"]
        assert b["totals"]["unit"]["over"] is None, b["totals"]
        assert any(w.startswith("G14") and "未判" in w for w in b["warnings"]), b["warnings"]


def test_render_lists_budget_section():
    # Given: 一份对账结果，预算段里有新增超线 1 条、老债 2 条、区域合计超预算、1 条已过期的放行、一行预算变更
    tl = load_hook("test-ledger")
    d, _ = tl.delta(base_ledger({OLD: case(1.0, tier="hooks")}),
                    ledger({OLD: case(1.0, tier="hooks"), NEW: case(42.0, tier="hooks")}))
    bud = {"judged": True, "why": None, "failed": [], "warnings": [],
           "new_n": 1, "new": [[NEW, 42.0, "hooks", 30.0]],
           "debt_n": 2, "debt": [[DEBT, 55.0, "hooks", 30.0]], "cross_n": 0, "cross": [], "allowed_n": 0,
           "totals": {"hooks": {"kind": "region", "cases": 4, "sec": 130.0, "no_sec": 0, "budget": 100.0,
                                "over": True, "added_sec": 12.0, "top": [[DEBT, 55.0]]}},
           "allow": {"total": 1, "expired": [BIG], "soon": [], "unlimited": 0},
           "changes": ["unit 单条上限 3s → 10s（放宽）"]}

    # When: 分别渲染不带与带预算段的对账结果
    plain = tl.render(d)
    lines = tl.render(dict(d, budget=bud)).splitlines()

    # Then: 预算段各行齐全，追加在原有输出之后；不带预算段时一行都没有
    assert any("新增超线" in l and NEW in l for l in lines), lines
    assert any("老债 2 条" in l for l in lines), lines
    assert any("hooks" in l and "130.0s / 100s" in l for l in lines), lines
    assert any("已过期" in l and BIG in l for l in lines), lines
    assert any("预算变更" in l for l in lines), lines
    assert "\n".join(lines).startswith(plain), (plain, lines)
    assert not any(w in plain for w in ("新增超线", "老债", "已过期", "预算变更")), plain


def test_budget_changes_are_listed():
    # Given: 单元层单条上限 3 → 10、区域 hooks 总量预算 300 → 取消；放行新增一条，另一条的上限 60 → 90 且理由也改了
    tl = load_hook("test-ledger")
    b1, b2 = H + "test_b1", H + "test_b2"
    old_b = {"unit": scope("unit", 3.0), "hooks": scope("region", None, 300.0)}
    new_b = {"unit": scope("unit", 10.0), "hooks": scope("region")}
    old_a = {b1: {"reason": "读大样本", "approved": "t · 放行", "limit_sec": 60}}
    new_a = {b1: {"reason": "换个说法", "approved": "t · 放行", "limit_sec": 90},
             b2: {"reason": "真实服务", "approved": "t · 放行", "limit_sec": 90}}

    # When: 比较两版
    lines = tl.budget_changes(old_b, new_b, old_a, new_a)

    # Then: 四处变动各有一行；完全相同或只有理由不同则为空
    assert any("unit" in l and "3s → 10s" in l and "放宽" in l for l in lines), lines
    assert any("hooks" in l and "300s" in l and "放宽" in l for l in lines), lines
    assert any("放行新增" in l and b2 in l for l in lines), lines
    assert any("放行改动" in l and b1 in l and "60s → 90s" in l for l in lines), lines
    assert tl.budget_changes(old_b, old_b, old_a, old_a) == []
    assert tl.budget_changes(old_b, old_b, old_a, {b1: dict(old_a[b1], reason="换个说法")}) == []


def test_noisy_delta_items_skip_region_cases():
    # Given: 单元层用例 1.0 → 3.0 秒，区域 hooks 的用例 10 → 40 秒，都是实测
    tl = load_hook("test-ledger")
    unit = "tests/unit/test_u.py::test_u"
    base = base_ledger({unit: case(1.0, tier="unit"), OLD: case(10.0, tier="hooks")})
    final = ledger({unit: case(3.0, tier="unit"), OLD: case(40.0, tier="hooks")})

    # When: 对账
    d, _ = tl.delta(base, final)

    # Then: 「变慢」只计单元层那一条；建议行里没有区域的「层耗时」
    assert d["slower_n"] == 1 and d["slower"] == [[unit, 1.0, 3.0]], d
    assert not any(line.startswith("hooks 层耗时") for line in d["advice"]), d["advice"]
