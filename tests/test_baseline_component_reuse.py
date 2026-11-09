"""红基线按部件复用；本 change 门禁脚本只按 gate.test 闭包影响测试结论
（scenario: baseline-anchor-reuse#red-baseline-test-part-reused / lint-only-gate-script-change-keeps-test-reuse）。"""
import json

import pytest

from conftest import commit_all
from final_helpers import PY, baseline, change_and_commit, make_repo


def set_verify(d, cmd):
    path = d / "slices.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["slices"][0]["verify"] = cmd
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


@pytest.mark.xfail(strict=True, reason="S3 未实现：红基线整份不复用（候选基线不是绿）")
def test_red_baseline_test_part_reused(git_repo, tmp_path):
    # Given: gate.test 每跑一次就往仓库外的计数文件追加一行；第一次基线因 S1 的 verify 为 false 而红
    counter = tmp_path / "runs.log"
    wrapper = "#!/usr/bin/env bash\necho run >> %s\nexec %s -m pytest -q -p no:cacheprovider tests\n" % (counter, PY)
    d = make_repo(git_repo, extra={"tools/gate.sh": wrapper}, gate_extra={"test": "bash tools/gate.sh"})
    set_verify(d, "false")
    commit_all(git_repo, "verify false")
    first = baseline(git_repo, d)
    assert first["ok"] is False, first

    # When: 把 S1 的 verify 改为 true 后再运行 baseline
    set_verify(d, "true")
    commit_all(git_repo, "verify true")
    out = baseline(git_repo, d)

    # Then: 基线 ok、S1 verify 为 0、来源是本 change 旧基线；计数文件只有一行（全量只跑了一次）
    assert out["ok"] is True, out.get("reasons")
    assert out["verify"]["S1"]["exit"] == 0, out["verify"]
    assert (out.get("incremental") or {}).get("source") == "own", out.get("incremental")
    assert counter.read_text(encoding="utf-8").splitlines() == ["run"]


@pytest.mark.xfail(strict=True, reason="S3 未实现：本 change 门禁脚本一律计入测试结论的 Δ")
def test_lint_only_gate_script_change_keeps_test_reuse(git_repo):
    # Given: change c 有全绿全量基线；gate.lint 是本 change 的 verify/lint.sh，gate.test 不引用它；之后只改了 lint.sh
    lint_rel = "openspec/changes/c/verify/lint.sh"
    d = make_repo(git_repo, extra={lint_rel: "exit 0\n"}, gate_extra={"lint": "bash " + lint_rel})
    baseline(git_repo, d)
    change_and_commit(git_repo, lint_rel, "# 改过\nexit 0\n")

    # When: 再运行 baseline
    out = baseline(git_repo, d)

    # Then: 增量；lint 记录没有 reused 标记（已重跑）
    assert out["mode"] == "incremental", out.get("reuse_skipped")
    assert not (out.get("lint") or {}).get("reused"), out.get("lint")
