"""每次门禁分层报告耗时：gate / baseline / final 输出 tier_sec，并写进 summary 与 timeline 备注
（scenario: test-tiers#tier-seconds-split-by-file、#slice-gate-reports-tier-seconds、
#baseline-and-final-report-tier-seconds、#no-tiers-file-no-tier-seconds）。
护栏（no-tiers-file-no-tier-seconds）在 base 上已成立。"""
import json
import shlex
import sys

import pytest

from conftest import commit_all, load_hook, run_hook, write

PY = shlex.quote(sys.executable)
UNIT_CMD = "%s -m pytest -q -p no:cacheprovider tests/unit" % PY
HOOKS_CMD = "%s -m pytest -q -p no:cacheprovider tests/integration/hooks" % PY
UNIT_T = "tests/unit/test_u.py::test_u"
HOOKS_T = "tests/integration/hooks/test_h.py::test_h"
TIERS = {
    "unit": {"paths": ["tests/unit/**"], "cmd": UNIT_CMD},
    "regions": {
        "docs": {"paths": ["tests/integration/docs/**"], "covers": ["docs/**"], "cmd": "true"},
        "hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"], "cmd": HOOKS_CMD},
    },
    "slow_allow": {},
}


def sleeper(name, sec):
    return "import time\n\n\ndef %s():\n    time.sleep(%s)\n" % (name, sec)


def setup_change(repo, owns, with_tiers=True, files=True):
    """被测仓库：pytest.ini、src/app.py；openspec/test-tiers.json（with_tiers 时，区域 hooks 与 docs）；
    change c 单片 S1（verify 恒绿），两个 scenario 分别映射到单元层用例（睡 0.3 秒）与区域 hooks 的用例（睡 0.6 秒）；
    files 为 False 时不预先写这两个测试文件（由调用方在切片起跑后再写）。返回 change 目录。"""
    write(repo / "pytest.ini", "[pytest]\n")
    write(repo / "src" / "app.py", "X = 1\n")
    if files:
        write(repo / "tests" / "unit" / "test_u.py", sleeper("test_u", 0.3))
        write(repo / "tests" / "integration" / "hooks" / "test_h.py", sleeper("test_h", 0.6))
    if with_tiers:
        write(repo / "openspec" / "test-tiers.json", json.dumps(TIERS, ensure_ascii=False))
    d = repo / "openspec" / "changes" / "c"
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "slices" / "S1.md", "# S1\n")
    gate = {"test": UNIT_CMD, "pytest": "%s -m pytest" % PY, "lint": None, "typecheck": None}
    if with_tiers:
        gate["integration"] = ["hooks"]
    data = {
        "version": 1, "change": "c", "gate": gate,
        "slices": [{"id": "S1", "title": "S1", "owns": list(owns), "deps": [], "verify": "true",
                    "scenarios": ["c#u", "c#h"], "packet": "slices/S1.md"}],
        "scenario_tests": {"c#u": UNIT_T, "c#h": HOOKS_T},
    }
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return d


def timeline_rows(d, event):
    """timeline.md 里某事件的备注列表。"""
    path = d / "timeline.md"
    if not path.exists():
        return []
    rows = [l.split("\t") for l in path.read_text(encoding="utf-8").splitlines() if "\t" in l]
    return [r[2] for r in rows if len(r) >= 3 and r[1] == event]


def test_tier_seconds_split_by_file():
    # Given: 逐用例耗时：单元层两个用例 0.5 与 0.3 秒（其中一个带参数后缀）、区域 hooks 一个 2.0 秒、
    #        区域 docs 一个 1.0 秒、不在任何层的 tests/test_loose.py 一个 0.1 秒
    sg = load_hook("slice-gate")
    durations = {
        "tests/unit/test_a.py::t1": 0.5,
        "tests/unit/test_a.py::t2[x]": 0.3,
        "tests/integration/hooks/test_h.py::t": 2.0,
        "tests/integration/docs/test_d.py::t": 1.0,
        "tests/test_loose.py::t": 0.1,
    }

    # When: 按分层文件归层累加
    ts = sg.tier_seconds(durations, TIERS)

    # Then: 单元 0.8 秒；集成 3.0 秒，其中 hooks 2.0、docs 1.0；未归层 0.1 秒
    assert ts["unit"] == pytest.approx(0.8), ts
    assert ts["integration"] == pytest.approx(3.0), ts
    assert ts["regions"] == {"docs": pytest.approx(1.0), "hooks": pytest.approx(2.0)}, ts
    assert ts["unclassified"] == pytest.approx(0.1), ts


