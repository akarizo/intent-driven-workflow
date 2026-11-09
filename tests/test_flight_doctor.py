"""flight-doctor.py：forecast / cost / doctor（scenario: test-cost-visibility#forecast-* / cost-* / doctor-*）。"""
import json

import pytest

from conftest import git, run_hook, write
from final_helpers import baseline, make_repo

UNMEASURED = {"kind": "plugins-dropped",
              "why": "包装脚本没把 -p 参数传给 pytest：转发 $FLIGHT_PLUGIN_PATH 与 $FLIGHT_PYTEST_ARGS（见 .claude/flight-runner-contract.md）"}


def plan_dir(repo, name, full_sec=816):
    """只有 slices.json 的最小 change 目录（gate.test 为 true）。"""
    d = repo / "openspec" / "changes" / name
    data = {"version": 1, "change": name,
            "gate": {"test": "true", "lint": None, "typecheck": None, "full_suite_sec": full_sec},
            "slices": [{"id": "S1", "title": "S1", "owns": ["src/**"], "deps": [], "verify": "true",
                        "scenarios": [], "packet": "slices/S1.md"}],
            "scenario_tests": {}}
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    return d


def unmeasured_baseline(repo, d):
    bl = {"commit": git(repo, "rev-parse", "HEAD"), "ok": True, "mode": "full", "reasons": [],
          "test": {"exit": 0, "sec": 816.0}, "deps_unmeasured": UNMEASURED, "snapshot": {}}
    write(d / "gate-baseline.json", json.dumps(bl, ensure_ascii=False))


def forecast(repo, d):
    p = run_hook("flight-doctor", "forecast", "--change-dir", str(d), "--json", cwd=repo)
    return p, (json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else None)


@pytest.mark.xfail(strict=True, reason="S4 未实现：没有 flight-doctor.py")
def test_forecast_predicts_full_final_when_deps_unmeasured(git_repo):
    # Given: 基线 deps_unmeasured.kind 为 plugins-dropped，gate.full_suite_sec 为 816
    d = plan_dir(git_repo, "c")
    unmeasured_baseline(git_repo, d)

    # When: 运行 forecast --json
    p, j = forecast(git_repo, d)

    # Then: 退出 0；final 全量、816 秒，原因含类别与 FLIGHT_PYTEST_ARGS
    assert p.returncode == 0, p.stderr
    assert j["final"]["mode"] == "full" and j["final"]["sec"] == 816, j
    assert "plugins-dropped" in j["final"]["why"] and "FLIGHT_PYTEST_ARGS" in j["final"]["why"], j


@pytest.mark.xfail(strict=True, reason="S4 未实现：没有 flight-doctor.py")
def test_forecast_reports_incremental_when_anchor_usable(git_repo):
    # Given: change 刚跑完测到依赖图的全量基线
    d = make_repo(git_repo)
    baseline(git_repo, d)

    # When: 运行 forecast --json
    p, j = forecast(git_repo, d)

    # Then: final 预计增量
    assert p.returncode == 0, p.stderr
    assert j["final"]["mode"] == "incremental", j


@pytest.mark.xfail(strict=True, reason="S4 未实现：没有 flight-doctor.py")
def test_forecast_pending_while_baseline_running(git_repo):
    # Given: gate-baseline.json 是运行标记
    d = plan_dir(git_repo, "c")
    write(d / "gate-baseline.json", json.dumps({"running": True, "pid": 1, "started": "2026-11-09T00:00:00Z"}))

    # When: 运行 forecast --json
    p, j = forecast(git_repo, d)

    # Then: 退出 0，baseline 待定
    assert p.returncode == 0, p.stderr
    assert j["baseline"]["mode"] == "pending", j


TIMELINE = """<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-09T01:00:00Z\tbaseline\texit 0, 410.0s ok；全量：锚点不可用（依赖图未测：plugins-dropped）
2026-11-09T02:00:00Z\tbaseline\texit 0, 500.0s ok；全量：无可用候选（锚点池为空）
2026-11-09T03:00:00Z\tbaseline\t增量（经锚点 c@abcdef1234，补跑 1 个测试文件 2.0s） ok
2026-11-09T04:00:00Z\tfinal\t全量（没有可用锚点） ok
2026-11-09T05:00:00Z\tfinal\t增量 ok
"""


@pytest.mark.xfail(strict=True, reason="S4 未实现：没有 flight-doctor.py")
def test_cost_tallies_full_runs_by_reason(git_repo):
    # Given: timeline.md 有三条 baseline（两条全量、一条增量）与两条 final（一条全量、一条增量）
    d = plan_dir(git_repo, "c")
    (d / "timeline.md").write_text(TIMELINE, encoding="utf-8")

    # When: 运行 cost --json
    p = run_hook("flight-doctor", "cost", "--change-dir", str(d), "--json", cwd=git_repo)

    # Then: 计数与秒数正确；依赖图未测归「可避免」，锚点池为空归「必要」
    assert p.returncode == 0, p.stderr
    j = json.loads(p.stdout)
    assert j["baseline"] == {"full": 2, "incremental": 1, "full_sec": 910.0}, j
    assert (j["final"]["full"], j["final"]["incremental"]) == (1, 1), j
    runs = j["full_runs"]
    assert any(r["class"] == "可避免" and "plugins-dropped" in r["reason"] for r in runs), runs
    assert any(r["class"] == "必要" and "锚点池为空" in r["reason"] for r in runs), runs


@pytest.mark.xfail(strict=True, reason="S4 未实现：没有 flight-doctor.py")
def test_doctor_reports_unforwarded_wrapper(git_repo):
    # Given: 两个在途 change 的基线 deps_unmeasured.kind 都是 plugins-dropped
    for name in ("c1", "c2"):
        unmeasured_baseline(git_repo, plan_dir(git_repo, name))

    # When: 运行 doctor
    p = run_hook("flight-doctor", "doctor", "--openspec-root", str(git_repo / "openspec"), cwd=git_repo)

    # Then: 退出 0；[runner] 段写明 2 份 plugins-dropped，并点名两个契约变量
    assert p.returncode == 0, p.stderr
    runner = p.stdout.split("[runner]", 1)[1].split("\n[", 1)[0]
    assert "plugins-dropped" in runner and "2" in runner, runner
    assert "FLIGHT_PLUGIN_PATH" in runner and "FLIGHT_PYTEST_ARGS" in runner, runner
