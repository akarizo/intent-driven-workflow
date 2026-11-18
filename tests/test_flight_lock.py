"""flight-lock.py：全机测试锁的独占 / 共享 / 不饿死 / 重入 / 放弃等待 / 回退
（scenario: machine-test-lock#exclusive-holders-mutually-exclude、#shared-holders-run-together、
#exclusive-waiter-blocks-new-shared、#killed-holder-releases-lock、#status-lists-live-holders、
#nested-run-does-not-wait、#test-suite-uses-isolated-lock-dir、#waiter-gives-up-on-stalled-holder、
#lock-off-or-unavailable-runs-unlocked，共 9 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json
import os
import subprocess
import sys
import time

from conftest import hook_path, load_hook
from lock_helpers import INFO_PREFIX, Locks, wait_for


def test_exclusive_holders_mutually_exclude(tmp_path):
    # Given: 进程 A（标签 holder-a）持有独占锁，命令尚未结束
    with Locks(tmp_path) as lk:
        a = lk.hold("a", label="holder-a")

        # When: 进程 B 以同一锁目录请求独占，它的命令以 5 退出
        b = lk.spawn("b", code=5)

        # Then: B 的 stderr 出现排队提示并点名 A 的标签，B 的命令没有开始；
        #       A 结束后 B 的命令才运行，B 以 5 退出，状态 held、排队秒数大于 0
        assert wait_for(lambda: b.queued() or b.exited()), b.stderr()
        assert b.queued() and "holder-a" in b.stderr(), b.stderr()
        assert not b.running()
        time.sleep(0.3)  # 让排队秒数在保留 1 位小数后仍大于 0
        assert a.release() == 0
        assert wait_for(lambda: b.running() or b.exited()), b.stderr()
        assert b.running(), b.stderr()
        assert b.release() == 5
        info = b.info()
        assert info["mode"] == "exclusive" and info["state"] == "held" and info["waited"] > 0, info


def test_shared_holders_run_together(tmp_path):
    # Given: 进程 A 持有共享锁，命令尚未结束
    with Locks(tmp_path) as lk:
        a = lk.hold("a", mode="shared")

        # When: 进程 B 以同一锁目录请求共享
        b = lk.spawn("b", mode="shared")

        # Then: A 还没结束时 B 的命令已经开始；两者都正常结束
        assert wait_for(lambda: b.running() or b.exited()), b.stderr()
        assert b.running() and not a.exited(), b.stderr()
        assert b.release() == 0
        assert a.release() == 0
        assert b.info()["state"] == "held", b.info()


def test_exclusive_waiter_blocks_new_shared(tmp_path):
    # Given: 进程 A 持有共享锁；进程 X 请求独占并已在排队
    with Locks(tmp_path) as lk:
        a = lk.hold("a", mode="shared")
        x = lk.spawn("x", mode="exclusive")
        assert wait_for(lambda: x.queued() or x.exited()), x.stderr()
        assert x.queued() and not x.running(), x.stderr()

        # When: 进程 C 请求共享
        c = lk.spawn("c", mode="shared")

        # Then: C 排队、命令没有开始；A 结束后 X 先运行，X 运行期间 C 仍未开始；X 结束后 C 才运行
        assert wait_for(lambda: c.queued() or c.exited()), c.stderr()
        assert c.queued() and not c.running() and not x.running(), c.stderr()
        assert a.release() == 0
        assert wait_for(lambda: x.running() or x.exited()), x.stderr()
        assert x.running() and not c.running(), c.stderr()
        assert x.release() == 0
        assert wait_for(lambda: c.running() or c.exited()), c.stderr()
        assert c.running(), c.stderr()
        assert c.release() == 0


def test_killed_holder_releases_lock(tmp_path):
    # Given: 进程 A 持有独占锁，进程 B 请求独占并在排队
    with Locks(tmp_path) as lk:
        a = lk.hold("a")
        b = lk.spawn("b")
        assert wait_for(lambda: b.queued() or b.exited()), b.stderr()
        assert b.queued() and not b.running(), b.stderr()

        # When: A 的 flight-lock.py 进程被 SIGKILL 杀掉
        a.proc.kill()
        a.proc.wait(timeout=5)

        # Then: B 的命令随即运行；status 只列出 B，不再列出 A
        assert wait_for(lambda: b.running() or b.exited()), b.stderr()
        assert b.running(), b.stderr()
        assert [h["pid"] for h in lk.status()["holders"]] == [b.pid]
        assert b.release() == 0


def test_status_lists_live_holders(tmp_path):
    # Given: 进程 A 以 --change demo --label "final gate" 持有独占锁
    with Locks(tmp_path) as lk:
        a = lk.hold("a", change="demo", label="final gate")

        # When: 运行 flight-lock.py status --json
        holders = lk.status()["holders"]

        # Then: 持有者列表恰有一项：独占、change demo、标签 final gate、pid 是 A 的 pid
        assert len(holders) == 1, holders
        h = holders[0]
        assert (h["mode"], h["change"], h["label"], h["pid"]) == ("exclusive", "demo", "final gate", a.pid), h
        assert a.release() == 0


def test_nested_run_does_not_wait(tmp_path):
    # Given: 外层 run exclusive 的命令是以同一锁目录再次 run exclusive（内层命令什么都不做）
    inner = [sys.executable, str(hook_path("flight-lock")), "run", "exclusive", "--label", "inner", "--",
             sys.executable, "-c", "pass"]
    with Locks(tmp_path) as lk:
        # When: 外层运行
        outer = lk.spawn("outer", command=inner)

        # Then: 外层以 0 退出；stderr 里先后两条 flight-lock 行：内层 nested、排队 0 秒，外层 held
        assert outer.proc.wait(timeout=20) == 0, outer.stderr()
        infos = [json.loads(l[len("flight-lock: "):]) for l in outer.stderr().splitlines() if l.startswith(INFO_PREFIX)]
        assert len(infos) == 2, outer.stderr()
        assert infos[0]["state"] == "nested" and infos[0]["waited"] == 0, infos
        assert infos[1]["state"] == "held", infos


def test_test_suite_uses_isolated_lock_dir():
    # Given: 本仓的 pytest 会话（tests/conftest.py 已导入）
    home_claude = os.path.realpath(os.path.join(os.path.expanduser("~"), ".claude"))

    # When: 读取环境变量 FLIGHT_LOCK_DIR
    d = os.environ.get("FLIGHT_LOCK_DIR")

    # Then: 它指向一个存在的目录，不在用户主目录的 .claude 之下；外层的锁开关没有漏进套件
    assert d and os.path.isdir(d), d
    assert not (os.path.realpath(d) + os.sep).startswith(home_claude + os.sep), d
    assert "FLIGHT_LOCK" not in os.environ


def test_waiter_gives_up_on_stalled_holder(tmp_path):
    # Given: 进程 A（标签 stuck-a）以 FLIGHT_LOCK_MAX_HOLD_SEC=0.3 持有独占锁且一直不结束
    with Locks(tmp_path) as lk:
        a = lk.hold("a", label="stuck-a", env={"FLIGHT_LOCK_MAX_HOLD_SEC": "0.3"})

        # When: 进程 B 以同一锁目录请求独占，它的命令以 7 退出
        b = lk.spawn("b", code=7)

        # Then: A 仍持有时 B 的命令已经运行；B 以 7 退出，状态 timeout，原因点名 A 的标签
        assert wait_for(lambda: b.running() or b.exited()), b.stderr()
        assert b.running() and not a.exited(), b.stderr()
        assert b.release() == 7
        info = b.info()
        assert info["state"] == "timeout" and "stuck-a" in info["why"], info


def test_lock_off_or_unavailable_runs_unlocked(tmp_path):
    # Given: 进程 A 持有独占锁；另有一个普通文件 plainfile
    blocker = tmp_path / "plainfile"
    blocker.write_text("x", encoding="utf-8")
    with Locks(tmp_path) as lk:
        a = lk.hold("a")

        # When: B 带 FLIGHT_LOCK=off 请求独占（命令以 3 退出）；C 的锁目录指到 plainfile 之下（命令以 4 退出）
        off = lk.spawn("off", code=3, env={"FLIGHT_LOCK": "off"})
        bad = lk.spawn("bad", code=4, env={"FLIGHT_LOCK_DIR": str(blocker / "sub")})

        # Then: 两次的命令都在 A 仍持有时运行，退出码取自命令；状态分别为 off 与 unavailable（原因非空）
        assert wait_for(lambda: (off.running() or off.exited()) and (bad.running() or bad.exited()))
        assert off.running() and bad.running() and not a.exited(), off.stderr() + bad.stderr()
        assert off.release() == 3
        assert bad.release() == 4
        assert off.info()["state"] == "off", off.info()
        assert bad.info()["state"] == "unavailable" and bad.info()["why"], bad.info()
        assert a.release() == 0


def test_exclusive_acquire_clears_holder_file_of_reused_pid(tmp_path, monkeypatch):
    # Given: 一个无关的在世子进程；锁目录 holders/ 下有一份 pid 为它、since 很早的假持有者文件
    monkeypatch.setenv("FLIGHT_LOCK_DIR", str(tmp_path / "lk"))
    monkeypatch.delenv("FLIGHT_LOCK_HELD", raising=False)
    monkeypatch.delenv("FLIGHT_LOCK", raising=False)
    fl = load_hook("flight-lock")
    other = subprocess.Popen(["sleep", "30"])
    try:
        hd = tmp_path / "lk" / "holders"
        hd.mkdir(parents=True)
        fake = hd / ("%d.json" % other.pid)
        fake.write_text(json.dumps({"pid": other.pid, "mode": "exclusive", "change": "ghost", "label": "killed",
                                    "since": 1.0, "cap_sec": 1.0}), encoding="utf-8")
        assert [h["pid"] for h in fl.holders()] == [other.pid]

        # When: 以独占方式 acquire 再 release
        hold = fl.acquire("exclusive", change="c", label="t")
        state = hold.info["state"]
        hold.release()

        # Then: 拿到锁；假持有者文件已不存在，holders() 为空
        assert state == "held", hold.info
        assert not fake.exists()
        assert fl.holders() == []
    finally:
        other.kill()
        other.wait(timeout=5)
