"""pytest-cov 覆盖率未达标时全量测试不可度量、按退出码判红（摘自原仓 #60；scenario: gate-full-suite-baseline#*-on-coverage-failure）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；workflow-edition S2 实现后去掉标记即解锁。
COVERAGE_FAIL 按 pytest-cov 7.1.0 源码（pytest_cov/plugin.py）的做法构造：测试跑完后打印两行标记，并让 session.testsfailed 加 1。"""
import json

import pytest

from conftest import commit_all, write
from test_slice_gate_final import OLD_RED, PYTEST, _baseline, _final, _repo

COVERAGE_FAIL = (
    "import pytest\n\n\n"
    "@pytest.hookimpl(hookwrapper=True)\n"
    "def pytest_runtestloop(session):\n"
    "    yield\n"
    "    tr = session.config.pluginmanager.getplugin('terminalreporter')\n"
    "    tr.write('\\nERROR: Coverage failure: total of 10 is less than fail-under=90\\n')\n"
    "    session.testsfailed += 1\n\n\n"
    "def pytest_terminal_summary(terminalreporter):\n"
    "    terminalreporter.write('FAIL Required test coverage of 90% not reached. Total coverage: 10.00%\\n')\n"
)


def test_final_red_on_coverage_failure(git_repo):
    # Given: gate.test 为 pytest；基线已生成（test_old 预存红，其余通过）；之后提交了按 pytest-cov 做法报覆盖率未达标的 tests/conftest.py
    change = _repo(git_repo, PYTEST, files={"tests/test_old.py": OLD_RED})
    assert _baseline(git_repo, change).returncode == 0
    write(git_repo / "tests" / "conftest.py", COVERAGE_FAIL)
    commit_all(git_repo, "coverage fail-under")

    # When: 运行 slice-gate.py final
    out = _final(git_repo, change)

    # Then: ok 为 false；failed 有一项以「G2 test」开头，含「按退出码判」与「覆盖率」
    assert out["ok"] is False, out
    assert any(f.startswith("G2 test") and "按退出码判" in f and "覆盖率" in f for f in out["failed"]), out["failed"]


def test_baseline_red_on_coverage_failure(git_repo):
    # Given: gate.test 为 pytest；test_old 失败，且 tests/conftest.py 按 pytest-cov 做法报覆盖率未达标
    change = _repo(git_repo, PYTEST, files={"tests/test_old.py": OLD_RED, "tests/conftest.py": COVERAGE_FAIL})

    # When: 运行 slice-gate.py baseline
    p = _baseline(git_repo, change)

    # Then: 退出 1；reasons 有一项含「覆盖率」与 --no-cov
    assert p.returncode == 1, p.stdout + p.stderr
    bl = json.loads((change / "gate-baseline.json").read_text(encoding="utf-8"))
    assert any("覆盖率" in r and "--no-cov" in r for r in bl["reasons"]), bl["reasons"]
