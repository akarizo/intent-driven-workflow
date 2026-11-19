"""检查的 slice 命令（全局守护）：lint、plan_sha、baseline 记录、切片门禁的 G15
（scenario: slice-guards#lint-accepts-slice-command、#lint-requires-slice-declared-by-repo-default、
#slice-command-is-part-of-plan-sha、#baseline-runs-and-records-slice-command、#baseline-red-when-slice-command-fails、
#gate-runs-guards-in-slice-phase、#gate-reds-g13-when-guard-fails、#gate-g13-needs-green-baseline-record、
#gate-without-guards-unchanged，共 9 条）。
骨架：strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。最后一条是既有行为的守卫，在基线上已成立，不带 xfail。"""
import json
import shlex

from conftest import git, load_hook, run_hook, write
from final_helpers import timeline_rows
from test_baseline_incremental import baseline, read_bl
from test_final_tests_only import _second_repo
from test_gate_checks_baseline import check_cmd, check_dir, runs, setup_checks
from test_slice_gate import gate_repo, plan, slice_, write_plan


def lint(change):
    return run_hook("slice-gate", "lint", "--change-dir", str(change))


def checks_plan(checks, skip=None):
    gate = {"test": "python3 -m pytest -q tests", "lint": None, "typecheck": None, "checks": checks}
    if skip:
        gate["checks_skip"] = skip
    return plan([slice_("S1", ["a/**"])], gate=gate)


