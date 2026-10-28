"""全量运行记录依赖图并写入锚点池
（scenario: incremental-final#full-run-records-dependency-map、#blind-subprocess-marks-test-file、
#baseline-records-failed-nodes）。"""
import json

import pytest

from final_helpers import baseline, latest_anchor, make_repo

XF = pytest.mark.xfail(strict=True, reason="S1 尚未实现")

TEST_ISO = """
    import os
    import subprocess
    import sys

    TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "c.py")


    def test_iso():
        subprocess.run([sys.executable, TOOL], check=True, capture_output=True, env={})
"""


@XF
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


@XF
def test_blind_subprocess_marks_test_file(git_repo):
    # Given: tests/test_iso.py 用 env={} 起一个 Python 子进程运行仓库内脚本
    d = make_repo(git_repo, extra={"tests/test_iso.py": TEST_ISO})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: 锚点的盲文件清单含 tests/test_iso.py
    anchor = latest_anchor(git_repo)
    assert "tests/test_iso.py" in anchor["blind"], anchor.get("blind")


@XF
def test_baseline_records_failed_nodes(git_repo):
    # Given: 有一个预存失败的用例 tests/test_old.py::test_broken
    d = make_repo(git_repo, extra={"tests/test_old.py": "def test_broken():\n    assert False\n"})

    # When: baseline 跑全量
    baseline(git_repo, d)

    # Then: gate-baseline.json 的 test.failed_nodes 恰好是这一条，锚点的失败用例相同
    bl = json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))
    assert bl["test"]["failed_nodes"] == ["tests/test_old.py::test_broken"], bl["test"]
    assert latest_anchor(git_repo)["failed"] == ["tests/test_old.py::test_broken"]
