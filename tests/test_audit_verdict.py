"""test-tiers.py audit：提示、未判、结论与退出码，输出与筛选
（scenario: test-audit#audit-unjudged-when-no-measurement、#audit-unjudged-scope-with-unmeasured-files、
#audit-compliant-exits-zero、#audit-filters-by-scope-category-top）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

from test_audit_scan import H, HF, U, UF, audit, ids, in_days, item, setup, tiers


def test_audit_unjudged_when_no_measurement(git_repo):
    # Given: 分层与预算都合规，每个测试文件恰属一层；本机没有账本
    setup(git_repo, tiers(hooks_budget={"case_sec": 5}), extra_files=(UF, HF), ledger=False)

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 没有不合规项，但也没有测量：退出 3，结论是判不全
    assert p.returncode == 3 and out is not None, p.stdout + p.stderr
    assert out["verdict"] == "unjudged" and out["counts"]["violation"] == 0, out
    assert "unjudged:no-measure" in ids(out), ids(out)


def test_audit_unjudged_scope_with_unmeasured_files(git_repo):
    # Given: 区域 hooks 写了总量预算 5 秒；账本覆盖单元层全部文件，hooks 的两个测试文件里只有一个有测量（9.0 秒）
    other = "tests/integration/hooks/test_h2.py"
    setup(git_repo, tiers(hooks_budget={"case_sec": 60, "total_sec": 5}), {U + "test_ok": 0.2, H + "test_a": 9.0},
          extra_files=(other,))

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 退出 3；hooks 记未判并点名没有测量的文件，不出总量超预算；单元层照常
    assert p.returncode == 3 and out is not None, p.stdout + p.stderr
    un = item(out, "unjudged:scope:hooks")
    assert un["level"] == "unjudged" and other in un["text"], un
    assert "total-over:hooks" not in ids(out) and "unjudged:scope:unit" not in ids(out), ids(out)


def test_audit_compliant_exits_zero(git_repo):
    # Given: 分层、预算、放行都合规，账本覆盖全部测试文件且都在线内；一条 3 天后到期的放行（用例 5.0 秒、上限 10 秒）、
    #        一条耗时已回到线内的放行（用例 0.2 秒）；两条用例没写 Given / When / Then 注释
    soon, unneeded = U + "test_soon", U + "test_fast"
    e = {"reason": "读大样本", "approved": "2026-11-18T03:12:00Z · 放行"}
    allow = {soon: dict(e, limit_sec=10, expires=in_days(3)), unneeded: dict(e, limit_sec=10, expires=in_days(400))}
    setup(git_repo, tiers(hooks_budget={"case_sec": 60}, allow=allow),
          {soon: 5.0, unneeded: 0.2, U + "test_plain1": 0.2, U + "test_plain2": 0.2, H + "test_a": 1.0},
          no_gwt=(U + "test_plain1", U + "test_plain2"))

    # When: 先取文本输出，再取 JSON
    text = audit(git_repo)[0]
    p, out = audit(git_repo, "--json")

    # Then: 两次都退出 0；文本首行与结论行；提示不影响结论，缺注释的用例只计数
    assert text.returncode == 0 and p.returncode == 0 and out is not None, text.stdout + text.stderr + p.stderr
    lines = text.stdout.splitlines()
    assert lines and lines[0].startswith("测试体检") and "结论：合规" in lines, text.stdout
    assert out["verdict"] == "compliant" and out["counts"]["violation"] == 0, out
    by_cat = {it["category"]: it for it in out["items"]}
    for cat in ("allow-soon", "allow-unneeded", "purity-unchecked", "gwt-missing"):
        assert by_cat[cat]["level"] == "advice", (cat, out["items"])
    assert by_cat["gwt-missing"]["count"] == 2, by_cat["gwt-missing"]
    assert by_cat["allow-unneeded"]["id"] == "allow-unneeded:" + unneeded, by_cat["allow-unneeded"]


def test_audit_filters_by_scope_category_top(git_repo, tmp_path):
    # Given: 区域 hooks 有两条超线用例（9.0 秒与 7.0 秒），单元层有一条超线用例
    setup(git_repo, tiers(hooks_budget={"case_sec": 5}),
          {H + "test_big": 9.0, H + "test_mid": 7.0, H + "test_ok": 1.0, U + "test_slow": 4.0, U + "test_ok": 0.2})
    saved = tmp_path / "audit.json"

    # When: 按类别取最慢 1 条并存档；再按范围 unit 取
    p1, top = audit(git_repo, "--json", "--category", "region-slow", "--top", "1", "--out", str(saved))
    p2, unit = audit(git_repo, "--json", "--scope", "unit")

    # Then: 明细被截到最慢那条，计数仍是截断前的；存档与 stdout 相同；按范围取时不含别的范围；结论都是不合规
    assert top is not None and unit is not None, p1.stdout + p1.stderr + p2.stderr
    assert [(it["id"], it["sec"]) for it in top["items"]] == [("region-slow:" + H + "test_big", 9.0)], top["items"]
    assert top["counts"]["by_category"]["region-slow"] == 2, top["counts"]
    assert json.loads(saved.read_text(encoding="utf-8")) == top
    assert not [it for it in unit["items"] if it["scope"] == "hooks"] and list(unit["scopes"]) == ["unit"], unit
    assert "unit-slow:" + U + "test_slow" in ids(unit), ids(unit)
    assert (p1.returncode, p2.returncode) == (1, 1), (p1.returncode, p2.returncode)
