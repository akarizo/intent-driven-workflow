"""slice-gate.py reap：飞行收口回收本次飞行留下的切片临时 worktree（scenario: flight-close-reap#close-reap-removes-landed-slice-worktree、
#close-reap-ignores-worktrees-without-flight-evidence、#close-reap-skips-locked-worktree、#close-reap-archives-superseded-attempt、
#close-reap-archives-uncommitted-work、#close-reap-keeps-worktree-with-own-submodule-clone、#close-reap-reports-and-records-timeline，共 7 条）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json
import os
import subprocess


from conftest import git, run_hook, write
from submodule_helpers import g as gsub, git_rc
from test_merge_reap import CHANGE, flight_dirt, home_repo, listed, slice_worktree

ATTIC = "refs/flight/c/attic/"


def reap(cwd):
    p = run_hook("slice-gate", "reap", "--change-dir", CHANGE, cwd=cwd)
    return p, (json.loads(p.stdout) if p.stdout.strip() else None)


def real(p):
    return os.path.realpath(str(p))


def marker(path, change="c", slice_id="S1"):
    """仿 slice-gate.py start 写的切片标记：change_dir 是该 worktree 里 change 目录的绝对路径。"""
    write(path / ".openspec-slice", json.dumps({"slice": slice_id, "change_dir": str(path / "openspec" / "changes" / change),
                                               "base": "0" * 40, "started": "2026-11-19T00:00:00Z"}))


def integrate(git_repo, sha, sid="S1"):
    git(git_repo, "merge", "-q", "--no-ff", sha, "-m", "integrate: " + sid)


def test_close_reap_removes_landed_slice_worktree(git_repo):
    # Given: change 家检出 worktree-c；一间临时 worktree 的提交已 --no-ff 合进 change 分支，里面只剩飞行记录、切片标记与字节码
    home_repo(git_repo)
    w1, c1 = slice_worktree(git_repo, "wf_r-1", "src/a.py")
    flight_dirt(w1)
    marker(w1)
    integrate(git_repo, c1)

    # When: 在 change 家运行 reap --change-dir openspec/changes/c
    p, out = reap(git_repo)

    # Then: 退出 0；reaped 只列出这一间，archived 为空；目录与登记都消失，分支被删除；change 家仍在原分支
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert [real(x) for x in out["reaped"]] == [real(w1)], out
    assert out["archived"] == [], out
    assert not w1.exists() and not listed(git_repo, w1)
    assert git_rc(git_repo, "rev-parse", "-q", "--verify", "refs/heads/worktree-wf_r-1") != 0
    assert git(git_repo, "branch", "--show-current") == "worktree-c"


def test_close_reap_ignores_worktrees_without_flight_evidence(git_repo):
    # Given: 一间人开的 worktree（HEAD 就是 change 分支的 tip，没有切片标记、没有飞行记录改动）；
    #        一间切片标记指向另一个 change（other）的 worktree
    home_repo(git_repo)
    mine = git_repo.parent / "mine"
    git(git_repo, "worktree", "add", "-q", "-b", "worktree-mine", str(mine), "worktree-c")
    other, _ = slice_worktree(git_repo, "wf_other-1", "src/o.py")
    marker(other, change="other")

    # When: 在 change 家运行 reap
    p, out = reap(git_repo)

    # Then: 两间都原样保留（目录、登记、分支都在），且不出现在 reaped / archived / kept 任何一个列表里
    assert p.returncode == 0, (p.stdout, p.stderr)
    for w, branch in ((mine, "worktree-mine"), (other, "worktree-wf_other-1")):
        assert w.is_dir() and listed(git_repo, w)
        assert git_rc(git_repo, "rev-parse", "-q", "--verify", "refs/heads/" + branch) == 0
    mentioned = [real(x) for x in out["reaped"]] + [real(a["path"]) for a in out["archived"]] + [real(k["path"]) for k in out["kept"]]
    assert real(mine) not in mentioned and real(other) not in mentioned, out


def test_close_reap_skips_locked_worktree(git_repo):
    # Given: 一间带本 change 飞行记录改动的临时 worktree，提交已合进 change 分支，但被 git worktree lock 锁住
    home_repo(git_repo)
    w1, c1 = slice_worktree(git_repo, "wf_r-1", "src/a.py")
    flight_dirt(w1)
    integrate(git_repo, c1)
    git(git_repo, "worktree", "lock", str(w1))

    # When: 在 change 家运行 reap
    p, out = reap(git_repo)

    # Then: 退出 0；这间原样保留；kept 里有它，原因写明已锁定
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert w1.is_dir() and listed(git_repo, w1)
    hit = [k for k in out["kept"] if real(k["path"]) == real(w1)]
    assert len(hit) == 1 and "锁定" in hit[0]["why"], out


def test_close_reap_archives_superseded_attempt(git_repo):
    # Given: 一间临时 worktree 的提交没有进 change 分支（门禁红后重派留下的旧尝试），只剩本 change 的飞行记录改动
    home_repo(git_repo)
    old, c_old = slice_worktree(git_repo, "wf_r-old", "src/a.py")
    flight_dirt(old)

    # When: 在 change 家运行 reap
    p, out = reap(git_repo)

    # Then: refs/flight/c/attic/wf_r-old 指向原 HEAD；目录与登记消失；它自己的分支仍在；archived 列出路径与 ref
    assert p.returncode == 0, (p.stdout, p.stderr)
    ref = ATTIC + "wf_r-old"
    assert git(git_repo, "rev-parse", ref) == c_old
    assert not old.exists() and not listed(git_repo, old)
    assert git(git_repo, "rev-parse", "refs/heads/worktree-wf_r-old") == c_old
    assert [(real(a["path"]), a["ref"]) for a in out["archived"]] == [(real(old), ref)], out
    assert [real(x) for x in out["reaped"]] == [real(old)], out


def test_close_reap_archives_uncommitted_work(git_repo, tmp_path):
    # Given: 一间未交回执行体的游离 HEAD 临时 worktree：带切片标记；src/a.py（已提交）被改成 X = 2；另有未跟踪的 src/new.py
    home_repo(git_repo)
    half, c0 = slice_worktree(git_repo, "wf_r-half", "src/a.py", branch=False)
    marker(half)
    write(half / "src" / "a.py", "X = 2\n")
    write(half / "src" / "new.py", "NEW = 1\n")

    # When: 在 change 家运行 reap
    p, out = reap(git_repo)

    # Then: attic ref 指向以原 HEAD 为唯一父提交的新提交，树里有改过的 a.py 与 new.py，没有切片标记；目录已删除；
    #       从 attic ref 检出的工作树里能读到这两处内容
    assert p.returncode == 0, (p.stdout, p.stderr)
    ref = ATTIC + "wf_r-half"
    tip = git(git_repo, "rev-parse", ref)
    assert git(git_repo, "rev-list", "--parents", "-n", "1", tip).split()[1:] == [c0]
    assert git(git_repo, "show", ref + ":src/a.py") == "X = 2"
    assert git(git_repo, "show", ref + ":src/new.py") == "NEW = 1"
    assert git_rc(git_repo, "cat-file", "-e", ref + ":.openspec-slice") != 0
    assert not half.exists() and not listed(git_repo, half)
    back = tmp_path / "back"
    git(git_repo, "worktree", "add", "-q", "--detach", str(back), ref)
    assert (back / "src" / "a.py").read_text(encoding="utf-8") == "X = 2\n"
    assert (back / "src" / "new.py").read_text(encoding="utf-8") == "NEW = 1\n"


def test_close_reap_keeps_worktree_with_own_submodule_clone(git_repo, tmp_path):
    # Given: change 分支带 submodule vendor/sub；一间临时 worktree 自己初始化了子仓克隆，提交已合进 change 分支，只剩飞行记录改动
    home_repo(git_repo)
    sub = tmp_path / "sub-origin"
    sub.mkdir()
    gsub(sub, "init", "-q", "-b", "main")
    gsub(sub, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "s")
    gsub(git_repo, "submodule", "add", "-q", str(sub), "vendor/sub")
    git(git_repo, "commit", "-q", "-m", "add sub")
    w1, c1 = slice_worktree(git_repo, "wf_r-sub", "src/a.py")
    gsub(w1, "submodule", "update", "--init", "-q")
    assert (w1 / "vendor" / "sub" / ".git").exists()
    flight_dirt(w1)
    integrate(git_repo, c1)

    # When: 在 change 家运行 reap
    p, out = reap(git_repo)

    # Then: 退出 0；这间原样保留，子仓仍是填充状态；kept 里有它，原因提到子仓
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert w1.is_dir() and listed(git_repo, w1)
    assert (w1 / "vendor" / "sub" / ".git").exists()
    hit = [k for k in out["kept"] if real(k["path"]) == real(w1)]
    assert len(hit) == 1 and "子仓" in hit[0]["why"], out


def test_close_reap_reports_and_records_timeline(git_repo):
    # Given: 本次飞行留下一间已落地的临时 worktree 和一间作废的尝试，两间都只剩本 change 的飞行记录改动
    home_repo(git_repo)
    landed, c1 = slice_worktree(git_repo, "wf_r-1", "src/a.py")
    old, _ = slice_worktree(git_repo, "wf_r-0", "lib/b.py")
    for w in (landed, old):
        flight_dirt(w)
    integrate(git_repo, c1)

    # When: 在 change 家运行 reap
    p, out = reap(git_repo)

    # Then: 退出 0；JSON 含 reaped（2）/ archived（1）/ kept（空）/ freed_kb（> 0）；
    #       change 家 timeline.md 的最后一行是 reap 事件，备注含「回收 2 个」「归档 1 个」
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert len(out["reaped"]) == 2 and len(out["archived"]) == 1 and out["kept"] == [], out
    assert isinstance(out["freed_kb"], int) and out["freed_kb"] > 0, out
    last = (git_repo / CHANGE / "timeline.md").read_text(encoding="utf-8").strip().splitlines()[-1].split("\t")
    assert last[1] == "reap", last
    assert "回收 2 个" in last[2] and "归档 1 个" in last[2], last
