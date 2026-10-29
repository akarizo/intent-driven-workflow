"""部件运行器（root 下运行、JUnit 契约、探针适配器契约、内置探针顶层 id）与逐部件 G10 / G11 判定
（scenario: test-tiers-polyglot#part-runs-in-root-with-junit … #part-g11-and-unmeasurable-warnings）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现 run_part / part_tier_verdicts 后去掉标记即解锁。"""
import os
import shlex
import sys
import time

import pytest

from conftest import load_hook, write

XF = pytest.mark.xfail(strict=True, reason="S2 尚未实现")
PY = shlex.quote(sys.executable)

# 在当前目录写 cwd.txt，再往 $FLIGHT_JUNIT 写两个 testcase（一个无 file 属性、一个有）
RUN_JUNIT = '''import os
open("cwd.txt", "w").write(os.getcwd())
open(os.environ["FLIGHT_JUNIT"], "w").write(
    '<testsuites><testsuite name="s">'
    '<testcase classname="pkg" name="TestA" time="0.5"/>'
    '<testcase classname="pkg" file="a_test.go" name="TestB" time="0.25"/>'
    '</testsuite></testsuites>')
'''
# 不写 $FLIGHT_JUNIT，只在固定位置 reports/new.xml 写报告
RUN_REPORT = '''import os
os.makedirs("reports", exist_ok=True)
open("reports/new.xml", "w").write(
    '<testsuite name="s"><testcase classname="pkg" name="TestNew" time="0.3"/></testsuite>')
'''
# 适配器：执行 $FLIGHT_UNIT_CMD，按内置探针格式写两条记录，退出码沿用测试命令
ADAPTER = '''import json, os, subprocess, sys
rc = subprocess.call(os.environ["FLIGHT_UNIT_CMD"], shell=True)
with open(os.environ["FLIGHT_TIER_OUT"], "a", encoding="utf-8") as f:
    for rec in ({"probe": "start"},
                {"nodeid": "a_test.go::TestA", "sec": 0.1, "hits": {}},
                {"nodeid": "b_test.go::TestB", "sec": 0.2, "hits": {"文件": "open x"}}):
        f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
sys.exit(rc)
'''


def sg():
    return load_hook("slice-gate")


def sh_part(**unit):
    """部件 sh（root svc/sh）；unit 字段由关键字参数给出。"""
    u = {"paths": ["svc/sh/**/*_test.go"]}
    u.update(unit)
    return {"root": "svc/sh", "unit": u}


# ---------------------------------------------------------------- 运行器


@XF
def test_part_runs_in_root_with_junit(git_repo):
    # Given: 部件 sh 的单元命令把当前目录写进 cwd.txt，并往 $FLIGHT_JUNIT 写 TestA（无 file）与 TestB（file=a_test.go）
    write(git_repo / "svc" / "sh" / "run.py", RUN_JUNIT)
    part = sh_part(cmd="%s run.py" % PY)

    # When: 部件运行器运行该部件
    res = sg().run_part(str(git_repo), "sh", part)

    # Then: 退出 0；命令在 svc/sh 下运行；secs 恰为两个换成顶层坐标的 id
    assert res["rc"] == 0, res["out"]
    cwd = (git_repo / "svc" / "sh" / "cwd.txt").read_text()
    assert os.path.realpath(cwd) == os.path.realpath(str(git_repo / "svc" / "sh"))
    assert res["secs"] == {"sh::pkg::TestA": 0.5, "svc/sh/a_test.go::TestB": 0.25}, res["secs"]


@XF
def test_part_reads_fresh_junit_glob_only(git_repo):
    # Given: unit.junit 是 reports/*.xml；reports/old.xml 是一天前的旧报告（含 TestOld）；单元命令只写 reports/new.xml
    old = write(git_repo / "svc" / "sh" / "reports" / "old.xml",
                '<testsuite name="s"><testcase classname="pkg" name="TestOld" time="9.9"/></testsuite>')
    day_ago = time.time() - 86400
    os.utime(str(old), (day_ago, day_ago))
    write(git_repo / "svc" / "sh" / "run.py", RUN_REPORT)
    part = sh_part(cmd="%s run.py" % PY, junit="reports/*.xml")

    # When: 部件运行器运行该部件
    res = sg().run_part(str(git_repo), "sh", part)

    # Then: secs 含 TestNew，不含 TestOld
    secs = res["secs"] or {}
    assert any(k.endswith("TestNew") for k in secs), secs
    assert not any("TestOld" in k for k in secs), secs


