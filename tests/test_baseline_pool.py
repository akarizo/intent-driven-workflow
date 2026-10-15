"""跨 change 复用全量与基线池（scenario: baseline-incremental-reuse#cross-change-reuse-same-tree、#cross-change-reuse-after-test-only-commit、
#cross-change-ignores-sourced-files、#failed-rerun-not-repeated-across-candidates、#pool-pruned-and-tolerant、#pool-write-failure-only-warns）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。
#cross-change-refused-when-script-differs、#cross-change-refused-when-candidate-has-preexisting-red 在 S1 之后即成立，放在 test_baseline_incremental.py（S1）。"""
import json
import os
import pathlib
import time

import pytest

from conftest import git, write
from test_baseline_incremental import (PY, append, baseline, clear, counting_test, full_c, marker, read_bl, read_plan,
                                       setup_change, two_changes)

POOL = "flight-baseline-pool"


def pool_dir(git_repo):
    """git common dir 下的基线池目录。"""
    common = git(git_repo, "rev-parse", "--git-common-dir")
    base = pathlib.Path(common) if os.path.isabs(common) else git_repo / common
    return base / POOL


def pool_entries(git_repo):
    """池里不以 .tmp- 开头的 .json 文件名；池不存在或不是目录时为空列表。"""
    p = pool_dir(git_repo)
    if not p.is_dir():
        return []
    return [n for n in os.listdir(p) if n.endswith(".json") and not n.startswith(".tmp-")]


def test_cross_change_reuse_same_tree(git_repo):
    # Given: change c 跑过一次全量绿基线，没有预存红；change d 的全量脚本与 c 内容相同、命令只差 change 目录名，还没有基线；
    #        c 的工件与门禁脚本都没有提交
    c, d = two_changes(git_repo, old_red=False)
    bc = full_c(git_repo, c)

    # When: 对 d 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；gate.test 没有运行；d 的 mode 为 incremental、from.change 为 c；d 的 test.exit 为 0；
    #       d 的 gate.full_suite_sec 等于 c 基线的 test.sec
    assert p.returncode == 0, p.stdout + p.stderr
    assert not marker(git_repo, "ran-full").exists()
    bd = read_bl(d)
    assert bd["mode"] == "incremental" and bd["incremental"]["from"]["change"] == "c", bd
    assert bd["test"]["exit"] == 0 and bc["test"]["exit"] == 0, (bd["test"], bc["test"])
    assert read_plan(d)["gate"]["full_suite_sec"] == bc["test"]["sec"]


def test_cross_change_reuse_after_test_only_commit(git_repo):
    # Given: change c 跑过一次全量绿基线，没有预存红；之后提交了一个只新增 tests/test_more.py（用例通过）的 commit；
    #        d 的全量脚本与 c 内容相同
    c, d = two_changes(git_repo, old_red=False)
    full_c(git_repo, c)
    write(git_repo / "tests" / "test_more.py", "def test_more():\n    assert True\n")
    git(git_repo, "add", "tests/test_more.py")
    git(git_repo, "commit", "-q", "-m", "more tests")

    # When: 对 d 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: gate.test 没有运行；mode 为 incremental，incremental.files 为 ["tests/test_more.py"]
    assert p.returncode == 0, p.stdout + p.stderr
    assert not marker(git_repo, "ran-full").exists()
    bd = read_bl(d)
    assert bd["mode"] == "incremental" and bd["incremental"]["files"] == ["tests/test_more.py"], bd


def test_cross_change_ignores_sourced_files(git_repo):
    # Given: change c 跑过一次全量绿基线，没有预存红；d 的全量脚本与 c 内容相同，但两者各自 source 的 verify/_env.sh 内容不同
    c, d = two_changes(git_repo, c_env="OWNED_PY=(a.py)\n", d_env="OWNED_PY=(b.py)\n", old_red=False)
    full_c(git_repo, c)

    # When: 对 d 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: gate.test 没有运行；mode 为 incremental，from.change 为 c
    assert p.returncode == 0, p.stdout + p.stderr
    assert not marker(git_repo, "ran-full").exists()
    bd = read_bl(d)
    assert bd["mode"] == "incremental" and bd["incremental"]["from"]["change"] == "c", bd


