"""ship 的「final 过期」理由带补跑预告；成本预告的耗时取自基线（scenario: ship-rerun-forecast#stale-final-reason-says-incremental-rerun、
#stale-final-reason-says-full-rerun-with-why、#forecast-reads-suite-sec-from-baseline，共 3 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, git, run_hook, write
from final_helpers import baseline, change_and_commit, final, make_repo
from test_flight_doctor import forecast, plan_dir

PENDING = pytest.mark.xfail(strict=True, reason="骨架：切片 S3 实现后去掉")


def _green_final(repo):
    """基线测到依赖图、final 已绿并留下锚点、飞行记录已提交的 change。"""
    d = make_repo(repo)
    baseline(repo, d)
    out, _ = final(repo, d)
    assert out["ok"] is True, out
    commit_all(repo, "chore(flight): 记录")
    return d


def _ship(repo, d):
    p = run_hook("slice-gate", "ship", "--change-dir", str(d), cwd=repo)
    return p, json.loads(p.stdout)


@PENDING
def test_stale_final_reason_says_incremental_rerun(git_repo):
    # Given: 基线测到了依赖图，final 已绿并留下锚点；之后提交了对 src/a.py 的修改
    d = _green_final(git_repo)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # touched\n")

    # When: 运行 slice-gate.py ship
    p, out = _ship(git_repo, d)

    # Then: 退出 1；有一条理由同时含「final 过期」与「补跑将是增量」
    assert p.returncode == 1, out
    assert any("final 过期" in r and "补跑将是增量" in r for r in out["reasons"]), out["reasons"]


@PENDING
def test_stale_final_reason_says_full_rerun_with_why(git_repo):
    # Given: 同样的 change；之后提交了对全局文件 pytest.ini 的修改
    d = _green_final(git_repo)
    change_and_commit(git_repo, "pytest.ini", "[pytest]\naddopts = -q\n")

    # When: 运行 slice-gate.py ship
    p, out = _ship(git_repo, d)

    # Then: 退出 1；有一条理由同时含「final 过期」「补跑将是全量」与 pytest.ini
    assert p.returncode == 1, out
    assert any("final 过期" in r and "补跑将是全量" in r and "pytest.ini" in r for r in out["reasons"]), out["reasons"]


@PENDING
def test_forecast_reads_suite_sec_from_baseline(git_repo):
    # Given: change c 的计划里没有 full_suite_sec、基线的 full_suite_sec 为 300.5；
    #        change old 的基线没有该字段、计划里旧的 gate.full_suite_sec 为 816
    head = git(git_repo, "rev-parse", "HEAD")
    c = plan_dir(git_repo, "c", full_sec=None)
    write(c / "gate-baseline.json", json.dumps({"commit": head, "ok": True, "mode": "full", "reasons": [],
                                                 "test": {"exit": 0, "sec": 290.0}, "full_suite_sec": 300.5,
                                                 "snapshot": {}}))
    old = plan_dir(git_repo, "old", full_sec=816)
    write(old / "gate-baseline.json", json.dumps({"commit": head, "ok": True, "mode": "full", "reasons": [],
                                                   "test": {"exit": 0, "sec": 800.0}, "snapshot": {}}))

    # When: 分别运行 flight-doctor.py forecast --json
    p1, j1 = forecast(git_repo, c)
    p2, j2 = forecast(git_repo, old)

    # Then: 都退出 0；c 的 final.sec 来自基线（300.5），old 的回退到旧字段（816）
    assert p1.returncode == 0 and p2.returncode == 0, (p1.stderr, p2.stderr)
    assert j1["final"]["sec"] == 300.5, j1
    assert j2["final"]["sec"] == 816, j2
