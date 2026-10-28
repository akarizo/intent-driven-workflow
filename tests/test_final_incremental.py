"""final 默认增量运行，命中触发条件时自动全量
（scenario: incremental-final#final-reruns-only-affected-tests、#final-incremental-red-on-new-failure、
#final-reruns-anchor-failures-and-changed-tests、#final-moves-anchor-forward、#final-full-when-global-file-changes、
#final-full-when-no-anchor、#final-full-when-unseen-non-python-file-changes、#final-full-flag-forces-full）。"""
import shutil

from conftest import commit_all
from final_helpers import anchors, baseline, change_and_commit, final, head, make_repo, timeline_rows

A_OK = "def a():\n    return 1  # 改过，仍正确\n"


def test_final_reruns_only_affected_tests(git_repo):
    # Given: 依赖图已记录的仓库，baseline 绿；随后只改了 src/a.py，而且仍然正确
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", A_OK)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 绿，增量只重跑 tests/test_a.py；test_b / test_c 的用例计入沿用；summary 与 timeline 写明增量与锚点
    assert out["ok"] is True, out
    inc = out["incremental"]
    assert inc["mode"] == "incremental", inc
    assert inc["rerun"] == ["tests/test_a.py"], inc
    assert inc["inherited_tests"] >= 2, inc
    anchor10 = inc["anchor"]["commit"][:10]
    assert "增量" in out["summary"] and anchor10 in out["summary"], out["summary"]
    note = timeline_rows(d, "final")[-1]
    assert note.startswith("增量") and anchor10 in note and note.endswith(" ok"), note


def test_final_incremental_red_on_new_failure(git_repo):
    # Given: 依赖图已记录的仓库，baseline 绿；随后改坏了 src/a.py，使 tests/test_a.py::test_a 失败
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 2\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 红，G2 test 列出 tests/test_a.py::test_a；仍是增量
    assert out["ok"] is False, out
    assert any("G2 test" in f and "tests/test_a.py::test_a" in f for f in out["failed"]), out["failed"]
    assert out["incremental"]["mode"] == "incremental", out["incremental"]


def test_final_reruns_anchor_failures_and_changed_tests(git_repo):
    # Given: baseline 记录了预存红 tests/test_old.py::test_broken；随后只改了测试文件 tests/test_b.py
    d = make_repo(git_repo, extra={"tests/test_old.py": "def test_broken():\n    assert False\n"})
    baseline(git_repo, d)
    change_and_commit(git_repo, "tests/test_b.py", (git_repo / "tests" / "test_b.py").read_text() + "# 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 重跑的恰好是 test_b 与 test_old；test_broken 仍失败但属基线预存红，final 绿
    assert out["incremental"]["mode"] == "incremental", out["incremental"]
    assert sorted(out["incremental"]["rerun"]) == ["tests/test_b.py", "tests/test_old.py"], out["incremental"]
    assert out["ok"] is True, out["failed"]


def test_final_moves_anchor_forward(git_repo):
    # Given: 第一次 final 增量通过（只改了 src/a.py）；之后提交飞行记录，又改了 src/c_lib.py 并提交
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", A_OK)
    first, _ = final(git_repo, d)
    assert first["ok"] is True and first["incremental"]["mode"] == "incremental", first
    head1 = head(git_repo)
    commit_all(git_repo, "flight")
    change_and_commit(git_repo, "src/c_lib.py", "VALUE = 3  # 改过\n")

    # When: 再运行一次 final
    out, p = final(git_repo, d)

    # Then: 锚点是第一次 final 时的 HEAD，只重跑 tests/test_c.py
    inc = out["incremental"]
    assert inc["anchor"]["commit"] == head1, (inc, head1)
    assert inc["rerun"] == ["tests/test_c.py"], inc
    assert out["ok"] is True, out


def test_final_full_when_global_file_changes(git_repo):
    # Given: 依赖图已记录的仓库，baseline 绿；随后新增了 tests/conftest.py
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "tests/conftest.py", "# 全局夹具\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 全量运行，full_why 含 conftest.py
    inc = out["incremental"]
    assert inc["mode"] == "full" and "conftest.py" in inc["full_why"], inc
    assert out["ok"] is True, out


def test_final_full_when_no_anchor(git_repo):
    # Given: baseline 之后锚点目录被删，随后改了 src/a.py
    d = make_repo(git_repo)
    baseline(git_repo, d)
    shutil.rmtree(git_repo / ".git" / "flight-anchors", ignore_errors=True)
    change_and_commit(git_repo, "src/a.py", A_OK)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 全量运行，full_why 说明没有可用锚点；跑完后锚点池里有一条本次的锚点
    inc = out["incremental"]
    assert inc["mode"] == "full" and "锚点" in inc["full_why"], inc
    assert [a for a in anchors(git_repo) if a.get("commit") == head(git_repo)], anchors(git_repo)


def test_final_full_when_unseen_non_python_file_changes(git_repo):
    # Given: scripts/helper.sh 从未被任何用例触及，baseline 后改了它
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "scripts/helper.sh", "echo changed\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 全量运行，full_why 含 scripts/helper.sh
    inc = out["incremental"]
    assert inc["mode"] == "full" and "scripts/helper.sh" in inc["full_why"], inc


def test_final_full_flag_forces_full(git_repo):
    # Given: 依赖图已记录的仓库，只改了 src/a.py
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", A_OK)

    # When: 运行 final --full
    out, p = final(git_repo, d, "--full")

    # Then: 全量运行，full_why 说明是手动要求
    inc = out["incremental"]
    assert inc["mode"] == "full" and "--full" in inc["full_why"], inc
