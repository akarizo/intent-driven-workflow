"""部件形态下 baseline / final / preflight 逐部件运行与对账、tier_sec.parts
（scenario: test-tiers-polyglot#baseline-runs-each-part-and-reports-part-seconds … #preflight-stale-when-part-cmd-changed）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。
被测仓库里没有 .claude/hooks/test-tiers.py：门禁若执行了 gate.test（驱动命令）就会红。"""
import json
import os
import shlex
import sys

import pytest

from conftest import commit_all, run_hook, write

PY = shlex.quote(sys.executable)
DRIVER = "python3 .claude/hooks/test-tiers.py run unit"
PY_UNIT = "%s -m pytest -q -p no:cacheprovider tests/unit" % PY
SH_UNIT = "%s run.py" % PY
PURE = "def test_ok():\n    assert 1 + 1 == 2\n"

# 部件 sh 的单元命令：把当前目录写到仓外标记文件，往 $FLIGHT_JUNIT 写一个用例，退出码取 rc.txt（缺省 0）
SH_RUN = '''import os, sys
open(%r, "w").write(os.getcwd())
open(os.environ["FLIGHT_JUNIT"], "w").write(
    '<testsuite name="s"><testcase classname="sh" name="TestS" time="0.01"/></testsuite>')
sys.exit(int(open("rc.txt").read()) if os.path.exists("rc.txt") else 0)
'''


def setup_parts(repo, py_tests=PURE):
    """被测仓库：部件 py（root svc/py，pytest）与部件 sh（root svc/sh，脚本写 junit）；change c 单片 S1，
    gate.test = 驱动命令，gate.pytest = 本解释器的 pytest。返回 change 目录。"""
    write(repo / "svc" / "py" / "pytest.ini", "[pytest]\n")
    write(repo / "svc" / "py" / "tests" / "unit" / "test_p.py", py_tests)
    write(repo / "svc" / "sh" / "run.py", SH_RUN % str(repo.parent / "sh-cwd.txt"))
    tiers = {
        "parts": {
            "py": {"root": "svc/py", "test_files": ["svc/py/tests/**/test_*.py"],
                   "unit": {"paths": ["svc/py/tests/unit/**"], "cmd": PY_UNIT}},
            "sh": {"root": "svc/sh", "test_files": ["svc/sh/**/*_test.sh"],
                   "unit": {"paths": ["svc/sh/**"], "cmd": SH_UNIT}},
        },
        "slow_allow": {},
    }
    write(repo / "openspec" / "test-tiers.json", json.dumps(tiers, ensure_ascii=False))
    d = repo / "openspec" / "changes" / "c"
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "slices" / "S1.md", "# S1\n")
    data = {
        "version": 1, "change": "c",
        "gate": {"test": DRIVER, "pytest": "%s -m pytest" % PY, "lint": None, "typecheck": None},
        "slices": [{"id": "S1", "title": "S1", "owns": ["svc/py/app.py"], "deps": [], "verify": "true",
                    "scenarios": [], "packet": "slices/S1.md"}],
        "scenario_tests": {},
    }
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return d


def baseline(repo, d):
    return run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=repo)


def read_bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def final_json(repo, d):
    p = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=repo)
    return json.loads(p.stdout)


def change_sh_cmd(repo):
    """改分层文件里部件 sh 的 unit.cmd 并提交。"""
    path = repo / "openspec" / "test-tiers.json"
    t = json.loads(path.read_text(encoding="utf-8"))
    t["parts"]["sh"]["unit"]["cmd"] = SH_UNIT + " --again"
    path.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    commit_all(repo, "change sh cmd")


# ---------------------------------------------------------------- baseline


