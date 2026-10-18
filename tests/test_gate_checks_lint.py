"""gate.checks 与仓库默认检查的计划校验（scenario: gate-paired-checks#lint-rejects-malformed-checks … #lint-rejects-unreadable-repo-defaults）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。护栏（lint-accepts-valid-checks、
lint-accepts-default-check-skipped-with-reason）在 base 上已成立，不带 xfail。"""
import json

import pytest

from conftest import run_hook, write
from test_slice_gate import plan, slice_, write_plan


def _plan_with(checks=None, skip=None):
    """单片合法计划；可带 gate.checks 与 gate.checks_skip。"""
    data = plan([slice_("S1", ["a/**"])])
    if checks is not None:
        data["gate"]["checks"] = checks
    if skip is not None:
        data["gate"]["checks_skip"] = skip
    return data


def _defaults(openspec_root, names):
    """在 openspec 根目录写仓库默认检查文件 gate-checks.json。"""
    write(openspec_root / "gate-checks.json",
          json.dumps([{"name": n, "baseline": "true", "final": "true"} for n in names], ensure_ascii=False))


def _lint(change):
    return run_hook("slice-gate", "lint", "--change-dir", str(change))


def _checks_lines(stderr):
    """stderr 里以 checks: 开头的违规行（die 的格式是 `  - checks: …`）。"""
    return [l.strip()[2:] for l in stderr.splitlines() if l.strip().startswith("- checks:")]


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_lint_rejects_malformed_checks(tmp_path):
    # Given: gate.checks 有 name 为 Bad 的、no-final 缺 final 的、两个 dup、zero-timeout 的 timeout_sec 为 0、typo 带未知字段 base_line；
    #        checks_skip 里 empty-reason 的理由是空白，ok-check 同时出现在 gate.checks 与 checks_skip
    checks = [
        {"name": "Bad", "final": "true"},
        {"name": "no-final", "baseline": "true"},
        {"name": "dup", "final": "true"},
        {"name": "dup", "final": "true"},
        {"name": "zero-timeout", "final": "true", "timeout_sec": 0},
        {"name": "typo", "final": "true", "base_line": "true"},
        {"name": "ok-check", "final": "true"},
    ]
    change = write_plan(tmp_path / "openspec" / "changes" / "c",
                        _plan_with(checks, {"empty-reason": "  ", "ok-check": "理由"}))

    # When: 运行 slice-gate.py lint
    p = _lint(change)

    # Then: 退出非 0；stderr 里以 checks: 开头的行分别点名 Bad、no-final、dup、zero-timeout、typo、empty-reason、ok-check
    assert p.returncode != 0, p.stdout
    lines = _checks_lines(p.stderr)
    for name in ("Bad", "no-final", "dup", "zero-timeout", "typo", "empty-reason", "ok-check"):
        assert any(name in l for l in lines), (name, p.stderr)


def test_lint_accepts_valid_checks(tmp_path):
    # Given: gate.checks 有 parity（baseline、final、timeout_sec 60）与 linkage（baseline 为 null、只有 final）；
    #        checks_skip 为 {"other": "本 change 不碰共用包"}
    checks = [
        {"name": "parity", "baseline": "true", "final": "true", "timeout_sec": 60},
        {"name": "linkage", "baseline": None, "final": "true"},
    ]
    change = write_plan(tmp_path / "openspec" / "changes" / "c", _plan_with(checks, {"other": "本 change 不碰共用包"}))

    # When: 运行 slice-gate.py lint
    p = _lint(change)

    # Then: 退出 0，stdout 打印 waves
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == [["S1"]]


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_lint_requires_repo_default_check(tmp_path):
    # Given: openspec/gate-checks.json 列出 coverage-parity；openspec/changes/c 的 gate.checks 与 checks_skip 都没有它
    _defaults(tmp_path / "openspec", ["coverage-parity"])
    change = write_plan(tmp_path / "openspec" / "changes" / "c", _plan_with())

    # When: 运行 slice-gate.py lint
    p = _lint(change)

    # Then: 退出非 0；stderr 有一行以 checks: 开头并点名 coverage-parity
    assert p.returncode != 0, p.stdout
    assert any("coverage-parity" in l for l in _checks_lines(p.stderr)), p.stderr


def test_lint_accepts_default_check_skipped_with_reason(tmp_path):
    # Given: openspec/gate-checks.json 列出 coverage-parity；本 change 的 checks_skip 为 {"coverage-parity": "只改文档，见 design D3"}
    _defaults(tmp_path / "openspec", ["coverage-parity"])
    change = write_plan(tmp_path / "openspec" / "changes" / "c",
                        _plan_with(skip={"coverage-parity": "只改文档，见 design D3"}))

    # When: 运行 slice-gate.py lint
    p = _lint(change)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_lint_repo_defaults_follow_change_dir(tmp_path):
    # Given: change 目录在 template/openspec/changes/c；template/openspec/gate-checks.json 列出 coverage-parity；
    #        template/ 的上一级没有 openspec/；本 change 没写这个检查
    _defaults(tmp_path / "template" / "openspec", ["coverage-parity"])
    change = write_plan(tmp_path / "template" / "openspec" / "changes" / "c", _plan_with())
    assert not (tmp_path / "openspec").exists()

    # When: 运行 slice-gate.py lint
    p = _lint(change)

    # Then: 退出非 0；stderr 有一行以 checks: 开头并点名 coverage-parity
    assert p.returncode != 0, p.stdout
    assert any("coverage-parity" in l for l in _checks_lines(p.stderr)), p.stderr


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_lint_rejects_unreadable_repo_defaults(tmp_path):
    # Given: openspec/gate-checks.json 的内容不是合法 JSON；本 change 的计划其余部分合法
    write(tmp_path / "openspec" / "gate-checks.json", "[{not json\n")
    change = write_plan(tmp_path / "openspec" / "changes" / "c", _plan_with())

    # When: 运行 slice-gate.py lint
    p = _lint(change)

    # Then: 退出非 0；stderr 有一行以 checks: 开头并含 gate-checks.json
    assert p.returncode != 0, p.stdout
    assert any("gate-checks.json" in l for l in _checks_lines(p.stderr)), p.stderr