@XF
def test_adapter_wraps_unit_cmd(git_repo):
    # Given: 部件 sh 写了 probe.cmd；适配器执行 $FLIGHT_UNIT_CMD（以 3 退出）并写 TestA（无触碰）、TestB（文件触碰）
    write(git_repo / "svc" / "sh" / "adapter.py", ADAPTER)
    probe = {"cmd": "%s adapter.py" % PY, "canary": "true", "canary_files": ["svc/sh/canary/**"],
             "sha": {}, "checked": "2026-10-29T00:00:00+00:00"}
    part = sh_part(cmd="%s -c 'import sys; sys.exit(3)'" % PY, probe=probe)

    # When: 部件运行器运行该部件
    res = sg().run_part(str(git_repo), "sh", part)

    # Then: 退出 3；探针 id 补上 root 前缀，TestB 带文件触碰；secs 取自探针记录
    assert res["rc"] == 3, res["out"]
    a, b = "svc/sh/a_test.go::TestA", "svc/sh/b_test.go::TestB"
    assert set(res["probe"] or {}) == {a, b}, res["probe"]
    assert "文件" in res["probe"][b]["hits"] and not res["probe"][a]["hits"], res["probe"]
    assert res["secs"] == {a: 0.1, b: 0.2}, res["secs"]


@XF
def test_builtin_probe_ids_from_toplevel(git_repo):
    # Given: 部件 py（root svc/py，pytest.ini 在 svc/py，没写 probe）；tests/unit/test_p.py 有纯函数 test_pure 与读文件的 test_touch
    write(git_repo / "svc" / "py" / "pytest.ini", "[pytest]\n")
    write(git_repo / "svc" / "py" / "tests" / "unit" / "test_p.py", """
        def test_pure():
            assert 1 + 1 == 2


        def test_touch():
            with open(__file__, encoding="utf-8") as f:
                assert f.read()
        """)
    part = {"root": "svc/py", "unit": {"paths": ["svc/py/tests/unit/**"],
                                       "cmd": "%s -m pytest -q -p no:cacheprovider tests/unit" % PY}}

    # When: 部件运行器带探针运行该部件
    res = sg().run_part(str(git_repo), "py", part)

    # Then: 探针 id 相对 git 顶层；只有 test_touch 带文件触碰
    pure, touch = "svc/py/tests/unit/test_p.py::test_pure", "svc/py/tests/unit/test_p.py::test_touch"
    assert set(res["probe"] or {}) == {pure, touch}, (res["probe"], res["probe_why"], res["out"])
    assert not res["probe"][pure]["hits"], res["probe"]
    assert "文件" in res["probe"][touch]["hits"], res["probe"]


# ---------------------------------------------------------------- 逐部件 G10 / G11（纯函数）


@XF
def test_part_g10_confirmed_by_rerun():
    # Given: 部件 go 没有探针结果；junit 耗时 TestSlow 3.4、TestFast 0.1、TestFlaky 3.1、TestOk 3.2；
    #        整部件重跑 TestSlow 3.5、TestFlaky 0.4、TestOk 3.3；slow_allow 含 TestOk
    slow, fast = "svc/go/a_test.go::TestSlow", "svc/go/a_test.go::TestFast"
    flaky, ok = "svc/go/b_test.go::TestFlaky", "svc/go/b_test.go::TestOk"
    res = {"probe": None, "probe_why": "没有探针输出（不是 pytest？）",
           "secs": {slow: 3.4, fast: 0.1, flaky: 3.1, ok: 3.2}, "secs_why": None}
    rerun = {slow: 3.5, flaky: 0.4, ok: 3.3}
    allow = {ok: {"reason": "读大样本", "approved": "2026-10-29T00:00:00+00:00 · 放行 TestOk"}}

    # When: 判定该部件
    failed, warnings = sg().part_tier_verdicts("go", res, rerun, allow)

    # Then: 失败恰一条 G10，点名 TestSlow、含「部件 go」；警告有 TestOk 的已放行 G10 与「G11 不可度量：部件 go」；都不提 TestFlaky
    assert len(failed) == 1 and failed[0].startswith("G10"), failed
    assert slow in failed[0] and "部件 go" in failed[0], failed
    assert any(w.startswith("G10") and ok in w for w in warnings), warnings
    assert any(w.startswith("G11 不可度量：部件 go") for w in warnings), warnings
    assert not any(flaky in x for x in failed + warnings), (failed, warnings)


@XF
def test_part_g11_and_unmeasurable_warnings():
    # Given: 部件 py 的探针结果里 test_net 有网络触碰；部件 go 既没有探针结果也没有逐用例耗时
    net = "svc/py/x_test.py::test_net"
    py_res = {"probe": {net: {"sec": 0.1, "hits": {"网络": "socket.connect ('127.0.0.1', 1)"}}}, "probe_why": None,
              "secs": {net: 0.1}, "secs_why": None}
    go_res = {"probe": None, "probe_why": "没有探针输出（不是 pytest？）", "secs": None, "secs_why": "没有 junit 输出"}

    # When: 分别判定两个部件
    py_failed, _ = sg().part_tier_verdicts("py", py_res, {}, {})
    go_failed, go_warnings = sg().part_tier_verdicts("go", go_res, {}, {})

    # Then: py 有一条 G11 失败，含「部件 py」与「网络」；go 没有失败，警告恰一条，以「G10/G11 不可度量：部件 go」开头
    assert any(f.startswith("G11") and "部件 py" in f and "网络" in f for f in py_failed), py_failed
    assert go_failed == [], go_failed
    assert len(go_warnings) == 1 and go_warnings[0].startswith("G10/G11 不可度量：部件 go"), go_warnings
