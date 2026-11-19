"""test-tiers.py audit：只读体检——数据来源与归层、十个不合规类别
（scenario: test-audit#audit-without-tiers-file-points-to-test-tiers、#audit-lists-over-line-cases-from-ledger、
#audit-recomputes-layer-and-drops-missing-files、#audit-works-for-parts-form、#audit-flags-layering-problems、
#audit-flags-region-without-case-limit、#audit-flags-total-over-budget、#audit-flags-allow-entries、
#audit-probe-flags-impure-unit-cases）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。夹具函数供 test_audit_verdict / test_audit_compare 复用。"""
import datetime
import json

from conftest import run_hook, write

UF, HF = "tests/unit/test_u.py", "tests/integration/hooks/test_h.py"
U, H = UF + "::", HF + "::"
GWT = "def %s():\n    # Given: 无\n    # When: 无\n    # Then: 恒真\n    assert True\n"
BARE = "def %s():\n    assert True\n"


def tiers(unit_budget=None, hooks_budget=None, docs=False, allow=None, hooks_paths=None):
    """简写形态：单元层 tests/unit/**，区域 hooks（tests/integration/hooks/**），可选区域 docs（不写预算）。"""
    unit = {"paths": ["tests/unit/**"], "cmd": "true"}
    hooks = {"paths": hooks_paths or ["tests/integration/hooks/**"], "covers": ["src/hooks/**"], "cmd": "true"}
    if unit_budget:
        unit["budget"] = unit_budget
    if hooks_budget:
        hooks["budget"] = hooks_budget
    regions = {"hooks": hooks}
    if docs:
        regions["docs"] = {"paths": ["tests/integration/docs/**"], "covers": [], "cmd": "true"}
    return {"unit": unit, "regions": regions, "slow_allow": allow or {}}


def layer_of(nodeid):
    """夹具里账本记的层：tests/unit/ → unit，tests/integration/<区域>/ → 区域名，其余 None。"""
    path = nodeid.split("::", 1)[0]
    if path.startswith("tests/unit/"):
        return "unit"
    if path.startswith("tests/integration/"):
        return path.split("/")[2]
    return None


def setup(repo, tiers_obj, cases=None, missing=(), no_gwt=(), extra_files=(), ledger=True, recorded=None, **led):
    """写分层文件（tiers_obj 为 None 则不写）；为每条用例所在文件写出同名用例（缺省带 GWT 注释；missing 里的用例不建文件，
    no_gwt 里的不写注释）；extra_files 另建只有一条用例的测试文件；写 change c 的收口账本（ledger=False 不写）。
    cases = {nodeid: 秒}；recorded = {nodeid: 账本里记的层}，缺省按路径推。"""
    cases = cases or {}
    if tiers_obj is not None:
        write(repo / "openspec" / "test-tiers.json", json.dumps(tiers_obj, ensure_ascii=False))
    files = {}
    for nid in cases:
        if nid not in missing:
            path, name = nid.split("::", 1)
            files.setdefault(path, []).append((BARE if nid in no_gwt else GWT) % name)
    for path in extra_files:
        files.setdefault(path, []).append(GWT % "test_extra")
    for path, bodies in files.items():
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("\n\n".join(bodies), encoding="utf-8")
    if ledger:
        rows = {nid: {"o": "passed", "s": sec, "t": (recorded or {}).get(nid, layer_of(nid)), "m": 1}
                for nid, sec in cases.items()}
        doc = {"v": 1, "change": "c", "commit": "a" * 40, "at": "2026-11-18T03:00:00Z", "phase": "final",
               "mode": "full", "lock": "held", "id_form": "nodeid", "tiered": True, "complete": True, "cases": rows}
        doc.update(led)
        write(repo / ".git" / "flight-ledger" / "c" / "final.json", json.dumps(doc, ensure_ascii=False))


def audit(repo, *args):
    """运行 test-tiers.py audit；→ (CompletedProcess, stdout 解析出的 JSON 或 None)。"""
    p = run_hook("test-tiers", "audit", *args, cwd=repo)
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = None
    return p, out


def ids(out):
    return [it["id"] for it in out["items"]]


def item(out, item_id):
    return next(it for it in out["items"] if it["id"] == item_id)


def in_days(n):
    return (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=n)).isoformat()


def test_audit_without_tiers_file_points_to_test_tiers(git_repo):
    # Given: 被测仓库没有分层文件，也没有账本
    write(git_repo / "tests" / "test_a.py", GWT % "test_a")

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 退出 1；只报一条 no-tiers，指向 /test-tiers
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    assert (out["form"], out["verdict"]) == ("none", "violations"), out
    assert [it["category"] for it in out["items"]] == ["no-tiers"], out["items"]
    assert "/test-tiers" in out["items"][0]["text"], out["items"]


