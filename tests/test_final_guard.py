"""嵌套 pytest 会话不污染门禁的度量
（scenario: incremental-final#nested-pytest-does-not-overwrite-junit、#nested-pytest-not-recorded-in-probe-or-deps、
#guard-plugin-load-failure-falls-back）。"""
import shlex
import sys

from conftest import load_hook, write
from final_helpers import final, latest_anchor, make_repo

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


# 用例里起一个嵌套 pytest：继承 PYTEST_ADDOPTS（含 -p flight_guard）却把 PYTHONPATH 覆写掉 → 嵌套会话插件导入失败；
# 它的输出经 -s 进了外层输出。每跑一次往仓库外的计数文件追加一行
SPAWN_BROKEN_NESTED = """
    import os
    import subprocess
    import sys


    def test_spawn(tmp_path):
        with open(%r, "a") as f:
            f.write("x\\n")
        (tmp_path / "test_inner.py").write_text("def test_inner():\\n    pass\\n")
        env = dict(os.environ, PYTHONPATH=os.devnull)
        p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(tmp_path)],
                           env=env, capture_output=True, text=True)
        print(p.stdout + p.stderr)
"""


def test_nested_plugin_failure_not_taken_as_outer_failure(git_repo, tmp_path):
    # Given: 被测仓库有一个用例起嵌套 pytest 并故意让它导入 flight 插件失败（错误文字进了外层输出），外层自身正常；
    #        gate.test 带 -s，锚点池为空
    count = tmp_path / "count.txt"
    d = make_repo(git_repo, extra={"tests/test_spawn.py": SPAWN_BROKEN_NESTED % str(count)},
                  gate_extra={"test": "%s -m pytest -q -s -p no:cacheprovider tests" % PY})

    # When: 运行 final（没有锚点 → 全量）
    out, p = final(git_repo, d)

    # Then: 全量只跑一次（不去插件重跑）；依赖图测到，没有「依赖图未测」警告，锚点 measured 为真
    assert out["incremental"]["mode"] == "full", out["incremental"]
    assert count.read_text().count("x") == 1, count.read_text()
    assert not [w for w in out["warnings"] if "依赖图未测" in w], out["warnings"]
    assert latest_anchor(git_repo)["measured"] is True
