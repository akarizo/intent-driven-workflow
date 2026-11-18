"""baseline / final 按分层文件的预算判定：集成层新增超线 G13、单元层总量 G14、争抢下降级、预算变更、判定失败不改结论
（scenario: tier-budgets#final-red-on-new-slow-integration-case 等 9 条）。
骨架：strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。
护栏（no-budget-keeps-output-unchanged）在 base 上已成立，不带 xfail。"""
import json
import shutil
import subprocess
import sys

from conftest import HOOKS, commit_all, git, run_hook
from final_helpers import change_and_commit, final, gate_json, latest_anchor
from lock_helpers import Locks
from test_ledger_baseline import read_ledger
from test_tiers_gate import HOOKS_OK, PURE, setup_tiers
from test_tiers_parts_gate import setup_parts

H_FILE = "tests/integration/hooks/test_h.py"
SLOW_FILE = "tests/integration/hooks/test_slow.py"
SLOW_ID = SLOW_FILE + "::test_slow"
SLOW = "import time\n\n\ndef test_slow():\n    time.sleep(1.0)\n"
NAP = "import time\n\n\ndef test_nap():\n    time.sleep(0.3)\n"
LINE = 0.4  # 区域 hooks 的单条上限：普通用例毫秒级，test_slow 睡 1 秒


def set_tiers(repo, mutate, msg="tiers"):
    """改分层文件并提交。"""
    path = repo / "openspec" / "test-tiers.json"
    tiers = json.loads(path.read_text(encoding="utf-8"))
    mutate(tiers)
    path.write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
    commit_all(repo, msg)


def hooks_budget(repo, **budget):
    set_tiers(repo, lambda t: t["regions"]["hooks"].__setitem__("budget", budget))


def unit_budget(repo, **budget):
    set_tiers(repo, lambda t: t["unit"].__setitem__("budget", budget))


def run_baseline(repo, d, env=None):
    """跑 baseline 并提交飞行记录；返回 CompletedProcess。"""
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=repo, env=env)
    if git(repo, "status", "--porcelain"):  # 基线在写任何文件之前就退出时没有东西可提交
        commit_all(repo, "baseline")
    return p


def bl_of(d):
    """gate-baseline.json；基线没写出文件时返回空对象。"""
    path = d / "gate-baseline.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def texts(*groups):
    return [t for g in groups for t in (g or [])]


def test_final_red_on_new_slow_integration_case(git_repo):
    # Given: 区域 hooks 单条上限 0.4 秒，基线已跑且通过；之后提交了一个新的区域测试文件，里面一条用例睡 1 秒
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {H_FILE: HOOKS_OK})
    hooks_budget(git_repo, case_sec=LINE)
    b = run_baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    change_and_commit(git_repo, SLOW_FILE, SLOW, "add slow region test")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 红在 G13，点名该用例；预算摘要里新增超线 1 条
    assert p.returncode == 1, p.stdout + p.stderr
    assert any(f.startswith("G13 slow integration test") and SLOW_ID in f for f in out["failed"]), out["failed"]
    assert out["tests"]["budget"]["new_n"] == 1, out["tests"]


def test_debt_keeps_baseline_and_final_green(git_repo):
    # Given: 区域 hooks 单条上限 0.4 秒，区域里已有一条睡 1 秒的用例
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {H_FILE: HOOKS_OK, SLOW_FILE: SLOW})
    hooks_budget(git_repo, case_sec=LINE)

    # When: 跑 baseline；改动该区域另一个测试文件（让 final 重跑这个区域）后跑 final
    b = run_baseline(git_repo, d)
    change_and_commit(git_repo, H_FILE, HOOKS_OK + "\n\ndef test_more():\n    assert True\n", "touch region")
    out, p = final(git_repo, d)

    # Then: 两次都绿；都有一条「老债」警告；final 的摘要里老债 1 条、新增超线 0 条
    assert b.returncode == 0 and p.returncode == 0, b.stdout + b.stderr + p.stdout + p.stderr
    assert any("老债" in w for w in bl_of(d).get("warnings") or []), bl_of(d).get("warnings")
    assert any("老债" in w for w in out["warnings"]), out["warnings"]
    assert (out["tests"]["budget"]["debt_n"], out["tests"]["budget"]["new_n"]) == (1, 0), out["tests"]


def test_baseline_red_on_unit_total_over_budget(git_repo):
    # Given: 单元层总量预算 0.05 秒，单元层有一条睡 0.3 秒的纯函数用例
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": NAP}, {H_FILE: HOOKS_OK})
    unit_budget(git_repo, total_sec=0.05)

    # When: 跑 baseline；把预算改成 60 秒后再跑
    p1 = run_baseline(git_repo, d)
    reasons = bl_of(d).get("reasons") or []
    unit_budget(git_repo, total_sec=60)
    p2 = run_baseline(git_repo, d)

    # Then: 第一次红在 G14；第二次绿
    assert p1.returncode != 0, p1.stdout + p1.stderr
    assert any(r.startswith("G14 tier budget") for r in reasons), reasons
    assert p2.returncode == 0, p2.stdout + p2.stderr


