"""基线只有 nodeid 形式的预存红时，final 全量按 nodeid 差分（scenario: baseline-anchor-reuse#anchor-baseline-diffs-final-by-nodes）。"""
import json

from conftest import commit_all
from final_helpers import baseline, final, make_repo

RED = "def test_red():\n    assert False\n"


def test_anchor_baseline_diffs_final_by_nodes(git_repo):
    # Given: 基线 test.failed_form 为 nodes，failed_nodes 只有 tests/test_red.py::test_red，该用例在当前树上仍然失败
    d = make_repo(git_repo, extra={"tests/test_red.py": RED})
    baseline(git_repo, d)
    path = d / "gate-baseline.json"
    bl = json.loads(path.read_text(encoding="utf-8"))
    bl["test"].update({"failed": None, "failed_form": "nodes", "failed_nodes": ["tests/test_red.py::test_red"]})
    path.write_text(json.dumps(bl, ensure_ascii=False, indent=2), encoding="utf-8")
    commit_all(git_repo, "nodes-form baseline")

    # When: 运行 final --full
    out, p = final(git_repo, d, "--full")

    # Then: 不把 test_red 判为新增失败，G2 test 不红
    assert not [f for f in out["failed"] if f.startswith("G2 test")], out["failed"]


IMPACTED_RED = """
    import subprocess
    import sys

    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_red.py"]))
"""


def test_impacted_final_with_nodes_only_baseline_goes_full(git_repo):
    # Given: 配了 gate.impacted（选测命中恒红的 tests/test_red.py）；基线预存红只有 nodeid 形式；之后只改了 src/a.py
    from final_helpers import change_and_commit
    d = make_repo(git_repo, extra={"tests/test_red.py": RED, "tools/impacted.py": IMPACTED_RED},
                  gate_extra={"impacted": "python3 tools/impacted.py"})
    baseline(git_repo, d)
    path = d / "gate-baseline.json"
    bl = json.loads(path.read_text(encoding="utf-8"))
    bl["test"].update({"failed": None, "failed_form": "nodes", "failed_nodes": ["tests/test_red.py::test_red"]})
    path.write_text(json.dumps(bl, ensure_ascii=False, indent=2), encoding="utf-8")
    commit_all(git_repo, "nodes-form baseline")
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final（不带 --full）
    out, p = final(git_repo, d)

    # Then: gate.impacted 无法按 nodeid 差分 → 自动全量并说明原因；预存红不被判为新增失败
    assert out["incremental"]["mode"] == "full", out["incremental"]
    assert "nodeid" in out["incremental"]["full_why"], out["incremental"]
    assert not [f for f in out["failed"] if f.startswith("G2 test")], out["failed"]
