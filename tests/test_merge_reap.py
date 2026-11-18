"""slice-gate.py merge 合回后回收切片临时 worktree，铁律 6 措辞同步（scenario: slice-worktree-reap#merge-reaps-merged-slice-worktrees、
#merge-keeps-worktree-with-unmerged-work、#merge-never-touches-unrelated-worktrees、#merge-reap-returns-borrowed-submodule、
#reap-failure-does-not-fail-merge、#iron-rule-names-reap-exception，共 6 条）。
骨架：strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import json
import os

import pytest

from conftest import ROOT, commit_all, git, run_hook, write
from submodule_helpers import SUB, g, git_rc, make_super, run_executor
from test_clean_after_merged_docs import iron6
from test_slice_gate import plan, slice_, write_plan

PENDING = pytest.mark.xfail(strict=True, reason="change slice-resume-deterministic S5 未实现")
CHANGE = "openspec/changes/c"


def home_repo(git_repo):
    """git_repo 自己当 change 家：计划与一份 timeline.md 已提交，检出分支 worktree-c。"""
    write_plan(git_repo / "openspec" / "changes" / "c", plan([slice_("S1", ["src/**"]), slice_("S2", ["lib/**"])]))
    write(git_repo / CHANGE / "timeline.md", "<!-- timeline -->\n")
    commit_all(git_repo, "plan")
    git(git_repo, "switch", "-q", "-c", "worktree-c")


def slice_worktree(git_repo, name, rel, branch=True):
    """仿运行时开的切片临时 worktree（带自己的分支 worktree-<name>），提交一个文件；返回 (路径, commit)。"""
    path = git_repo.parent / name
    if branch:
        git(git_repo, "worktree", "add", "-q", "-b", "worktree-" + name, str(path), "worktree-c")
    else:
        git(git_repo, "worktree", "add", "-q", "--detach", str(path), "worktree-c")
    write(path / rel, "X = 1\n")
    git(path, "add", rel)
    git(path, "commit", "-q", "-m", name)
    return path, git(path, "rev-parse", "HEAD")


def flight_dirt(path):
    """门禁在临时 worktree 里留下的东西：改过的 timeline.md、未跟踪的 gate-report.md 与字节码。"""
    with open(path / CHANGE / "timeline.md", "a", encoding="utf-8") as f:
        f.write("2026-11-18T00:00:00Z\tgate\tS1 ok\n")
    write(path / CHANGE / "gate-report.md", "# Gate Report\n")
    write(path / "src" / "__pycache__" / "a.cpython-312.pyc", "x")


def merge(cwd, *pairs):
    p = run_hook("slice-gate", "merge", *pairs, cwd=cwd)
    return p, (json.loads(p.stdout) if p.stdout.strip() else None)


def listed(git_repo, path):
    return os.path.realpath(str(path)) in [os.path.realpath(x[len("worktree "):]) for x in
                                           git(git_repo, "worktree", "list", "--porcelain").splitlines()
                                           if x.startswith("worktree ")]


@PENDING
def test_merge_reaps_merged_slice_worktrees(git_repo):
    # Given: 两间切片临时 worktree 各提交了一个文件，里面只剩门禁留下的飞行记录与字节码
    home_repo(git_repo)
    w1, c1 = slice_worktree(git_repo, "wf_x-1", "src/a.py")
    w2, c2 = slice_worktree(git_repo, "wf_x-2", "lib/b.py")
    flight_dirt(w1)
    flight_dirt(w2)

    # When: 在 change 家运行 merge S1=<c1> S2=<c2>
    p, out = merge(git_repo, "S1=" + c1, "S2=" + c2)

    # Then: 合回成功；两间临时 worktree 与它们的分支都被收走，reaped 列出两条路径；change 家还在、文件已合入
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert out["ok"] is True and out["merged"] == ["S1", "S2"], out
    assert sorted(os.path.realpath(x) for x in out["reaped"]) == sorted(os.path.realpath(str(x)) for x in (w1, w2)), out
    for w, name in ((w1, "wf_x-1"), (w2, "wf_x-2")):
        assert not w.exists() and not listed(git_repo, w)
        assert git_rc(git_repo, "rev-parse", "-q", "--verify", "refs/heads/worktree-" + name) != 0
    assert (git_repo / "src" / "a.py").is_file() and (git_repo / "lib" / "b.py").is_file()
    assert git(git_repo, "branch", "--show-current") == "worktree-c"


@PENDING
def test_merge_keeps_worktree_with_unmerged_work(git_repo):
    # Given: 切片临时 worktree 提交之后，工作树里还有一个不属于飞行记录的未提交文件
    home_repo(git_repo)
    w1, c1 = slice_worktree(git_repo, "wf_x-1", "src/a.py")
    flight_dirt(w1)
    write(w1 / "src" / "half.py", "HALF = 1\n")

    # When: 在 change 家运行 merge S1=<c1>
    p, out = merge(git_repo, "S1=" + c1)

    # Then: 合回成功；这间 worktree 原样留着（未提交文件与飞行记录都没被动过），warnings 点名它与那个文件
    assert p.returncode == 0 and out["ok"] is True and out["merged"] == ["S1"], out
    assert not out.get("reaped")
    assert (w1 / "src" / "half.py").is_file() and (w1 / CHANGE / "gate-report.md").is_file()
    assert any("未回收" in w and "wf_x-1" in w and "src/half.py" in w for w in out["warnings"]), out["warnings"]
    assert git_rc(git_repo, "rev-parse", "-q", "--verify", "refs/heads/worktree-wf_x-1") == 0


@PENDING
def test_merge_never_touches_unrelated_worktrees(git_repo):
    # Given: 除了本片最终那间临时 worktree，还有：上一轮留下的同片 worktree（停在本片较早的提交上）、
    #        另一个 change 的 worktree（HEAD 是 change 分支的祖先，但不是本片的提交）
    home_repo(git_repo)
    early, c_early = slice_worktree(git_repo, "wf_x-1", "src/a.py", branch=False)
    final = git_repo.parent / "wf_x-2"
    git(git_repo, "worktree", "add", "-q", "--detach", str(final), c_early)
    write(final / "src" / "b.py", "B = 2\n")
    git(final, "add", "src/b.py")
    git(final, "commit", "-q", "-m", "S1 修补")
    c_final = git(final, "rev-parse", "HEAD")
    other = git_repo.parent / "other-change"
    git(git_repo, "worktree", "add", "-q", "-b", "worktree-other", str(other), "main")

    # When: 在 change 家运行 merge S1=<最终提交>
    p, out = merge(git_repo, "S1=" + c_final)

    # Then: 本片的两间（最终的与上一轮的）被收走；另一个 change 的 worktree、它的分支与 change 家都不动
    assert p.returncode == 0 and out["ok"] is True, out
    assert not early.exists() and not final.exists()
    assert other.is_dir() and listed(git_repo, other)
    assert git_rc(git_repo, "rev-parse", "-q", "--verify", "refs/heads/worktree-other") == 0
    assert listed(git_repo, git_repo)


@PENDING
def test_merge_reap_returns_borrowed_submodule(tmp_path):
    # Given: 带 submodule 的仓库；隔离执行体在临时 worktree 里借出子仓、提交了子仓与父仓（gitlink）、跑过门禁
    env = make_super(tmp_path)
    first = run_executor(env, "S1", "lib1")
    assert first.gate["ok"] is True, first.gate

    # When: 在 change 家运行 merge S1=<父仓 commit>
    p, out = merge(env.home, "S1=" + first.commit)

    # Then: 合回成功；借出的子仓 worktree 先归还、临时 worktree 随后被收走；change 家的子仓里有该片的文件
    assert p.returncode == 0 and out["ok"] is True, (p.stdout, p.stderr)
    assert not first.iso.exists()
    assert str(first.iso) not in g(env.home / SUB, "worktree", "list", "--porcelain")
    assert (env.home / SUB / "lib1.py").is_file()
    assert g(env.home / SUB, "cat-file", "-t", first.sub_commit) == "commit"


@PENDING
def test_reap_failure_does_not_fail_merge(git_repo):
    # Given: 切片临时 worktree 被锁住（git worktree lock），不带强制参数删不掉
    home_repo(git_repo)
    w1, c1 = slice_worktree(git_repo, "wf_x-1", "src/a.py")
    git(git_repo, "worktree", "lock", str(w1))

    # When: 在 change 家运行 merge S1=<c1>
    p, out = merge(git_repo, "S1=" + c1)

    # Then: 合回照常成功（退出 0）；worktree 留着，warnings 写明未回收及原因
    assert p.returncode == 0 and out["ok"] is True and out["merged"] == ["S1"], out
    assert w1.is_dir() and listed(git_repo, w1)
    assert any("未回收" in w and "wf_x-1" in w for w in out["warnings"]), out["warnings"]


@PENDING
def test_iron_rule_names_reap_exception():
    # Given: 根 CLAUDE.md 与 template/CLAUDE.md.snippet
    root = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    snippet = (ROOT / "template" / "CLAUDE.md.snippet").read_text(encoding="utf-8")

    # When: 找出两者的铁律 6 那一行
    r6, s6 = iron6(root), iron6(snippet)

    # Then: 两行都写明切片临时 worktree 合回后由 slice-gate.py merge 回收；既有措辞（不删 worktree、/clean-after-merged、branch -D）保留；
    #       snippet 不超过 8KB
    assert len(r6) == 1 and len(s6) == 1, (r6, s6)
    for line in (r6[0], s6[0]):
        assert "临时 worktree" in line and "slice-gate.py merge" in line, line
        assert "/clean-after-merged" in line, line
    assert "不删 worktree" in r6[0] and "branch -D" in r6[0] and "不带强制参数" in r6[0], r6[0]
    assert len(snippet.encode("utf-8")) <= 8 * 1024
