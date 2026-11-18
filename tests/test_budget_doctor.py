"""flight-doctor.py doctor 的 [tests]：各层预算对实际、超线条数、放行名单的到期情况
（scenario: tier-budgets#doctor-tests-lists-budgets、#doctor-tests-names-allow-entries）。
骨架：strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import datetime
import json

from conftest import write
from test_flight_doctor_tests import BIG, add_change, doctor, section

U = "tests/unit/test_u.py::test_u%02d"


def tiers(unit_budget=None, hooks_budget=None, allow=None):
    unit = {"paths": ["tests/unit/**"], "cmd": "true"}
    hooks = {"paths": ["tests/integration/hooks/**"], "covers": [], "cmd": "true"}
    if unit_budget:
        unit["budget"] = unit_budget
    if hooks_budget:
        hooks["budget"] = hooks_budget
    return {"unit": unit, "regions": {"hooks": hooks}, "slow_allow": allow or {}}


def final_ledger(repo):
    """在途 change c 的收口账本：单元层 12 条共 3.0 秒，区域 hooks 一条 9.0 秒。"""
    add_change(repo, "c")
    cases = {U % i: {"o": "passed", "s": 0.25, "t": "unit", "m": 1} for i in range(12)}
    cases[BIG] = {"o": "passed", "s": 9.0, "t": "hooks", "m": 1}
    led = {"v": 1, "change": "c", "commit": "a" * 40, "at": "2026-11-18T03:00:00Z", "phase": "final", "mode": "full",
           "lock": "held", "id_form": "nodeid", "tiered": True, "complete": True, "cases": cases}
    write(repo / ".git" / "flight-ledger" / "c" / "final.json", json.dumps(led, ensure_ascii=False))


def in_days(n):
    return (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=n)).isoformat()


def test_doctor_tests_lists_budgets(git_repo):
    # Given: 单元层总量预算 2 秒、区域 hooks 单条上限 5 秒；收口账本里单元层共 3.0 秒，hooks 有一条 9.0 秒的用例
    write(git_repo / "openspec" / "test-tiers.json", json.dumps(tiers({"total_sec": 2}, {"case_sec": 5})))
    final_ledger(git_repo)

    # When: 运行 doctor
    p = doctor(git_repo)

    # Then: [tests] 里单元层标出超预算，区域 hooks 标出超线 1 条并点名
    sec = section(p.stdout)
    assert p.returncode == 0 and sec, p.stdout + p.stderr
    assert any("unit" in l and "3.0s / 2s" in l and "超预算" in l for l in sec), sec
    assert any("hooks" in l and "超线 1 条" in l and BIG in l for l in sec), sec


def test_doctor_tests_names_allow_entries(git_repo):
    # Given: 放行名单三条：已过期的、3 天后到期的、既没有上限也没有期限的；另一个仓库状态是没有预算也没有放行
    gone, soon, bare = U % 1, U % 2, U % 3
    entry = {"reason": "读大样本", "approved": "t · 放行"}
    allow = {gone: dict(entry, limit_sec=10, expires="2000-01-01"), soon: dict(entry, limit_sec=10, expires=in_days(3)),
             bare: dict(entry)}
    path = git_repo / "openspec" / "test-tiers.json"
    final_ledger(git_repo)

    # When: 先以带放行名单的分层文件跑 doctor，再换成没有预算也没有放行的分层文件跑一次
    write(path, json.dumps(tiers(allow=allow), ensure_ascii=False))
    with_allow = section(doctor(git_repo).stdout)
    write(path, json.dumps(tiers(), ensure_ascii=False))
    plain = section(doctor(git_repo).stdout)

    # Then: 放行一行数清总数、已过期（点名）、快到期、没有上限；没有预算与放行时不出这些行
    line = next((l for l in with_allow if l.strip().startswith("放行")), "")
    assert "共 3 条" in line and "已过期 1 条" in line and gone in line, with_allow
    assert "14 天内到期 1 条" in line and "无上限 1 条" in line, line
    assert plain and not any("预算" in l or "放行" in l for l in plain), plain
