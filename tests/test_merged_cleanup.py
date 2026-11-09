"""合并后清理的判定与执行（scenario: merged-cleanup-plan#plan-removes-merged-clean-worktree、#plan-detects-squash-merge、
#plan-keeps-fresh-and-unmerged、#plan-forces-flight-records-only、#plan-defers-other-dirty-to-user、
#plan-defers-locked-and-outside-worktrees、#plan-guards-unpushed-submodule-commit、#apply-prunes-borrowed-submodule-worktree、
#apply-syncs-target-before-branch-delete、#plan-lists-remote-delete-for-user、#apply-removes-landed-flight-refs、
#plan-refuses-outside-main-worktree，共 12 条）。

夹具：裸仓 `origin.git` + 主 checkout `main`（分支 main，跟踪 origin/main）；「服务器」克隆 `srv` 模拟 PR 合并
（--no-ff 或 squash，缺省删远端分支）。子仓场景另有子仓远端 `sub.git`，change 家 `.worktrees/c` 在自己的 linked worktree
里初始化子仓（仓库本体位于 `.git/worktrees/c/modules/mods/sub`）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json
import subprocess
import types

import pytest


from conftest import run_hook, write

HOOK = "merged-cleanup"


def g(cwd, *args):
    """git（带 protocol.file.allow=always，本地路径 submodule 要用）；失败抛 CalledProcessError。"""
    return subprocess.run(["git", "-c", "protocol.file.allow=always", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout.strip()


def ok(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True).returncode == 0


def has_ref(repo, ref):
    return ok(repo, "rev-parse", "--verify", "-q", ref)


def ident(repo):
    g(repo, "config", "user.email", "t@example.com")
    g(repo, "config", "user.name", "t")


def commit(repo, files, msg):
    for rel, text in files.items():
        write(repo / rel, text)
    g(repo, "add", "-A")
    g(repo, "commit", "-q", "-m", msg)
    return g(repo, "rev-parse", "HEAD")


@pytest.fixture
def w(tmp_path):
    origin = tmp_path / "origin.git"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    main = tmp_path / "main"
    main.mkdir()
    g(main, "init", "-q", "-b", "main")
    ident(main)
    commit(main, {"README.md": "r\n"}, "init")
    g(main, "remote", "add", "origin", str(origin))
    g(main, "push", "-q", "-u", "origin", "main")
    return types.SimpleNamespace(tmp=tmp_path, origin=origin, main=main)


def feature(w, name, files=None, path=None, base="main"):
    """建 worktree（分支 worktree-<name>，缺省路径 .worktrees/<name>）并提交 files（缺省一个 <name>.py）。"""
    rel = path or ".worktrees/" + name
    g(w.main, "worktree", "add", "-q", rel, "-b", "worktree-" + name, base)
    wt = w.main / rel
    commit(wt, files or {name + ".py": "x = 1\n"}, "feat: " + name)
    return wt


def srv(w):
    s = w.tmp / "srv"
    if not s.exists():
        g(w.tmp, "clone", "-q", str(w.origin), str(s))
        ident(s)
    g(s, "fetch", "-q", "--prune", "origin")
    g(s, "checkout", "-q", "main")
    g(s, "reset", "-q", "--hard", "origin/main")
    return s


def land(w, branch, squash=False, keep_remote=False, upstream=False):
    """把本地分支推到远端，在 srv 里合入 main 并推回，模拟 PR 合并（缺省 --no-ff、删远端分支）。"""
    g(w.main, "push", "-q", *(["-u"] if upstream else []), "origin", branch)
    s = srv(w)
    if squash:
        g(s, "merge", "-q", "--squash", "origin/" + branch)
        g(s, "commit", "-q", "-m", "squash " + branch)
    else:
        g(s, "merge", "-q", "--no-ff", "origin/" + branch, "-m", "Merge " + branch)
    g(s, "push", "-q", "origin", "main")
    if not keep_remote:
        g(s, "push", "-q", "origin", "--delete", branch)


def sync(w):
    g(w.main, "fetch", "-q", "--prune", "origin")
    g(w.main, "merge", "-q", "--ff-only", "origin/main")


def run(cwd, *args):
    return run_hook(HOOK, *args, cwd=str(cwd))


def plan(w, *extra):
    r = run(w.main, "plan", *extra)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def apply(w, *extra):
    r = run(w.main, "apply", *extra)
    return r.returncode, json.loads(r.stdout)


def item(out, kind, name):
    hit = [i for i in out["items"] if i["kind"] == kind and i["name"] == name]
    assert len(hit) == 1, (kind, name, out["items"])
    return hit[0]


def has_reason(it, tag):
    return any(r.startswith(tag) for r in it["reasons"])


def with_sub(w):
    """主仓加 submodule mods/sub（子仓远端 sub.git）并推送。"""
    seed = w.tmp / "sub-seed"
    seed.mkdir()
    g(seed, "init", "-q", "-b", "main")
    ident(seed)
    commit(seed, {"a.txt": "a\n"}, "init")
    sub_origin = w.tmp / "sub.git"
    g(w.tmp, "clone", "-q", "--bare", str(seed), str(sub_origin))
    g(w.main, "submodule", "add", "-q", str(sub_origin), "mods/sub")
    g(w.main, "commit", "-q", "-m", "add sub")
    g(w.main, "push", "-q", "origin", "main")


def home_with_sub_commit(w):
    """change 家 .worktrees/c：在自己的 linked worktree 里初始化子仓，提交一个未推送的子仓提交并钉 gitlink。"""
    g(w.main, "worktree", "add", "-q", ".worktrees/c", "-b", "worktree-c")
    home = w.main / ".worktrees" / "c"
    g(home, "submodule", "update", "--init", "-q")
    sub = home / "mods" / "sub"
    ident(sub)
    sha = commit(sub, {"b.txt": "b\n"}, "sub: b")
    g(home, "add", "mods/sub")
    g(home, "commit", "-q", "-m", "bump sub")
    return home, sha


def test_plan_removes_merged_clean_worktree(w):
    # Given: worktree-a 带一个提交，已在远端以 --no-ff 合入 main，本地 main 已同步；.worktrees/a 干净
    feature(w, "a")
    land(w, "worktree-a")
    sync(w)

    # When: 在主 worktree 运行 plan
    out = plan(w)

    # Then: worktree 项 ancestor / safe / 不 force，命令为 git worktree remove .worktrees/a；分支项 safe，命令 git branch -d worktree-a
    wt = item(out, "worktree", ".worktrees/a")
    assert (wt["merged"], wt["tier"], wt["force"]) == ("ancestor", "safe", False), wt
    assert wt["command"] == "git worktree remove .worktrees/a", wt
    br = item(out, "branch", "worktree-a")
    assert br["tier"] == "safe" and br["command"] == "git branch -d worktree-a", br


def test_plan_detects_squash_merge(w):
    # Given: worktree-s 的改动在远端以 squash 合入 main（tip 不是 main 的祖先），worktree 干净，本地已同步
    feature(w, "s")
    land(w, "worktree-s", squash=True)
    sync(w)

    # When: 运行 plan
    out = plan(w)

    # Then: 分支项 content / manual，命令 git branch -D worktree-s，原因以 content 开头；worktree 项 safe
    br = item(out, "branch", "worktree-s")
    assert (br["merged"], br["tier"]) == ("content", "manual"), br
    assert br["command"] == "git branch -D worktree-s" and has_reason(br, "content"), br
    assert item(out, "worktree", ".worktrees/s")["tier"] == "safe"


def test_plan_keeps_fresh_and_unmerged(w):
    # Given: 刚从 main 建出的 .worktrees/f（无独有提交）；worktree-u 带一个未合并提交
    g(w.main, "worktree", "add", "-q", ".worktrees/f", "-b", "worktree-f")
    feature(w, "u")

    # When: 运行 plan，再运行 apply --no-fetch
    out = plan(w)
    rc, res = apply(w, "--no-fetch")

    # Then: 两个 worktree 与两个分支都是 keep（fresh / unmerged）；apply 之后都还在
    for kind, name, state in (("worktree", ".worktrees/f", "fresh"), ("worktree", ".worktrees/u", "unmerged"),
                              ("branch", "worktree-f", "fresh"), ("branch", "worktree-u", "unmerged")):
        it = item(out, kind, name)
        assert (it["merged"], it["tier"]) == (state, "keep"), it
    assert rc == 0, res
    assert (w.main / ".worktrees" / "f").is_dir() and (w.main / ".worktrees" / "u").is_dir()
    assert has_ref(w.main, "refs/heads/worktree-f") and has_ref(w.main, "refs/heads/worktree-u")


def test_plan_forces_flight_records_only(w):
    # Given: 已合并的临时 worktree .claude/worktrees/wf_1，未提交改动只有已跟踪的 timeline.md 被改、未跟踪的 gate-report.md
    wt = feature(w, "wf_1", files={"openspec/changes/c/timeline.md": "t0\n", "x.py": "x = 1\n"},
                 path=".claude/worktrees/wf_1")
    land(w, "worktree-wf_1")
    sync(w)
    write(wt / "openspec/changes/c/timeline.md", "t0\nt1\n")
    write(wt / "openspec/changes/c/gate-report.md", "g\n")

    # When: 运行 plan
    out = plan(w)

    # Then: safe + force，命令带 --force，原因以 flight-records 开头
    it = item(out, "worktree", ".claude/worktrees/wf_1")
    assert (it["tier"], it["force"]) == ("safe", True), it
    assert it["command"] == "git worktree remove --force .claude/worktrees/wf_1", it
    assert has_reason(it, "flight-records"), it


def test_plan_defers_other_dirty_to_user(w):
    # Given: 已合并的 .worktrees/d 里有一个未跟踪的 src/new.py
    wt = feature(w, "d")
    land(w, "worktree-d")
    sync(w)
    write(wt / "src/new.py", "y = 2\n")

    # When: 运行 plan、plan --markdown，再运行 apply --no-fetch
    out = plan(w)
    md = run(w.main, "plan", "--markdown")
    rc, res = apply(w, "--no-fetch")

    # Then: manual + force，dirty 含 src/new.py，原因以 dirty 开头；命令进顶层 manual 与 markdown；apply 不执行它
    it = item(out, "worktree", ".worktrees/d")
    cmd = "git worktree remove --force .worktrees/d"
    assert (it["tier"], it["force"]) == ("manual", True) and "src/new.py" in it["dirty"], it
    assert has_reason(it, "dirty"), it
    assert cmd in out["manual"], out["manual"]
    assert md.returncode == 0 and cmd in md.stdout, md.stdout
    assert (wt / "src" / "new.py").is_file() and cmd in res["manual"], res


def test_plan_defers_locked_and_outside_worktrees(w):
    # Given: 已合并且干净的 .worktrees/l 被 lock（reason "agent running"）；另一个已合并且干净的 worktree 在仓库目录之外
    feature(w, "l")
    land(w, "worktree-l")
    outside = feature(w, "o", path=str(w.tmp / "outside-wt"))
    land(w, "worktree-o")
    sync(w)
    g(w.main, "worktree", "lock", "--reason", "agent running", ".worktrees/l")

    # When: 运行 plan，再运行 apply --no-fetch
    out = plan(w)
    apply(w, "--no-fetch")

    # Then: 前者 manual（locked，含 agent running），后者 manual（outside）；apply 之后两者都在
    lk = item(out, "worktree", ".worktrees/l")
    assert lk["tier"] == "manual", lk
    assert any(r.startswith("locked") and "agent running" in r for r in lk["reasons"]), lk
    ot = [i for i in out["items"] if i["kind"] == "worktree" and i["name"].endswith("outside-wt")]
    assert len(ot) == 1 and ot[0]["tier"] == "manual" and has_reason(ot[0], "outside"), ot
    assert (w.main / ".worktrees" / "l").is_dir() and outside.is_dir()


def test_plan_defers_locked_missing_worktree(w):
    # Given: 已合并的 .worktrees/l 被 lock（reason "agent running"）后目录被 rm -rf；另有已合并且干净的 .worktrees/a
    import shutil
    feature(w, "l")
    land(w, "worktree-l")
    feature(w, "a")
    land(w, "worktree-a")
    sync(w)
    g(w.main, "worktree", "lock", "--reason", "agent running", ".worktrees/l")
    shutil.rmtree(str(w.main / ".worktrees" / "l"))

    # When: 运行 plan 与 apply --no-fetch，再执行该项的 manual 命令
    out = plan(w)
    rc, res = apply(w, "--no-fetch")
    lk = item(out, "worktree", ".worktrees/l")
    fix = subprocess.run(lk["command"], shell=True, cwd=str(w.main), capture_output=True, text=True)

    # Then: 不崩溃；l 为 manual，原因含 locked 与 missing；其他项照常判定并执行；manual 命令能清掉该登记
    assert lk["tier"] == "manual" and has_reason(lk, "locked") and has_reason(lk, "missing"), lk
    assert lk["command"] in out["manual"], out["manual"]
    assert item(out, "worktree", ".worktrees/a")["tier"] == "safe"
    assert rc == 0 and res["failed"] == [], res
    assert not (w.main / ".worktrees" / "a").exists()
    assert fix.returncode == 0, fix.stderr
    assert ".worktrees/l" not in g(w.main, "worktree", "list")


def test_plan_guards_unpushed_submodule_commit(w):
    # Given: 主仓含 mods/sub；change 家 .worktrees/c 在子仓提交了未推送的提交并钉 gitlink；worktree-c 已合入远端 main
    with_sub(w)
    home, _ = home_with_sub_commit(w)
    land(w, "worktree-c")
    sync(w)

    # When: 运行 plan；再把子仓提交推到子仓远端后重跑 plan
    first = item(plan(w), "worktree", ".worktrees/c")
    g(home / "mods" / "sub", "push", "-q", "origin", "HEAD:refs/heads/feat")
    second = item(plan(w), "worktree", ".worktrees/c")

    # Then: 推送前 manual + force，原因以 unpushed-submodule 开头且含 mods/sub；推送后 safe，原因以 submodule 开头
    assert (first["tier"], first["force"]) == ("manual", True), first
    assert any(r.startswith("unpushed-submodule") and "mods/sub" in r for r in first["reasons"]), first
    assert second["tier"] == "safe" and has_reason(second, "submodule"), second


def test_apply_prunes_borrowed_submodule_worktree(w):
    # Given: 家 .worktrees/c（子仓提交未推送）；临时 worktree .claude/worktrees/wf_1 的 mods/sub 是从家子仓借出的 linked worktree；
    #        worktree-wf_1 的提交经 worktree-c 合入远端 main，wf_1 干净，主仓已 fetch
    with_sub(w)
    home, sha = home_with_sub_commit(w)
    g(w.main, "worktree", "add", "-q", ".claude/worktrees/wf_1", "-b", "worktree-wf_1", "worktree-c")
    wf = w.main / ".claude" / "worktrees" / "wf_1"
    g(home / "mods" / "sub", "worktree", "add", "-q", "--detach", str(wf / "mods" / "sub"), sha)
    commit(wf, {"x.py": "x = 1\n"}, "feat: wf_1")
    g(home, "merge", "-q", "--no-ff", "worktree-wf_1", "-m", "integrate: wf_1")
    land(w, "worktree-c")
    g(w.main, "fetch", "-q", "--prune", "origin")

    # When: 运行 apply --no-fetch
    rc, res = apply(w, "--no-fetch")

    # Then: wf_1 被 --force 删除；家子仓的 worktree list 不再列出它；家 worktree 仍在
    assert "git worktree remove --force .claude/worktrees/wf_1" in res["done"], res
    assert not wf.exists()
    assert "wf_1" not in g(home / "mods" / "sub", "worktree", "list")
    assert home.is_dir()


def test_apply_syncs_target_before_branch_delete(w):
    # Given: worktree-wf_1（无 upstream）经 change 分支 worktree-c（有 upstream）合入远端 main，远端已删 worktree-c；
    #        两者的 worktree 已删除；主 worktree 在 main 上、干净，但落后于 origin/main（2026-11-09 实测形态）
    home = feature(w, "c")
    feature(w, "wf_1", path=".claude/worktrees/wf_1", base="worktree-c")
    g(home, "merge", "-q", "--no-ff", "worktree-wf_1", "-m", "integrate: wf_1")
    land(w, "worktree-c", upstream=True)
    g(w.main, "worktree", "remove", ".claude/worktrees/wf_1")
    g(w.main, "worktree", "remove", ".worktrees/c")

    # When: 运行 apply（含 fetch --prune）
    rc, res = apply(w)

    # Then: main 快进到 origin/main；两个分支都已删除；ff 同步排在 branch -d 之前；无失败、退出 0
    assert rc == 0 and res["failed"] == [], res
    assert g(w.main, "rev-parse", "main") == g(w.main, "rev-parse", "origin/main")
    assert not has_ref(w.main, "refs/heads/worktree-wf_1") and not has_ref(w.main, "refs/heads/worktree-c")
    done = res["done"]
    assert done.index("git merge --ff-only origin/main") < done.index("git branch -d worktree-wf_1"), done


def test_plan_lists_remote_delete_for_user(w):
    # Given: worktree-a 已合入远端 main，远端分支 worktree-a 仍在；主仓已 fetch 并同步
    feature(w, "a")
    land(w, "worktree-a", keep_remote=True)
    sync(w)

    # When: 运行 plan，再运行 apply --no-fetch
    out = plan(w)
    apply(w, "--no-fetch")

    # Then: remote 项 origin/worktree-a 为 manual，命令 git push origin --delete worktree-a；apply 之后远端分支仍在
    it = item(out, "remote", "origin/worktree-a")
    assert it["tier"] == "manual" and it["command"] == "git push origin --delete worktree-a", it
    assert "refs/heads/worktree-a" in g(w.main, "ls-remote", "--heads", "origin")


def test_apply_removes_landed_flight_refs(w):
    # Given: 远端 main 树里有 openspec/changes/c/proposal.md、没有 openspec/changes/d/；本地有 refs/flight/c/S1 与 refs/flight/d/S1
    s = srv(w)
    commit(s, {"openspec/changes/c/proposal.md": "p\n"}, "land c")
    g(s, "push", "-q", "origin", "main")
    sync(w)
    head = g(w.main, "rev-parse", "HEAD")
    g(w.main, "update-ref", "refs/flight/c/S1", head)
    g(w.main, "update-ref", "refs/flight/d/S1", head)

    # When: 运行 apply --no-fetch
    rc, res = apply(w, "--no-fetch")

    # Then: c 的快照 ref 被删除，d 的仍在
    assert rc == 0, res
    assert not has_ref(w.main, "refs/flight/c/S1")
    assert has_ref(w.main, "refs/flight/d/S1")


def test_plan_refuses_outside_main_worktree(w):
    # Given: 已合并且干净的 .worktrees/a
    wt = feature(w, "a")
    land(w, "worktree-a")
    sync(w)

    # When: 以 .worktrees/a 为当前目录运行 plan 与 apply --no-fetch
    runs = [run(wt, "plan"), run(wt, "apply", "--no-fetch")]

    # Then: 都退出 2、ok 为假、原因以 not-main-worktree 开头；worktree 与分支都还在
    for r in runs:
        out = json.loads(r.stdout)
        assert r.returncode == 2 and out["ok"] is False, r.stdout
        assert any(x.startswith("not-main-worktree") for x in out["reasons"]), out
    assert wt.is_dir() and has_ref(w.main, "refs/heads/worktree-a")

def test_plan_in_project_that_is_a_submodule(w):
    # Given: 本项目（origin.git）作为父仓 parent 的 submodule proj 检出（gitdir 在 parent/.git/modules/proj）；
    #        proj 有分支 worktree-x，父仓有分支 worktree-parent-only
    parent = w.tmp / "parent"
    parent.mkdir()
    g(parent, "init", "-q", "-b", "main")
    ident(parent)
    commit(parent, {"p.txt": "p\n"}, "init")
    g(parent, "submodule", "add", "-q", str(w.origin), "proj")
    g(parent, "commit", "-q", "-m", "add proj")
    g(parent, "branch", "worktree-parent-only")
    proj = parent / "proj"
    g(proj, "branch", "worktree-x")

    # When: 在 parent/proj 里运行 plan --target main
    r = run(proj, "plan", "--target", "main")
    out = json.loads(r.stdout)

    # Then: 只处理 proj 自己：列出 worktree-x，不出现父仓的 worktree-parent-only
    assert r.returncode == 0 and out["ok"] is True, r.stdout + r.stderr
    names = [i["name"] for i in out["items"]]
    assert "worktree-x" in names and "worktree-parent-only" not in names, out["items"]
