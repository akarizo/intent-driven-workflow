"""审批页显示钉住的模型路由（scenario: spec-html-routing#spec-html-shows-pinned-routing、#spec-html-warns-missing-routing，共 2 条）。
切片 S4 已解锁。"""
import json

from conftest import write
from test_spec_html import artifacts, render

FLIGHT = {"executor": {"model": "opus", "effort": "medium"}, "executor-large": {"model": "opus", "effort": "medium"},
          "fixer": {"model": "opus", "effort": "high"}, "reviewer": {"model": "opus", "effort": "high"},
          "integrator": {"model": "sonnet", "effort": "low"}}
SHIP = {"reviewer": {"model": "opus", "effort": "high"}, "followup": {"model": "opus", "effort": "high"}}


def _plan(change, routing=None):
    data = {"gate": {"test": "pytest -q"},
            "slices": [{"id": "S1", "title": "t", "owns": ["a.py"], "deps": [], "verify": "true", "scenarios": [],
                        "packet": "slices/S1.md"}],
            "scenario_tests": {}}
    if routing is not None:
        data["routing"] = routing
    write(change / "slices.json", json.dumps(data, ensure_ascii=False))


def row(html, key):
    return next(seg for seg in html.split("<tr>") if key in seg)


def test_spec_html_shows_pinned_routing(tmp_path):
    # Given: slices.json 含 routing（flight.executor opus·medium、flight.integrator sonnet·low）
    change = artifacts(tmp_path / "openspec" / "changes" / "c")
    _plan(change, {"source": "openspec/model-routing.json", "flight": FLIGHT, "ship": SHIP})

    # When: 渲染 spec.html
    p = render(change, tmp_path / "spec.html")

    # Then: 页面有「模型路由」，flight.executor 行含 opus 与 medium，flight.integrator 行含 sonnet 与 low
    assert p.returncode == 0, p.stderr
    html = (tmp_path / "spec.html").read_text(encoding="utf-8")
    assert "模型路由" in html
    ex, it = row(html, "flight.executor<"), row(html, "flight.integrator<")
    assert "opus" in ex and "medium" in ex, ex
    assert "sonnet" in it and "low" in it, it


def test_spec_html_warns_missing_routing(tmp_path):
    # Given: 没有 routing 的 slices.json
    change = artifacts(tmp_path / "openspec" / "changes" / "c")
    _plan(change)

    # When: 渲染 spec.html
    p = render(change, tmp_path / "spec.html")

    # Then: 页面含 model-routing.py pin 的提示
    assert p.returncode == 0, p.stderr
    assert "model-routing.py pin" in (tmp_path / "spec.html").read_text(encoding="utf-8")
