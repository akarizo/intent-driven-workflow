"""merged-cleanup.py 识别执行体临时 worktree：被合进其他分支（landed）与已落地 change 的作废尝试（dead-attempt）
（scenario: merged-cleanup-agent-worktrees#cleanup-removes-worktree-merged-into-change-branch、#cleanup-keeps-worktree-only-forked-from、
#cleanup-removes-dead-attempt-of-landed-change、#cleanup-defers-detached-dead-attempt、#cleanup-treats-archived-change-as-landed，共 5 条）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import write
from test_merged_cleanup import apply, commit, feature, g, has_reason, has_ref, item, plan, srv, sync, w  # noqa: F401  w 是 fixture


def land_change_dir(w, rel):
    """在远端 main 树里放一个 change 目录（模拟 change 已合入 / 已归档），本地 main 同步。"""
    s = srv(w)
    commit(s, {rel + "/proposal.md": "p\n"}, "land " + rel)
    g(s, "push", "-q", "origin", "main")
    sync(w)


def reasons_with(it, tag):
    return [r for r in it["reasons"] if r.startswith(tag)]


@pytest.mark.xfail(strict=True, reason="scenario: merged-cleanup-agent-worktrees#cleanup-removes-worktree-merged-into-change-branch")
def test_cleanup_removes_worktree_merged_into_change_branch(w):
    # Given: change 分支 worktree-c（.worktrees/c）未合入 main；临时 worktree .claude/worktrees/wf_1 从它派生、提交后被 --no-ff 合进 worktree-c；
    #        wf_1 里只剩飞行记录改动（已跟踪的 timeline.md 被追加）
    feature(w, "c")
    wt = feature(w, "wf_1", files={"openspec/changes/c/timeline.md": "t0\n", "a.py": "a = 1\n"},
                 path=".claude/worktrees/wf_1", base="worktree-c")
    home = w.main / ".worktrees" / "c"
    g(home, "merge", "-q", "--no-ff", "worktree-wf_1", "-m", "integrate: S1")
    write(wt / "openspec/changes/c/timeline.md", "t0\nt1\n")

    # When: 在主 worktree 运行 plan，再运行 apply --no-fetch
    out = plan(w)
    it = item(out, "worktree", ".claude/worktrees/wf_1")
    rc, res = apply(w, "--no-fetch")

    # Then: wf_1 落在 safe，原因里有以 landed: 开头且写明 worktree-c 的一条；apply 后它不再存在；worktree-c 分支与 change 家不受影响
    assert it["tier"] == "safe", it
    assert any("worktree-c" in r for r in reasons_with(it, "landed:")), it
    assert rc == 0, res
    assert not wt.exists()
    assert has_ref(w.main, "refs/heads/worktree-c") and home.is_dir()


@pytest.mark.xfail(strict=True, reason="scenario: merged-cleanup-agent-worktrees#cleanup-keeps-worktree-only-forked-from")
def test_cleanup_keeps_worktree_only_forked_from(w):
    # Given: .claude/worktrees/base（游离 HEAD）停在 worktree-c 的某个提交上、没有独有提交；
    #        临时 worktree .claude/worktrees/wf_1 从同一提交派生、提交后被 --no-ff 合进 worktree-c；worktree-c 未合入 main
    feature(w, "c")
    tip = g(w.main, "rev-parse", "worktree-c")
    g(w.main, "worktree", "add", "-q", "--detach", ".claude/worktrees/base", tip)
    feature(w, "wf_1", path=".claude/worktrees/wf_1", base="worktree-c")
    g(w.main / ".worktrees" / "c", "merge", "-q", "--no-ff", "worktree-wf_1", "-m", "integrate: S1")

    # When: 运行 plan
    out = plan(w)

    # Then: wf_1 有 landed: 原因；base 只在 worktree-c 的 first-parent 链上，仍是 keep，原因不含 landed:
    assert reasons_with(item(out, "worktree", ".claude/worktrees/wf_1"), "landed:")
    it = item(out, "worktree", ".claude/worktrees/base")
    assert it["tier"] == "keep", it
    assert not reasons_with(it, "landed:"), it


@pytest.mark.xfail(strict=True, reason="scenario: merged-cleanup-agent-worktrees#cleanup-removes-dead-attempt-of-landed-change")
def test_cleanup_removes_dead_attempt_of_landed_change(w):
    # Given: main 树里有 openspec/changes/c/；临时 worktree .claude/worktrees/wf_2 在自己的分支上有一个没进任何其他分支的提交，
    #        未提交改动只有 openspec/changes/c/ 下未跟踪的 gate-report.md
    land_change_dir(w, "openspec/changes/c")
    wt = feature(w, "wf_2", files={"x2.py": "x = 2\n"}, path=".claude/worktrees/wf_2")
    write(wt / "openspec/changes/c/gate-report.md", "# Gate Report\n")

    # When: 运行 plan
    out = plan(w)

    # Then: wf_2 落在 safe，原因里有以 dead-attempt: 开头且写明 c 的一条；它的分支 worktree-wf_2 仍是 keep
    it = item(out, "worktree", ".claude/worktrees/wf_2")
    assert it["tier"] == "safe", it
    dead = reasons_with(it, "dead-attempt:")
    assert dead and dead[0].startswith("dead-attempt: c"), it
    assert item(out, "branch", "worktree-wf_2")["tier"] == "keep"


@pytest.mark.xfail(strict=True, reason="scenario: merged-cleanup-agent-worktrees#cleanup-defers-detached-dead-attempt")
def test_cleanup_defers_detached_dead_attempt(w):
    # Given: main 树里有 openspec/changes/c/；一间游离 HEAD 的临时 worktree .claude/worktrees/wf_d 带一个只存在于它自己的提交，
    #        切片标记指向 change c
    land_change_dir(w, "openspec/changes/c")
    g(w.main, "worktree", "add", "-q", "--detach", ".claude/worktrees/wf_d", "main")
    wt = w.main / ".claude" / "worktrees" / "wf_d"
    commit(wt, {"d.py": "d = 1\n"}, "half")
    write(wt / ".openspec-slice", json.dumps({"slice": "S1", "change_dir": str(wt / "openspec" / "changes" / "c"),
                                               "base": "0" * 40, "started": "2026-11-19T00:00:00Z"}))

    # When: 运行 plan
    out = plan(w)

    # Then: wf_d 落在 manual，有 dead-attempt: 原因，并写明删除会丢失提交
    it = item(out, "worktree", ".claude/worktrees/wf_d")
    assert it["tier"] == "manual", it
    dead = reasons_with(it, "dead-attempt:")
    assert dead and "丢失" in dead[0], it


@pytest.mark.xfail(strict=True, reason="scenario: merged-cleanup-agent-worktrees#cleanup-treats-archived-change-as-landed")
def test_cleanup_treats_archived_change_as_landed(w):
    # Given: main 树里没有 openspec/changes/c/，但有 openspec/changes/archive/2026-11-19-c/；
    #        本地有 refs/flight/c/S1，以及一间属于 c、在自己分支上的作废尝试 .claude/worktrees/wf_3（只剩 c 的飞行记录改动）
    land_change_dir(w, "openspec/changes/archive/2026-11-19-c")
    g(w.main, "update-ref", "refs/flight/c/S1", g(w.main, "rev-parse", "HEAD"))
    wt = feature(w, "wf_3", files={"x3.py": "x = 3\n"}, path=".claude/worktrees/wf_3")
    write(wt / "openspec/changes/c/gate-report.md", "# Gate Report\n")

    # When: 运行 plan
    out = plan(w)

    # Then: refs/flight/c/S1 与 .claude/worktrees/wf_3 都落在 safe
    assert item(out, "ref", "refs/flight/c/S1")["tier"] == "safe"
    assert item(out, "worktree", ".claude/worktrees/wf_3")["tier"] == "safe"
