"""slice-gate.py start --continue 与区间起点（scenario: slice-continue#continue-replays-all-previous-commits、
#continue-fast-forwards-descendant、#continue-conflict-rolls-back-with-g0、#continue-noop-when-already-applied、
#base-is-branch-merge-base、#continue-populates-submodule-at-new-gitlink，共 6 条）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, git, run_hook, write
from submodule_helpers import BRANCH, SUB, g, iso as sub_iso, make_super, run_executor, start as sub_start
from test_slice_gate import plan, slice_, write_plan

PENDING = pytest.mark.xfail(strict=True, reason="change slice-resume-deterministic S1 未实现")
CHANGE = "openspec/changes/c"


def home_repo(git_repo):
    """git_repo 自己当 change 家：计划已提交，检出分支 worktree-c。返回分支最新 commit。"""
    write_plan(git_repo / "openspec" / "changes" / "c", plan([slice_("S1", ["src/**", "tests/**"])]))
    write(git_repo / CHANGE / "timeline.md", "<!-- timeline -->\n")
    commit_all(git_repo, "plan")
    git(git_repo, "switch", "-q", "-c", BRANCH)
    return git(git_repo, "rev-parse", "HEAD")


def iso(git_repo, name, ref=BRANCH):
    """从 change 分支开一间 detached 的切片临时 worktree。"""
    path = git_repo.parent / ("iso-" + name)
    git(git_repo, "worktree", "add", "-q", "--detach", str(path), ref)
    return path


def start(cwd, *extra):
    p = run_hook("slice-gate", "start", "S1", "--change-dir", CHANGE, *extra, cwd=cwd)
    return p, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else None)


def commit_file(cwd, rel, text, msg):
    write(cwd / rel, text)
    git(cwd, "add", rel)
    git(cwd, "commit", "-q", "-m", msg)
    return git(cwd, "rev-parse", "HEAD")


def first_round(git_repo):
    """上一轮执行体：在临时 worktree A 里 start 后提交两次。返回 (A, 第一个提交, 第二个提交)。"""
    a = iso(git_repo, "round1")
    p, _ = start(a, "--expect-branch", BRANCH)
    assert p.returncode == 0, (p.stdout, p.stderr)
    s1 = commit_file(a, "src/a.py", "A = 1\n", "S1 主实现")
    s2 = commit_file(a, "src/b.py", "B = 2\n", "S1 修补")
    return a, s1, s2


def record_on_branch(git_repo, note):
    """change 分支自己前进一个飞行记录提交。"""
    with open(git_repo / CHANGE / "timeline.md", "a", encoding="utf-8") as f:
        f.write("2026-11-18T00:00:00Z\t%s\tx\n" % note)
    git(git_repo, "add", CHANGE + "/timeline.md")
    git(git_repo, "commit", "-q", "-m", "chore(flight): 记录")
    return git(git_repo, "rev-parse", "HEAD")


@PENDING
def test_continue_replays_all_previous_commits(git_repo):
    # Given: 上一轮在基点 T 上提交了两次；change 分支随后多了一个飞行记录提交 R；重派开了从 R 分叉的新 worktree B
    home_repo(git_repo)
    _, s1, s2 = first_round(git_repo)
    tip = record_on_branch(git_repo, "approve")
    b = iso(git_repo, "round2")

    # When: 在 B 里运行 start S1 --continue <第二个提交> --expect-branch worktree-c
    p, out = start(b, "--continue", s2, "--expect-branch", BRANCH)

    # Then: 退出 0；两个提交按原顺序接在 R 之上；输出带 continued；标记的 base 为 R
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert (b / "src" / "a.py").is_file() and (b / "src" / "b.py").is_file()
    assert git(b, "log", "--reverse", "--format=%s", "%s..HEAD" % tip).splitlines() == ["S1 主实现", "S1 修补"]
    assert out["continued"] == {"from": s2, "mode": "pick", "applied": 2}, out
    assert out["base"] == tip
    assert json.loads((b / ".openspec-slice").read_text(encoding="utf-8"))["base"] == tip
    assert s1 != git(b, "rev-parse", "HEAD~1")  # 是重放出来的新提交，不是把旧基点整条搬过来


@PENDING
def test_continue_fast_forwards_descendant(git_repo):
    # Given: 上一轮在基点 T 上提交了两次；change 分支没有前进；新 worktree B 从 T 分叉
    tip = home_repo(git_repo)
    _, _, s2 = first_round(git_repo)
    b = iso(git_repo, "round2")

    # When: 在 B 里运行 start S1 --continue <第二个提交> --expect-branch worktree-c
    p, out = start(b, "--continue", s2, "--expect-branch", BRANCH)

    # Then: 退出 0；HEAD 就是上一轮的第二个提交（快进，不产生新提交）；base 仍为 T
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert git(b, "rev-parse", "HEAD") == s2
    assert out["continued"] == {"from": s2, "mode": "ff", "applied": 2}, out
    assert out["base"] == tip


@PENDING
def test_continue_conflict_rolls_back_with_g0(git_repo):
    # Given: 上一轮改了 src/a.py；change 分支随后合回了另一处对 src/a.py 的不同改动；新 worktree B 从分支最新 commit 分叉
    home_repo(git_repo)
    _, _, s2 = first_round(git_repo)
    tip = commit_file(git_repo, "src/a.py", "A = 99\n", "integrate: S9")
    b = iso(git_repo, "round2")

    # When: 在 B 里运行 start S1 --continue <第二个提交> --expect-branch worktree-c
    p, out = start(b, "--continue", s2, "--expect-branch", BRANCH)

    # Then: 退出 1；JSON 的 failed 首项是 G0 base 且点名接续与冲突文件；B 回到分叉时的 HEAD、工作树干净、没有标记
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert out["ok"] is False and out["commit"] == ""
    assert out["failed"][0].startswith("G0 base") and "接续" in out["failed"][0] and "src/a.py" in out["failed"][0], out
    assert git(b, "rev-parse", "HEAD") == tip
    assert git(b, "status", "--porcelain") == ""
    assert not (b / ".openspec-slice").exists()


@PENDING
def test_continue_noop_when_already_applied(git_repo):
    # Given: 上一轮的 worktree A 里标记还在（门禁红），HEAD 已经含上一轮的全部提交
    tip = home_repo(git_repo)
    a, _, s2 = first_round(git_repo)

    # When: 在 A 里连续两次运行 start S1 --continue <第二个提交> --expect-branch worktree-c
    runs = [start(a, "--continue", s2, "--expect-branch", BRANCH) for _ in range(2)]

    # Then: 两次都退出 0、HEAD 不动、continued 的 mode 为 noop；标记的 base 仍是首轮的 T
    for p, out in runs:
        assert p.returncode == 0, (p.stdout, p.stderr)
        assert out["continued"] == {"from": s2, "mode": "noop", "applied": 0}, out
        assert out["base"] == tip
    assert git(a, "rev-parse", "HEAD") == s2


@PENDING
def test_base_is_branch_merge_base(git_repo):
    # Given: 上一轮在旧基点 T 上提交了一次；change 分支此后多了两个飞行记录提交；新 worktree B 从分支最新 commit 分叉，
    #        并已按旧工作流的第零步把上一轮的提交 cherry-pick 上来
    old = home_repo(git_repo)
    a = iso(git_repo, "round1")
    assert start(a, "--expect-branch", BRANCH)[0].returncode == 0
    s1 = commit_file(a, "src/a.py", "A = 1\n", "S1")
    record_on_branch(git_repo, "gate")
    tip = record_on_branch(git_repo, "approve")
    b = iso(git_repo, "round2")
    git(b, "cherry-pick", s1)

    # When: 在 B 里运行 start S1 --base <旧基点 T> --expect-branch worktree-c，再运行 gate S1
    p, out = start(b, "--base", old, "--expect-branch", BRANCH)
    gate = json.loads(run_hook("slice-gate", "gate", "S1", "--change-dir", CHANGE, cwd=b).stdout)

    # Then: start 退出 0，区间起点是 HEAD 与分支的合并基点（分支最新 commit），不是传入的旧值；
    #       门禁区间只含本片自己的文件，不把分支上的飞行记录提交算进来
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert out["base"] == tip and gate["base"] == tip
    assert not [f for f in gate["failed"] if f.startswith("G6")], gate["failed"]


@PENDING
def test_continue_populates_submodule_at_new_gitlink(tmp_path):
    # Given: 上一轮执行体在隔离 worktree A 里提交了子仓 s1 与父仓 C1（gitlink → s1）；重派开了新的隔离 worktree B
    env = make_super(tmp_path)
    first = run_executor(env, "S1", "lib1")
    path = sub_iso(env, "S1-retry")

    # When: 在 B 里运行 start S1 --continue C1 --expect-branch worktree-c（不再有手工 cherry-pick）
    p = sub_start(path, "S1", "--continue", first.commit, "--expect-branch", BRANCH)

    # Then: 退出 0；父仓 HEAD 是 C1；B 的子仓检出在 s1 上，上一轮的文件在场
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert g(path, "rev-parse", "HEAD") == first.commit
    assert g(path / SUB, "rev-parse", "HEAD") == first.sub_commit
    assert (path / SUB / "lib1.py").is_file()
