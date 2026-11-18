"""inert 声明的静态核对与依赖图对账（scenario: inert-paths#lint-rejects-inert-matching-test-or-global-files、
#lint-reconciles-inert-with-dependency-graph、#inert-consistent-with-graph-passes-lint、#doctor-lists-inert-and-conflicts，共 4 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import SCOPE_DECL, commit_all, run_hook
from final_helpers import baseline, make_repo

PENDING = pytest.mark.xfail(strict=True, reason="骨架：切片 S2 实现后去掉")


def _decl(repo, **extra):
    (repo / "openspec" / "gate-scope.json").write_text(json.dumps(dict(SCOPE_DECL, **extra)) + "\n", encoding="utf-8")


def _lint(repo, d):
    return run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=repo)


def _lines(text, word):
    return [l.strip() for l in text.splitlines() if word in l]


def _doctor(repo):
    return run_hook("flight-doctor", "doctor", "--openspec-root", str(repo / "openspec"), cwd=repo)


@PENDING
def test_lint_rejects_inert_matching_test_or_global_files(git_repo):
    # Given: inert 写了 ["tests/**", "*.ini"]：前者匹配到测试文件，后者匹配到全局文件 pytest.ini
    _decl(git_repo, inert=["tests/**", "*.ini"])
    d = make_repo(git_repo)

    # When: 运行 lint
    p = _lint(git_repo, d)

    # Then: 退出非 0；两条违规分别点名 glob、匹配到的路径与它的类别
    assert p.returncode != 0, p.stdout
    assert any("tests/**" in l and "tests/test_a.py" in l and "测试路径" in l for l in _lines(p.stderr, "inert")), p.stderr
    assert any("*.ini" in l and "pytest.ini" in l and "全局文件" in l for l in _lines(p.stderr, "inert")), p.stderr


@PENDING
def test_lint_reconciles_inert_with_dependency_graph(git_repo):
    # Given: 基线测到 tests/test_b.py 读 data/b.json；之后把 data/** 声明成 inert
    d = make_repo(git_repo)
    assert baseline(git_repo, d)["ok"] is True
    _decl(git_repo, inert=["data/**"])
    commit_all(git_repo, "declare inert")

    # When: 分别运行 lint 与 preflight
    lint = _lint(git_repo, d)
    pre = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 都非 0；违规同时点名 data/b.json 与依赖它的 tests/test_b.py
    for p in (lint, pre):
        assert p.returncode != 0, p.stdout
        assert any("data/b.json" in l and "tests/test_b.py" in l for l in _lines(p.stderr, "inert")), p.stderr


@PENDING
def test_inert_consistent_with_graph_passes_lint(git_repo):
    # Given: 基线测到了依赖图，没有任何用例触及 scripts/helper.sh；之后把 scripts/** 声明成 inert
    d = make_repo(git_repo)
    assert baseline(git_repo, d)["ok"] is True
    _decl(git_repo, inert=["scripts/**"])
    commit_all(git_repo, "declare inert")

    # When: 运行 lint
    p = _lint(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


@PENDING
def test_doctor_lists_inert_and_conflicts(git_repo):
    # Given: 仓库 A 声明了 inert ["data/**"] 但还没有任何锚点；随后基线测到 tests/test_b.py 读 data/b.json
    _decl(git_repo, inert=["scripts/**"])
    d = make_repo(git_repo)
    before = _doctor(git_repo)
    assert baseline(git_repo, d)["ok"] is True
    _decl(git_repo, inert=["data/**"])
    commit_all(git_repo, "declare inert")

    # When: 运行 flight-doctor.py doctor
    after = _doctor(git_repo)

    # Then: 都退出 0；没有锚点时注明无法对账；有锚点后 [declare] 列出 inert 的值与矛盾的文件、测试文件
    assert before.returncode == 0 and after.returncode == 0, (before.stderr, after.stderr)
    assert any("无法对账" in l for l in _lines(before.stdout, "inert")), before.stdout
    assert any("data/**" in l for l in _lines(after.stdout, "inert")), after.stdout
    assert any("矛盾" in l and "data/b.json" in l and "tests/test_b.py" in l for l in _lines(after.stdout, "inert")), after.stdout