def test_failed_rerun_not_repeated_across_candidates(git_repo):
    # Given: change c 与 d 的全量脚本内容相同，各跑过一次全量绿基线（d 用 --full），池里至少有它们两条；
    #        之后往 tests/test_cap.py 追加一个会失败的用例，它每运行一次就往仓外计数文件追加一个字符；
    #        d 的 S1 verify 不运行 tests/test_cap.py（只数补跑与全量）
    counter = marker(git_repo, "count")
    c, d = two_changes(git_repo, old_red=False)
    plan = read_plan(d)
    plan["slices"][0]["verify"] = "%s -c pass" % PY
    write(d / "slices.json", json.dumps(plan, ensure_ascii=False, indent=1))
    full_c(git_repo, c)
    pd = baseline(git_repo, d, "--full")
    assert pd.returncode == 0, pd.stdout + pd.stderr
    assert len(pool_entries(git_repo)) >= 2, pool_entries(git_repo)
    clear(marker(git_repo, "ran-full"), counter)
    append(git_repo / "tests" / "test_cap.py", "\n\n" + counting_test(counter, name="test_count_red", fail=True))

    # When: 对 d 运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；mode 为 full；计数文件恰好 2 个字符（补跑 1 次、全量 1 次）
    assert marker(git_repo, "ran-full").exists()
    assert read_bl(d)["mode"] == "full"
    assert counter.read_text() == "xx", counter.read_text()


def test_pool_pruned_and_tolerant(git_repo):
    # Given: 基线池里预置 31 条 cmd_key 不同的旧条目、1 个内容不是 JSON 的 bad.json，以及一个修改时间在两小时前的 .tmp-stale.json；
    #        change c 没有预存红
    d = setup_change(git_repo, old_red=False)
    pdir = pool_dir(git_repo)
    pdir.mkdir(parents=True)
    for i in range(31):
        (pdir / ("20260101T0000%02dZ-z-000000000000.json" % i)).write_text(json.dumps({
            "change": "z", "commit": "0" * 40, "at": "2026-01-01T00:00:%02dZ" % i, "ok": True,
            "cmd_key": "other", "snapshot": {}, "test": {"exit": 0, "sec": 1.0}}), encoding="utf-8")
    (pdir / "bad.json").write_text("{not json", encoding="utf-8")
    stale = pdir / ".tmp-stale.json"
    stale.write_text("{}", encoding="utf-8")
    old = time.time() - 7200
    os.utime(str(stale), (old, old))

    # When: 对 c 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；池里不以 .tmp- 开头的 .json 文件恰好 30 个，其中有一条的 change 为 c；.tmp-stale.json 已不存在
    assert p.returncode == 0, p.stdout + p.stderr
    names = pool_entries(git_repo)
    assert len(names) == 30, sorted(names)

    def change_of(name):
        try:
            return json.loads((pdir / name).read_text(encoding="utf-8")).get("change")
        except ValueError:
            return None
    assert any(change_of(n) == "c" for n in names), sorted(names)
    assert not stale.exists()


def test_pool_write_failure_only_warns(git_repo):
    # Given: git common dir 下的 flight-baseline-pool 是一个普通文件；change c 没有预存红
    d = setup_change(git_repo, old_red=False)
    pool_dir(git_repo).write_text("not a dir\n", encoding="utf-8")

    # When: 对 c 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；warnings 有一项含「基线池写入失败」
    assert p.returncode == 0, p.stdout + p.stderr
    assert any("基线池写入失败" in w for w in read_bl(d).get("warnings") or []), read_bl(d)
