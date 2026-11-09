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