def test_slice_gate_reports_tier_seconds(git_repo):
    # Given: 分层文件合法、计划选了区域 hooks；切片 S1 起跑后提交两个 scenario 测试：
    #        单元层用例睡 0.3 秒，区域 hooks 的用例睡 0.6 秒
    d = setup_change(git_repo, owns=("tests/**",), files=False)
    s = run_hook("slice-gate", "start", "S1", "--change-dir", str(d), cwd=git_repo)
    assert s.returncode == 0, s.stdout + s.stderr
    write(git_repo / "tests" / "unit" / "test_u.py", sleeper("test_u", 0.3))
    write(git_repo / "tests" / "integration" / "hooks" / "test_h.py", sleeper("test_h", 0.6))
    commit_all(git_repo, "S1")

    # When: 运行 slice-gate.py gate S1
    p = run_hook("slice-gate", "gate", "S1", "--change-dir", str(d), cwd=git_repo)

    # Then: tier_sec 的单元不少于 0.25 秒且少于 0.6 秒，集成与 regions.hooks 都不少于 0.55 秒；
    #       summary 含「单元」与「集成」；timeline 的 gate 备注以 S1 开头、含「单元」与「集成」、仍以 ok 或 red 结尾
    out = json.loads(p.stdout)
    ts = out["tier_sec"]
    assert 0.25 <= ts["unit"] < 0.6, ts
    assert ts["integration"] >= 0.55 and ts["regions"]["hooks"] >= 0.55, ts
    assert "单元" in out["summary"] and "集成" in out["summary"], out["summary"]
    notes = timeline_rows(d, "gate")
    assert notes, "timeline 没有 gate 行"
    note = notes[-1]
    assert note.startswith("S1 ") and "单元" in note and "集成" in note, note
    assert note.endswith((" ok", " red")), note


def test_baseline_and_final_report_tier_seconds(git_repo):
    # Given: 分层文件合法、计划只选了区域 hooks；单元层用例睡 0.3 秒，hooks 的用例睡 0.6 秒，两者都是已去标记的 scenario 测试
    d = setup_change(git_repo, owns=("src/app.py",))

    # When: 运行 slice-gate.py baseline，再运行 slice-gate.py final
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo)
    bl = json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))
    f = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=git_repo)
    out = json.loads(f.stdout)

    # Then: baseline 退出 0，tier_sec 的单元不少于 0.25 秒，regions 只有 hooks 且不少于 0.55 秒，集成等于 regions 之和；
    #       final 的 tier_sec 单元不少于 0.25 秒、集成不少于 0.55 秒，summary 含「单元」与「集成」；
    #       timeline 的 baseline 与 final 备注都含「单元」与「集成」
    assert p.returncode == 0, p.stdout + p.stderr
    ts = bl["tier_sec"]
    assert ts["unit"] >= 0.25, ts
    assert set(ts["regions"]) == {"hooks"} and ts["regions"]["hooks"] >= 0.55, ts
    assert ts["integration"] == pytest.approx(sum(ts["regions"].values()), abs=0.11), ts
    ft = out["tier_sec"]
    assert ft["unit"] >= 0.25 and ft["integration"] >= 0.55, ft
    assert "单元" in out["summary"] and "集成" in out["summary"], out["summary"]
    for event in ("baseline", "final"):
        notes = timeline_rows(d, event)
        assert notes and "单元" in notes[-1] and "集成" in notes[-1], (event, notes)


def test_no_tiers_file_no_tier_seconds(git_repo):
    # Given: openspec 根目录下没有 test-tiers.json；计划没有 gate.integration；两个 scenario 测试已去标记
    d = setup_change(git_repo, owns=("src/app.py",), with_tiers=False)

    # When: 运行 slice-gate.py baseline，再运行 slice-gate.py final
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo)
    bl = json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))
    out = json.loads(run_hook("slice-gate", "final", "--change-dir", str(d), cwd=git_repo).stdout)

    # Then: gate-baseline.json 与 final 输出都没有 tier_sec 键；final 的 summary 与 timeline 备注都不含「单元」
    assert p.returncode == 0, p.stdout + p.stderr
    assert "tier_sec" not in bl and "tier_sec" not in out, (bl, out)
    assert "单元" not in out["summary"], out["summary"]
    assert not any("单元" in n for n in timeline_rows(d, "baseline") + timeline_rows(d, "final"))
