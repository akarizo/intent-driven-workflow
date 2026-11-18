"""部件形态：已选区域的运行进账本、区域的新增超线判红；全机测试锁的预计耗时取全量秒数
（scenario: tier-budgets#parts-region-run-is-observed、#parts-region-new-slow-case-is-red、#lock-cap-uses-full-suite-seconds）。
骨架：strict xfail，断言是真实的；切片 S7 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, git, load_hook, run_hook, write
from final_helpers import change_and_commit, final
from test_ledger_baseline import read_ledger
from test_tiers_parts_gate import PY, setup_parts

PENDING = pytest.mark.xfail(strict=True, reason="change tier-budgets S7 未实现")

API_CMD = "%s -m pytest -q -p no:cacheprovider tests/api" % PY
SLOW = "import time\n\n\ndef test_slow():\n    time.sleep(1.0)\n"


def parts_with_api(repo, budget=None):
    """setup_parts 的仓库再给部件 py 加一个区域 api（pytest，在部件 root 下跑 tests/api），本 change 选上它。返回 change 目录。"""
    d = setup_parts(repo)
    path = repo / "openspec" / "test-tiers.json"
    tiers = json.loads(path.read_text(encoding="utf-8"))
    region = {"paths": ["svc/py/tests/api/**"], "covers": ["svc/py/app/**"], "cmd": API_CMD}
    if budget:
        region["budget"] = budget
    tiers["parts"]["py"]["regions"] = {"api": region}
    path.write_text(json.dumps(tiers, ensure_ascii=False), encoding="utf-8")
    plan = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    plan["gate"]["integration"] = ["api"]
    (d / "slices.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    write(repo / "svc" / "py" / "tests" / "api" / "test_api.py", "def test_api_ok():\n    assert True\n")
    commit_all(repo, "api region")
    return d


def run_baseline(repo, d):
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=repo)
    if git(repo, "status", "--porcelain"):  # 基线在写任何文件之前就退出时没有东西可提交
        commit_all(repo, "baseline")
    return p


def api_cases(led):
    return {cid: c for cid, c in ((led or {}).get("cases") or {}).items() if c.get("t") == "api"}


@PENDING
def test_parts_region_run_is_observed(git_repo):
    # Given: 部件形态：部件 py 有区域 api（pytest，在部件 root 下运行），本 change 选了它
    d = parts_with_api(git_repo)

    # When: 依次运行 baseline 与 final
    b = run_baseline(git_repo, d)
    out, p = final(git_repo, d)

    # Then: 两次都绿；两份账本里都有层为 api 的用例，带耗时、是本次实测
    assert b.returncode == 0 and p.returncode == 0, b.stdout + b.stderr + p.stdout + p.stderr
    for phase in ("baseline", "final"):
        cases = api_cases(read_ledger(git_repo, "c", phase))
        assert cases, (phase, read_ledger(git_repo, "c", phase))
        assert all(c["s"] is not None and c["m"] == 1 for c in cases.values()), (phase, cases)


@PENDING
def test_parts_region_new_slow_case_is_red(git_repo):
    # Given: 同样的仓库，区域 api 单条上限 0.4 秒，基线已跑且通过；之后提交了一条睡 1 秒的新区域用例
    d = parts_with_api(git_repo, budget={"case_sec": 0.4})
    b = run_baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    change_and_commit(git_repo, "svc/py/tests/api/test_slow.py", SLOW, "add slow api test")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 红在 G13，点名区域 api 与用例 test_slow
    assert p.returncode == 1, p.stdout + p.stderr
    assert any(f.startswith("G13 slow integration test") and "api" in f and "test_slow" in f
               for f in out["failed"]), out["failed"]


@PENDING
def test_lock_cap_uses_full_suite_seconds():
    # Given: 三份基线记录：增量且记着全量 400 秒；增量且没有全量耗时；全量 300 秒
    sg = load_hook("slice-gate")
    inc = {"mode": "incremental", "test": {"exit": 0, "sec": 25.0}, "full_suite_sec": 400}
    inc_unknown = {"mode": "incremental", "test": {"exit": 0, "sec": 25.0}, "full_suite_sec": None}
    full = {"mode": "full", "test": {"exit": 0, "sec": 300.0}, "full_suite_sec": 300.0}

    # When: 计算取锁时声明的预计耗时
    got = [sg._lock_expect_sec(inc, {}), sg._lock_expect_sec(inc_unknown, {}), sg._lock_expect_sec(full, {}),
           sg._lock_expect_sec(inc_unknown, {"full_suite_sec": 600})]

    # Then: 取全量耗时；增量基线的补跑秒数不算；都不知道时不声明
    assert got == [400, None, 300.0, 600], got
