"""全量运行记录依赖图并写入锚点池
（scenario: incremental-final#full-run-records-dependency-map、#blind-subprocess-marks-test-file、
#baseline-records-failed-nodes）。"""
import argparse
import json

from conftest import commit_all, load_hook, write
from final_helpers import PY, anchors, baseline, latest_anchor, make_repo


TEST_ISO = """
    import os
    import subprocess
    import sys

    TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "c.py")


    def test_iso():
        subprocess.run([sys.executable, TOOL], check=True, capture_output=True, env={})
"""


def test_full_run_records_dependency_map(git_repo):
    # Given: tests/test_a.py 静态 import src/a.py；tests/test_b.py 读 data/b.json；
    #        tests/test_c.py 用子进程运行 tools/c.py，而 tools/c.py import src/c_lib.py
    d = make_repo(git_repo)

    # When: baseline 跑全量
    bl = baseline(git_repo, d)

    # Then: 锚点池里有一条本 change 的锚点，measured 为真，依赖图逐文件含对应的仓库文件
    assert bl["ok"] is True, bl
    anchor = latest_anchor(git_repo)
    assert anchor["change"] == "c" and anchor["measured"] is True, anchor
    deps = anchor["deps"]
    assert "src/a.py" in deps["tests/test_a.py"], deps
    assert "data/b.json" in deps["tests/test_b.py"], deps
    assert {"tools/c.py", "src/c_lib.py"} <= set(deps["tests/test_c.py"]), deps


def test_blind_subprocess_marks_test_file(git_repo):
    # Given: tests/test_iso.py 用 env={} 起一个 Python 子进程运行仓库内脚本
    d = make_repo(git_repo, extra={"tests/test_iso.py": TEST_ISO})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: 锚点的盲文件清单含 tests/test_iso.py
    anchor = latest_anchor(git_repo)
    assert "tests/test_iso.py" in anchor["blind"], anchor.get("blind")


def test_baseline_records_failed_nodes(git_repo):
    # Given: 有一个预存失败的用例 tests/test_old.py::test_broken
    d = make_repo(git_repo, extra={"tests/test_old.py": "def test_broken():\n    assert False\n"})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: gate-baseline.json 的 test.failed_nodes 恰好是这一条，锚点的失败用例相同
    bl = json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))
    assert bl["test"]["failed_nodes"] == ["tests/test_old.py::test_broken"], bl["test"]
    assert latest_anchor(git_repo)["failed"] == ["tests/test_old.py::test_broken"]


CONFTEST_IMPORT = """
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    import helper
"""
CONFTEST_SESSION = """
    import os

    import pytest

    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "s.txt")


    @pytest.fixture(scope="session")
    def sdata():
        with open(DATA, encoding="utf-8") as f:
            return f.read().strip()
"""


def test_conftest_imports_recorded_as_dependency(git_repo):
    # Given: tests/conftest.py 在收集阶段 import src/helper.py；tests/test_b.py 本身不 import 它
    d = make_repo(git_repo, extra={"tests/conftest.py": CONFTEST_IMPORT, "src/helper.py": "X = 1\n"})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: tests/test_b.py 的依赖含 src/helper.py 与 tests/conftest.py
    deps = latest_anchor(git_repo)["deps"]
    assert {"src/helper.py", "tests/conftest.py"} <= set(deps["tests/test_b.py"]), deps


def test_session_fixture_reads_recorded_for_every_user(git_repo):
    # Given: tests/conftest.py 的 session 级 fixture sdata 读 data/s.txt；tests/test_p.py 与 tests/test_q.py 都用它
    use = "def test_%s(sdata):\n    assert sdata == 'ok'\n"
    d = make_repo(git_repo, extra={"tests/conftest.py": CONFTEST_SESSION, "data/s.txt": "ok\n",
                                   "tests/test_p.py": use % "p", "tests/test_q.py": use % "q"})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: tests/test_p.py 与 tests/test_q.py 的依赖都含 data/s.txt
    deps = latest_anchor(git_repo)["deps"]
    assert "data/s.txt" in deps["tests/test_p.py"], deps
    assert "data/s.txt" in deps["tests/test_q.py"], deps