def test_audit_lists_over_line_cases_from_ledger(git_repo):
    # Given: 区域 hooks 单条上限 5 秒；change c 的收口账本里单元层一条 4.0 秒、hooks 一条 9.0 秒，其余在线内
    setup(git_repo, tiers(hooks_budget={"case_sec": 5}),
          {U + "test_slow": 4.0, U + "test_ok": 0.2, H + "test_big": 9.0, H + "test_ok": 1.0})

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 退出 1；两条超线各归其类，带耗时、线、规则号；来源是 change c 的收口账本；各范围给出分布
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    u, h = item(out, "unit-slow:" + U + "test_slow"), item(out, "region-slow:" + H + "test_big")
    assert (u["sec"], u["line"], u["rule"], u["level"]) == (4.0, 3, "R4", "violation"), u
    assert (h["sec"], h["line"], h["rule"], h["scope"]) == (9.0, 5, "R6", "hooks"), h
    assert (out["source"]["ledger"]["change"], out["source"]["ledger"]["phase"]) == ("c", "final"), out["source"]
    assert (out["scopes"]["unit"]["cases"], out["scopes"]["hooks"]["cases"]) == (2, 2), out["scopes"]
    assert (out["scopes"]["unit"]["sec"], out["scopes"]["hooks"]["sec"]) == (4.2, 10.0), out["scopes"]
    assert all(k in out["scopes"]["hooks"] for k in ("p50", "p95", "max")) and out["scopes"]["hooks"]["max"] == 9.0


def test_audit_recomputes_layer_and_drops_missing_files(git_repo):
    # Given: 账本记 tests/a/test_x.py::test_x 在 unit、4.0 秒，但当前分层文件里它落在区域 hooks（单条 5 秒）；
    #        另一条 8.0 秒用例所在的文件已不存在
    moved, gone = "tests/a/test_x.py::test_x", "tests/unit/test_gone.py::test_g"
    setup(git_repo, tiers(hooks_budget={"case_sec": 5}, hooks_paths=["tests/integration/hooks/**", "tests/a/**"]),
          {moved: 4.0, gone: 8.0, U + "test_ok": 0.2}, missing=(gone,), recorded={moved: "unit", gone: "unit"})

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 按当前分层文件重新归层后没有超线；文件不存在的那条被丢弃并计数
    assert out is not None, p.stdout + p.stderr
    assert not [it for it in out["items"] if it["category"] in ("unit-slow", "region-slow")], out["items"]
    assert out["source"]["dropped"] == 1, out["source"]


def test_audit_works_for_parts_form(git_repo):
    # Given: 部件形态：部件 py（root svc/py，单元层 svc/py/tests/unit/**）；账本里它的一条用例 4.0 秒；
    #        另有一个不属于任何部件的测试文件 misc/test_loose.py
    slow = "svc/py/tests/unit/test_p.py::test_slow"
    parts = {"parts": {"py": {"root": "svc/py", "test_files": ["svc/py/tests/**/test_*.py"],
                              "unit": {"paths": ["svc/py/tests/unit/**"], "cmd": "true"}}}, "slow_allow": {}}
    setup(git_repo, parts, {slow: 4.0}, extra_files=("misc/test_loose.py",), recorded={slow: "unit"})

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 退出 1；单元层范围名带部件；归属问题沿用 check 的判据
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    assert out["form"] == "parts", out
    assert item(out, "unit-slow:" + slow)["scope"] == "py/unit", out["items"]
    assert "不属于任何部件" in item(out, "layering:misc/test_loose.py")["text"], out["items"]


def test_audit_flags_layering_problems(git_repo):
    # Given: 区域 hooks 的 paths 含 tests/integration/** 与 tests/unit/test_both.py；仓库里有未归层与匹配多层的测试文件
    t = tiers(hooks_budget={"case_sec": 5}, hooks_paths=["tests/integration/**", "tests/unit/test_both.py"])
    setup(git_repo, t, extra_files=("tests/unit/test_a.py", "tests/unit/test_both.py", "tests/test_loose.py"),
          ledger=False)

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 退出 1；两个文件各一条 layering，规则 R2
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    loose, both = item(out, "layering:tests/test_loose.py"), item(out, "layering:tests/unit/test_both.py")
    assert "未归层" in loose["text"] and "匹配多层" in both["text"], (loose, both)
    assert (loose["rule"], both["rule"]) == ("R2", "R2") and loose["level"] == "violation", (loose, both)
    assert "layering:tests/unit/test_a.py" not in ids(out), ids(out)


