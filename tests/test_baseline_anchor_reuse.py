"""基线经锚点复用（scenario: baseline-anchor-reuse#replan-after-landing-reuses-anchor / global-file-in-delta-forces-full-baseline /
cross-change-anchor-with-preexisting-red-reruns-failed / baseline-anchor-chain-limit-forces-full）。"""
import json

import pytest

from conftest import SCOPE_DECL, commit_all, write
from final_helpers import baseline, change_and_commit, make_repo

RED = "def test_red():\n    assert False\n"


def set_all_hops(repo, hops):
    """把锚点池里每条锚点的 hops 改成同一个值（构造「链已耗尽」的池）。"""
    files = [f for f in (repo / ".git" / "flight-anchors").glob("*.json") if not f.name.startswith(".tmp-")]
    assert files, "锚点池为空"
    for f in files:
        e = json.loads(f.read_text(encoding="utf-8"))
        e["hops"] = hops
        f.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def clone_change(repo, src, dst):
    """把 change src 的计划原样复制成 change dst（gate 相同），提交；返回 dst 目录。"""
    s, t = repo / "openspec" / "changes" / src, repo / "openspec" / "changes" / dst
    data = json.loads((s / "slices.json").read_text(encoding="utf-8"))
    data["change"] = dst
    write(t / "proposal.md", (s / "proposal.md").read_text(encoding="utf-8"))
    write(t / "slices" / "S1.md", "# S1\n")
    write(t / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan " + dst)
    return t


@pytest.mark.xfail(strict=True, reason="S3 未实现：基线候选不含锚点，非测试改动一律全量")
def test_replan_after_landing_reuses_anchor(git_repo):
    # Given: change c 有一次测到依赖图的全量基线；之后提交了非测试文件 src/a.py 的改动
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 再运行 baseline
    out = baseline(git_repo, d)

    # Then: 增量，来源是锚点；补跑的测试文件恰为 tests/test_a.py
    assert out["mode"] == "incremental", out.get("reuse_skipped")
    inc = out["incremental"]
    assert inc["source"] == "anchor", inc
    assert inc["rerun_files"] == ["tests/test_a.py"], inc


@pytest.mark.xfail(strict=True, reason="S3 未实现：没有锚点候选，也就没有锚点候选的拒绝理由")
def test_global_file_in_delta_forces_full_baseline(git_repo):
    # Given: change c 有一次测到依赖图的全量基线；之后提交了 pytest.ini 的改动
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "pytest.ini", "[pytest]\n# 改过\n")

    # When: 再运行 baseline
    out = baseline(git_repo, d)

    # Then: 全量；reuse_skipped 有一条锚点候选的理由同时含「全局文件」与 pytest.ini
    assert out["mode"] == "full", out
    reasons = [s.get("reason") or "" for s in out.get("reuse_skipped") or []]
    assert any("全局文件" in r and "pytest.ini" in r for r in reasons), reasons


@pytest.mark.xfail(strict=True, reason="S3 未实现：跨 change 带预存红的结论不复用")
def test_cross_change_anchor_with_preexisting_red_reruns_failed(git_repo):
    # Given: 一个总是失败的用例 test_red；change other 跑过全量基线（锚点测到依赖图、预存红含 test_red）；
    #        change c 与 other 的 gate.test 相同，且 c 还没有基线
    d = make_repo(git_repo, extra={"tests/test_red.py": RED})
    other = clone_change(git_repo, "c", "other")
    baseline(git_repo, other)

    # When: 对 c 运行 baseline
    out = baseline(git_repo, d)

    # Then: 增量，来自 other；补跑含 tests/test_red.py；c 的 failed_nodes 含 test_red
    assert out["mode"] == "incremental", out.get("reuse_skipped")
    inc = out["incremental"]
    assert inc["from"]["change"] == "other", inc
    assert "tests/test_red.py" in inc["rerun_files"], inc
    assert "tests/test_red.py::test_red" in (out["test"].get("failed_nodes") or []), out["test"]


@pytest.mark.xfail(strict=True, reason="S3 未实现：基线侧没有锚点链上限")
def test_baseline_anchor_chain_limit_forces_full(git_repo):
    # Given: anchor_max_hops 为 1；change c 的旧基线后有非测试改动；锚点池里全部锚点的 hops 都是 1
    (git_repo / "openspec" / "gate-scope.json").write_text(
        json.dumps(dict(SCOPE_DECL, anchor_max_hops=1)) + "\n", encoding="utf-8")
    d = make_repo(git_repo)
    baseline(git_repo, d)
    set_all_hops(git_repo, 1)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 baseline
    out = baseline(git_repo, d)

    # Then: 全量；reuse_skipped 有一条含「上限 1」
    assert out["mode"] == "full", out
    reasons = [s.get("reason") or "" for s in out.get("reuse_skipped") or []]
    assert any("上限 1" in r for r in reasons), reasons
