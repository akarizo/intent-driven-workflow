"""slice-gate final 先判 G7、gate.test 按基线逐条差分（摘自原仓 #45；scenario: gate-full-suite-baseline#final-* / baseline-records-* / diff-* / non-pytest-* / exit-1-*）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；workflow-edition S2 实现后去掉标记即解锁。"""
import json
import shlex
import sys

import pytest

from conftest import commit_all, run_hook, write
from test_slice_gate import plan, slice_, write_plan

PYTEST = "%s -m pytest -q tests" % shlex.quote(sys.executable)
PASSING = "def test_adds():\n    assert 1 + 1 == 2\n"
STILL_XFAIL = (
    "import pytest\n\n\n"
    "@pytest.mark.xfail(strict=True, reason=\"pending\")\n"
    "def test_adds():\n    assert 1 + 1 == 3\n"
)
ORDERED = (
    "def test_adds():\n"
    "    with open('order.log', 'a', encoding='utf-8') as f:\n"
    "        f.write('g7\\n')\n"
    "    assert 1 + 1 == 2\n"
)
OLD_RED = "def test_old():\n    assert False\n"
NEW_RED = "def test_new():\n    assert False\n"


def _repo(git_repo, gate_test, cap_test=PASSING, lint=None, files=None):
    """单片计划：cap#adds → tests/test_cap.py::test_adds；gate.test / gate.lint 可注入；返回 change 目录。"""
    change = git_repo / "openspec" / "changes" / "c"
    data = plan(
        [slice_("S1", ["src/**", "tests/**"], scenarios=["cap#adds"])],
        gate={"test": gate_test, "lint": lint, "typecheck": None, "full_suite_sec": None},
        scenario_tests={"cap#adds": "tests/test_cap.py::test_adds"},
    )
    write_plan(change, data)
    write(git_repo / "tests" / "test_cap.py", cap_test)
    for rel, text in (files or {}).items():
        write(git_repo / rel, text)
    commit_all(git_repo, "artifacts")
    return change


def _final(git_repo, change):
    p = run_hook("slice-gate", "final", "--change-dir", str(change), cwd=git_repo)
    return json.loads(p.stdout)


