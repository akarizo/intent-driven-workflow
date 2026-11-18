"""slice-gate.py landed：列出已落地的切片（scenario: retakeoff-landed#landed-lists-green-merged-slices、
#landed-excludes-slice-whose-plan-changed，共 2 条）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, run_hook, write
from test_slice_gate import plan, slice_

PENDING = pytest.mark.xfail(strict=True, reason="change wave-integration-guard S3 未实现")


def flown_repo(repo):
    """三个切片的计划（含切片包与规格）已提交，之后又有一个实现提交。返回 (change 目录, 实现提交的 sha)。"""
    change = repo / "openspec" / "changes" / "c"
    data = plan([slice_("S1", ["a/**"]), slice_("S2", ["b/**"]), slice_("S3", ["c/**"])])
    write(change / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    for sid in ("S1", "S2", "S3"):
        write(change / "slices" / (sid + ".md"), "# %s\n" % sid)
    write(change / "specs" / "cap" / "spec.md", "## ADDED Requirements\n")
    commit_all(repo, "plan")
    write(repo / "a" / "impl.py", "X = 1\n")
    return change, commit_all(repo, "impl")


def record(repo, change, sid, commit, red=False):
    args = ["--red", "--failed", "G1 verify: exit 1"] if red else []
    p = run_hook("slice-gate", "record", "--change-dir", str(change), "--slice", sid, "--commit", commit, *args, cwd=repo)
    assert p.returncode == 0, p.stderr


def landed(repo, change):
    p = run_hook("slice-gate", "landed", "--change-dir", str(change), cwd=repo)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def edit_plan(change, sid, **fields):
    data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    for s in data["slices"]:
        if s["id"] == sid:
            s.update(fields)
    write(change / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))


@PENDING
def test_landed_lists_green_merged_slices(git_repo):
    # Given: S1 的最新门禁行是绿的且 commit 在分支历史里；S2 的最新门禁行是红的；S3 的门禁行是绿的但 commit 不在对象库
    change, sha = flown_repo(git_repo)
    record(git_repo, change, "S1", sha)
    record(git_repo, change, "S2", sha, red=True)
    record(git_repo, change, "S3", "f" * 40)

    # When: 运行 landed
    out = landed(git_repo, change)

    # Then: 输出只有 S1，值是它门禁行里的 commit
    assert out == {"S1": sha[:10]}, out


@PENDING
def test_landed_excludes_slice_whose_plan_changed(git_repo):
    # Given: S1、S2 的门禁行都是绿的且 commit 在分支历史里
    change, sha = flown_repo(git_repo)
    record(git_repo, change, "S1", sha)
    record(git_repo, change, "S2", sha)

    # When: 改了 S1 的切片包后运行；还原后只改 S2 的 owns 再运行；再改 S2 的 verify 后运行
    write(change / "slices" / "S1.md", "# S1\n\n补了一条约束。\n")
    packet_changed = landed(git_repo, change)
    write(change / "slices" / "S1.md", "# S1\n")
    edit_plan(change, "S2", owns=["b/**", "tests/test_b_stub.py"])
    owns_changed = landed(git_repo, change)
    edit_plan(change, "S2", verify="python3 -m pytest -q tests/test_b.py")
    verify_changed = landed(git_repo, change)

    # Then: 切片包改了的不算落地；只改 owns 不影响；改了 verify 的不算落地
    assert sorted(packet_changed) == ["S2"], packet_changed
    assert sorted(owns_changed) == ["S1", "S2"], owns_changed
    assert sorted(verify_changed) == ["S1"], verify_changed
