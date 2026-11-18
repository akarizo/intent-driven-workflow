"""test-ledger.py：账本的合成、存取与 show 子命令（scenario: test-ledger#build-marks-measured-and-inherited 等 5 条）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json
import os
import pathlib

import pytest

from conftest import git, load_hook, run_hook, write

PENDING = pytest.mark.xfail(strict=True, reason="change test-ledger S1 未实现")

META = {"change": "c", "commit": "0" * 40, "at": "2026-11-18T00:00:00Z", "phase": "final", "mode": "incremental",
        "lock": "held"}
A, B, C = "tests/test_a.py::test_a", "tests/test_b.py::test_b", "tests/test_b.py::test_c"


def obs(form, outcomes, secs, **extra):
    return dict({"form": form, "outcomes": outcomes, "secs": secs}, **extra)


def tier_of(path):
    if path.startswith("tests/unit/"):
        return "unit"
    return "hooks" if "/hooks/" in path else None


@PENDING
def test_build_marks_measured_and_inherited():
    # Given: 全集三条用例；本次只实测到 B 与 C；来源有 A 与 B 的耗时
    tl = load_hook("test-ledger")
    universe = {A: "passed", B: "passed", C: "failed"}
    observations = [obs("nodeid", {B: "PASSED", C: "FAILED"}, {B: 0.2, C: 1.5})]
    source = {"cases": {A: {"o": "passed", "s": 0.4}, B: {"o": "passed", "s": 9.0}}}

    # When: 合成账本；再把来源里 A 的耗时去掉重做
    led = tl.build(META, observations, universe=universe, source=source, rerun_files=["tests/test_b.py"])
    led2 = tl.build(META, observations, universe=universe, source={"cases": {A: {"o": "passed", "s": None}}},
                    rerun_files=["tests/test_b.py"])

    # Then: B / C 是本次实测，A 沿用来源的耗时；来源没有耗时就记 null，不编数
    assert led["cases"][B] == {"o": "passed", "s": 0.2, "t": None, "m": 1}, led
    assert led["cases"][C] == {"o": "failed", "s": 1.5, "t": None, "m": 1}, led
    assert led["cases"][A] == {"o": "passed", "s": 0.4, "t": None, "m": 0}, led
    assert (led["v"], led["id_form"], led["complete"], led["change"], led["lock"]) == (1, "nodeid", True, "c", "held")
    assert led2["cases"][A] == {"o": "passed", "s": None, "t": None, "m": 0}, led2
    assert tl.summary(led2)["no_sec"] == 1
    assert tl.summary(led) == {"cases": 3, "measured": 2, "inherited": 1, "no_sec": 0, "id_form": "nodeid",
                               "complete": True, "tiers": {"-": {"cases": 3, "sec": 2.1}}}


@PENDING
def test_build_keeps_unrerun_cases_from_source_ledger(tmp_path):
    # Given: 没有全集；观测有 junit 与 nodeid 两种形式；来源账本是 junit 形式；只补跑了 tests/test_b.py
    tl = load_hook("test-ledger")
    write(tmp_path / "tests" / "test_a.py", "")
    write(tmp_path / "tests" / "test_b.py", "")
    observations = [obs("nodeid", {B: "PASSED"}, {B: 0.2}),
                    obs("junit", {"tests.test_b::test_b": "passed"}, {"tests.test_b::test_b": 0.2})]
    source = {"cases": {"tests.test_a::test_a": {"o": "passed", "s": 0.1},
                        "tests.test_b::test_old": {"o": "passed", "s": 0.3}}}

    # When: 合成账本；再不给来源重做；再只给 nodeid 形式的观测、来源标明是 junit 形式
    led = tl.build(META, observations, source=source, rerun_files=["tests/test_b.py"], root=str(tmp_path))
    led2 = tl.build(META, observations, rerun_files=["tests/test_b.py"], root=str(tmp_path))
    led3 = tl.build(META, observations[:1], source=dict(source, id_form="junit"), rerun_files=["tests/test_b.py"],
                    root=str(tmp_path))

    # Then: 只用 junit 形式；没补跑文件的用例沿用来源，被补跑文件里已不存在的用例不留；nodeid 观测换算后并入
    assert set(led["cases"]) == {"tests.test_a::test_a", "tests.test_b::test_b"}, led
    assert led["cases"]["tests.test_a::test_a"] == {"o": "passed", "s": 0.1, "t": None, "m": 0}
    assert led["cases"]["tests.test_b::test_b"] == {"o": "passed", "s": 0.2, "t": None, "m": 1}
    assert (led["id_form"], led["complete"]) == ("junit", True)
    assert led2["complete"] is False, led2
    assert led3["cases"] == led["cases"] and led3["id_form"] == "junit", led3


@PENDING
def test_build_attributes_tiers_per_case():
    # Given: 一条单元层用例、一条区域 hooks 的用例；另有一条 id 里没有文件路径、观测自带 tier 的用例
    tl = load_hook("test-ledger")
    u, h = "tests/unit/test_u.py::test_u", "tests/integration/hooks/test_h.py::test_h"
    observations = [obs("nodeid", {u: "PASSED", h: "PASSED"}, {u: 0.1, h: 5.0})]

    # When: 带 tier_of 合成、不带 tier_of 合成、用自带 tier 的观测合成
    led = tl.build(META, observations, tier_of=tier_of)
    led2 = tl.build(META, observations)
    led3 = tl.build(META, [obs("nodeid", {}, {"sh::sh::TestS": 0.01}, tier="unit")])

    # Then: 层按文件归属；不给 tier_of 就不分层；观测自带的 tier 优先
    assert (led["cases"][u]["t"], led["cases"][h]["t"], led["tiered"]) == ("unit", "hooks", True)
    assert tl.summary(led)["tiers"] == {"unit": {"cases": 1, "sec": 0.1}, "hooks": {"cases": 1, "sec": 5.0}}
    assert [c["t"] for c in led2["cases"].values()] == [None, None] and led2["tiered"] is False
    assert set(tl.summary(led2)["tiers"]) == {"-"}
    assert led3["cases"]["sh::sh::TestS"] == {"o": None, "s": 0.01, "t": "unit", "m": 1}, led3
    assert led3["tiered"] is True


@PENDING
def test_ledger_stored_per_change_in_git_common_dir(git_repo):
    # Given: 一个 git 仓库和它的一间 worktree；一份账本
    tl = load_hook("test-ledger")
    wt = git_repo.parent / "wt"
    git(git_repo, "worktree", "add", "-q", str(wt), "-b", "side")
    led = tl.build(META, [obs("nodeid", {A: "PASSED"}, {A: 0.1})])

    # When: 在主工作区存，在 worktree 里读；再造满 30 个 change 目录后给新 change 存一份
    path = tl.save(str(git_repo), "c", "baseline", led)
    back = tl.load(str(wt), "c", "baseline")
    base = git_repo / ".git" / "flight-ledger"
    for i in range(29):
        f = write(base / ("old%02d" % i) / "baseline.json", "{}")
        os.utime(f, (1000 + i, 1000 + i))
    tl.save(str(git_repo), "new", "baseline", led)

    # Then: 文件在 git common dir 下，worktree 读到同一份；不存在的返回 None；最旧的目录被清掉，剩 30 个
    assert pathlib.Path(path).resolve() == (base / "c" / "baseline.json").resolve()
    assert back == led
    assert tl.load(str(git_repo), "nope", "baseline") is None
    names = {p.name for p in base.iterdir() if p.is_dir()}
    assert "old00" not in names and {"c", "new", "old01", "old28"} <= names and len(names) == 30, sorted(names)


@PENDING
def test_show_lists_cases_by_tier_and_seconds(git_repo):
    # Given: change c 存有一份 final 账本：单元层两条（0.1 秒、2.0 秒），区域 hooks 一条（5.0 秒）
    tl = load_hook("test-ledger")
    d = git_repo / "openspec" / "changes" / "c"
    write(d / "proposal.md", "## Why\n")
    u1, u2, h = "tests/unit/test_u.py::test_fast", "tests/unit/test_u.py::test_slow", "tests/integration/hooks/test_h.py::test_h"
    led = tl.build(META, [obs("nodeid", {u1: "PASSED", u2: "PASSED", h: "PASSED"}, {u1: 0.1, u2: 2.0, h: 5.0})],
                   tier_of=tier_of)
    tl.save(str(git_repo), "c", "final", led)
    other = git_repo / "openspec" / "changes" / "none"
    write(other / "proposal.md", "## Why\n")

    # When: show --json；show --tier unit --top 1；对没有账本的 change 跑 show
    pj = run_hook("test-ledger", "show", "--change-dir", str(d), "--json", cwd=git_repo)
    pt = run_hook("test-ledger", "show", "--change-dir", str(d), "--tier", "unit", "--top", "1", cwd=git_repo)
    pn = run_hook("test-ledger", "show", "--change-dir", str(other), cwd=git_repo)

    # Then: 按耗时由大到小；摘要各层正确；筛层与条数生效；没有账本退出 1 并说明
    assert pj.returncode == 0, pj.stdout + pj.stderr
    j = json.loads(pj.stdout)
    assert [c["id"] for c in j["cases"]] == [h, u2, u1], j
    assert j["summary"]["tiers"] == {"unit": {"cases": 2, "sec": 2.1}, "hooks": {"cases": 1, "sec": 5.0}}, j
    assert pt.returncode == 0 and u2 in pt.stdout and u1 not in pt.stdout and h not in pt.stdout, pt.stdout
    assert pn.returncode == 1 and "没有账本" in (pn.stdout + pn.stderr), pn.stdout + pn.stderr