def guard_gate(repo, cmd, record=True, rec_cmd=None):
    """已开工的切片 S1（改动都在 owns 内）+ 计划里带 slice 命令的检查 layering；record 为真时另写一份基线，
    其中 layering 的 slice 记录是绿的（rec_cmd 给了就记那条命令）。返回 change 目录。"""
    change = gate_repo(repo)
    data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    data["gate"]["checks"] = [{"name": "layering", "slice": cmd, "final": "true"}]
    write(change / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    if record:
        bl = {"ok": True, "commit": git(repo, "rev-parse", "HEAD~1"), "plan_sha": "stub", "reasons": [],
              "test": {"exit": 0, "failed": [], "sec": 1.0}, "lint": None, "typecheck": None,
              "checks": {"layering": {"slice": {"exit": 0, "sec": 0.1, "cmd": rec_cmd or cmd}}}}
        write(change / "gate-baseline.json", json.dumps(bl, ensure_ascii=False))
    return change


def gate(repo):
    return json.loads(run_hook("slice-gate", "gate", "S1", "--change-dir", "openspec/changes/c", cwd=repo).stdout)


def phase_cmd(path):
    return "printf '%s\\n' \"$GATE_PHASE\" >> " + shlex.quote(str(path))


def test_lint_accepts_slice_command(tmp_path):
    # Given: 计划的检查 layering 带 slice 命令与 final 命令
    change = tmp_path / "openspec" / "changes" / "c"
    write_plan(change, checks_plan([{"name": "layering", "slice": "true", "final": "true"}]))

    # When: 运行 lint；再把 slice 改成空白串后运行
    ok = lint(change)
    write_plan(change, checks_plan([{"name": "layering", "slice": "  ", "final": "true"}]))
    blank = lint(change)

    # Then: 第一次退出 0；第二次以 2 退出并点名 layering 与 slice
    assert ok.returncode == 0, ok.stderr
    assert blank.returncode == 2 and "layering" in blank.stderr and "slice" in blank.stderr, blank.stderr


def test_lint_requires_slice_declared_by_repo_default(tmp_path):
    # Given: gate-checks.json 里的检查 layering 带 slice；计划里的 layering 只有 final
    change = tmp_path / "openspec" / "changes" / "c"
    write_plan(change, checks_plan([{"name": "layering", "final": "true"}]))
    write(tmp_path / "openspec" / "gate-checks.json",
          json.dumps([{"name": "layering", "slice": "python3 tools/layering.py", "final": "true"}]))

    # When: 运行 lint；再把 layering 挪进 checks_skip 并写理由后运行
    missing = lint(change)
    write_plan(change, checks_plan([], skip={"layering": "本 change 不碰包边界"}))
    skipped = lint(change)

    # Then: 第一次以 2 退出，点名 layering 与 slice；第二次退出 0
    assert missing.returncode == 2 and "layering" in missing.stderr and "slice" in missing.stderr, missing.stderr
    assert skipped.returncode == 0, skipped.stderr


def test_slice_command_is_part_of_plan_sha():
    # Given: 两份只差检查 layering 有没有 slice 命令的计划，以及一份把 slice 写成 null 的计划
    sg = load_hook("slice-gate")
    without = checks_plan([{"name": "layering", "final": "true"}])
    with_slice = checks_plan([{"name": "layering", "slice": "true", "final": "true"}])
    null_slice = checks_plan([{"name": "layering", "slice": None, "final": "true"}])

    # When: 分别计算 plan_sha
    a, b, c = sg.plan_sha(without), sg.plan_sha(with_slice), sg.plan_sha(null_slice)

    # Then: 带 slice 命令的那份与另外两份不同；没有 slice 与 slice 为 null 的两份相同
    assert a == c
    assert b != a


def test_baseline_runs_and_records_slice_command(git_repo):
    # Given: 检查 layering 没有 baseline 命令，slice 命令把收到的环境变量写进共用目录
    cmd = check_cmd(git_repo, "slice", "ok")
    d = setup_checks(git_repo, [{"name": "layering", "baseline": None, "slice": cmd,
                                 "final": check_cmd(git_repo, "final", "ok")}])

    # When: 运行 baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；基线记下 slice 的结果与命令；slice 命令运行过一次，收到的 GATE_PHASE 为 slice
    assert p.returncode == 0, p.stdout + p.stderr
    rec = read_bl(d)["checks"]["layering"]["slice"]
    assert rec["exit"] == 0 and rec["cmd"] == cmd, rec
    assert runs(git_repo) == ["slice ok"], runs(git_repo)
    env = json.loads((check_dir(git_repo, "c", "layering") / "env-slice.json").read_text(encoding="utf-8"))
    assert env["GATE_PHASE"] == "slice", env


def test_baseline_red_when_slice_command_fails(git_repo):
    # Given: 检查 layering 的 slice 命令以 3 退出
    d = setup_checks(git_repo, [{"name": "layering", "baseline": None, "slice": check_cmd(git_repo, "slice", "exit3"),
                                 "final": check_cmd(git_repo, "final", "ok")}])

    # When: 运行 baseline
    p = baseline(git_repo, d)

    # Then: 退出非 0，ok 为假；reasons 有一条同时含 layering 与 slice
    bl = read_bl(d)
    assert p.returncode != 0 and bl["ok"] is False, p.stdout + p.stderr
    assert any("layering" in r and "slice" in r for r in bl["reasons"]), bl["reasons"]


def test_gate_runs_guards_in_slice_phase(git_repo):
    # Given: 已开工的切片 S1，改动都在 owns 内；检查 layering 的 slice 命令在基线上是绿的
    seen = git_repo.parent / "phase.txt"
    change = guard_gate(git_repo, phase_cmd(seen))

    # When: 运行 gate S1
    out = gate(git_repo)

    # Then: 门禁通过，带 guards；slice 命令收到的 GATE_PHASE 为 slice；时间线备注含「守护 layering」
    assert out["ok"] is True, out
    assert out["guards"]["layering"]["exit"] == 0, out
    assert seen.read_text(encoding="utf-8").split() == ["slice"]
    assert "守护 layering" in timeline_rows(change, "gate")[-1]


def test_gate_reds_g13_when_guard_fails(git_repo):
    # Given: 已开工的切片 S1；检查 layering 的 slice 命令打印 boom 后以 3 退出
    guard_gate(git_repo, "echo boom; exit 3")

    # When: 运行 gate S1
    out = gate(git_repo)

    # Then: 门禁红；failed 有一项以 G15 guard layering 开头，含 exit 3、boom 与本片的日志路径
    assert out["ok"] is False, out
    item = next(f for f in out["failed"] if f.startswith("G15 guard layering"))
    assert "exit 3" in item and "boom" in item and ".gate-slice-S1.log" in item, item


def test_gate_g13_needs_green_baseline_record(git_repo, tmp_path):
    # Given: 已开工的切片 S1，计划里的检查 layering 带 slice 命令但没有基线；
    #        另一个仓库里基线记录的 slice 命令与计划不同
    ran_a, ran_b = git_repo.parent / "ran-a", git_repo.parent / "ran-b"
    guard_gate(git_repo, "touch " + shlex.quote(str(ran_a)), record=False)
    other = _second_repo(tmp_path)
    guard_gate(other, "touch " + shlex.quote(str(ran_b)), rec_cmd="true")

    # When: 分别运行 gate S1
    outs = [gate(git_repo), gate(other)]

    # Then: 两次都红，failed 有一项以 G15 guard layering 开头并含「重跑 baseline」；slice 命令都没有被运行
    for out in outs:
        assert out["ok"] is False, out
        assert any(f.startswith("G15 guard layering") and "重跑 baseline" in f for f in out["failed"]), out["failed"]
    assert not ran_a.exists() and not ran_b.exists()


def test_gate_without_guards_unchanged(git_repo):
    # Given: 已开工的切片 S1；计划里没有任何检查带 slice
    change = gate_repo(git_repo)

    # When: 运行 gate S1
    out = gate(git_repo)

    # Then: 门禁 JSON 没有 guards，failed 没有 G15 开头的项；时间线的 gate 备注不含「守护」
    assert out["ok"] is True, out
    assert "guards" not in out and not [f for f in out["failed"] if f.startswith("G15")], out
    assert "守护" not in timeline_rows(change, "gate")[-1]
