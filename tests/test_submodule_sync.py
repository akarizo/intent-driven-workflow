"""隔离 worktree 的 submodule 从 change 家借出 linked worktree（scenario: submodule-worktree-sync#start-populates-isolated-submodule、
#executor-commit-visible-at-home、#start-refuses-when-home-submodule-missing、#start-skips-populate-when-base-check-fails、
#retry-after-cherry-pick-populates-new-gitlink、#checkpoint-covers-submodule、#preflight-refuses-unsynced-home-submodule、
#sub-sync-cli-for-fix，共 8 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。
护栏 start-skips-populate-when-base-check-fails 在 base 上已成立（G0 基点校验先于一切），不带 xfail。"""
import json

from conftest import run_hook, write
from submodule_helpers import (BRANCH, CHANGE, SUB, commit_parent, commit_sub, g, iso, make_super, run_executor, start,
                               write_impl)


def _populated(path):
    return (path / SUB / ".git").exists()


def test_start_populates_isolated_submodule(tmp_path):
    # Given: 从主 checkout 建出的隔离 worktree（HEAD = change 分支 tip），其中 mods/sub 是空目录；家里子仓的 gitlink 是本地未 push 的提交
    env = make_super(tmp_path)
    path = iso(env, "S1")
    assert not _populated(path)

    # When: 在隔离 worktree 里运行 start S1 --expect-branch worktree-c
    p = start(path, "S1", "--expect-branch", BRANCH)

    # Then: 退出 0；隔离 worktree 的子仓检出在 gitlink 上；家里子仓的 worktree 列表登记了这个目录（借出的 linked worktree，不访问远端）
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert _populated(path)
    assert g(path / SUB, "rev-parse", "HEAD") == env.gitlink
    assert str((path / SUB).resolve()) in g(env.home / SUB, "worktree", "list", "--porcelain")


def test_executor_commit_visible_at_home(tmp_path):
    # Given: 隔离 worktree 已 start（子仓已填充）
    env = make_super(tmp_path)
    path = iso(env, "S1")
    assert start(path, "S1", "--expect-branch", BRANCH).returncode == 0

    # When: 执行体在隔离 worktree 的子仓里提交
    sha = commit_sub(path, "S1 sub", write_impl(path, "lib1"))

    # Then: 家里子仓的对象库立即能找到这个提交（无需 fetch）
    assert g(env.home / SUB, "cat-file", "-t", sha) == "commit"


def test_start_refuses_when_home_submodule_missing(tmp_path):
    # Given: change 家里的子仓被 deinit（未初始化），隔离 worktree 的子仓同样为空
    env = make_super(tmp_path)
    g(env.home, "submodule", "deinit", "-q", "-f", SUB)
    path = iso(env, "S1")

    # When: 在隔离 worktree 里运行 start S1 --expect-branch worktree-c
    p = start(path, "S1", "--expect-branch", BRANCH)

    # Then: 退出 1；stdout 是 ok 为 false 的 JSON，failed 首项以 G0 submodule 开头，点名 mods/sub 并给出 git submodule update --init 修法；不写切片标记
    assert p.returncode == 1, (p.stdout, p.stderr)
    out = json.loads(p.stdout)
    assert out["ok"] is False
    assert out["failed"][0].startswith("G0 submodule") and SUB in out["failed"][0], out["failed"]
    assert "submodule update --init" in out["failed"][0]
    assert not (path / ".openspec-slice").exists()


def test_start_skips_populate_when_base_check_fails(tmp_path):
    # Given: change 分支又前进了一个提交；隔离 worktree 从它的上一个提交分叉（有计划，但不是分支 tip 的后代）
    env = make_super(tmp_path)
    write(env.home / "later.txt", "x\n")
    commit_parent(env.home, "later", "later.txt")
    path = iso(env, "S1", ref=BRANCH + "~1")

    # When: 运行 start S1 --expect-branch worktree-c
    p = start(path, "S1", "--expect-branch", BRANCH)

    # Then: 以 G0 base 拒绝（退出 1），子仓不被填充
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert json.loads(p.stdout)["failed"][0].startswith("G0 base")
    assert not _populated(path)