def test_contended_run_downgrades_budget_verdicts(git_repo, tmp_path):
    # Given: 单元层总量预算 0.05 秒、一条睡 0.3 秒的用例；另一个进程持有独占锁且已超过它的持有上限
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": NAP}, {H_FILE: HOOKS_OK})
    unit_budget(git_repo, total_sec=0.05)
    with Locks(tmp_path) as lk:
        a = lk.hold("a", label="stuck-final", env={"FLIGHT_LOCK_MAX_HOLD_SEC": "0.3"})

        # When: 以同一锁目录运行 baseline
        p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo,
                     env={"FLIGHT_LOCK_DIR": str(lk.dir)})
        still_held = not a.exited()

    # Then: 以 0 退出，锁状态 timeout；G14 不在 reasons 里，而在 warnings 里并注明降为警告
    bl = bl_of(d)
    assert still_held
    assert p.returncode == 0, p.stdout + p.stderr
    assert bl["lock"]["state"] == "timeout", bl["lock"]
    assert not any("G14" in r for r in bl["reasons"]), bl["reasons"]
    assert any("G14" in w and "降为警告" in w for w in bl.get("warnings") or []), bl.get("warnings")


def test_budget_failure_does_not_fail_gate(git_repo, tmp_path):
    # Given: 一份不含 test-ledger.py 的 hooks 副本；区域 hooks 单条上限 0.4 秒，基线已用副本跑过，之后新增一条睡 1 秒的区域用例
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {H_FILE: HOOKS_OK})
    hooks_budget(git_repo, case_sec=LINE)
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("test-ledger.py", "__pycache__"))
    gate = [sys.executable, str(hooks / "slice-gate.py")]
    b = subprocess.run(gate + ["baseline", "--change-dir", str(d)], cwd=git_repo, capture_output=True, text=True)
    assert b.returncode == 0, b.stdout + b.stderr
    commit_all(git_repo, "baseline")
    change_and_commit(git_repo, SLOW_FILE, SLOW, "add slow region test")

    # When: 用副本里的 slice-gate.py 运行 final
    p = subprocess.run(gate + ["final", "--change-dir", str(d)], cwd=git_repo, capture_output=True, text=True)

    # Then: final 照常通过；只多一条「预算未判」的警告
    out = gate_json(p)
    assert p.returncode == 0 and out["failed"] == [], p.stdout + p.stderr
    assert any(w.startswith("预算未判") for w in out["warnings"]), out["warnings"]


def test_final_reports_budget_changes(git_repo):
    # Given: 区域 hooks 单条上限 30 秒，基线已跑；之后把它改成 300 秒并提交
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {H_FILE: HOOKS_OK})
    hooks_budget(git_repo, case_sec=30)
    b = run_baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    hooks_budget(git_repo, case_sec=300)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 警告里点名这处放宽；预算摘要带变更清单
    assert p.returncode == 0, p.stdout + p.stderr
    assert any(w.startswith("预算变更") and "hooks" in w and "30s → 300s" in w and "放宽" in w
               for w in out["warnings"]), out["warnings"]
    assert out["tests"]["budget"]["changes"], out["tests"]


def test_parts_unit_total_judged_per_part(git_repo):
    # Given: 部件形态：部件 py 的单元层总量预算 0.05 秒（它有一条睡 0.3 秒的纯函数用例），部件 sh 没写预算
    d = setup_parts(git_repo, py_tests=NAP)
    set_tiers(git_repo, lambda t: t["parts"]["py"]["unit"].__setitem__("budget", {"total_sec": 0.05}))

    # When: 跑 baseline
    p = run_baseline(git_repo, d)

    # Then: 红在部件 py 的 G14；部件 sh 没有 G14
    reasons = bl_of(d).get("reasons") or []
    assert p.returncode != 0, p.stdout + p.stderr
    assert any(r.startswith("G14 tier budget") and "部件 py" in r for r in reasons), reasons
    assert not any("G14" in r and "部件 sh" in r for r in reasons), reasons


def test_region_only_rerun_keeps_unit_cases(git_repo):
    # Given: 有分层文件，基线已跑；之后只提交了区域 hooks 的一个新测试文件
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {H_FILE: HOOKS_OK})
    b = run_baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    change_and_commit(git_repo, SLOW_FILE, SLOW, "add region test")

    # When: 运行 final（增量：单元层一条都不用重跑，只重跑该区域）
    out, p = final(git_repo, d)

    # Then: 收口账本与新锚点里仍有单元层用例（沿用），对账里没有「未重测」
    unit = "tests/unit/test_u.py::test_adds"
    led = read_ledger(git_repo, "c", "final")
    assert p.returncode == 0 and out["incremental"]["mode"] == "incremental", p.stdout + p.stderr
    assert (led["cases"].get(unit) or {}).get("m") == 0, led["cases"]
    assert unit in latest_anchor(git_repo)["nodes"], latest_anchor(git_repo)["nodes"]
    assert out["tests"]["delta"]["unknown"] == 0, out["tests"]["delta"]


def test_no_budget_keeps_output_unchanged(git_repo):
    # Given: 有分层文件但没有任何 budget，区域 hooks 里有一条睡 1 秒的用例
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {H_FILE: HOOKS_OK, SLOW_FILE: SLOW})

    # When: 跑 baseline；改动该区域一个测试文件后跑 final
    b = run_baseline(git_repo, d)
    change_and_commit(git_repo, H_FILE, HOOKS_OK + "\n\ndef test_more():\n    assert True\n", "touch region")
    out, p = final(git_repo, d)

    # Then: 两次都绿；输出里没有预算摘要，也没有任何 G13 / G14 文本
    bl = bl_of(d)
    assert b.returncode == 0 and p.returncode == 0, b.stdout + b.stderr + p.stdout + p.stderr
    assert "budget" not in bl["ledger"] and "budget" not in out["tests"], (bl["ledger"], out["tests"])
    everything = texts(bl.get("reasons"), bl.get("warnings"), out["failed"], out["warnings"])
    assert not any("G13" in t or "G14" in t for t in everything), everything
