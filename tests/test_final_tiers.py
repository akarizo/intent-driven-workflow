"""增量 final 与测试分层叠加
（scenario: incremental-final#tiers-incremental-probes-selected-unit-files、#tiers-region-runs-only-when-selected）。"""
import json
import shlex
import sys

from conftest import commit_all, write
from final_helpers import baseline, change_and_commit, final

PY = shlex.quote(sys.executable)
UNIT_CMD = "%s -m pytest -q -p no:cacheprovider tests/unit" % PY
HOOKS_CMD = "%s -m pytest -q -p no:cacheprovider tests/integration/hooks" % PY
IMPORT_SRC = ("import os\nimport sys\n\nsys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "
              "%r))\n")


def tiers_repo(repo, with_region):
    """分层仓库：单元层 tests/unit（test_a 依赖 src/a.py，test_z 纯算术）；with_region 时另有区域 hooks
    （tests/integration/hooks/test_h.py 依赖 src/hooks/h.py）并选进 gate.integration。scenario 映射到 test_z。"""
    write(repo / "pytest.ini", "[pytest]\n")
    write(repo / "src" / "a.py", "def a():\n    return 1\n")
    write(repo / "tests" / "unit" / "test_a.py",
          IMPORT_SRC % "../../src" + "from a import a\n\n\ndef test_a():\n    assert a() == 1\n")
    write(repo / "tests" / "unit" / "test_z.py", "def test_z():\n    assert 1 + 1 == 2\n")
    tiers = {"unit": {"paths": ["tests/unit/**"], "cmd": UNIT_CMD}, "regions": {}, "slow_allow": {}}
    gate = {"test": UNIT_CMD, "pytest": "%s -m pytest" % PY, "lint": None, "typecheck": None}
    if with_region:
        write(repo / "src" / "hooks" / "h.py", "H = 1\n")
        write(repo / "tests" / "integration" / "hooks" / "test_h.py",
              IMPORT_SRC % "../../../src/hooks" + "import h\n\n\ndef test_h():\n    assert h.H == 1\n")
        tiers["regions"]["hooks"] = {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"],
                                     "cmd": HOOKS_CMD}
        gate["integration"] = ["hooks"]
    write(repo / "openspec" / "test-tiers.json", json.dumps(tiers, ensure_ascii=False))
    d = repo / "openspec" / "changes" / "c"
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "slices" / "S1.md", "# S1\n")
    data = {"version": 1, "change": "c", "gate": gate,
            "slices": [{"id": "S1", "title": "S1", "owns": ["src/**"], "deps": [], "verify": "true",
                        "scenarios": ["c#z"], "packet": "slices/S1.md"}],
            "scenario_tests": {"c#z": "tests/unit/test_z.py::test_z"}}
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return d


def test_tiers_incremental_probes_selected_unit_files(git_repo):
    # Given: 分层仓库 baseline 绿；随后改了 src/a.py，使单元层 tests/unit/test_a.py 的用例开始写真实文件；
    #        tests/unit/test_z.py 不依赖 src/a.py
    d = tiers_repo(git_repo, with_region=False)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "import os\nimport tempfile\n\n\ndef a():\n"
                      "    open(os.path.join(tempfile.mkdtemp(), 'x'), 'w').close()\n    return 1\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 红，G11 点名 tests/unit/test_a.py 的用例；tests/unit/test_z.py 没有被重跑
    assert out["ok"] is False, out
    assert any("G11" in f and "tests/unit/test_a.py" in f for f in out["failed"]), out["failed"]
    assert out["incremental"]["mode"] == "incremental", out["incremental"]
    assert "tests/unit/test_z.py" not in out["incremental"]["rerun"], out["incremental"]


def test_tiers_region_runs_only_when_selected(git_repo):
    # Given: 分层仓库已选区域 hooks，baseline 绿；随后只改了单元层依赖的 src/a.py
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 区域 hooks 没有运行，regions_skipped 含 hooks；final 绿
    assert out["ok"] is True, out
    assert "hooks" not in out["tier_sec"]["regions"], out["tier_sec"]
    assert "hooks" in out["incremental"]["regions_skipped"], out["incremental"]


def test_tiers_region_runs_when_anchor_never_tested_it(git_repo):
    # Given: change c 已选区域 hooks 并跑过 baseline；随后另一个 change o（同一分层文件、同一 gate.test，未选任何区域）
    #        跑了 baseline，留下更新的锚点；之后把区域 covers 下的 src/hooks/h.py 改坏（H = 2，tests/integration/hooks/test_h.py 会失败）
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["change"] = "o"
    data["gate"].pop("integration")
    o = git_repo / "openspec" / "changes" / "o"
    write(o / "proposal.md", "## Why\n\n另一个 change。\n")
    write(o / "slices" / "S1.md", "# S1\n")
    write(o / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    write(git_repo / "src" / "a.py", "# o 顺带的无害改动：让 o 的锚点 Δ 严格更小、必被选中\ndef a():\n    return 1\n")
    commit_all(git_repo, "plan o")
    baseline(git_repo, o)
    change_and_commit(git_repo, "src/hooks/h.py", "H = 2\n")

    # When: 对 change c 运行 final
    out, p = final(git_repo, d)

    # Then: 区域 hooks 运行了，final 红且 G2 region hooks 点名失败
    assert "hooks" in out["tier_sec"]["regions"], out
    assert out["ok"] is False and any("region hooks" in f for f in out["failed"]), out


def test_tiers_region_runs_when_selected_file_in_region(git_repo):
    # Given: 分层仓库已选区域 hooks，baseline 绿（锚点测过 hooks）；随后只改了区域里的测试文件
    #        tests/integration/hooks/test_h.py（落在区域 paths 里、不在 covers 里），并让它失败
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    change_and_commit(git_repo, "tests/integration/hooks/test_h.py",
                      IMPORT_SRC % "../../../src/hooks" + "import h\n\n\ndef test_h():\n    assert h.H == 2\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 区域 hooks 运行了（不在 regions_skipped），rerun 含该测试文件；final 红且 G2 region hooks 点名失败
    assert "hooks" in out["tier_sec"]["regions"], out
    assert "hooks" not in out["incremental"]["regions_skipped"], out["incremental"]
    assert "tests/integration/hooks/test_h.py" in out["incremental"]["rerun"], out["incremental"]
    assert out["ok"] is False and any("region hooks" in f for f in out["failed"]), out