def test_audit_flags_region_without_case_limit(git_repo):
    # Given: 区域 hooks 写了单条上限，区域 docs 没写 budget
    setup(git_repo, tiers(hooks_budget={"case_sec": 5}, docs=True), ledger=False)

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 只有 docs 被点名，规则 R5，去向只有 budget
    assert out is not None, p.stdout + p.stderr
    d = item(out, "no-case-limit:docs")
    assert (d["rule"], d["level"], d["fix"], d["scope"]) == ("R5", "violation", ["budget"], "docs"), d
    assert "no-case-limit:hooks" not in ids(out), ids(out)


def test_audit_flags_total_over_budget(git_repo):
    # Given: 单元层总量预算 2 秒、账本合计 3.0 秒；区域 hooks 总量预算 5 秒、账本合计 9.0 秒
    cases = {U + "test_u%02d" % i: 0.25 for i in range(12)}
    cases[H + "test_big"] = 9.0
    setup(git_repo, tiers(unit_budget={"total_sec": 2}, hooks_budget={"case_sec": 60, "total_sec": 5}), cases)

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 两个范围都记不合规（区域在门禁里只警告，体检里一样点名），文本写出合计与预算
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    tu, th = item(out, "total-over:unit"), item(out, "total-over:hooks")
    assert (tu["level"], th["level"], tu["rule"]) == ("violation", "violation", "R7"), (tu, th)
    assert "3.0" in tu["text"] and "2" in tu["text"] and "9.0" in th["text"] and "5" in th["text"], (tu, th)


def test_audit_flags_allow_entries(git_repo):
    # Given: 放行名单五条：已过期的、没有上限也没有期限的、所指文件已不存在的、3 天后到期的、远期到期的；对应用例都是 5.0 秒
    gone, bare, soon, far = (U + "test_u%d" % i for i in (1, 2, 3, 4))
    stale = "tests/unit/test_removed.py::test_r"
    e = {"reason": "读大样本", "approved": "2026-11-18T03:12:00Z · 放行"}
    allow = {gone: dict(e, limit_sec=10, expires="2000-01-01"), bare: dict(e),
             stale: dict(e, limit_sec=10, expires=in_days(400)), soon: dict(e, limit_sec=10, expires=in_days(3)),
             far: dict(e, limit_sec=10, expires=in_days(400))}
    setup(git_repo, tiers(hooks_budget={"case_sec": 5}, allow=allow), {gone: 5.0, bare: 5.0, soon: 5.0, far: 5.0})

    # When: 体检
    p, out = audit(git_repo, "--json")

    # Then: 三类放行问题各一条；快到期的只有提示；远期的没有任何条目
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    for iid in ("allow-expired:" + gone, "allow-unbounded:" + bare, "allow-stale:" + stale):
        assert (item(out, iid)["level"], item(out, iid)["rule"]) == ("violation", "R8"), iid
    assert [i for i in ids(out) if i.endswith(soon)] == ["allow-soon:" + soon], ids(out)
    assert item(out, "allow-soon:" + soon)["level"] == "advice"
    assert not [i for i in ids(out) if i.endswith(far)], ids(out)


def test_audit_probe_flags_impure_unit_cases(git_repo, tmp_path):
    # Given: 探针结果：单元层用例 test_spawns 有「子进程」触碰；区域 hooks 的文件里两条用例中有一条无触碰且 0.1 秒
    cases = {U + "test_spawns": 0.1, U + "test_pure": 0.1, H + "test_io": 1.0, H + "test_calc": 0.1}
    setup(git_repo, tiers(hooks_budget={"case_sec": 60}), cases, ledger=False)
    hits = {U + "test_spawns": {"子进程": "subprocess.Popen true"}, H + "test_io": {"文件": "open /data/x"}}
    probe = tmp_path / "probe.json"
    probe.write_text(json.dumps({"total": 4, "files": {},
                                 "tests": {n: {"sec": s, "hits": hits.get(n, {})} for n, s in cases.items()}},
                                ensure_ascii=False), encoding="utf-8")

    # When: 分别带探针结果与不带地体检（都不读账本）
    _, with_probe = audit(git_repo, "--json", "--no-ledger", "--probe", str(probe))
    _, plain = audit(git_repo, "--json", "--no-ledger")

    # Then: 带探针：单元层不纯记不合规（R3），区域里的纯用例只是提示；不带探针：两条都没有，另有一条「纯度未核对」的提示
    assert with_probe is not None and plain is not None
    imp = item(with_probe, "unit-impure:" + U + "test_spawns")
    assert (imp["rule"], imp["level"]) == ("R3", "violation") and "子进程" in imp["text"], imp
    assert item(with_probe, "pure-in-region:" + HF)["level"] == "advice", with_probe["items"]
    assert "purity-unchecked" not in [it["category"] for it in with_probe["items"]], with_probe["items"]
    cats = [it["category"] for it in plain["items"]]
    assert "unit-impure" not in cats and "pure-in-region" not in cats and "purity-unchecked" in cats, cats
