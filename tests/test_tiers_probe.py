"""单元层探针：逐用例记录触碰与耗时、插件加载失败回退、非 pytest 不可度量
（scenario: test-tiers#probe-classifies-each-test、#probe-counts-setup-and-teardown、
#probe-falls-back-when-plugin-cannot-load、#probe-unmeasurable-for-non-pytest）。"""
import shlex
import sys

from conftest import load_hook, write

PY = shlex.quote(sys.executable)
CMD = "%s -m pytest -q -p no:cacheprovider tests/unit" % PY


def run_probe(root, cmd=CMD):
    """在 root 以探针方式运行单元层：slice-gate.run_test_gate(cmd, root, probe=True)。"""
    write(root / "pytest.ini", "[pytest]\n")
    return load_hook("slice-gate").run_test_gate(cmd, str(root), probe=True)


def test_probe_classifies_each_test(tmp_path):
    # Given: 单元层有四个用例：只做算术的；在 tmp_path 里写文件的；用子进程运行当前解释器的；
    #        在测试函数里首次 import 测试目录下另一个模块（helper_mod）的
    write(tmp_path / "tests" / "unit" / "helper_mod.py", "VALUE = 42\n")
    write(tmp_path / "tests" / "unit" / "test_mix.py", """
        import subprocess
        import sys


        def test_math():
            assert 1 + 1 == 2


        def test_writes(tmp_path):
            (tmp_path / "f.txt").write_text("x")


        def test_spawns():
            subprocess.run([sys.executable, "-c", "pass"], check=True)


        def test_imports():
            import helper_mod
            assert helper_mod.VALUE == 42
    """)

    # When: slice-gate 以探针方式运行单元层
    res = run_probe(tmp_path)

    # Then: 写文件的被记为碰了「文件」，用子进程的被记为碰了「子进程」；只做算术的与首次 import 模块的都没有触碰记录
    assert res["rc"] == 0, res["out"]
    probe = res["probe"]
    nid = "tests/unit/test_mix.py::%s"
    assert "文件" in probe[nid % "test_writes"]["hits"], probe
    assert "子进程" in probe[nid % "test_spawns"]["hits"], probe
    assert probe[nid % "test_math"]["hits"] == {}, probe
    assert probe[nid % "test_imports"]["hits"] == {}, probe


def test_probe_counts_setup_and_teardown(tmp_path):
    # Given: 单元层有一个用例，它的 fixture 在准备阶段与清理阶段各睡 0.4 秒，测试函数本身不睡
    write(tmp_path / "tests" / "unit" / "test_slowfix.py", """
        import time

        import pytest


        @pytest.fixture
        def slow():
            time.sleep(0.4)
            yield
            time.sleep(0.4)


        def test_uses(slow):
            assert True
    """)

    # When: slice-gate 以探针方式运行单元层
    res = run_probe(tmp_path)

    # Then: 该用例记录的耗时不少于 0.8 秒
    rec = res["probe"]["tests/unit/test_slowfix.py::test_uses"]
    assert rec["sec"] >= 0.8, rec


def test_probe_falls_back_when_plugin_cannot_load(tmp_path):
    # Given: gate.test 是 env PYTHONPATH= <解释器> -m pytest …（包装命令清空了 PYTHONPATH），单元层用例全绿
    write(tmp_path / "tests" / "unit" / "test_ok.py", "def test_ok():\n    assert True\n")
    cmd = "env PYTHONPATH= %s -m pytest -q -p no:cacheprovider tests/unit" % PY

    # When: slice-gate 以探针方式运行单元层
    res = run_probe(tmp_path, cmd)

    # Then: 结果的退出码为 0，判为不可度量（probe 为 None），原因含「探针」
    assert res["rc"] == 0, res["out"]
    assert res["probe"] is None, res
    assert "探针" in (res["probe_why"] or ""), res


def test_probe_unmeasurable_for_non_pytest(tmp_path):
    # Given: gate.test 是 true（不是 pytest）

    # When: slice-gate 以探针方式运行单元层
    res = run_probe(tmp_path, "true")

    # Then: 结果判为不可度量：没有逐用例记录，并给出原因
    assert res["probe"] is None, res
    assert res["probe_why"], res
