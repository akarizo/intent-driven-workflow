"""slice-gate.py merge：逐片 merge --no-ff，gitlink 冲突在家子仓内合并后钉（scenario: submodule-merge#merge-parallel-submodule-slices、
#merge-rolls-back-on-submodule-conflict、#merge-plain-repo-equals-no-ff、#merge-aborts-on-file-conflict、
#next-wave-populates-from-merged-gitlink，共 5 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

from conftest import commit_all, git, run_hook, write
from submodule_helpers import (BRANCH, SUB, SUB_BRANCH, commit_parent, commit_sub, g, git_rc, iso, make_super,
                               run_executor, start)


def merge(cwd, *pairs):
    p = run_hook("slice-gate", "merge", *pairs, cwd=cwd)
    return p, (json.loads(p.stdout) if p.stdout.strip() else None)


def _in_merge(repo):
    return git_rc(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD") == 0


def test_merge_parallel_submodule_slices(tmp_path):
    # Given: 同一 wave 的 S1、S2 各在自己的隔离 worktree 里改子仓（文件不相交）、各自提交 gitlink，门禁都绿
    env = make_super(tmp_path)
    r1, r2 = run_executor(env, "S1", "lib1"), run_executor(env, "S2", "lib2")
    assert r1.gate["ok"] and r2.gate["ok"], (r1.gate, r2.gate)

    # When: 在 change 家里运行 slice-gate.py merge S1=<C1> S2=<C2>
    p, out = merge(env.home, "S1=" + r1.commit, "S2=" + r2.commit)

    # Then: 退出 0，ok 为 true、merged 为 [S1, S2]；家子仓的分支 feat-sub 与检出都等于父仓 HEAD 的 gitlink，含两片的子仓提交与文件；父仓工作树干净
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert out["ok"] is True and out["merged"] == ["S1", "S2"], out
    sub = env.home / SUB
    link = g(env.home, "rev-parse", "HEAD:" + SUB)
    assert g(sub, "rev-parse", "HEAD") == link == g(sub, "rev-parse", SUB_BRANCH)
    assert g(sub, "branch", "--show-current") == SUB_BRANCH
    for sha in (r1.sub_commit, r2.sub_commit):
        assert git_rc(sub, "merge-base", "--is-ancestor", sha, "HEAD") == 0
    assert (sub / "lib1.py").is_file() and (sub / "lib2.py").is_file()
    assert g(env.home, "status", "--porcelain") == ""
    assert [g(env.home, "log", "-1", "--format=%s", r) for r in ("HEAD~1", "HEAD")] == ["integrate: S1", "integrate: S2"]


def test_merge_rolls_back_on_submodule_conflict(tmp_path):
    # Given: S1 正常改子仓 lib1.py；S2 在另一个隔离 worktree 里把同一个 lib1.py 改成不同内容（人为制造子仓内容冲突）
    env = make_super(tmp_path)
    r1 = run_executor(env, "S1", "lib1")
    b = iso(env, "S2")
    assert start(b, "S2", "--expect-branch", BRANCH).returncode == 0
    write(b / SUB / "lib1.py", "def lib1(a, b):\n    return a - b\n")
    commit_sub(b, "S2 sub", ["lib1.py"])
    c2 = commit_parent(b, "S2")

    # When: 在家里运行 merge S1=<C1> S2=<C2>
    p, out = merge(env.home, "S1=" + r1.commit, "S2=" + c2)

    # Then: 退出 1，ok 为 false、merged 为 [S1]，failed 首项点名 S2 与 mods/sub；父仓与子仓都不在合并中，子仓检出仍等于父仓 HEAD 的 gitlink（S1 已合回）
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert out["ok"] is False and out["merged"] == ["S1"], out
    assert "S2" in out["failed"][0] and SUB in out["failed"][0], out["failed"]
    assert not _in_merge(env.home) and not _in_merge(env.home / SUB)
    assert g(env.home / SUB, "rev-parse", "HEAD") == g(env.home, "rev-parse", "HEAD:" + SUB)
    assert g(env.home, "log", "-1", "--format=%s") == "integrate: S1"


def test_merge_refuses_fork_when_sub_checkout_stale(tmp_path):
    # Given: S1、S2 并行改子仓；家子仓里有未跟踪的 lib1.py，S1 合回后检出同步（ff-only）会失败，子仓 HEAD 停在旧提交
    env = make_super(tmp_path)
    r1, r2 = run_executor(env, "S1", "lib1"), run_executor(env, "S2", "lib2")
    sub = env.home / SUB
    stale = g(sub, "rev-parse", "HEAD")
    write(sub / "lib1.py", "# untracked\n")

    # When: 在家里运行 merge S1=<C1> S2=<C2>
    p, out = merge(env.home, "S1=" + r1.commit, "S2=" + r2.commit)

    # Then: 退出 1、merged 为 [S1]，failed 首项点名 S2、mods/sub 与“不一致”；父仓 gitlink 仍是 S1 的子仓提交，子仓没有新合并提交，不在合并中
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert out["ok"] is False and out["merged"] == ["S1"], out
    assert "S2" in out["failed"][0] and SUB in out["failed"][0] and "不一致" in out["failed"][0], out["failed"]
    assert g(env.home, "rev-parse", "HEAD:" + SUB) == r1.sub_commit
    assert g(sub, "rev-parse", "HEAD") == stale
    assert not _in_merge(env.home) and not _in_merge(sub)


def _side(repo, name, path, text):
    """从 main 拉一个旁支提交（改 path），回到 main，返回旁支 commit。"""
    git(repo, "switch", "-q", "-c", name)
    write(repo / path, text)
    sha = commit_all(repo, name)
    git(repo, "switch", "-q", "main")
    return sha


def test_merge_plain_repo_equals_no_ff(git_repo):
    # Given: 没有 submodule 的仓库；两个从 main 分叉的旁支提交分别新增 a.txt、b.txt
    a = _side(git_repo, "a", "a.txt", "a\n")
    b = _side(git_repo, "b", "b.txt", "b\n")

    # When: 运行 merge S1=<a> S2=<b>
    p, out = merge(git_repo, "S1=" + a, "S2=" + b)

    # Then: 退出 0、merged 为 [S1, S2]；依次生成两个双亲 merge commit，说明为 integrate: S1 / integrate: S2（与逐条 git merge --no-ff 等价）
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert out == {"ok": True, "merged": ["S1", "S2"], "failed": [], "warnings": []}, out
    for rev, msg in (("HEAD~1", "integrate: S1"), ("HEAD", "integrate: S2")):
        assert git(git_repo, "log", "-1", "--format=%s", rev) == msg
        assert len(git(git_repo, "log", "-1", "--format=%P", rev).split()) == 2
    assert (git_repo / "a.txt").is_file() and (git_repo / "b.txt").is_file()


def test_merge_aborts_on_file_conflict(git_repo):
    # Given: 没有 submodule 的仓库；两个旁支把 README.md 改成不同内容
    a = _side(git_repo, "a", "README.md", "# a\n")
    b = _side(git_repo, "b", "README.md", "# b\n")

    # When: 运行 merge S1=<a> S2=<b>
    p, out = merge(git_repo, "S1=" + a, "S2=" + b)

    # Then: 退出 1、merged 为 [S1]，failed 首项以 merge S2 开头并点名 README.md；不在合并中，HEAD 停在 integrate: S1
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert out["ok"] is False and out["merged"] == ["S1"], out
    assert out["failed"][0].startswith("merge S2") and "README.md" in out["failed"][0], out["failed"]
    assert not _in_merge(git_repo)
    assert git(git_repo, "log", "-1", "--format=%s") == "integrate: S1"


def test_next_wave_populates_from_merged_gitlink(tmp_path):
    # Given: wave 1 的 S1、S2 已由 merge 合回家里（父仓 gitlink = 家子仓里的合并提交）
    env = make_super(tmp_path)
    r1, r2 = run_executor(env, "S1", "lib1"), run_executor(env, "S2", "lib2")
    assert merge(env.home, "S1=" + r1.commit, "S2=" + r2.commit)[0].returncode == 0

    # When: wave 2 的 S3 在新的隔离 worktree 里走完执行体流程（start → 子仓提交 → gitlink → gate）
    r3 = run_executor(env, "S3", "lib3")

    # Then: S3 的子仓检出起点是合并后的 gitlink（lib1.py、lib2.py 都在场），门禁绿
    assert (r3.iso / SUB / "lib1.py").is_file() and (r3.iso / SUB / "lib2.py").is_file()
    assert r3.gate["ok"] is True, r3.gate
