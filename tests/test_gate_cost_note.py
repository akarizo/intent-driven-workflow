"""final 留下 gate.test 与各项检查的秒数；test-tiers.py run / probe 持独占锁
（scenario: machine-test-lock#final-note-records-test-and-check-seconds、#test-tiers-run-and-probe-hold-exclusive-lock）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import json
import re
import shlex
import subprocess
import sys

from conftest import commit_all, hook_path, write
from final_helpers import baseline, change_and_commit, final, make_repo, timeline_rows
from lock_helpers import QUEUED, Locks, wait_for

PY = shlex.quote(sys.executable)
CHECK = {"name": "probe-check", "baseline": "true", "final": "true", "timeout_sec": 60}


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def test_final_note_records_test_and_check_seconds(git_repo):
    # Given: 计划配了一项检查 probe-check，baseline 已绿，之后改了 src/a.py
    d = make_repo(git_repo, gate_extra={"checks": [CHECK]})
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # touched\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 输出 JSON 的 sec.test 是数字，sec.checks 恰含 probe-check 且值是数字；
    #       时间线备注带「测试 <数字>s」与「检查 probe-check <数字>s」，并以 ok 结尾
    assert p.returncode == 0, p.stdout + p.stderr
    sec = out["sec"]
    assert number(sec["test"]), sec
    assert set(sec["checks"]) == {"probe-check"} and number(sec["checks"]["probe-check"]), sec
    note = timeline_rows(d, "final")[-1]
    assert re.search(r"测试 \d+\.\ds", note), note
    assert re.search(r"检查 probe-check \d+\.\ds", note), note
    assert note.endswith(" ok"), note


def test_test_tiers_run_and_probe_hold_exclusive_lock(git_repo, tmp_path):
    # Given: 一个有分层文件的仓库（单元层一个纯函数用例）
    write(git_repo / "pytest.ini", "[pytest]\n")
    write(git_repo / "tests" / "unit" / "test_u.py", "def test_adds():\n    assert 1 + 1 == 2\n")
    tiers = {"unit": {"paths": ["tests/unit/**"], "cmd": "%s -m pytest -q -p no:cacheprovider tests/unit" % PY},
             "regions": {}, "slow_allow": {}}
    write(git_repo / "openspec" / "test-tiers.json", json.dumps(tiers, ensure_ascii=False))
    commit_all(git_repo, "tiers")

    for sub in (["run", "unit"], ["probe"]):
        base = tmp_path / sub[0]
        base.mkdir()
        err_path = base / "stderr"
        with Locks(base) as lk:
            # Given: 另一个进程在同一锁目录持有独占锁
            a = lk.hold("a", label="their baseline")

            # When: 运行 test-tiers.py run unit / probe
            with open(err_path, "w", encoding="utf-8") as fe:
                proc = subprocess.Popen([sys.executable, str(hook_path("test-tiers")), *sub], cwd=git_repo,
                                        env=lk.env(), stdout=subprocess.DEVNULL, stderr=fe)
            try:
                # Then: stderr 出现排队提示，持有者结束之前不结束；持有者结束后以 0 退出
                queued = lambda: QUEUED in err_path.read_text(encoding="utf-8", errors="replace")
                assert wait_for(lambda: queued() or proc.poll() is not None, 20), sub
                assert queued() and proc.poll() is None, (sub, err_path.read_text(encoding="utf-8"))
                assert a.release() == 0
                assert proc.wait(timeout=120) == 0, (sub, err_path.read_text(encoding="utf-8"))
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=5)
