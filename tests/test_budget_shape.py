"""分层文件的预算与放行期限：形状校验、范围摊平；单元层 G10 取预算线、放行看上限与期限
（scenario: tier-budgets#budget-shape-validated 等 9 条）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import copy
import datetime
import json

import pytest

from conftest import commit_all, load_hook, run_hook
from test_tiers_gate import HOOKS_OK, setup_tiers

PENDING = pytest.mark.xfail(strict=True, reason="change tier-budgets S2 未实现")

BIG = "tests/unit/test_a.py::test_big"
SIMPLE = {
    "unit": {"paths": ["tests/unit/**"], "cmd": "true", "budget": {"case_sec": 1.5, "total_sec": 60}},
    "regions": {"hooks": {"paths": ["tests/integration/hooks/**"], "covers": [], "cmd": "true",
                          "budget": {"case_sec": 30}}},
    "slow_allow": {},
}
PARTS = {
    "parts": {
        "py": {"root": "svc/py", "unit": {"paths": ["svc/py/tests/unit/**"], "cmd": "true", "budget": {"total_sec": 100}},
               "regions": {"api": {"paths": ["svc/py/tests/api/**"], "covers": [], "cmd": "true",
                                   "budget": {"case_sec": 60}}}},
        "sh": {"root": "svc/sh", "unit": {"paths": ["svc/sh/**"], "cmd": "true"}},
    },
    "slow_allow": {},
}


def check(tmp_path, tiers):
    """把 tiers 写成文件后交给 slice-gate 校验 → (tiers | None, errors)。"""
    path = tmp_path / "test-tiers.json"
    path.write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
    return load_hook("slice-gate")._load_tiers_file(str(path))


def day(offset):
    """UTC 今天加 offset 天，YYYY-MM-DD。"""
    return (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=offset)).isoformat()


def g10(failed):
    return [f for f in failed if f.startswith("G10")]


@PENDING
def test_budget_shape_validated(tmp_path):
    # Given: 单元层与区域 hooks 都写了合法的 budget
    bad_case, bad_total, bad_key = copy.deepcopy(SIMPLE), copy.deepcopy(SIMPLE), copy.deepcopy(SIMPLE)
    bad_case["unit"]["budget"]["case_sec"] = 0
    bad_total["unit"]["budget"]["total_sec"] = "60"
    bad_key["regions"]["hooks"]["budget"]["max"] = 9

    # When: 校验原样的与三份改坏的
    tiers, errors = check(tmp_path, SIMPLE)
    e_case, e_total, e_key = check(tmp_path, bad_case)[1], check(tmp_path, bad_total)[1], check(tmp_path, bad_key)[1]

    # Then: 原样的通过；改坏的各有一条点名层与字段的错误
    assert errors == [] and tiers is not None, errors
    assert any(e.startswith("tiers:") and "unit" in e and "case_sec" in e for e in e_case), e_case
    assert any(e.startswith("tiers:") and "unit" in e and "total_sec" in e for e in e_total), e_total
    assert any(e.startswith("tiers:") and "区域 hooks" in e and "max" in e for e in e_key), e_key


@PENDING
def test_allow_entry_limit_and_expires_validated(tmp_path):
    # Given: 一条放行带 limit_sec 与 expires，另一条只有 reason 与 approved
    old = "tests/unit/test_a.py::test_old"
    good = copy.deepcopy(SIMPLE)
    good["slow_allow"] = {BIG: {"reason": "读大样本", "approved": "t · 放行 test_big", "limit_sec": 90,
                                "expires": "2027-02-01"},
                          old: {"reason": "旧条目", "approved": "t · 放行 test_old"}}
    variants = []
    for field, value in (("limit_sec", -1), ("expires", "2027-13-40"), ("expires", "明年")):
        bad = copy.deepcopy(good)
        bad["slow_allow"][BIG][field] = value
        variants.append((field, bad))

    # When: 校验
    tiers, errors = check(tmp_path, good)
    results = [(field, check(tmp_path, bad)[1]) for field, bad in variants]

    # Then: 合法的通过；改坏的各有一条点名用例 id 与字段的错误
    assert errors == [] and tiers is not None, errors
    for field, errs in results:
        assert any(BIG in e and field in e for e in errs), (field, errs)


@PENDING
def test_parts_budget_shape_validated(tmp_path):
    # Given: 部件形态：部件 py 的单元层与它的区域 api 都写了 budget
    bad = copy.deepcopy(PARTS)
    bad["parts"]["py"]["regions"]["api"]["budget"]["case_sec"] = 0

    # When: 校验原样的与改坏的
    tiers, errors = check(tmp_path, PARTS)
    errs = check(tmp_path, bad)[1]

    # Then: 原样的通过；改坏的点名部件、区域与字段
    assert errors == [] and tiers is not None, errors
    assert any("部件 py" in e and "区域 api" in e and "case_sec" in e for e in errs), errs


@PENDING
def test_budget_scopes_resolved():
    # Given: 简写形态（单元层没写 budget，区域 hooks 单条上限 30）与部件形态（部件 py 的单元层总量预算 100）
    sg = load_hook("slice-gate")
    simple = copy.deepcopy(SIMPLE)
    del simple["unit"]["budget"]

    # When: 摊平预算、取范围映射
    sb, pb = sg.tier_budgets(simple), sg.tier_budgets(PARTS)
    s_of, p_of = sg.budget_scope_of(simple), sg.budget_scope_of(PARTS)

    # Then: 简写形态是 unit 与区域名；部件形态是 <部件>/unit 与区域名；单元层用例按 id 归到部件
    assert (sb["unit"]["kind"], sb["unit"]["case_sec"], sb["unit"]["total_sec"]) == ("unit", 3.0, None), sb
    assert (sb["hooks"]["kind"], sb["hooks"]["case_sec"]) == ("region", 30), sb
    assert pb["py/unit"]["total_sec"] == 100 and "sh/unit" in pb and pb["api"]["case_sec"] == 60, pb
    assert s_of("tests/unit/test_a.py::test_ok", "unit") == "unit"
    assert p_of("svc/py/tests/unit/test_p.py::test_ok", "unit") == "py/unit"
    assert p_of("sh::sh::TestS", "unit") == "sh/unit"
    assert p_of("py::tests.api.test_x::test_y", "api") == "api" and s_of("x::y", "hooks") == "hooks"


@PENDING
def test_unit_case_budget_replaces_default_line():
    # Given: 用例 test_mid 首跑 1.5 秒、单独重跑 1.4 秒
    sg = load_hook("slice-gate")
    mid = "tests/unit/test_a.py::test_mid"
    probe = {mid: {"sec": 1.5, "hits": {}}}

    # When: 分别以 1 秒与缺省的单条上限判定单元层
    tight, _ = sg.tier_verdicts(probe, None, {mid: 1.4}, {}, case_sec=1.0)
    loose, _ = sg.tier_verdicts(probe, None, {mid: 1.4}, {})

    # Then: 1 秒线下恰有一条 G10，文本含 ≥1s；缺省线下没有
    assert len(g10(tight)) == 1 and mid in g10(tight)[0] and "≥1s" in g10(tight)[0], tight
    assert g10(loose) == [], loose


@PENDING
def test_unit_case_budget_applies_in_baseline(git_repo):
    # Given: 被测仓库的单元层单条上限是 0.1 秒，单元层有一条睡 0.3 秒的纯函数用例
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": "import time\n\n\ndef test_nap():\n    time.sleep(0.3)\n"},
                    {"tests/integration/hooks/test_h.py": HOOKS_OK})
    path = git_repo / "openspec" / "test-tiers.json"
    tiers = json.loads(path.read_text(encoding="utf-8"))
    tiers["unit"]["budget"] = {"case_sec": 0.1}
    path.write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
    commit_all(git_repo, "unit budget")

    # When: 运行 baseline
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo)

    # Then: 基线红在 G10，点名该用例，文本里的线是 0.1 秒
    bl_path = d / "gate-baseline.json"
    reasons = json.loads(bl_path.read_text(encoding="utf-8")).get("reasons") if bl_path.exists() else []
    assert p.returncode != 0, p.stdout + p.stderr
    assert any(r.startswith("G10") and "test_nap" in r and "≥0.1s" in r for r in reasons or []), (reasons, p.stdout)


@PENDING
def test_allowed_slow_over_limit_is_red():
    # Given: test_big 在放行名单里，limit_sec 是 5
    sg = load_hook("slice-gate")
    allow = {BIG: {"reason": "读大样本", "approved": "2026-11-18T03:12:00Z · 放行 test_big", "limit_sec": 5}}

    # When: 首跑 6.0 / 重跑 5.5 判一次，首跑 4.0 / 重跑 3.9 判一次
    over, _ = sg.tier_verdicts({BIG: {"sec": 6.0, "hits": {}}}, None, {BIG: 5.5}, allow)
    within, warns = sg.tier_verdicts({BIG: {"sec": 4.0, "hits": {}}}, None, {BIG: 3.9}, allow)

    # Then: 超过上限判红并写明上限；上限之内只警告
    assert len(g10(over)) == 1 and BIG in g10(over)[0] and "放行上限" in g10(over)[0] and "5" in g10(over)[0], over
    assert g10(within) == [], within
    assert any(BIG in w and "放行" in w for w in warns), warns


@PENDING
def test_expired_allow_is_red_and_soon_is_flagged():
    # Given: test_big 首跑 3.4 秒、重跑 3.3 秒，在放行名单里
    sg = load_hook("slice-gate")
    probe = {BIG: {"sec": 3.4, "hits": {}}}

    def run(expires):
        allow = {BIG: {"reason": "读大样本", "approved": "t · 放行 test_big", "expires": expires}}
        return sg.tier_verdicts(probe, None, {BIG: 3.3}, allow)

    # When: expires 分别是很久以前、3 天后、60 天后
    past, _ = run("2000-01-01")
    soon_f, soon_w = run(day(3))
    far_f, far_w = run(day(60))

    # Then: 过期的判红并写明日期；快到期的警告带「将于」；还早的只是普通放行警告
    assert len(g10(past)) == 1 and "到期" in g10(past)[0] and "2000-01-01" in g10(past)[0], past
    assert g10(soon_f) == [] and any(BIG in w and "将于" in w and day(3) in w for w in soon_w), (soon_f, soon_w)
    assert g10(far_f) == [] and any(BIG in w for w in far_w) and not any("将于" in w for w in far_w), (far_f, far_w)


@PENDING
def test_part_unit_budget_applies_per_part():
    # Given: 部件 sh 的一个用例首跑 1.5 秒、重跑 1.5 秒
    sg = load_hook("slice-gate")
    nid = "sh::sh::TestS"
    res = {"secs": {nid: 1.5}, "probe": None, "probe_why": "非 pytest 部件", "secs_why": None}

    # When: 分别以 1 秒与缺省的单条上限判定部件 sh 的单元层
    tight, _ = sg.part_tier_verdicts("sh", res, {nid: 1.5}, {}, case_sec=1.0)
    loose, _ = sg.part_tier_verdicts("sh", res, {nid: 1.5}, {})

    # Then: 1 秒线下有一条点名部件与用例的 G10；缺省线下没有
    assert len(g10(tight)) == 1 and "部件 sh" in g10(tight)[0] and nid in g10(tight)[0], tight
    assert g10(loose) == [], loose
