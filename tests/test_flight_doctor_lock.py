"""flight-doctor.py doctor 的 [checks] 与 [lock] 两节
（scenario: machine-test-lock#doctor-flags-check-as-slow-as-tests、#doctor-reports-lock-holders）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import run_hook, write
from lock_helpers import Locks

PENDING = pytest.mark.xfail(strict=True, reason="change machine-test-lock S4 未实现")

FINAL_NOTE = "全量（没有可用锚点） 测试 100.0s · 检查 ratchet 95.0s / style 1.0s · 排队 0.0s ok"


def section(text, name):
    """doctor 输出里 name 一节的正文（到下一个以 [ 开头的行为止）。"""
    return text.split(name, 1)[1].split("\n[", 1)[0]


def doctor(repo, **env):
    p = run_hook("flight-doctor", "doctor", "--openspec-root", str(repo / "openspec"), cwd=repo, env=env or None)
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout


@PENDING
def test_doctor_flags_check_as_slow_as_tests(git_repo):
    # Given: 在途 change c1 的最近一条 final 备注：测试 100 秒，检查 ratchet 95 秒、style 1 秒
    d = git_repo / "openspec" / "changes" / "c1"
    write(d / "slices.json", json.dumps({"gate": {"test": "true"}, "slices": []}))
    (d / "timeline.md").write_text("2026-11-18T03:00:00Z\tfinal\t%s\n" % FINAL_NOTE, encoding="utf-8")

    # When: 运行 doctor
    out = doctor(git_repo)

    # Then: [checks] 一节点名 c1 与 ratchet 并写明疑似重跑；不出现 style
    sec = section(out, "[checks]")
    assert "c1" in sec and "ratchet" in sec and "重跑" in sec, out
    assert "style" not in sec, sec


@PENDING
def test_doctor_reports_lock_holders(git_repo, tmp_path):
    # Given: 一个进程以 --change demo --label "final gate" 在锁目录持有独占锁
    with Locks(tmp_path) as lk:
        a = lk.hold("a", change="demo", label="final gate")

        # When: 以同一锁目录运行 doctor；持有者结束后再运行一次
        busy = doctor(git_repo, FLIGHT_LOCK_DIR=str(lk.dir))
        assert a.release() == 0
        idle = doctor(git_repo, FLIGHT_LOCK_DIR=str(lk.dir))

    # Then: 第一次的 [lock] 一节含 demo 与 final gate；第二次含「空闲」
    assert "demo" in section(busy, "[lock]") and "final gate" in section(busy, "[lock]"), busy
    assert "空闲" in section(idle, "[lock]"), idle
