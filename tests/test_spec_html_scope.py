"""审批页显示选测范围（scenario: gate-scope-report#spec-html-shows-scope-reasons、#spec-html-shows-repo-default-scope；
scope-provider-contract#spec-html-shows-provider-state）。
前两条由 change scope-fallback-guard 落地，最后一条由 change scope-guard-enforced 落地；来源措辞按契约 v2 为「仓库声明」。"""
import json

from conftest import write
from test_spec_html import artifacts, render

def _slices(change, gate):
    """单片 slices.json，gate 原样写入。"""
    write(change / "slices.json", json.dumps({
        "version": 1, "change": "add-export", "gate": gate,
        "slices": [{"id": "S1", "title": "导出", "owns": ["src/**"], "deps": [], "verify": "true",
                    "scenarios": [], "packet": "slices/S1.md"}],
        "scenario_tests": {}}, ensure_ascii=False))


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


def test_spec_html_shows_repo_default_scope(tmp_path):
    # Given: openspec 根的 gate-scope.json 是 {"cmd": "bash tools/scope.sh"}，计划没写 gate.scope
    change = artifacts(tmp_path / "openspec" / "changes" / "add-export")
    write(tmp_path / "openspec" / "gate-scope.json", json.dumps({"cmd": "bash tools/scope.sh"}))
    _slices(change, {"test": "pytest -q"})
    out = tmp_path / "spec.html"

    # When: 运行 spec_html.py
    p = render(change, out)

    # Then: HTML 含「选测范围」、仓库声明的命令与「仓库声明」
    assert p.returncode == 0, p.stderr
    html = out.read_text(encoding="utf-8")
    for word in ("选测范围", "bash tools/scope.sh", "仓库声明"):
        assert word in html, word


def test_spec_html_shows_provider_state(tmp_path):
    # Given: 三个 change：仓库声明 {"builtin": true}；仓库声明 {"cmd": "python3 tools/scope.py"}；没有任何声明
    def change(name, decl):
        base = tmp_path / name
        c = artifacts(base / "openspec" / "changes" / "add-export")
        if decl is not None:
            write(base / "openspec" / "gate-scope.json", json.dumps(decl))
        _slices(c, {"test": "pytest -q"})
        return c, base / "spec.html"

    cases = [change("b", {"builtin": True}), change("c", {"cmd": "python3 tools/scope.py"}), change("u", None)]

    # When: 分别渲染 spec.html
    runs = [render(c, out) for c, out in cases]

    # Then: builtin 那份含「模板内建」；cmd 那份含命令原文与「仓库声明」；未声明那份含「未声明选测范围」
    assert all(p.returncode == 0 for p in runs), [p.stderr for p in runs]
    html = [out.read_text(encoding="utf-8") for _, out in cases]
    assert "模板内建" in html[0]
    assert "python3 tools/scope.py" in html[1] and "仓库声明" in html[1]
    assert "未声明选测范围" in html[2]
