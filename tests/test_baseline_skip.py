"""代码树没变时 lint / typecheck 沿用、全量可度量时 verify 从全量 junit 推导
（scenario: baseline-redundant-run-skip#lint-reused-when-tree-unchanged … #verify-run-when-gate-test-not-plain-pytest）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。护栏（verify-run-when-scope-has-preexisting-red、
verify-run-when-not-derivable、verify-run-when-gate-test-not-plain-pytest）在 base 上已成立，不带 xfail。"""
import shlex

import pytest

from conftest import write
from test_baseline_incremental import (PLAIN_FULL, PY, append, baseline, counting_test, first_full, marker, read_bl,
                                       setup_change)

PLAIN_VERIFY = "%s -m pytest -q -p no:cacheprovider" % PY


# ---------------------------------------------------------------- 代码树没变时 lint / typecheck 沿用


@pytest.mark.xfail(strict=True, reason="S3 未实现：代码树没变时 lint 沿用")
def test_lint_reused_when_tree_unchanged(git_repo):
    # Given: change c 已有一次全量绿基线，gate.lint 运行时会写一个标记文件；之后只改了本 change 的 proposal.md，并清掉 lint 标记
    d = setup_change(git_repo, lint=True)
    first = first_full(git_repo, d, marker(git_repo, "ran-lint"))
    append(d / "proposal.md", "补一句。\n")

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；lint 标记文件不存在；lint.reused 为 true，lint.exit 与第一次相同
    assert p.returncode == 0, p.stdout + p.stderr
    assert not marker(git_repo, "ran-lint").exists()
    bl = read_bl(d)
    assert bl["lint"].get("reused") is True and bl["lint"]["exit"] == first["lint"]["exit"], bl["lint"]


@pytest.mark.xfail(strict=True, reason="S3 未实现：严格差异含其他 change 目录")
def test_lint_rerun_when_other_change_edited(git_repo):
    # Given: change c 已有一次全量绿基线，gate.lint 运行时会写一个标记文件；之后在 openspec/changes/other/verify/ 下新建了一个文件，
    #        并清掉 lint 标记
    d = setup_change(git_repo, lint=True)
    first_full(git_repo, d, marker(git_repo, "ran-lint"))
    write(git_repo / "openspec" / "changes" / "other" / "verify" / "x.py", "x = 1\n")

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；mode 为 incremental；lint 标记文件存在；lint 没有 reused
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["mode"] == "incremental", bl
    assert marker(git_repo, "ran-lint").exists()
    assert "reused" not in bl["lint"], bl["lint"]


@pytest.mark.xfail(strict=True, reason="S3 未实现：lint 命令指纹含直接写出的计划工件")
def test_lint_rerun_when_referenced_plan_file_changed(git_repo):
    # Given: gate.lint 的命令里直接写出了本 change 的 proposal.md，运行时会写一个标记文件；change c 已有一次全量绿基线；
    #        之后只改了 proposal.md，并清掉 lint 标记
    rel = "openspec/changes/c"
    lint_cmd = "%s %s/verify/lint.py %s %s/proposal.md" % (PY, rel, shlex.quote(str(marker(git_repo, "ran-lint"))), rel)
    d = setup_change(git_repo, lint_cmd=lint_cmd)
    first_full(git_repo, d, marker(git_repo, "ran-lint"))
    append(d / "proposal.md", "补一句。\n")

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: mode 为 incremental；lint 标记文件存在；lint 没有 reused
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["mode"] == "incremental", bl
    assert marker(git_repo, "ran-lint").exists()
    assert "reused" not in bl["lint"], bl["lint"]


# ---------------------------------------------------------------- verify 从全量 junit 推导


