"""slice-gate final 的脏工作树标注、baseline 运行标记、preflight 识别、gate.test 必填（摘自原仓 #45，不含读账本的 --reuse-fix）
（scenario: gate-full-suite-baseline#final-marks-* / final-ignores-* / lint-requires-gate-test / baseline-* / preflight-*）。"""
import json
import os
import shlex
import subprocess
import sys

from conftest import commit_all, run_hook, write
from test_slice_gate import plan, slice_, write_plan

PASSING = "def test_adds():\n    assert 1 + 1 == 2\n"
CHECK_RUNNING = (
    "import json, sys\n"
    "d = json.load(open('openspec/changes/c/gate-baseline.json', encoding='utf-8'))\n"
    "sys.exit(0 if d.get('running') is True else 1)\n"
)


def _repo(git_repo, gate_test="touch ran-g2"):
    """单片计划 + 源码 + 通过的 scenario 测试，提交一次；返回 change 目录。"""
    change = git_repo / "openspec" / "changes" / "c"
    data = plan(
        [slice_("S1", ["src/**", "tests/**"], scenarios=["cap#adds"])],
        gate={"test": gate_test, "lint": None, "typecheck": None, "full_suite_sec": None},
        scenario_tests={"cap#adds": "tests/test_cap.py::test_adds"},
    )
    write_plan(change, data)
    write(git_repo / "src" / "mod.py", "x = 1\n")
    write(git_repo / "tests" / "test_cap.py", PASSING)
    commit_all(git_repo, "artifacts + fix")
    return change


def test_final_marks_dirty_worktree(git_repo):
    # Given: 已提交的单片计划；工作树另有未跟踪的 src/extra.py
    change = _repo(git_repo)
    write(git_repo / "src" / "extra.py", "y = 1\n")

    # When: 运行 slice-gate.py final
    out = json.loads(run_hook("slice-gate", "final", "--change-dir", str(change), cwd=git_repo).stdout)

    # Then: 结果带 dirty=true，warnings 有一项含「未提交改动」与 src/extra.py
    assert out.get("dirty") is True, out
    assert any("未提交改动" in w and "src/extra.py" in w for w in out["warnings"]), out["warnings"]


def test_final_ignores_bookkeeping_dirt(git_repo):
    # Given: 已提交的单片计划；只有本 change 的 timeline.md 未提交
    change = _repo(git_repo)
    write(change / "timeline.md", "x\n")

    # When: 运行 slice-gate.py final
    out = json.loads(run_hook("slice-gate", "final", "--change-dir", str(change), cwd=git_repo).stdout)

    # Then: 结果不带 dirty，warnings 不含「未提交改动」
    assert "dirty" not in out, out
    assert not any("未提交改动" in w for w in out["warnings"]), out["warnings"]


def test_lint_requires_gate_test(tmp_path):
    # Given: slices.json 合法，但 gate 里没有 test
    data = plan([slice_("S1", ["a/**"])], gate={"test": None, "lint": None, "typecheck": None, "full_suite_sec": None})
    change = write_plan(tmp_path / "c", data)

    # When: 运行 slice-gate.py lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(change))

    # Then: 退出码非 0，stderr 含 gate.test
    assert p.returncode != 0
    assert "gate.test" in p.stderr, p.stderr


def test_baseline_marks_running(git_repo):
    # Given: gate.test 是一个读取 gate-baseline.json、running 为 true 才退出 0 的脚本
    write(git_repo / "check_running.py", CHECK_RUNNING)
    change = _repo(git_repo, gate_test="%s check_running.py" % shlex.quote(sys.executable))

    # When: 运行 slice-gate.py baseline
    p = run_hook("slice-gate", "baseline", "--change-dir", str(change), cwd=git_repo)

    # Then: 退出 0；结束后 gate-baseline.json 的 ok 为 true，且没有 running 字段
    assert p.returncode == 0, p.stdout + p.stderr
    bl = json.loads((change / "gate-baseline.json").read_text(encoding="utf-8"))
    assert bl["ok"] is True and "running" not in bl, bl


def _edit_plan_script(git_repo, field, value):
    """写一个脚本作 gate.test：运行时把 slices.json 里 S1 的 field 改成 value（模拟 baseline 后台跑期间人改计划）。"""
    write(git_repo / "edit_plan.py", (
        "import json\n"
        "p = 'openspec/changes/c/slices.json'\n"
        "d = json.load(open(p, encoding='utf-8'))\n"
        "d['slices'][0][%r] = %r\n"
        "json.dump(d, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)\n"
    ) % (field, value))
    return "%s edit_plan.py" % shlex.quote(sys.executable)


def test_baseline_keeps_plan_edits_made_while_running(git_repo):
    # Given: gate.test 运行时把 S1 的 owns 改成 ["src/**", "tests/**", "docs/**"]
    change = _repo(git_repo, gate_test=_edit_plan_script(git_repo, "owns", ["src/**", "tests/**", "docs/**"]))

    # When: 运行 slice-gate.py baseline
    p = run_hook("slice-gate", "baseline", "--change-dir", str(change), cwd=git_repo)

    # Then: 退出 0；slices.json 里 S1 的 owns 保留了 docs/**，且 gate.full_suite_sec 已写入
    assert p.returncode == 0, p.stdout + p.stderr
    data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    assert "docs/**" in data["slices"][0]["owns"], data["slices"][0]
    assert isinstance(data["gate"]["full_suite_sec"], (int, float)), data["gate"]


def test_baseline_red_when_verify_edited_while_running(git_repo):
    # Given: gate.test 运行时把 S1 的 verify 改成 "test -d src"
    change = _repo(git_repo, gate_test=_edit_plan_script(git_repo, "verify", "test -d src"))

    # When: 运行 slice-gate.py baseline，再运行 preflight
    p = run_hook("slice-gate", "baseline", "--change-dir", str(change), cwd=git_repo)
    pre = run_hook("slice-gate", "preflight", "--change-dir", str(change), cwd=git_repo)

    # Then: baseline 退出非 0、reasons 有一项含「重跑 baseline」；slices.json 保留新的 verify；preflight 拒绝起飞
    assert p.returncode != 0, p.stdout + p.stderr
    bl = json.loads((change / "gate-baseline.json").read_text(encoding="utf-8"))
    assert any("重跑 baseline" in r for r in bl["reasons"]), bl
    data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
    assert data["slices"][0]["verify"] == "test -d src", data["slices"][0]
    assert pre.returncode != 0


def test_preflight_reports_running_baseline(git_repo):
    # Given: gate-baseline.json 为 running 标记，pid 是当前仍存活的进程
    change = _repo(git_repo)
    write(change / "gate-baseline.json", json.dumps({"running": True, "pid": os.getpid(), "started": "2026-10-10T00:00:00Z"}))

    # When: 运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(change), cwd=git_repo)

    # Then: 退出码非 0，stderr 含「仍在跑」
    assert p.returncode != 0
    assert "仍在跑" in p.stderr, p.stderr


def test_preflight_reports_interrupted_baseline(git_repo):
    # Given: gate-baseline.json 为 running 标记，pid 是一个已经退出的进程
    change = _repo(git_repo)
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    write(change / "gate-baseline.json", json.dumps({"running": True, "pid": gone.pid, "started": "2026-10-10T00:00:00Z"}))

    # When: 运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(change), cwd=git_repo)

    # Then: 退出码非 0，stderr 含「中断」与 baseline
    assert p.returncode != 0
    assert "中断" in p.stderr and "baseline" in p.stderr, p.stderr
