"""嵌套 pytest 会话不污染门禁的度量
（scenario: incremental-final#nested-pytest-does-not-overwrite-junit、#nested-pytest-not-recorded-in-probe-or-deps、
#guard-plugin-load-failure-falls-back）。"""
import shlex
import sys

import pytest

from conftest import load_hook, write

XF = pytest.mark.xfail(strict=True, reason="S1 尚未实现")
PY = shlex.quote(sys.executable)
CMD = "%s -m pytest -q -p no:cacheprovider tests" % PY

# 会话结束、junit 写完之后再起一个继承环境的嵌套 pytest（afa 预算插件复测的同一模式）
LATE_NESTED_CONFTEST = """
    import os
    import subprocess
    import sys
    import tempfile

    import pytest


    @pytest.hookimpl(trylast=True)
    def pytest_unconfigure(config):
        inner = tempfile.mkdtemp()
        with open(os.path.join(inner, "test_inner.py"), "w") as f:
            f.write("def test_inner():\\n    pass\\n")
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", inner],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
"""


@XF
def test_nested_pytest_does_not_overwrite_junit(tmp_path):
    # Given: 被测套件有一个必然失败的用例 test_bad 与一个通过的用例；
    #        conftest 在外层会话结束、junit 写完之后起一个继承全部环境变量的嵌套 pytest（跑 0 个失败用例）
    write(tmp_path / "pytest.ini", "[pytest]\n")
    write(tmp_path / "conftest.py", LATE_NESTED_CONFTEST)
    write(tmp_path / "tests" / "test_x.py", "def test_ok():\n    pass\n\n\ndef test_bad():\n    assert False\n")
    sg = load_hook("slice-gate")

    # When: 门禁以 run_test_gate 运行这个套件
    res = sg.run_test_gate(CMD, str(tmp_path))

    # Then: 结果可度量，失败清单恰好是 test_bad，不报「计数不一致」
    assert res["rc"] == 1, res["out"]
    assert res["why"] is None, res["why"]
    assert res["failed"] == ["tests.test_x::test_bad"], res["failed"]


@XF
def test_nested_pytest_not_recorded_in_probe_or_deps(tmp_path):
    # Given: 被测套件有一个用例用子进程起嵌套 pytest，嵌套会话跑的 inner/test_ghost.py 不在外层套件里
    write(tmp_path / "pytest.ini", "[pytest]\n")
    write(tmp_path / "inner" / "test_ghost.py", "def test_ghost():\n    pass\n")
    write(tmp_path / "tests" / "test_outer.py", """
        import os
        import subprocess
        import sys

        INNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "inner")


        def test_outer():
            subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", INNER], check=True)
    """)
    sg = load_hook("slice-gate")

    # When: 门禁以依赖图与探针方式运行这个套件
    res = sg.run_test_gate(CMD, str(tmp_path), probe=True, deps=True)

    # Then: 依赖图与探针记录里都没有嵌套会话的用例或测试文件
    assert res["rc"] == 0, res["out"]
    assert res["probe"] is not None and res["deps"] is not None, (res["probe_why"], res["deps_why"])
    assert not [n for n in res["probe"] if "test_ghost" in n], res["probe"]
    assert "tests/test_outer.py" in res["deps"]["deps"], res["deps"]
    assert not [f for f in res["deps"]["deps"] if "test_ghost" in f], res["deps"]
    assert not [n for n in res["deps"]["nodes"] if "test_ghost" in n], res["deps"]


@XF
def test_guard_plugin_load_failure_falls_back(tmp_path):
    # Given: gate.test 是把 PYTHONPATH 覆写成固定值再运行 pytest 的包装命令；套件一过一败
    write(tmp_path / "pytest.ini", "[pytest]\n")
    write(tmp_path / "tests" / "test_x.py", "def test_ok():\n    pass\n\n\ndef test_bad():\n    assert False\n")
    cmd = "env PYTHONPATH=/nonexistent-flight %s" % CMD
    sg = load_hook("slice-gate")

    # When: 门禁带依赖图运行它
    res = sg.run_test_gate(cmd, str(tmp_path), deps=True)

    # Then: 用不带插件重跑的结果判定（失败清单照常）；依赖图判为没测到，并说明原因
    assert res["failed"] == ["tests.test_x::test_bad"], (res["why"], res["out"][-800:])
    assert res["deps"] is None
    assert res["deps_why"] and "加载失败" in res["deps_why"], res["deps_why"]