def _baseline(git_repo, change):
    return run_hook("slice-gate", "baseline", "--change-dir", str(change), cwd=git_repo)


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_final_skips_full_suite_when_g7_red(git_repo):
    # Given: cap#adds 的测试仍带 strict xfail；gate.test 运行时写下 ran-g2，gate.lint 运行时写下 ran-lint
    change = _repo(git_repo, "touch ran-g2", cap_test=STILL_XFAIL, lint="touch ran-lint")

    # When: 运行 slice-gate.py final
    out = _final(git_repo, change)

    # Then: ok 为 false 且 failed 含点名 cap#adds 的 G7 项；全量没跑、lint 照跑；warnings 含「G2 全量未跑」
    assert out["ok"] is False
    assert any(f.startswith("G7") and "cap#adds" in f for f in out["failed"]), out["failed"]
    assert not (git_repo / "ran-g2").exists()
    assert (git_repo / "ran-lint").exists()
    assert any("G2 全量未跑" in w for w in out["warnings"]), out["warnings"]


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_final_runs_g7_before_full_suite(git_repo):
    # Given: cap#adds 的测试通过、运行时向 order.log 追加 g7；gate.test 运行时向 order.log 追加 g2
    change = _repo(git_repo, "echo g2 >> order.log", cap_test=ORDERED)

    # When: 运行 slice-gate.py final
    out = _final(git_repo, change)

    # Then: ok 为 true；order.log 依次为 g7、g2
    assert out["ok"] is True, out
    assert (git_repo / "order.log").read_text(encoding="utf-8").split() == ["g7", "g2"]


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_baseline_records_preexisting_failures(git_repo):
    # Given: gate.test 为 pytest；tests 里 test_old 失败、其余通过
    change = _repo(git_repo, PYTEST, files={"tests/test_old.py": OLD_RED})

    # When: 运行 slice-gate.py baseline
    p = _baseline(git_repo, change)

    # Then: 退出 0；gate-baseline.json 的 ok 为 true，test.failed 恰 1 条且含 test_old；warnings 含「预存红」
    assert p.returncode == 0, p.stdout + p.stderr
    bl = json.loads((change / "gate-baseline.json").read_text(encoding="utf-8"))
    assert bl["ok"] is True
    assert len(bl["test"]["failed"]) == 1 and "test_old" in bl["test"]["failed"][0], bl["test"]
    assert any("预存红" in w for w in bl.get("warnings") or []), bl.get("warnings")


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_final_excludes_baseline_failures(git_repo):
    # Given: 上述基线已生成；test_old 仍失败，cap#adds 的测试通过
    change = _repo(git_repo, PYTEST, files={"tests/test_old.py": OLD_RED})
    assert _baseline(git_repo, change).returncode == 0

    # When: 运行 slice-gate.py final
    out = _final(git_repo, change)

    # Then: ok 为 true，warnings 含「按基线排除」
    assert out["ok"] is True, out
    assert any("按基线排除" in w for w in out["warnings"]), out["warnings"]


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_final_flags_new_failures(git_repo):
    # Given: 上述基线已生成；又新增一个失败的 test_new
    change = _repo(git_repo, PYTEST, files={"tests/test_old.py": OLD_RED})
    assert _baseline(git_repo, change).returncode == 0
    write(git_repo / "tests" / "test_new.py", NEW_RED)

    # When: 运行 slice-gate.py final
    out = _final(git_repo, change)

    # Then: ok 为 false；failed 有一项以「G2 test」开头、含「新增」与 test_new、不含 test_old
    assert out["ok"] is False
    g2 = [f for f in out["failed"] if f.startswith("G2 test")]
    assert len(g2) == 1, out["failed"]
    assert "新增" in g2[0] and "test_new" in g2[0] and "test_old" not in g2[0], g2[0]


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_diff_falls_back_when_unmeasurable(git_repo):
    # Given: gate.test 先后运行两次 pytest（输出两行汇总），其中有失败
    change = _repo(git_repo, "%s; %s" % (PYTEST, PYTEST), files={"tests/test_old.py": OLD_RED})

    # When: 运行 slice-gate.py baseline
    p = _baseline(git_repo, change)

    # Then: 退出 1；reasons 有一项含「按退出码」与「汇总行」
    assert p.returncode == 1, p.stdout + p.stderr
    bl = json.loads((change / "gate-baseline.json").read_text(encoding="utf-8"))
    assert any("按退出码" in r and "汇总行" in r for r in bl["reasons"]), bl["reasons"]


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_non_pytest_gate_keeps_exit_code(git_repo):
    # Given: gate.test 为 sh -c 'exit 1'
    change = _repo(git_repo, "sh -c 'exit 1'")

    # When: 运行 slice-gate.py baseline
    p = _baseline(git_repo, change)

    # Then: 退出 1；reasons 有一项含「exit 1」与「按退出码」
    assert p.returncode == 1, p.stdout + p.stderr
    bl = json.loads((change / "gate-baseline.json").read_text(encoding="utf-8"))
    assert any("exit 1" in r and "按退出码" in r for r in bl["reasons"]), bl["reasons"]


FORCE_EXIT_1 = (
    "def pytest_sessionfinish(session, exitstatus):\n"
    "    session.exitstatus = 1\n"
)


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_exit_1_without_failures_is_red(git_repo):
    # Given: gate.test 为 pytest；全部用例通过，但 tests/conftest.py 在 sessionfinish 把 exitstatus 设成 1
    change = _repo(git_repo, PYTEST, files={"tests/conftest.py": FORCE_EXIT_1})

    # When: 运行 slice-gate.py final
    out = _final(git_repo, change)

    # Then: ok 为 false；failed 有一项以「G2 test」开头且含「按退出码判」
    assert out["ok"] is False, out
    assert any(f.startswith("G2 test") and "按退出码判" in f for f in out["failed"]), out["failed"]