@pytest.mark.xfail(strict=True, reason="S3 未实现：verify 从全量 junit 推导")
def test_verify_derived_from_full_suite(git_repo):
    # Given: gate.test 是直接的 python -m pytest -q -p no:cacheprovider tests；S1 的 verify 是同一前缀加 tests/test_cap.py；
    #        tests/test_cap.py 的用例每运行一次就往仓外计数文件追加一个字符，且会通过
    counter = marker(git_repo, "count")
    d = setup_change(git_repo, old_red=False, gate_test=PLAIN_FULL, cap_body=counting_test(counter),
                     slices=[{"id": "S1", "verify": PLAIN_VERIFY + " tests/test_cap.py"}])

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；计数文件恰好 1 个字符；verify.S1.exit 为 0，verify.S1.derived 为 full
    assert p.returncode == 0, p.stdout + p.stderr
    assert counter.read_text() == "x", counter.read_text()
    v = read_bl(d)["verify"]["S1"]
    assert v["exit"] == 0 and v.get("derived") == "full", v


def test_verify_run_when_scope_has_preexisting_red(git_repo):
    # Given: gate.test 是直接的 pytest 调用；tests/test_old.py 有一个失败用例；S2 的 verify 是同一前缀加 tests/test_old.py
    d = setup_change(git_repo, old_red=True, gate_test=PLAIN_FULL,
                     slices=[{"id": "S1", "verify": PLAIN_VERIFY + " tests/test_cap.py"},
                             {"id": "S2", "verify": PLAIN_VERIFY + " tests/test_old.py"}])

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出非 0；verify.S2.exit 非 0，verify.S2 没有 derived
    assert p.returncode != 0, p.stdout + p.stderr
    v = read_bl(d)["verify"]["S2"]
    assert v["exit"] != 0 and "derived" not in v, v


def test_verify_run_when_not_derivable(git_repo):
    # Given: gate.test 是直接的 pytest 调用；tests/test_cap.py 的用例每运行一次就往仓外计数文件追加一个字符；三片的 verify 分别是：
    #        S1 包装脚本（运行时写标记）再跑 tests/test_cap.py；S2 同一前缀加 tests/test_cap.py::test_adds；S3 同一前缀加 -k adds tests/test_cap.py
    counter = marker(git_repo, "count")
    rel = "openspec/changes/c"
    d = setup_change(git_repo, old_red=False, gate_test=PLAIN_FULL, cap_body=counting_test(counter), slices=[
        {"id": "S1", "verify": "%s %s/verify/v.py %s tests/test_cap.py" % (PY, rel, shlex.quote(str(marker(git_repo, "v1"))))},
        {"id": "S2", "verify": PLAIN_VERIFY + " tests/test_cap.py::test_adds"},
        {"id": "S3", "verify": PLAIN_VERIFY + " -k adds tests/test_cap.py"},
    ])

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；S1 的标记文件存在；计数文件恰好 4 个字符；三片的 verify 记录都没有 derived
    assert p.returncode == 0, p.stdout + p.stderr
    assert marker(git_repo, "v1").exists()
    assert counter.read_text() == "xxxx", counter.read_text()
    vs = read_bl(d)["verify"]
    assert all("derived" not in vs[s] for s in ("S1", "S2", "S3")), vs


def test_verify_run_when_gate_test_not_plain_pytest(git_repo):
    # Given: gate.test 是本 change 目录下的包装脚本（内部调用 pytest 跑 tests）；S1 的 verify 是直接的 pytest 加 tests/test_cap.py；
    #        tests/test_cap.py 的用例每运行一次就往仓外计数文件追加一个字符
    counter = marker(git_repo, "count")
    d = setup_change(git_repo, old_red=False, cap_body=counting_test(counter),
                     slices=[{"id": "S1", "verify": PLAIN_VERIFY + " tests/test_cap.py"}])

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；计数文件恰好 2 个字符；verify.S1 没有 derived
    assert p.returncode == 0, p.stdout + p.stderr
    assert counter.read_text() == "xx", counter.read_text()
    v = read_bl(d)["verify"]["S1"]
    assert "derived" not in v, v
