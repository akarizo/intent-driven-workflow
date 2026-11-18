"""轮次分档：slice-gate.py turns 子命令与 lint 校验（scenario: turn-tiers#turns-computed-from-owned-files、
#turns-measured-at-baseline-commit、#turns-upgrade-declared-in-plan，共 3 条）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, git, run_hook, write
from test_slice_gate import plan, slice_, write_plan

PENDING = pytest.mark.xfail(strict=True, reason="change slice-resume-deterministic S3 未实现")


def tier_repo(git_repo, n_src, s1_extra=None, s2_extra=None):
    """S1 的 owns 是 src/**（仓库里有 n_src 个文件），S2 的 owns 是单个文件 lib/one.py。返回 change 目录。"""
    for i in range(n_src):
        write(git_repo / "src" / ("m%02d.py" % i), "X = %d\n" % i)
    write(git_repo / "lib" / "one.py", "ONE = 1\n")
    s1, s2 = slice_("S1", ["src/**"]), slice_("S2", ["lib/one.py"])
    s1.update(s1_extra or {})
    s2.update(s2_extra or {})
    change = write_plan(git_repo / "openspec" / "changes" / "c", plan([s1, s2]))
    commit_all(git_repo, "plan")
    return change


def turns(git_repo, change):
    p = run_hook("slice-gate", "turns", "--change-dir", str(change), cwd=git_repo)
    return p, (json.loads(p.stdout) if p.returncode == 0 else None)


def waves(git_repo, change):
    """waves 走同一套 lint 规则，但不跑选测命令。"""
    return run_hook("slice-gate", "waves", "--change-dir", str(change), cwd=git_repo)


@PENDING
def test_turns_computed_from_owned_files(git_repo):
    # Given: S1 的 owns 展开后在 HEAD 有 8 个现存文件，S2 有 1 个；没有基线
    change = tier_repo(git_repo, 8)

    # When: 运行 turns；再给 src/ 加第 9 个文件并提交，重新运行 turns
    p1, t1 = turns(git_repo, change)
    write(git_repo / "src" / "m08.py", "X = 8\n")
    commit_all(git_repo, "ninth")
    p2, t2 = turns(git_repo, change)

    # Then: 8 个文件是标准档，9 个是大片档；S2 始终是标准档；未提交的文件不计
    assert p1.returncode == 0 and p2.returncode == 0, (p1.stderr, p2.stderr)
    assert t1 == {"S1": "standard", "S2": "standard"}, t1
    assert t2 == {"S1": "large", "S2": "standard"}, t2
    write(git_repo / "lib" / "untracked.py", "U = 1\n")
    assert turns(git_repo, change)[1] == t2


@PENDING
def test_turns_measured_at_baseline_commit(git_repo):
    # Given: 基线记录的 commit 上 S1 有 8 个现存文件；之后实现又提交了 3 个新文件
    change = tier_repo(git_repo, 8)
    base = git(git_repo, "rev-parse", "HEAD")
    write(change / "gate-baseline.json", json.dumps({"commit": base, "ok": True}) + "\n")
    for i in (8, 9, 10):
        write(git_repo / "src" / ("m%02d.py" % i), "X = %d\n" % i)
    commit_all(git_repo, "impl")

    # When: 运行 turns；再把基线的 commit 改成对象库里没有的值，重新运行 turns
    _, measured = turns(git_repo, change)
    write(change / "gate-baseline.json", json.dumps({"commit": "0" * 40, "ok": True}) + "\n")
    _, fallback = turns(git_repo, change)

    # Then: 有基线时按基线那个 commit 的树数，飞行中新增的文件不改变档位；基线 commit 取不到时退回按 HEAD 数
    assert measured == {"S1": "standard", "S2": "standard"}, measured
    assert fallback == {"S1": "large", "S2": "standard"}, fallback


@PENDING
def test_turns_upgrade_declared_in_plan(git_repo):
    # Given: S1 展开后有 9 个现存文件（按规模是大片档）；S2 只有 1 个文件但计划里写了 "turns": "large"
    change = tier_repo(git_repo, 9, s2_extra={"turns": "large"})

    # When: 运行 turns 与 waves；再把 S1 写成 "turns": "standard"、把 S2 写成 "turns": "huge"，各运行一次 waves
    _, t = turns(git_repo, change)
    ok = waves(git_repo, change)
    data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    data["slices"][0]["turns"] = "standard"
    write_plan(change, data)
    downgrade = waves(git_repo, change)
    data["slices"][0].pop("turns")
    data["slices"][1]["turns"] = "huge"
    write_plan(change, data)
    unknown = waves(git_repo, change)

    # Then: 计划可以把小片升到大片档；按规模是大片档的不能写回标准档；未知取值判红；两处都点名切片与 turns
    assert t == {"S1": "large", "S2": "large"}, t
    assert ok.returncode == 0, ok.stderr
    assert downgrade.returncode == 2 and "turns" in downgrade.stderr and "S1" in downgrade.stderr, downgrade.stderr
    assert unknown.returncode == 2 and "turns" in unknown.stderr and "S2" in unknown.stderr, unknown.stderr
