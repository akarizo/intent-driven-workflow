"""final 运行检查并以 G9 判定、baseline 与 final 共用目录与环境变量
（scenario: gate-paired-checks#check-env-and-dir-shared-across-phases、#final-*）。
夹具来自 test_gate_checks_baseline.py（S2）。"""
import json
import os
import pathlib
import shlex

from conftest import commit_all, git, write
from test_baseline_incremental import baseline, first_full, marker, read_bl, setup_change
from test_gate_checks_baseline import check_dir, final_json, parity, runs, set_checks, setup_checks
from test_slice_gate_final import STILL_XFAIL, _repo as final_repo


# ---------------------------------------------------------------- 运行契约：两阶段共用目录与环境


def test_check_env_and_dir_shared_across_phases(git_repo):
    # Given: 在仓库的另一个 worktree 里有 change c，检查 parity 的 baseline 命令把收到的环境变量与工作目录写进 $GATE_CHECK_DIR，
    #        并写一个 seed.txt；final 命令同样记录环境变量，seed.txt 不存在就退出 4
    setup_checks(git_repo, [parity(git_repo, b_action="seed", f_action="need-seed")])
    wt = git_repo.parent / "wt"
    git(git_repo, "worktree", "add", "-q", str(wt), "-b", "wt")
    dw = wt / "openspec" / "changes" / "c"

    # When: 在该 worktree 里依次运行 slice-gate.py baseline 与 slice-gate.py final
    b = baseline(wt, dw)
    out = final_json(wt, dw)

    # Then: 两次都退出 0；两次拿到的 GATE_CHECK_DIR 相同，都是主仓库 .git/flight-gate-checks/c/parity；
    #       两次的 GATE_CHANGE 都是 c，GATE_BASE_COMMIT 都等于基线的 commit，工作目录都是该 worktree 的根；GATE_PHASE 依次为 baseline、final
    assert b.returncode == 0, b.stdout + b.stderr
    assert out["ok"] is True, out
    cdir = pathlib.Path(os.path.realpath(git_repo / ".git")) / "flight-gate-checks" / "c" / "parity"
    commit = read_bl(dw)["commit"]
    for phase in ("baseline", "final"):
        env = json.loads((cdir / ("env-%s.json" % phase)).read_text(encoding="utf-8"))
        assert env["GATE_PHASE"] == phase, env
        assert os.path.realpath(env["GATE_CHECK_DIR"]) == str(cdir), env
        assert env["GATE_CHANGE"] == "c", env
        assert env["GATE_BASE_COMMIT"] == commit, env
        assert os.path.realpath(env["cwd"]) == os.path.realpath(wt), env


# ---------------------------------------------------------------- final 运行检查并以 G9 判定


def test_final_red_when_check_fails(git_repo):
    # Given: 检查 parity 的 baseline 绿；final 命令依次打印 line-01 到 line-30 后退出 1；基线已绿
    d = setup_checks(git_repo, [parity(git_repo, f_action="noisy")])
    first_full(git_repo, d)

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: ok 为 false；failed 有一项以 G9 check parity 开头，含 exit 1 与 line-30，不含 line-10，并含 .gate-final.log 的路径；
    #       该日志文件含 line-01
    assert out["ok"] is False, out
    item = next(f for f in out["failed"] if f.startswith("G9 check parity"))
    assert "exit 1" in item and "line-30" in item and "line-10" not in item, item
    assert ".gate-final.log" in item, item
    log = check_dir(git_repo, "c", "parity") / ".gate-final.log"
    assert "line-01" in log.read_text(encoding="utf-8")


def test_final_skips_checks_when_g7_red(git_repo):
    # Given: scenario 测试仍带 strict xfail；检查 parity 的 final 命令运行时会写一个标记文件
    flag = marker(git_repo, "ran-check")
    change = final_repo(git_repo, "true", cap_test=STILL_XFAIL)
    set_checks(change, [{"name": "parity", "baseline": None, "final": "touch %s" % shlex.quote(str(flag))}])
    commit_all(git_repo, "checks")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, change)

    # Then: failed 有 G7 项；标记文件不存在；warnings 含「G9 检查未跑」，也仍含「G2 全量未跑」
    assert any(f.startswith("G7") for f in out["failed"]), out["failed"]
    assert not flag.exists()
    assert any("G9 检查未跑" in w for w in out["warnings"]), out["warnings"]
    assert any("G2 全量未跑" in w for w in out["warnings"]), out["warnings"]


def test_final_runs_checks_when_full_suite_red(git_repo):
    # Given: 基线已绿，检查 parity 的 final 命令运行时会记一笔；之后新增了一个失败的测试并提交；scenario 全绿
    d = setup_checks(git_repo, [parity(git_repo)])
    first_full(git_repo, d)
    write(git_repo / "tests" / "test_new_red.py", "def test_new_red():\n    assert False\n")
    commit_all(git_repo, "new red")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: ok 为 false，failed 有 G2 test 项；检查的 final 运行了一次
    assert out["ok"] is False, out
    assert any(f.startswith("G2 test") for f in out["failed"]), out["failed"]
    assert runs(git_repo).count("final ok") == 1, runs(git_repo)


def test_final_red_when_baseline_record_missing(git_repo):
    # Given: change c 的基线是在计划里还没有检查时跑的；之后加了两个检查：a 的 baseline 为 true、final 运行时写标记 A；
    #        b 的 baseline 为 null、final 运行时写标记 B
    fa, fb = marker(git_repo, "ran-a"), marker(git_repo, "ran-b")
    d = setup_change(git_repo, old_red=False)
    first_full(git_repo, d)
    set_checks(d, [{"name": "a", "baseline": "true", "final": "touch %s" % shlex.quote(str(fa))},
                   {"name": "b", "baseline": None, "final": "touch %s" % shlex.quote(str(fb))}])
    commit_all(git_repo, "add checks")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: failed 有一项以 G9 check a 开头并含「基线」；标记 A 不存在；标记 B 存在；failed 里没有 G9 check b
    assert any(f.startswith("G9 check a") and "基线" in f for f in out["failed"]), out["failed"]
    assert not fa.exists()
    assert fb.exists()
    assert not any(f.startswith("G9 check b") for f in out["failed"]), out["failed"]
