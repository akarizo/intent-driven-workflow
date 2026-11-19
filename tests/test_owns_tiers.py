"""owns 条数上限随轮次档、宽通配要写理由（scenario: owns-tiers#owns-cap-follows-turn-tier、#wide-glob-needs-reason、
#lint-prints-glob-expansion、#approved-change-not-reddened-by-wide-rule，共 4 条）。"""
import json

from conftest import commit_all, run_hook, write
from test_slice_gate import plan, slice_


WIDE = "lib/*.py"
EXPANSION = "owns: S1 %s → 21 个文件" % WIDE


def put_plan(repo, slices):
    """写计划并提交（git_repo 夹具已带选测声明）。返回 change 目录。"""
    change = repo / "openspec" / "changes" / "c"
    write(change / "slices.json", json.dumps(plan(slices), ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return change


def waves(repo, change):
    return run_hook("slice-gate", "waves", "--change-dir", str(change), cwd=repo)


def wide_repo(repo, extra_owns=(), owns_wide=None, approved=False):
    """lib/ 下 21 个现存文件；切片 S1 的 owns 是通配 lib/*.py（加 extra_owns）。"""
    for i in range(1, 22):
        write(repo / "lib" / ("m%02d.py" % i), "X = %d\n" % i)
    s1 = slice_("S1", [WIDE] + list(extra_owns))
    if owns_wide is not None:
        s1["owns_wide"] = owns_wide
    change = repo / "openspec" / "changes" / "c"
    if approved:
        write(change / "timeline.md", "2026-11-18T00:00:00Z\tapprove\t2026-11-18T00:00:00Z · 起飞\n")
    return put_plan(repo, [s1])


def set_slice(change, repo, sid, **fields):
    data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    for s in data["slices"]:
        if s["id"] == sid:
            s.update(fields)
    write(change / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan edit")


def test_owns_cap_follows_turn_tier(git_repo):
    # Given: 切片 S1 的 13 条 owns 都是现存文件；切片 S2 的 13 条 owns 里只有 2 个现存文件
    big = ["a/f%02d.py" % i for i in range(1, 14)]
    small = ["b/g1.py", "b/g2.py"] + ["b/n%02d.py" % i for i in range(1, 12)]
    for rel in big + small[:2]:
        write(git_repo / rel, "X = 1\n")
    change = put_plan(git_repo, [slice_("S1", big), slice_("S2", small)])

    # When: 运行 waves；给 S2 写上 turns: large 后再运行；再把 S1 的 owns 加到 31 条后运行
    first = waves(git_repo, change)
    set_slice(change, git_repo, "S2", turns="large")
    second = waves(git_repo, change)
    set_slice(change, git_repo, "S1", owns=big + ["a/x%02d.py" % i for i in range(1, 19)])
    third = waves(git_repo, change)

    # Then: 第一次只判 S2 超限并写出两档上限；第二次通过；第三次判 S1 超限
    assert first.returncode == 2 and "S2 的 owns" in first.stderr, first.stderr
    assert "12" in first.stderr and "30" in first.stderr and "S1 的 owns" not in first.stderr, first.stderr
    assert second.returncode == 0, second.stderr
    assert third.returncode == 2 and "S1 的 owns" in third.stderr, third.stderr


def test_wide_glob_needs_reason(git_repo):
    # Given: 切片 S1 的 owns 是一条展开出 21 个现存文件的通配
    change = wide_repo(git_repo)

    # When: 运行 waves；写了理由后再运行；把理由改成空串后运行；把 owns_wide 的键换成不在 owns 里的条目后运行
    bare = waves(git_repo, change)
    set_slice(change, git_repo, "S1", owns_wide={WIDE: "整个目录的机械迁移"})
    reasoned = waves(git_repo, change)
    set_slice(change, git_repo, "S1", owns_wide={WIDE: " "})
    blank = waves(git_repo, change)
    set_slice(change, git_repo, "S1", owns_wide={WIDE: "整个目录的机械迁移", "docs/*.md": "没有这一条"})
    stray = waves(git_repo, change)

    # Then: 没写理由判红并点名通配、文件数与 owns_wide；写了通过；空理由与多余的键都判红
    assert bare.returncode == 2, bare.stderr
    assert WIDE in bare.stderr and "21" in bare.stderr and "owns_wide" in bare.stderr, bare.stderr
    assert reasoned.returncode == 0, reasoned.stderr
    assert blank.returncode == 2 and "owns_wide" in blank.stderr, blank.stderr
    assert stray.returncode == 2 and "owns_wide" in stray.stderr, stray.stderr


def test_lint_prints_glob_expansion(git_repo):
    # Given: 切片 S1 的 owns 有一条展开出 21 个现存文件的通配并写了理由，另有一条字面路径
    write(git_repo / "NOTES.txt", "x\n")
    change = wide_repo(git_repo, extra_owns=["NOTES.txt"], owns_wide={WIDE: "整个目录的机械迁移"})

    # When: 运行 waves
    p = waves(git_repo, change)

    # Then: 通过；stderr 有该通配的展开行；字面路径不出现在这类行里
    assert p.returncode == 0, p.stderr
    assert EXPANSION in p.stderr, p.stderr
    assert "NOTES.txt →" not in p.stderr


def test_approved_change_not_reddened_by_wide_rule(git_repo):
    # Given: 切片 S1 的 owns 是一条展开出 21 个现存文件的通配，没有写理由；该 change 的时间线已有 approve 事件
    change = wide_repo(git_repo, approved=True)

    # When: 运行 waves
    p = waves(git_repo, change)

    # Then: 不判红；仍打印展开行并提示 owns_wide
    assert p.returncode == 0, p.stderr
    assert EXPANSION in p.stderr and "owns_wide" in p.stderr, p.stderr
