"""审批页显示全局守护与宽通配理由、成本归因列出 wave 集成检查（scenario: slice-guards#spec-html-shows-guards-and-wide-owns；
wave-check#cost-reports-wave-checks，共 2 条）。
骨架：strict xfail，断言是真实的；切片 S7 实现后去掉标记即解锁。"""
import json

from conftest import run_hook, write
from test_spec_html import artifacts, render


TIMELINE = (
    "<!-- timeline: ISO时间\\t事件\\t备注（由 hooks 自动追加） -->\n"
    "2026-11-18T01:00:00Z\twave-check\twave 1/2 · 守护 layering 1.2s · 测试 12.3s（3 个文件） · 排队 0.0s · 负载 1.0→1.2/8 ok\n"
    "2026-11-18T02:00:00Z\twave-check\twave 2/2 · 守护 layering 0.4s · 测试跳过（没有可用锚点） · 排队 0.0s ok\n"
    "2026-11-18T03:00:00Z\tfinal\t增量（锚点 abcdef0123，重跑 2 个文件 / 沿用 10 个用例） 测试 8.0s · 排队 0.0s ok\n"
)


def test_spec_html_shows_guards_and_wide_owns(tmp_path):
    # Given: 计划的检查 layering 带 slice 命令，gate.wave_test_budget_sec 为 300，切片 S1 的 owns_wide 为通配写了理由
    change = artifacts(tmp_path / "openspec" / "changes" / "add-export")
    gate = {"test": "pytest -q", "wave_test_budget_sec": 300,
            "checks": [{"name": "layering", "slice": "python3 tools/layering.py", "final": "true"}]}
    write(change / "slices.json", json.dumps({
        "version": 1, "change": "add-export", "gate": gate,
        "slices": [{"id": "S1", "title": "导出", "owns": ["src/**"], "owns_wide": {"src/**": "整个目录的机械迁移"},
                    "deps": [], "verify": "true", "scenarios": [], "packet": "slices/S1.md"}],
        "scenario_tests": {}}, ensure_ascii=False))
    out = tmp_path / "spec.html"

    # When: 渲染审批页
    p = render(change, out)

    # Then: 页面标出全局守护与命令原文，显示预算与通配的理由
    assert p.returncode == 0, p.stderr
    html = out.read_text(encoding="utf-8")
    for word in ("全局守护", "python3 tools/layering.py", "300", "整个目录的机械迁移"):
        assert word in html, word


def test_cost_reports_wave_checks(git_repo):
    # Given: 时间线有两条 wave-check 事件：一条守护 1.2 秒、测试 12.3 秒，一条守护 0.4 秒、测试跳过
    d = git_repo / "openspec" / "changes" / "c"
    write(d / "slices.json", json.dumps({"gate": {"test": "true"}, "slices": []}))
    (d / "timeline.md").write_text(TIMELINE, encoding="utf-8")

    # When: 运行 cost --json 与不带 --json 的 cost
    pj = run_hook("flight-doctor", "cost", "--change-dir", str(d), "--json", cwd=git_repo)
    pt = run_hook("flight-doctor", "cost", "--change-dir", str(d), cwd=git_repo)

    # Then: JSON 多一个 wave 汇总；文本多一行；final 的统计不受影响
    assert pj.returncode == 0 and pt.returncode == 0, pj.stderr + pt.stderr
    j = json.loads(pj.stdout)
    assert j["wave"] == {"count": 2, "guard_sec": 1.6, "test_sec": 12.3, "skipped": 1}, j
    assert (j["final"]["full"], j["final"]["incremental"]) == (0, 1), j
    assert any("wave 集成检查 2 次" in l for l in pt.stdout.splitlines()), pt.stdout
