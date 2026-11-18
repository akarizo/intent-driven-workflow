"""slice-gate.py 的逐用例采集：依赖图插件记耗时、junit 兜底、增量重跑恒取耗时、部件上报
（scenario: test-ledger#deps-run-records-case-seconds 等 4 条）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import pytest

from conftest import load_hook
from final_helpers import PY, PYTEST, TEST_CMD, make_repo
from test_tiers_parts_gate import setup_parts

PENDING = pytest.mark.xfail(strict=True, reason="change test-ledger S2 未实现")

SLOW = "import time\n\n\ndef test_slow():\n    time.sleep(0.3)\n"
# 只把 --junitxml 传给 pytest、丢掉 -p 插件参数的包装脚本（与 tests/test_runner_contract.py 的 DROPPING 同形）
DROPPING = """#!/usr/bin/env bash
J=$(printf '%%s\\n' $PYTEST_ADDOPTS | grep '^--junitxml=' || true)
unset PYTEST_ADDOPTS
exec %s -m pytest -q -p no:cacheprovider $J tests
""" % PY
NODE_A = "tests/test_a.py::test_a"


@PENDING
def test_deps_run_records_case_seconds(git_repo):
    # Given: gate.test 是直接的 pytest 调用，其中一条用例睡 0.3 秒
    make_repo(git_repo, extra={"tests/test_slow.py": SLOW})
    sg = load_hook("slice-gate")
    before = len(sg.ledger_observations())

    # When: 带依赖图跑一次
    tg = sg.run_test_gate(TEST_CMD, str(git_repo), deps=True)

    # Then: 依赖图多出逐用例耗时，nodes 不变；观测表多一条 nodeid 形式的观测
    deps = tg["deps"]
    assert deps is not None, tg["deps_why"]
    assert deps["nodes"] == {NODE_A: "PASSED", "tests/test_b.py::test_b": "PASSED", "tests/test_c.py::test_c": "PASSED",
                             "tests/test_slow.py::test_slow": "PASSED"}, deps["nodes"]
    assert set(deps["secs"]) == set(deps["nodes"]), deps["secs"]
    assert deps["secs"]["tests/test_slow.py::test_slow"] >= 0.3, deps["secs"]
    new = sg.ledger_observations()[before:]
    assert len(new) == 1 and new[0]["form"] == "nodeid", new
    assert set(new[0]["outcomes"]) == set(new[0]["secs"]) == set(deps["nodes"]), new


@PENDING
def test_junit_fallback_when_deps_unmeasured(git_repo):
    # Given: gate.test 是只转发 --junitxml、丢掉 -p 参数的包装脚本
    make_repo(git_repo, extra={"tools/gate.sh": DROPPING}, gate_extra={"test": "bash tools/gate.sh"})
    sg = load_hook("slice-gate")
    before = len(sg.ledger_observations())

    # When: 带依赖图跑一次
    tg = sg.run_test_gate("bash tools/gate.sh", str(git_repo), deps=True)

    # Then: 依赖图没测到；观测是 junit 形式，每条都有结局与耗时
    assert tg["deps"] is None and tg["deps_kind"] == "plugins-dropped", (tg["deps_kind"], tg["out"])
    new = sg.ledger_observations()[before:]
    assert len(new) == 1 and new[0]["form"] == "junit", new
    assert new[0]["outcomes"] == {"tests.test_a::test_a": "passed", "tests.test_b::test_b": "passed",
                                  "tests.test_c::test_c": "passed"}, new
    assert set(new[0]["secs"]) == set(new[0]["outcomes"]), new
    assert all(isinstance(v, float) and v >= 0 for v in new[0]["secs"].values()), new


@PENDING
def test_incremental_rerun_records_seconds(git_repo):
    # Given: 被测仓库有多个测试文件
    make_repo(git_repo)
    sg = load_hook("slice-gate")
    before = len(sg.ledger_observations())

    # When: 不传 durations 重跑一个文件；再传 durations 重跑一次
    outcomes, rc, _, timed_out = sg._pytest_outcomes(str(git_repo), ["tests/test_a.py"], {"pytest": PYTEST})
    first = sg.ledger_observations()[before:]
    durations = {}
    sg._pytest_outcomes(str(git_repo), ["tests/test_a.py"], {"pytest": PYTEST}, durations=durations)

    # Then: 返回值不变；两次各多一条只含被重跑用例的观测，都带耗时；durations 照旧被填
    assert (outcomes, rc, timed_out) == ([(NODE_A, "PASSED")], 0, False)
    assert len(first) == 1 and first[0]["form"] == "nodeid", first
    assert first[0]["outcomes"] == {NODE_A: "PASSED"} and set(first[0]["secs"]) == {NODE_A}, first
    assert first[0]["secs"][NODE_A] >= 0
    assert set(durations) == {NODE_A} and durations[NODE_A] >= 0, durations
    assert len(sg.ledger_observations()) == before + 2


@PENDING
def test_part_adapter_run_is_observed(git_repo):
    # Given: 部件形态的被测仓库，部件 sh 的单元命令是往 $FLIGHT_JUNIT 写报告的脚本
    d = setup_parts(git_repo)
    sg = load_hook("slice-gate")
    tiers, errors = sg._load_tiers(str(d))
    assert not errors, errors
    before = len(sg.ledger_observations())

    # When: 运行部件 sh 的单元层
    res = sg.run_part(str(git_repo), "sh", tiers["parts"]["sh"])

    # Then: 返回值不变；观测表多一条带 tier = unit 的观测，secs 等于返回值的 secs，结局未知
    assert res["rc"] == 0 and res["secs"] == {"sh::sh::TestS": 0.01}, res
    new = sg.ledger_observations()[before:]
    assert new == [{"form": "nodeid", "outcomes": {}, "secs": {"sh::sh::TestS": 0.01}, "tier": "unit"}], new