def test_baseline_runs_each_part_and_reports_part_seconds(git_repo):
    # Given: 部件 py（单元层全绿且纯）与 sh；gate.test 是驱动命令（被测仓库里没有 test-tiers.py）
    d = setup_parts(git_repo)

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 基线绿；test.parts 恰有 py 与 sh，cmd 等于 unit.cmd、exit 0；sh 在 svc/sh 下运行；tier_sec.parts 两个部件各有 unit
    bl = read_bl(d)
    assert bl["ok"] is True, (p.stdout, p.stderr, bl.get("reasons"))
    parts = bl["test"]["parts"]
    assert set(parts) == {"py", "sh"}, parts
    assert parts["py"]["cmd"] == PY_UNIT and parts["sh"]["cmd"] == SH_UNIT, parts
    assert parts["py"]["exit"] == 0 and parts["sh"]["exit"] == 0, parts
    cwd = (git_repo.parent / "sh-cwd.txt").read_text()
    assert os.path.realpath(cwd) == os.path.realpath(str(git_repo / "svc" / "sh"))
    ts = bl["tier_sec"]["parts"]
    assert set(ts) == {"py", "sh"} and all("unit" in v for v in ts.values()), ts


def test_baseline_records_part_preexisting_red(git_repo):
    # Given: 部件 py 单元层有一个失败用例 test_old
    d = setup_parts(git_repo, py_tests=PURE + "\n\ndef test_old():\n    assert False\n")

    # When: 运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: 基线绿；test.parts.py.failed 含 test_old
    bl = read_bl(d)
    assert bl["ok"] is True, bl.get("reasons")
    assert "test_old" in json.dumps(bl["test"]["parts"]["py"].get("failed")), bl["test"]

    # When: 让 sh 的单元命令以 1 退出后重跑 baseline
    write(git_repo / "svc" / "sh" / "rc.txt", "1")
    commit_all(git_repo, "sh red")
    baseline(git_repo, d)

    # Then: 基线红；reasons 有一条含「部件 sh」
    bl = read_bl(d)
    assert bl["ok"] is False, bl
    assert any("部件 sh" in r for r in bl["reasons"]), bl["reasons"]


def test_baseline_red_on_impure_part_unit(git_repo):
    # Given: 部件 py 单元层有一个读文件的用例
    impure = PURE + "\n\ndef test_io():\n    with open(__file__, encoding='utf-8') as f:\n        assert f.read()\n"
    d = setup_parts(git_repo, py_tests=impure)

    # When: 运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: 基线红；reasons 有一条 G11，含「部件 py」
    bl = read_bl(d)
    assert bl["ok"] is False, bl
    assert any(r.startswith("G11") and "部件 py" in r for r in bl["reasons"]), bl["reasons"]


# ---------------------------------------------------------------- final


def test_final_diffs_each_part(git_repo):
    # Given: 基线记录了 py 的预存红 test_old；之后 py 新增失败用例 test_new 并提交
    old = PURE + "\n\ndef test_old():\n    assert False\n"
    d = setup_parts(git_repo, py_tests=old)
    baseline(git_repo, d)
    assert read_bl(d)["ok"] is True
    write(git_repo / "svc" / "py" / "tests" / "unit" / "test_p.py", old + "\n\ndef test_new():\n    assert False\n")
    commit_all(git_repo, "new red")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: 有一条 G2 part py 点名 test_new、不点名 test_old；增量模式为 full，full_why 含「多部件」
    g2 = [f for f in out["failed"] if f.startswith("G2 part py")]
    assert len(g2) == 1 and "test_new" in g2[0] and "test_old" not in g2[0], out["failed"]
    assert out["incremental"]["mode"] == "full" and "多部件" in out["incremental"]["full_why"], out["incremental"]


def test_final_red_when_part_record_stale(git_repo):
    # Given: 基线建立后，部件 sh 的 unit.cmd 被改动并提交
    d = setup_parts(git_repo)
    baseline(git_repo, d)
    assert read_bl(d)["ok"] is True
    change_sh_cmd(git_repo)

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: 有一条 G2 part sh，含「重跑 baseline」
    assert any(f.startswith("G2 part sh") and "重跑 baseline" in f for f in out["failed"]), out["failed"]


# ---------------------------------------------------------------- preflight


def test_preflight_stale_when_part_cmd_changed(git_repo):
    # Given: 基线建立后，部件 sh 的 unit.cmd 被改动并提交
    d = setup_parts(git_repo)
    baseline(git_repo, d)
    assert read_bl(d)["ok"] is True
    change_sh_cmd(git_repo)

    # When: 运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；stderr 含「基线过期」与「部件 sh」
    assert p.returncode != 0, p.stdout
    assert "基线过期" in p.stderr and "部件 sh" in p.stderr, p.stderr
