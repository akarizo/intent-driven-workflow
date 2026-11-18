"""slice-gate.py final 写收口账本、报告测试变更（输出 JSON · 时间线 · delta.json · ship --markdown），部件形态同样落账
（scenario: test-ledger#final-full-reports-test-delta 等 6 条）。
骨架：strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import json
import re
import shutil
import subprocess
import sys

import pytest

from conftest import HOOKS, commit_all, run_hook
from final_helpers import (baseline, change_and_commit, final, gate_json, head, latest_anchor, make_repo,
                           timeline_rows)
from test_final_tests_only import TEST_A2, _nograph
from test_ledger_baseline import read_ledger
from test_tiers_parts_gate import setup_parts

PENDING = pytest.mark.xfail(strict=True, reason="change test-ledger S5 未实现")

NODE_A, NODE_NEW = "tests/test_a.py::test_a", "tests/test_new.py::test_new"
NEW_TEST = "import time\n\n\ndef test_new():\n    time.sleep(0.3)\n"


def with_new_test(repo):
    """change c：全量基线之后提交一个新测试文件（一条睡 0.3 秒的用例）。返回 change 目录。"""
    d = make_repo(repo)
    baseline(repo, d)
    change_and_commit(repo, "tests/test_new.py", NEW_TEST, "add test")
    return d


@PENDING
def test_final_full_reports_test_delta(git_repo):
    # Given: change c 有一次全量基线（3 条用例）；之后提交了一个新测试文件
    d = with_new_test(git_repo)

    # When: 运行 final --full
    out, p = final(git_repo, d, "--full")

    # Then: 输出带 tests 与对账结果；时间线多一段且不破坏现有解析；delta.json 对应当前 HEAD
    assert p.returncode == 0, p.stdout + p.stderr
    t = out["tests"]
    assert (t["cases"], t["measured"], t["why"]) == (4, 4, None), t
    assert (t["delta"]["added"], t["delta"]["removed"]) == (1, 0) and t["delta"]["added_sec"] >= 0.3, t["delta"]
    note = timeline_rows(d, "final")[-1]
    pieces = note.split(" · ")
    seg = next(i for i, x in enumerate(pieces) if x.startswith("用例 +1/-0（新增 "))
    assert any("测试 " in x for x in pieces[:seg]) and seg < len(pieces) - 1, note
    assert note.endswith(" ok"), note
    cost = json.loads(run_hook("flight-doctor", "cost", "--change-dir", str(d), "--json", cwd=git_repo).stdout)
    assert cost["final"]["full"] == 1, cost
    assert cost["final"]["full_sec"] == float(re.search(r"测试 ([\d.]+)s", note).group(1)), (cost, note)
    assert read_ledger(git_repo, "c", "delta")["commit"] == head(git_repo)


@PENDING
def test_incremental_final_marks_inherited_cases(git_repo):
    # Given: change c 有一次测到依赖图的全量基线；之后提交了一个新测试文件
    d = with_new_test(git_repo)

    # When: 运行 final（内建增量）
    out, p = final(git_repo, d)

    # Then: 新文件的用例是实测，没重跑的沿用且有耗时；锚点的 secs 覆盖全部用例
    assert p.returncode == 0 and out["incremental"]["mode"] == "incremental", p.stdout + p.stderr
    led = read_ledger(git_repo, "c", "final")
    assert (led["phase"], led["mode"]) == ("final", "incremental"), led
    assert led["cases"][NODE_NEW]["m"] == 1 and led["cases"][NODE_NEW]["s"] >= 0.3, led
    assert led["cases"][NODE_A]["m"] == 0 and led["cases"][NODE_A]["s"] is not None, led
    assert out["tests"]["inherited"] >= 1 and out["tests"]["complete"] is True, out["tests"]
    assert set(latest_anchor(git_repo)["secs"]) == set(led["cases"]) and len(led["cases"]) == 4


@PENDING
def test_tests_only_final_inherits_previous_final_ledger(git_repo):
    # Given: 依赖图测不到的仓库，final 已绿并留下收口账本；之后只提交了 tests/test_a.py 的改动（多一条用例）
    d = _nograph(git_repo)
    first = read_ledger(git_repo, "c", "final")
    change_and_commit(git_repo, "tests/test_a.py", TEST_A2)

    # When: 运行 final（无图退路，只重跑 tests/test_a.py）
    out, p = final(git_repo, d)
    led = read_ledger(git_repo, "c", "final")

    # Then: 账本记 tests-only、junit 形式、完整；被改文件的用例是实测，其余沿用上一份收口账本；对账新增 1 条
    assert p.returncode == 0 and out["incremental"]["source"] == "tests-only", p.stdout + p.stderr
    assert first is not None and (first["mode"], first["id_form"]) == ("full", "junit"), first
    assert (led["phase"], led["mode"], led["id_form"], led["complete"]) == ("final", "tests-only", "junit", True), led
    assert set(led["cases"]) == {"tests.test_a::test_a", "tests.test_a::test_a_again", "tests.test_b::test_b",
                                 "tests.test_c::test_c"}, led
    assert led["cases"]["tests.test_a::test_a"]["m"] == 1 and led["cases"]["tests.test_a::test_a_again"]["m"] == 1
    for cid in ("tests.test_b::test_b", "tests.test_c::test_c"):
        assert led["cases"][cid] == dict(first["cases"][cid], m=0), (cid, led["cases"][cid])
    assert (out["tests"]["delta"]["added"], out["tests"]["delta"]["removed"]) == (1, 0), out["tests"]


@PENDING
def test_ship_markdown_appends_test_delta_when_fresh(git_repo):
    # Given: change c 的 final 刚跑完且通过，留下了同一 commit 的 delta.json
    d = with_new_test(git_repo)
    out, p = final(git_repo, d)
    assert p.returncode == 0, p.stdout + p.stderr

    # When: ship --markdown；把 delta.json 的 commit 改掉后再来一次；再取 JSON 输出
    p1 = run_hook("slice-gate", "ship", "--change-dir", str(d), "--markdown", cwd=git_repo)
    path = git_repo / ".git" / "flight-ledger" / "c" / "delta.json"
    stale = dict(json.loads(path.read_text(encoding="utf-8")), commit="0" * 40)
    path.write_text(json.dumps(stale, ensure_ascii=False) + "\n", encoding="utf-8")
    p2 = run_hook("slice-gate", "ship", "--change-dir", str(d), "--markdown", cwd=git_repo)
    pj = run_hook("slice-gate", "ship", "--change-dir", str(d), cwd=git_repo)

    # Then: 对得上才附「测试变更」；退出码与 JSON 的键不变
    assert any(l.startswith("## 测试变更") for l in p1.stdout.splitlines()), p1.stdout
    assert "测试变更" not in p2.stdout, p2.stdout
    assert p1.returncode == p2.returncode == pj.returncode
    assert set(json.loads(pj.stdout)) == {"ready", "commit", "reasons", "blocked"}, pj.stdout


@PENDING
def test_ledger_failure_does_not_fail_final(git_repo, tmp_path):
    # Given: 一份不含 test-ledger.py 的 hooks 目录副本；change c 已用它跑过 baseline，之后提交了一个新测试文件
    d = make_repo(git_repo)
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("test-ledger.py", "__pycache__"))
    gate = [sys.executable, str(hooks / "slice-gate.py")]
    b = subprocess.run(gate + ["baseline", "--change-dir", str(d)], cwd=git_repo, capture_output=True, text=True)
    assert b.returncode == 0, b.stdout + b.stderr
    commit_all(git_repo, "baseline")
    change_and_commit(git_repo, "tests/test_new.py", NEW_TEST, "add test")

    # When: 用副本里的 slice-gate.py 运行 final
    p = subprocess.run(gate + ["final", "--change-dir", str(d)], cwd=git_repo, capture_output=True, text=True)

    # Then: final 照常通过，只多一条警告；没有 tests，时间线没有「用例 +」片段
    out = gate_json(p)
    assert p.returncode == 0 and out["ok"] is True and out["failed"] == [], p.stdout + p.stderr
    assert any(w.startswith("测试账本未写") for w in out["warnings"]), out["warnings"]
    assert "tests" not in out
    assert "用例 +" not in timeline_rows(d, "final")[-1]


@PENDING
def test_parts_runs_write_ledger(git_repo):
    # Given: 部件形态：部件 py（pytest）与部件 sh（脚本往 $FLIGHT_JUNIT 写报告）
    d = setup_parts(git_repo)

    # When: 依次运行 baseline 与 final
    b = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo)
    assert b.returncode == 0, b.stdout + b.stderr
    commit_all(git_repo, "baseline")
    p = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=git_repo)

    # Then: 两份账本都是 parts；部件 sh 的用例带耗时与层；没有新增与删除
    assert p.returncode == 0, p.stdout + p.stderr
    lb, lf = read_ledger(git_repo, "c", "baseline"), read_ledger(git_repo, "c", "final")
    assert lb is not None and lf is not None and lb["mode"] == lf["mode"] == "parts", (lb, lf)
    assert lf["cases"]["sh::sh::TestS"] == {"o": None, "s": 0.01, "t": "unit", "m": 1}, lf
    assert lf["cases"]["svc/py/tests/unit/test_p.py::test_ok"]["t"] == "unit", lf
    delta = json.loads(p.stdout)["tests"]["delta"]
    assert (delta["added"], delta["removed"]) == (0, 0), delta
