"""分层文件按条目参与增量 final（scenario: tier-file-incremental#slow-allow-change-keeps-incremental、
#selected-region-entry-change-runs-region、#unselected-region-change-ignored、#unit-change-still-full、
#impacted-not-full-on-slow-allow-change）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。护栏（unit-change-still-full）
在 base 上已成立，不带 xfail。"""
import json
import shlex
import sys

import pytest

from final_helpers import baseline, change_and_commit, final
from test_final_tiers import tiers_repo

PY = shlex.quote(sys.executable)
SRC_A2 = "def a():\n    return 1  # 改过\n"
TIER_REL = "openspec/test-tiers.json"


def _tiers_after(repo, fn):
    """读分层文件交给 fn 原地改，返回改后的 JSON 文本（不写盘）。"""
    t = json.loads((repo / TIER_REL).read_text(encoding="utf-8"))
    fn(t)
    return json.dumps(t, ensure_ascii=False)


def _allow(t, nodeid):
    t["slow_allow"][nodeid] = {"reason": "样本大", "approved": "2026-11-02T00:00:00Z · 放行"}


@pytest.mark.xfail(strict=True, reason="S1 未实现：slow_allow 改动不再让 final 全量")
def test_slow_allow_change_keeps_incremental(git_repo):
    # Given: 已选区域 hooks 的分层仓库 baseline 绿；随后在 slow_allow 新增 tests/unit/test_z.py::test_z 的放行条目，
    #        并改了单元层依赖的 src/a.py
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    change_and_commit(git_repo, TIER_REL, _tiers_after(git_repo, lambda t: _allow(t, "tests/unit/test_z.py::test_z")))
    change_and_commit(git_repo, "src/a.py", SRC_A2)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 绿、增量；重跑含 test_a（依赖 src/a.py）与 test_z（放行条目有变）；区域 hooks 跳过
    assert out["ok"] is True, out
    inc = out["incremental"]
    assert inc["mode"] == "incremental", inc
    assert {"tests/unit/test_a.py", "tests/unit/test_z.py"} <= set(inc["rerun"]), inc
    assert "hooks" in inc["regions_skipped"], inc


@pytest.mark.xfail(strict=True, reason="S1 未实现：已选区域条目改动只让该区域必跑")
def test_selected_region_entry_change_runs_region(git_repo):
    # Given: 已选区域 hooks 的分层仓库 baseline 绿；随后只给区域 hooks 的 covers 加了一个 glob，并改了 src/a.py
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    change_and_commit(git_repo, TIER_REL,
                      _tiers_after(git_repo, lambda t: t["regions"]["hooks"]["covers"].append("src/extra/**")))
    change_and_commit(git_repo, "src/a.py", SRC_A2)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 绿、增量；区域 hooks 运行了（tier_sec.regions 含它，regions_skipped 不含它）
    assert out["ok"] is True, out
    inc = out["incremental"]
    assert inc["mode"] == "incremental", inc
    assert "hooks" in out["tier_sec"]["regions"], out["tier_sec"]
    assert "hooks" not in inc["regions_skipped"], inc


@pytest.mark.xfail(strict=True, reason="S1 未实现：未选区域的改动不影响 final")
def test_unselected_region_change_ignored(git_repo):
    # Given: 已选区域 hooks 的分层仓库 baseline 绿；随后在分层文件里新增未选区域 extra，并改了 src/a.py
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    extra = {"paths": ["tests/integration/extra/**"], "covers": ["src/extra/**"],
             "cmd": "%s -m pytest -q -p no:cacheprovider tests/integration/extra" % PY}
    change_and_commit(git_repo, TIER_REL, _tiers_after(git_repo, lambda t: t["regions"].__setitem__("extra", extra)))
    change_and_commit(git_repo, "src/a.py", SRC_A2)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 绿、增量；区域 hooks 照旧跳过
    assert out["ok"] is True, out
    inc = out["incremental"]
    assert inc["mode"] == "incremental", inc
    assert "hooks" in inc["regions_skipped"], inc


def test_unit_change_still_full(git_repo):
    # Given: 已选区域 hooks 的分层仓库 baseline 绿；随后给 unit.paths 加了 glob tests/unit2/**，并改了 src/a.py
    d = tiers_repo(git_repo, with_region=True)
    baseline(git_repo, d)
    change_and_commit(git_repo, TIER_REL, _tiers_after(git_repo, lambda t: t["unit"]["paths"].append("tests/unit2/**")))
    change_and_commit(git_repo, "src/a.py", SRC_A2)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 单元层变了 → 全量，原因是没有可用锚点
    inc = out["incremental"]
    assert inc["mode"] == "full", inc
    assert "没有可用锚点" in inc["full_why"], inc


@pytest.mark.xfail(strict=True, reason="S1 未实现：gate.impacted 路径不因 slow_allow 改动退回全量")
def test_impacted_not_full_on_slow_allow_change(git_repo):
    # Given: 分层仓库（无区域）配了 gate.impacted（只跑 tests/unit/test_a.py），baseline 绿；
    #        随后在 slow_allow 新增 tests/unit/test_a.py::test_a 的放行条目，并改了 src/a.py
    d = tiers_repo(git_repo, with_region=False)
    rel = (d / "slices.json").relative_to(git_repo).as_posix()
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["gate"]["impacted"] = "%s -m pytest -q -p no:cacheprovider tests/unit/test_a.py" % PY
    change_and_commit(git_repo, rel, json.dumps(data, ensure_ascii=False, indent=1))
    baseline(git_repo, d)
    change_and_commit(git_repo, TIER_REL, _tiers_after(git_repo, lambda t: _allow(t, "tests/unit/test_a.py::test_a")))
    change_and_commit(git_repo, "src/a.py", SRC_A2)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 绿，增量由 gate.impacted 运行
    assert out["ok"] is True, out
    assert out["incremental"].get("source") == "impacted", out["incremental"]
