"""锚点链上限：final 侧（scenario: baseline-anchor-reuse#final-anchor-chain-limit-forces-full）。"""
import json

from conftest import SCOPE_DECL
from final_helpers import baseline, change_and_commit, final, latest_anchor, make_repo


def set_all_hops(repo, hops):
    """把锚点池里每条锚点的 hops 改成同一个值（构造「链已耗尽」的池）。"""
    pdir = repo / ".git" / "flight-anchors"
    files = [f for f in pdir.glob("*.json") if not f.name.startswith(".tmp-")]
    assert files, "锚点池为空"
    for f in files:
        e = json.loads(f.read_text(encoding="utf-8"))
        e["hops"] = hops
        f.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def test_final_anchor_chain_limit_forces_full(git_repo):
    # Given: anchor_max_hops 为 2；锚点池里全部锚点的 hops 都是 2；之后提交了 src/a.py 的改动
    (git_repo / "openspec" / "gate-scope.json").write_text(
        json.dumps(dict(SCOPE_DECL, anchor_max_hops=2)) + "\n", encoding="utf-8")
    d = make_repo(git_repo)
    baseline(git_repo, d)
    set_all_hops(git_repo, 2)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 全量，full_why 含「上限 2」；新写的锚点 hops 为 0
    inc = out.get("incremental") or {}
    assert inc.get("mode") == "full", (out, p.stderr)
    assert "上限 2" in (inc.get("full_why") or ""), inc
    assert latest_anchor(git_repo).get("hops") == 0
