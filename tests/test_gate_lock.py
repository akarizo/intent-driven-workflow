"""slice-gate.py 各命令按方式持全机测试锁、争抢时 G10 降级、时间线带排队与负载
（scenario: machine-test-lock#baseline-and-final-hold-exclusive-lock、#slice-gate-holds-shared-lock、
#final-queues-behind-exclusive-holder、#gate-runs-when-lock-module-missing、
#contended-run-downgrades-slow-unit-verdict、#lock-off-keeps-slow-unit-verdict、#timeline-records-wait-and-load，共 7 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

import pytest

from conftest import HOOKS, commit_all, hook_path, run_hook, write
from final_helpers import baseline, final, gate_json, make_repo, timeline_rows
from lock_helpers import QUEUED, Locks, wait_for

PENDING = pytest.mark.xfail(strict=True, reason="change machine-test-lock S3 未实现")

PY = shlex.quote(sys.executable)
UNIT_CMD = "%s -m pytest -q -p no:cacheprovider tests/unit" % PY
SLEEPY = "tests/unit/test_u.py::test_sleepy"


def tiers_repo(repo):
    """被测仓库：分层文件合法（只有单元层），单元层一个每次睡 3.1 秒的纯函数用例；change c 单片 S1（verify 恒绿）。
    返回 change 目录。"""
    write(repo / "pytest.ini", "[pytest]\n")
    write(repo / "src" / "app.py", "X = 1\n")
    write(repo / "tests" / "unit" / "test_u.py", "import time\n\n\ndef test_sleepy():\n    time.sleep(3.1)\n")
    tiers = {"unit": {"paths": ["tests/unit/**"], "cmd": UNIT_CMD}, "regions": {}, "slow_allow": {}}
    write(repo / "openspec" / "test-tiers.json", json.dumps(tiers, ensure_ascii=False))
    d = repo / "openspec" / "changes" / "c"
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "slices" / "S1.md", "# S1\n")
    data = {
        "version": 1, "change": "c",
        "gate": {"test": UNIT_CMD, "pytest": "%s -m pytest" % PY, "lint": None, "typecheck": None},
        "slices": [{"id": "S1", "title": "S1", "owns": ["src/app.py"], "deps": [], "verify": "true",
                    "scenarios": [], "packet": "slices/S1.md"}],
        "scenario_tests": {},
    }
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return d


def read_bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def held_exclusive(lock):
    return lock["mode"] == "exclusive" and lock["state"] == "held" and isinstance(lock["waited"], (int, float))


@PENDING
def test_baseline_and_final_hold_exclusive_lock(git_repo):
    # Given: 一个有计划、测试全绿的仓库，锁目录里没有其他持有者
    d = make_repo(git_repo)

    # When: 依次运行 baseline 与 final
    bout = baseline(git_repo, d)
    fout, fp = final(git_repo, d)

    # Then: 两次输出 JSON 的 lock 都是独占、held、排队秒数是数字；gate-baseline.json 里有同样的 lock
    assert bout["ok"] is True and fp.returncode == 0, (bout, fp.stdout + fp.stderr)
    assert held_exclusive(bout["lock"]), bout["lock"]
    assert held_exclusive(fout["lock"]), fout["lock"]
    assert held_exclusive(read_bl(d)["lock"]), read_bl(d)


@PENDING
def test_slice_gate_holds_shared_lock(git_repo):
    # Given: 同一个仓库，切片 S1 已 start
    d = make_repo(git_repo)
    p = run_hook("slice-gate", "start", "S1", "--change-dir", str(d), cwd=git_repo)
    assert p.returncode == 0, p.stdout + p.stderr

    # When: 运行 gate S1
    p = run_hook("slice-gate", "gate", "S1", "--change-dir", str(d), cwd=git_repo)

    # Then: 输出 JSON 的 lock 是共享、held
    lock = gate_json(p)["lock"]
    assert lock["mode"] == "shared" and lock["state"] == "held", lock


@PENDING
def test_final_queues_behind_exclusive_holder(git_repo, tmp_path):
    # Given: baseline 已绿；另一个进程在同一锁目录持有独占锁
    d = make_repo(git_repo)
    baseline(git_repo, d)
    out_path, err_path = tmp_path / "final.out", tmp_path / "final.err"
    with Locks(tmp_path) as lk:
        a = lk.hold("a", change="other", label="their final")

        # When: 以同一锁目录运行 final
        with open(out_path, "w", encoding="utf-8") as fo, open(err_path, "w", encoding="utf-8") as fe:
            proc = subprocess.Popen([sys.executable, str(hook_path("slice-gate")), "final", "--change-dir", str(d)],
                                    cwd=git_repo, env=lk.env(), stdout=fo, stderr=fe)
        try:
            # Then: final 的 stderr 出现排队提示，持有者结束之前 final 不结束；
            #       持有者结束后 final 以 0 退出，lock 为 held 且排队秒数大于 0
            queued = lambda: QUEUED in err_path.read_text(encoding="utf-8", errors="replace")
            assert wait_for(lambda: queued() or proc.poll() is not None, 20), err_path.read_text(encoding="utf-8")
            assert queued() and proc.poll() is None, err_path.read_text(encoding="utf-8")
            time.sleep(0.3)  # 让排队秒数在保留 1 位小数后仍大于 0
            assert proc.poll() is None
            assert a.release() == 0
            assert proc.wait(timeout=180) == 0, err_path.read_text(encoding="utf-8")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
    lines = [l for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    lock = json.loads(lines[-1])["lock"]
    assert lock["state"] == "held" and lock["waited"] > 0, lock


@PENDING
def test_gate_runs_when_lock_module_missing(git_repo, tmp_path):
    # Given: 一份不含 flight-lock.py 的 hooks 目录副本
    d = make_repo(git_repo)
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("flight-lock.py", "__pycache__"))
    assert not (hooks / "flight-lock.py").exists()

    # When: 用副本里的 slice-gate.py 运行 baseline
    p = subprocess.run([sys.executable, str(hooks / "slice-gate.py"), "baseline", "--change-dir", str(d)],
                       cwd=git_repo, capture_output=True, text=True)

    # Then: baseline 以 0 退出，lock.state 是 unavailable
    assert p.returncode == 0, p.stdout + p.stderr
    assert gate_json(p)["lock"]["state"] == "unavailable", p.stdout


@PENDING
def test_contended_run_downgrades_slow_unit_verdict(git_repo, tmp_path):
    # Given: 单元层有一个每次睡 3.1 秒的纯函数用例；另一个进程以 FLIGHT_LOCK_MAX_HOLD_SEC=0.3 持有独占锁且不结束
    d = tiers_repo(git_repo)
    with Locks(tmp_path) as lk:
        a = lk.hold("a", label="stuck-final", env={"FLIGHT_LOCK_MAX_HOLD_SEC": "0.3"})

        # When: 以同一锁目录运行 baseline
        p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo,
                     env={"FLIGHT_LOCK_DIR": str(lk.dir)})
        still_held = not a.exited()

    # Then: baseline 以 0 退出，lock.state 是 timeout；reasons 里没有 G10；
    #       warnings 里有一条同时含 G10、该用例 id 与「降为警告」
    bl = read_bl(d)
    assert still_held
    assert p.returncode == 0, p.stdout + p.stderr
    assert bl["lock"]["state"] == "timeout", bl["lock"]
    assert not any(r.startswith("G10") for r in bl["reasons"]), bl["reasons"]
    assert any("G10" in w and SLEEPY in w and "降为警告" in w for w in bl.get("warnings") or []), bl.get("warnings")


@PENDING
def test_lock_off_keeps_slow_unit_verdict(git_repo):
    # Given: 同样的仓库（单元层有一个每次睡 3.1 秒的纯函数用例）
    d = tiers_repo(git_repo)

    # When: 带 FLIGHT_LOCK=off 运行 baseline
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo, env={"FLIGHT_LOCK": "off"})

    # Then: lock.state 是 off；baseline 以非 0 退出，reasons 里有一条以 G10 开头并点名该用例
    bl = read_bl(d)
    assert bl["lock"]["state"] == "off", bl
    assert p.returncode != 0, p.stdout + p.stderr
    assert any(r.startswith("G10") and SLEEPY in r for r in bl["reasons"]), bl["reasons"]


@PENDING
def test_timeline_records_wait_and_load(git_repo):
    # Given: 一个有计划、测试全绿的仓库
    d = make_repo(git_repo)

    # When: 依次运行 baseline、start S1 + gate S1、final
    baseline(git_repo, d)
    p = run_hook("slice-gate", "start", "S1", "--change-dir", str(d), cwd=git_repo)
    assert p.returncode == 0, p.stdout + p.stderr
    run_hook("slice-gate", "gate", "S1", "--change-dir", str(d), cwd=git_repo)
    _, fp = final(git_repo, d)

    # Then: 三条时间线备注都带「排队 <数字>s」；final 的备注以 ok 结尾；gate 的备注以 S1 开头、以结论词结尾；
    #       平台取得到负载时三条备注都含「负载 」
    assert fp.returncode == 0, fp.stdout + fp.stderr
    notes = [timeline_rows(d, ev)[-1] for ev in ("baseline", "gate", "final")]
    for note in notes:
        assert re.search(r"排队 \d+\.\ds", note), note
    assert notes[2].endswith(" ok"), notes[2]
    assert notes[1].startswith("S1 ") and (notes[1].endswith(" ok") or notes[1].endswith(" red")), notes[1]
    try:
        os.getloadavg()
        has_load = True
    except (AttributeError, OSError):
        has_load = False
    if has_load:
        for note in notes:
            assert "负载 " in note, note
