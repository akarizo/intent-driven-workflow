"""submodule 场景的玩具仓夹具（change submodule-aware-flight）。

形态与 afa raw-file-viewer 一致：
- 子仓 origin `<tmp>/origin`：一个初始提交；
- 主 checkout `<tmp>/main`（分支 main）：`mods/sub` 指向 origin，带基座选测声明；
- change 家 `<tmp>/home`（分支 worktree-c）：submodule 已初始化，子仓分支 feat-sub 上有一个**未 push** 的本地提交，
  父仓钉了这个 gitlink，并提交了 change c 的计划；
- 隔离 worktree 由 `iso()` 从主 checkout `git worktree add --detach` 建出（模拟 Claude Code 的 isolation: worktree），
  其中 submodule 是空目录。
"""
import json
import subprocess
import types

from conftest import SCOPE_DECL, run_hook, write

SUB = "mods/sub"
BRANCH = "worktree-c"
SUB_BRANCH = "feat-sub"
CHANGE = "openspec/changes/c"

SRC = "def {fn}(a, b):\n    return a + b\n"
TEST = '''
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from {mod} import {fn}


def test_{fn}():
    # Given: 两个整数 1 与 2
    a, b = 1, 2
    # When: 调用 {fn}
    result = {fn}(a, b)
    # Then: 返回 3
    assert result == 3
'''


def g(cwd, *args):
    """git（带 protocol.file.allow=always，本地路径 submodule 要用）；失败抛 CalledProcessError。"""
    return subprocess.run(["git", "-c", "protocol.file.allow=always", *args], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout.strip()


def git_rc(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True).returncode


def _ident(repo):
    g(repo, "config", "user.email", "t@example.com")
    g(repo, "config", "user.name", "t")


def _slice(sid, mod, deps=()):
    return {"id": sid, "title": sid, "packet": "slices/%s.md" % sid, "deps": list(deps),
            "owns": ["%s/%s.py" % (SUB, mod), "%s/tests/test_%s.py" % (SUB, mod)],
            "verify": "python3 -m pytest -q %s/tests/test_%s.py" % (SUB, mod),
            "scenarios": ["cap#%s" % mod]}


# 三片都改子仓：S1 ∥ S2 同 wave，S3 依赖二者
SLICES = (("S1", "lib1", ()), ("S2", "lib2", ()), ("S3", "lib3", ("S1", "S2")))


def plan_data():
    return {
        "version": 1, "change": "c",
        "gate": {"test": "python3 -m pytest -q %s/tests" % SUB, "lint": None, "typecheck": None, "full_suite_sec": None},
        "slices": [_slice(s, m, d) for s, m, d in SLICES],
        "scenario_tests": {"cap#%s" % m: "%s/tests/test_%s.py::test_%s" % (SUB, m, m) for _, m, _ in SLICES},
    }


def make_super(tmp_path):
    """建好 origin / main / home 三处，返回 namespace(main, home, origin, change, gitlink)。"""
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "main")
    _ident(origin)
    write(origin / "README.md", "# sub\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "s0")

    main = tmp_path / "main"
    main.mkdir()
    g(main, "init", "-q", "-b", "main")
    _ident(main)
    write(main / "README.md", "# t\n")
    write(main / "openspec" / "gate-scope.json", json.dumps(SCOPE_DECL) + "\n")
    g(main, "submodule", "add", "-q", str(origin), SUB)
    g(main, "add", "-A")
    g(main, "commit", "-q", "-m", "init")

    home = tmp_path / "home"
    g(main, "worktree", "add", "-q", "-b", BRANCH, str(home))
    g(home, "submodule", "update", "-q", "--init")
    sub = home / SUB
    _ident(sub)
    g(sub, "switch", "-q", "-c", SUB_BRANCH)
    write(sub / "base.py", "BASE = 1\n")
    g(sub, "add", "base.py")
    g(sub, "commit", "-q", "-m", "local, not pushed")
    change = home / CHANGE
    write(change / "slices.json", json.dumps(plan_data(), ensure_ascii=False, indent=1))
    for sid, _, _ in SLICES:
        write(change / "slices" / ("%s.md" % sid), "# %s\n" % sid)
    write(change / "tasks.md", "".join("- [ ] %s x\n" % s for s, _, _ in SLICES))
    g(home, "add", SUB, "openspec")
    g(home, "commit", "-q", "-m", "artifacts + gitlink")
    return types.SimpleNamespace(main=main, home=home, origin=origin, change=change,
                                 gitlink=g(home, "rev-parse", "HEAD:" + SUB))


def iso(env, name, ref=BRANCH):
    """从主 checkout 建一个 detached 隔离 worktree（submodule 未填充），返回路径。"""
    path = env.main.parent / ("iso-" + name)
    g(env.main, "worktree", "add", "-q", "--detach", str(path), ref)
    return path


def start(cwd, sid, *extra):
    return run_hook("slice-gate", "start", sid, "--change-dir", CHANGE, *extra, cwd=cwd)


def gate(cwd, sid):
    p = run_hook("slice-gate", "gate", sid, "--change-dir", CHANGE, cwd=cwd)
    return p, (json.loads(p.stdout) if p.stdout.strip() else None)


def write_impl(cwd, mod, extra=""):
    """在 cwd 的子仓里写 <mod>.py（末尾附 extra）与配对测试，返回两者的子仓相对路径。"""
    sub = cwd / SUB
    write(sub / ("%s.py" % mod), SRC.format(fn=mod) + extra)
    write(sub / "tests" / ("test_%s.py" % mod), TEST.format(mod=mod, fn=mod))
    return ["%s.py" % mod, "tests/test_%s.py" % mod]


def commit_sub(cwd, msg, paths):
    sub = cwd / SUB
    g(sub, "add", *paths)
    g(sub, "commit", "-q", "-m", msg)
    return g(sub, "rev-parse", "HEAD")


def commit_parent(cwd, msg, *paths):
    g(cwd, "add", *(paths or (SUB,)))
    g(cwd, "commit", "-q", "-m", msg)
    return g(cwd, "rev-parse", "HEAD")


def run_executor(env, sid, mod, name=None):
    """模拟一个隔离执行体走完：建隔离 worktree → start（--expect-branch）→ 子仓提交 → 父仓提交 gitlink → gate。
    返回 namespace(iso, start, gate_proc, gate, sub_commit, commit)。"""
    path = iso(env, name or sid)
    st = start(path, sid, "--expect-branch", BRANCH)
    assert st.returncode == 0, (st.stdout, st.stderr)
    sub_commit = commit_sub(path, "%s sub" % sid, write_impl(path, mod))
    commit = commit_parent(path, "%s" % sid)
    p, out = gate(path, sid)
    return types.SimpleNamespace(iso=path, start=st, gate_proc=p, gate=out, sub_commit=sub_commit, commit=commit)
