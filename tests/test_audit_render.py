"""test-audit.py render：校验整改稿、按去向归轨道、写单文件审批页
（scenario: test-audit#render-writes-approval-page-with-tracks、#render-rejects-inapplicable-actions、
#render-checks-move-destinations、#render-lists-unplanned-violations）。
骨架：strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import run_hook, write

PENDING = pytest.mark.xfail(strict=True, reason="change test-audit S4 未实现")

FIX = {"unit-slow": ["speedup", "move", "allow"], "region-slow": ["speedup", "allow", "delete"],
       "no-case-limit": ["budget"], "allow-unbounded": ["allow", "drop-allow"]}
RULE = {"unit-slow": "R4", "region-slow": "R6", "no-case-limit": "R5", "allow-unbounded": "R8"}
U = "tests/unit/test_u.py::"
H_BIG = "region-slow:tests/integration/hooks/test_h.py::test_big"


def tiers(docs_budget=None):
    docs = {"paths": ["tests/integration/docs/**"], "covers": [], "cmd": "true"}
    if docs_budget:
        docs["budget"] = docs_budget
    return {"unit": {"paths": ["tests/unit/**"], "cmd": "true"},
            "regions": {"hooks": {"paths": ["tests/integration/hooks/**"], "covers": [], "cmd": "true",
                                  "budget": {"case_sec": 5}}, "docs": docs},
            "slow_allow": {}}


def entry(category, key, scope=None):
    return {"id": "%s:%s" % (category, key), "category": category, "rule": RULE[category], "level": "violation",
            "scope": scope, "case": key if "::" in key else None, "file": None, "sec": 9.0, "line": 5,
            "text": "演示", "fix": FIX[category]}


def render(repo, tmp_path, items, plan):
    """写分层文件、体检存档与整改稿，运行 render；→ (CompletedProcess, stdout 末行 JSON 或 None, 审批页路径)。"""
    write(repo / "openspec" / "test-tiers.json", json.dumps(tiers(), ensure_ascii=False))
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"v": 1, "at": "2026-11-18T00:00:00Z", "head": "a" * 40, "form": "shorthand",
                                 "verdict": "violations", "items": items}, ensure_ascii=False), encoding="utf-8")
    pl = tmp_path / "plan.json"
    pl.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    page = tmp_path / "plan.html"
    p = run_hook("test-audit", "render", "--audit", str(audit), "--plan", str(pl), "--out", str(page), cwd=repo)
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    try:
        out = json.loads(lines[-1]) if lines else None
    except ValueError:
        out = None
    return p, out, page


@PENDING
def test_render_writes_approval_page_with_tracks(git_repo, tmp_path):
    # Given: 体检里 unit-slow、region-slow、no-case-limit、allow-unbounded 各一条；整改稿依次是搬到区域 hooks、提速、
    #        写预算（稿的 tiers 给 docs 写了 case_sec）、交人放行
    slow, bare = "unit-slow:" + U + "test_slow", "allow-unbounded:" + U + "test_bare"
    items = [entry("unit-slow", U + "test_slow", "unit"), entry("region-slow", H_BIG.split(":", 1)[1], "hooks"),
             entry("no-case-limit", "docs", "docs"), entry("allow-unbounded", U + "test_bare", "unit")]
    plan = {"items": {slow: {"action": "move", "dest": "tests/integration/hooks/test_u.py"},
                      H_BIG: {"action": "speedup", "note": "缩小样本"},
                      "no-case-limit:docs": {"action": "budget"}, bare: {"action": "allow"}},
            "tiers": tiers(docs_budget={"case_sec": 30})}

    # When: 渲染审批页
    p, out, page = render(git_repo, tmp_path, items, plan)

    # Then: 退出 0；轨道条数由脚本归类；审批页含每个条目、每条一个勾选框与导出按钮
    assert p.returncode == 0 and out is not None, p.stdout + p.stderr
    assert out["tracks"] == {"mechanical": 2, "human": 1, "change": 1, "keep": 0, "unplanned": 0}, out
    html = page.read_text(encoding="utf-8")
    for iid in (slow, H_BIG, "no-case-limit:docs", bare):
        assert iid in html, iid
    assert "导出 Markdown" in html and html.count('type="checkbox"') >= 4, html[:400]


@PENDING
def test_render_rejects_inapplicable_actions(git_repo, tmp_path):
    # Given: 给 no-case-limit 条目写了 speedup；有一个体检结果里不存在的条目 id；一条 keep 没写理由
    slow = "unit-slow:" + U + "test_slow"
    items = [entry("unit-slow", U + "test_slow", "unit"), entry("no-case-limit", "docs", "docs")]
    plan = {"items": {"no-case-limit:docs": {"action": "speedup"}, "region-slow:ghost": {"action": "speedup"},
                      slow: {"action": "keep"}}}

    # When: 渲染审批页
    p, _, page = render(git_repo, tmp_path, items, plan)

    # Then: 退出 1；三处逐条点名；审批页照写且问题清单里有它们
    assert p.returncode == 1, p.stdout + p.stderr
    for iid in ("no-case-limit:docs", "region-slow:ghost", slow):
        assert any(iid in l for l in p.stderr.splitlines()), (iid, p.stderr)
    assert page.exists() and "region-slow:ghost" in page.read_text(encoding="utf-8")


@PENDING
def test_render_checks_move_destinations(git_repo, tmp_path):
    # Given: 三条 unit-slow 的去向都是 move：目标仍在单元层、目标不属于任何层、目标在区域 hooks
    one, two, three = ("unit-slow:" + U + n for n in ("test_one", "test_two", "test_three"))
    items = [entry("unit-slow", U + n, "unit") for n in ("test_one", "test_two", "test_three")]
    plan = {"items": {one: {"action": "move", "dest": "tests/unit/sub/test_one.py"},
                      two: {"action": "move", "dest": "misc/test_two.py"},
                      three: {"action": "move", "dest": "tests/integration/hooks/test_three.py"}}}

    # When: 渲染审批页
    p, _, _ = render(git_repo, tmp_path, items, plan)

    # Then: 退出 1；前两条各自点名原因，第三条不点名
    err = p.stderr.splitlines()
    assert p.returncode == 1, p.stdout + p.stderr
    assert any(one in l and "仍在单元层" in l for l in err), p.stderr
    assert any(two in l and "未归层" in l for l in err), p.stderr
    assert not any(three in l for l in err), p.stderr


@PENDING
def test_render_lists_unplanned_violations(git_repo, tmp_path):
    # Given: 体检里三条不合规项，整改稿只安排了其中一条
    items = [entry("unit-slow", U + n, "unit") for n in ("test_one", "test_two", "test_three")]
    plan = {"items": {"unit-slow:" + U + "test_one": {"action": "speedup"}}}

    # When: 渲染审批页
    p, out, page = render(git_repo, tmp_path, items, plan)

    # Then: 没排进稿的不算问题，但要数出来
    assert p.returncode == 0 and out is not None, p.stdout + p.stderr
    assert out["tracks"]["unplanned"] == 2 and out["tracks"]["change"] == 1, out
    assert "未安排 2 条" in page.read_text(encoding="utf-8")
