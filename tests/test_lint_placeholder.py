"""slice-gate.py lint 对 scaffold 占位标记判红的单元测试（不映射 scenario；端到端见 test_propose_toolchain.py）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, run_hook, write


def plan(git_repo, body):
    d = git_repo / "openspec" / "changes" / "c"
    write(git_repo / "tests" / "test_cap.py",
          "def test_works():\n    # Given: a\n    # When: b\n    # Then: c\n    %s\n" % body)
    write(d / "slices.json", json.dumps({
        "gate": {"test": "python3 -m pytest -q tests"},
        "slices": [{"id": "S1", "title": "t", "owns": ["src/a.py"], "deps": [], "verify": "python3 -m pytest -q tests",
                    "scenarios": ["cap#works"], "packet": "slices/S1.md"}],
        "scenario_tests": {"cap#works": "tests/test_cap.py::test_works"}}))
    commit_all(git_repo, "plan")
    return d


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_lint_flags_placeholder_in_scenario_test(git_repo):
    # Given: scenario 测试函数体仍含 PLAN-SCAFFOLD-PLACEHOLDER
    d = plan(git_repo, 'assert False, "PLAN-SCAFFOLD-PLACEHOLDER：换成真实断言"')

    # When: 运行 lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: exit 2，stderr 有 skeleton: 一条点名 tests/test_cap.py::test_works
    assert p.returncode == 2, (p.stdout, p.stderr)
    assert "skeleton:" in p.stderr and "tests/test_cap.py::test_works" in p.stderr, p.stderr


def test_lint_passes_real_assertion(git_repo):
    # Given: scenario 测试函数体是真实断言
    d = plan(git_repo, "assert 1 + 1 == 2")

    # When: 运行 lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: 没有 skeleton: 一条
    assert "skeleton:" not in p.stderr, p.stderr
