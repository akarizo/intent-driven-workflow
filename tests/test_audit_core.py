"""test-ledger.py 的 violations()：账本里全部超线用例的清单，线的取法与 budget() 相同
（scenario: test-audit#violations-list-every-over-line-case、#violations-honor-allow-limit-and-expiry、
#violations-skip-unjudgeable-cases、#violations-match-junit-form-ledger）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。只调纯函数，不碰真实文件、不起子进程。"""
import pytest

from conftest import load_hook
from test_budget_core import allowed, budgets, case, ledger, scope_of

PENDING = pytest.mark.xfail(strict=True, reason="change test-audit S1 未实现")

U = "tests/unit/test_u.py::"
H = "tests/integration/hooks/test_h.py::"


@PENDING
def test_violations_list_every_over_line_case():
    # Given: 单元层单条 3 秒、区域 hooks 单条 30 秒；单元层一条沿用的 3.0 秒与一条 0.2 秒，hooks 一条实测 42.0 秒与一条恰好 30.0 秒
    tl = load_hook("test-ledger")
    led = ledger({U + "test_edge": case(3.0, m=0, tier="unit"), U + "test_ok": case(0.2, tier="unit"),
                  H + "test_big": case(42.0, tier="hooks"), H + "test_line": case(30.0, tier="hooks")})

    # When: 取超线清单
    rows = tl.violations(led, budgets(hooks_case=30.0), scope_of)

    # Then: 先 hooks 的 42.0 秒，再单元层的 3.0 秒（单元层不小于线即超线）；线内的两条不在；都按预算线判
    assert [(r["case"], r["scope"], r["kind"], r["sec"], r["line"]) for r in rows] == [
        (H + "test_big", "hooks", "region", 42.0, 30.0), (U + "test_edge", "unit", "unit", 3.0, 3.0)], rows
    assert {r["by"] for r in rows} == {"budget"}, rows


@PENDING
def test_violations_honor_allow_limit_and_expiry():
    # Given: 区域 hooks 单条 30 秒；四条 74.0 秒的用例分别带：上限 90 的放行、上限 60 的放行、没有上限的放行、已过期的放行
    tl = load_hook("test-ledger")
    names = ("test_l90", "test_l60", "test_bare", "test_gone")
    led = ledger({H + n: case(74.0, tier="hooks") for n in names})
    allow = {H + "test_l90": allowed(limit=90.0), H + "test_l60": allowed(limit=60.0),
             H + "test_bare": allowed(), H + "test_gone": allowed(limit=90.0, expired=True)}

    # When: 取超线清单
    rows = tl.violations(led, budgets(hooks_case=30.0), scope_of, allow)

    # Then: 只有超过放行上限的那条（线 60，按放行判）与放行已过期的那条（线 30，按预算判）
    got = {r["case"]: (r["line"], r["by"]) for r in rows}
    assert got == {H + "test_l60": (60.0, "allow"), H + "test_gone": (30.0, "budget")}, rows


@PENDING
def test_violations_skip_unjudgeable_cases():
    # Given: 一条没有耗时的用例、一条所在层不在预算里的用例、一条在没写 case_sec 的区域 docs 里耗时 500 秒的用例
    tl = load_hook("test-ledger")
    led = ledger({H + "test_nosec": case(None, tier="hooks"), "tests/misc/test_m.py::test_m": case(99.0, tier=None),
                  "tests/integration/docs/test_d.py::test_d": case(500.0, tier="docs")})

    # When: 取超线清单
    rows = tl.violations(led, budgets(hooks_case=30.0), scope_of)

    # Then: 一条都不判
    assert rows == [], rows


@PENDING
def test_violations_match_junit_form_ledger():
    # Given: junit 形式的账本里 test_big 耗时 74.0 秒；放行名单的键是 nodeid 形式
    tl = load_hook("test-ledger")
    junit_id = "tests.integration.hooks.test_h::test_big"
    led = ledger({junit_id: case(74.0, tier="hooks")}, form="junit")

    # When: 分别以上限 90 秒与上限 60 秒的放行取超线清单
    loose = tl.violations(led, budgets(hooks_case=30.0), scope_of, {H + "test_big": allowed(limit=90.0)})
    tight = tl.violations(led, budgets(hooks_case=30.0), scope_of, {H + "test_big": allowed(limit=60.0)})

    # Then: 放行按换算后的键匹配：上限 90 时不超线；上限 60 时返回 junit 形式的那一条
    assert loose == [], loose
    assert [(r["case"], r["line"], r["by"]) for r in tight] == [(junit_id, 60.0, "allow")], tight