def test_retry_after_cherry_pick_populates_new_gitlink(tmp_path):
    # Given: 上一轮执行体在隔离 worktree A 里提交了子仓 s1 与父仓 C1（gitlink → s1）；重派开了新的隔离 worktree B
    env = make_super(tmp_path)
    first = run_executor(env, "S1", "lib1")
    path = iso(env, "S1-retry")

    # When: 按重派第零步 cherry-pick C1，再运行带上一轮 --base 的 start
    g(path, "cherry-pick", first.commit)
    base = json.loads(first.start.stdout)["base"]
    p = start(path, "S1", "--base", base, "--expect-branch", BRANCH)

    # Then: 退出 0；B 的子仓检出在 s1 上（新 gitlink），上一轮的文件在场
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert g(path / SUB, "rev-parse", "HEAD") == first.sub_commit
    assert (path / SUB / "lib1.py").is_file()


def test_checkpoint_covers_submodule(tmp_path):
    # Given: 隔离 worktree A 已 start S1，子仓里写了 owns 内的 lib1.py 但未提交；PostToolUse 快照 hook 跑过一次；执行体随后未返回
    env = make_super(tmp_path)
    a = iso(env, "S1")
    assert start(a, "S1", "--expect-branch", BRANCH).returncode == 0
    write(a / SUB / "lib1.py", "def lib1(a, b):\n    return a + b  # 半成品\n")
    ck = run_hook("slice-gate", "checkpoint", stdin=json.dumps({"cwd": str(a)}), cwd=a)
    assert ck.returncode == 0
    b = iso(env, "S1-retry")

    # When: 重派在新的隔离 worktree B 里运行 start S1 --resume-checkpoint --expect-branch worktree-c
    p = start(b, "S1", "--resume-checkpoint", "--expect-branch", BRANCH)

    # Then: 退出 0；checkpoint.restored 含 mods/sub/lib1.py；B 的子仓里该文件内容与 A 的半成品一致（未提交改动）
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert SUB + "/lib1.py" in json.loads(p.stdout)["checkpoint"]["restored"], p.stdout
    assert "半成品" in (b / SUB / "lib1.py").read_text(encoding="utf-8")


def test_preflight_refuses_unsynced_home_submodule(tmp_path):
    # Given: change 家里子仓多了一个本地提交，但父仓 gitlink 没跟上（子仓 HEAD ≠ gitlink）；计划的切片 owns 落在 mods/sub 里
    env = make_super(tmp_path)
    commit_sub(env.home, "unrecorded", write_impl(env.home, "lib9"))

    # When: 在家里运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", CHANGE, cwd=env.home)

    # Then: 退出非 0，stderr 点名 mods/sub 与 gitlink，在检查基线之前就拒绝起飞
    assert p.returncode != 0
    assert SUB in p.stderr and "gitlink" in p.stderr, p.stderr
    assert "缺基线" not in p.stderr


def test_sub_sync_cli_for_fix(tmp_path):
    # Given: 一个隔离 worktree（fix 执行体用；slices.json 没有 fix 条目，不能靠 start 填充）
    env = make_super(tmp_path)
    path = iso(env, "fix")

    # When: 运行 slice-gate.py sub-sync --expect-branch worktree-c --change-dir openspec/changes/c
    p = run_hook("slice-gate", "sub-sync", "--expect-branch", BRANCH, "--change-dir", CHANGE, cwd=path)

    # Then: 退出 0，stdout JSON 的 ok 为 true、synced 为 ["mods/sub"]；子仓检出在 gitlink 上；再跑一次幂等（synced 为空、仍 ok）
    assert p.returncode == 0, (p.stdout, p.stderr)
    out = json.loads(p.stdout)
    assert out["ok"] is True and out["synced"] == [SUB], out
    assert g(path / SUB, "rev-parse", "HEAD") == env.gitlink
    again = json.loads(run_hook("slice-gate", "sub-sync", "--expect-branch", BRANCH, "--change-dir", CHANGE, cwd=path).stdout)
    assert again["ok"] is True and again["synced"] == [], again
