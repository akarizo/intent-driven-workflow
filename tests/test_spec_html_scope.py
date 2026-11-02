"""审批页显示选测范围（scenario: gate-scope-report#spec-html-shows-scope-reasons、#spec-html-shows-repo-default-scope）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import write
from test_spec_html import artifacts, render


def _slices(change, gate):
    """单片 slices.json，gate 原样写入。"""
    write(change / "slices.json", json.dumps({
        "version": 1, "change": "add-export", "gate": gate,
        "slices": [{"id": "S1", "title": "导出", "owns": ["src/**"], "deps": [], "verify": "true",
                    "scenarios": [], "packet": "slices/S1.md"}],
        "scenario_tests": {}}, ensure_ascii=False))


@pytest.mark.xfail(strict=True, reason="S3 未实现：spec.html 渲染选测命令与「触发项 → 理由」表")
def test_spec_html_shows_scope_reasons(tmp_path):
    # Given: slices.json 的 gate.scope 是 python3 tools/scope.py，gate.scope_full_reason 为登记表写了「理由甲」
    change = artifacts(tmp_path / "openspec" / "changes" / "add-export")
    _slices(change, {"test": "pytest -q", "scope": "python3 tools/scope.py",
                     "scope_full_reason": {"executor/tests/tiering_registry.json": "理由甲"}})
    out = tmp_path / "spec.html"

    # When: 运行 spec_html.py
    p = render(change, out)

    # Then: HTML 含「选测范围」、命令原文、触发项与理由
    assert p.returncode == 0, p.stderr
    html = out.read_text(encoding="utf-8")
    for word in ("选测范围", "python3 tools/scope.py", "executor/tests/tiering_registry.json", "理由甲"):
        assert word in html, word


@pytest.mark.xfail(strict=True, reason="S3 未实现：spec.html 显示仓库默认选测命令")
def test_spec_html_shows_repo_default_scope(tmp_path):
    # Given: openspec 根的 gate-scope.json 是 {"cmd": "bash tools/scope.sh"}，计划没写 gate.scope
    change = artifacts(tmp_path / "openspec" / "changes" / "add-export")
    write(tmp_path / "openspec" / "gate-scope.json", json.dumps({"cmd": "bash tools/scope.sh"}))
    _slices(change, {"test": "pytest -q"})
    out = tmp_path / "spec.html"

    # When: 运行 spec_html.py
    p = render(change, out)

    # Then: HTML 含「选测范围」、仓库默认命令与「仓库默认」
    assert p.returncode == 0, p.stderr
    html = out.read_text(encoding="utf-8")
    for word in ("选测范围", "bash tools/scope.sh", "仓库默认"):
        assert word in html, word