def test_read_deps_merges_per_process_files(tmp_path):
    # Given: 两个进程各写一份依赖图：deps.jsonl.101 记 tests/test_a.py 依赖 src/a.py，
    #        deps.jsonl.202 记 tests/test_b.py 依赖 data/b.json；两份都有开跑记录，101（外层 controller）另有会话结束标记
    sg = load_hook("slice-gate")
    rec = '{"flight_deps": "start"}\n{"file": "%s", "deps": ["%s"], "test": true}\n'
    (tmp_path / "deps.jsonl.101").write_text(rec % ("tests/test_a.py", "src/a.py") + '{"flight_deps": "end"}\n',
                                             encoding="utf-8")
    (tmp_path / "deps.jsonl.202").write_text(rec % ("tests/test_b.py", "data/b.json"), encoding="utf-8")

    # When: 按 deps.jsonl 读依赖图
    got, why = sg._read_deps(str(tmp_path / "deps.jsonl"))

    # Then: 两个测试文件的依赖都被读到
    assert got is not None, why
    assert got["deps"] == {"tests/test_a.py": ["src/a.py"], "tests/test_b.py": ["data/b.json"]}, got


def test_read_deps_unmeasurable_on_corrupt_line(tmp_path):
    # Given: 依赖图有开跑记录，但 tests/test_a.py 那条记录被截断成半行
    sg = load_hook("slice-gate")
    (tmp_path / "deps.jsonl.101").write_text(
        '{"flight_deps": "start"}\n{"file": "tests/test_a.py", "deps": ["src/a\n', encoding="utf-8")

    # When: 按 deps.jsonl 读依赖图
    got, why = sg._read_deps(str(tmp_path / "deps.jsonl"))

    # Then: 判为不可度量，原因写明记录损坏
    assert got is None, got
    assert "损坏" in why, why


def test_anchor_unmeasured_when_full_run_stops_early(git_repo):
    # Given: gate.test 带 -x；tests/test_0.py 预存失败，排在其他测试文件之前（-x 停下后其余文件没跑到）
    d = make_repo(git_repo, extra={"tests/test_0.py": "def test_zero():\n    assert False\n"},
                  gate_extra={"test": "%s -m pytest -q -x -p no:cacheprovider tests" % PY})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: 全量提前停止，没跑到的测试文件没有运行时依赖 → 锚点 measured 为假
    assert latest_anchor(git_repo)["measured"] is False, latest_anchor(git_repo)


def test_anchor_unmeasured_when_baseline_red(git_repo):
    # Given: 全量测试全绿，但 S1 的 verify 在基线上红（基线 reasons 非空、ok 为假）
    d = make_repo(git_repo)
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["slices"][0]["verify"] = "false"
    (d / "slices.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    commit_all(git_repo, "verify red")

    # When: baseline 跑全量
    bl = baseline(git_repo, d)

    # Then: 基线无效 → 锚点 measured 为假
    assert bl["ok"] is False, bl
    assert latest_anchor(git_repo)["measured"] is False, latest_anchor(git_repo)


def test_deps_unmeasured_when_session_not_finished(tmp_path):
    # Given: 被测套件的 tests/test_z.py 在用例里 os._exit(0)，外层会话跑不到 sessionfinish（退出码仍为 0）
    write(tmp_path / "pytest.ini", "[pytest]\n")
    write(tmp_path / "tests" / "test_a.py", "def test_a():\n    pass\n")
    write(tmp_path / "tests" / "test_z.py", "import os\n\n\ndef test_z():\n    os._exit(0)\n")
    sg = load_hook("slice-gate")

    # When: 门禁以依赖图方式运行这个套件
    res = sg.run_test_gate("%s -m pytest -q -p no:cacheprovider tests" % PY, str(tmp_path), deps=True)

    # Then: 依赖图只有开跑记录、没有结束标记 → 判为没测到，原因写明会话未正常结束
    assert res["rc"] == 0, res["out"]
    assert res["deps"] is None, res["deps"]
    assert "不完整" in res["deps_why"], res["deps_why"]


def test_anchor_unmeasured_when_end_snapshot_fails(git_repo, monkeypatch, capsys):
    # Given: 依赖图可测的仓库；baseline 结束时的内容快照失败（开跑快照正常）
    d = make_repo(git_repo)
    sg = load_hook("slice-gate")
    real, calls = sg._snapshot, []

    def flaky(root, change_rel):
        calls.append(1)
        if len(calls) > 1:
            raise RuntimeError("模拟快照失败")
        return real(root, change_rel)

    monkeypatch.setattr(sg, "_snapshot", flaky)
    monkeypatch.chdir(git_repo)

    # When: 进程内跑 baseline
    try:
        sg.cmd_baseline(argparse.Namespace(change_dir=str(d), full=False))
    except SystemExit:
        pass

    # Then: 锚点要么不写、要么 measured 为假（snapshot 为 None 的锚点不得可用）
    assert len(calls) >= 2, calls
    assert all(a.get("measured") is False for a in anchors(git_repo)), anchors(git_repo)
