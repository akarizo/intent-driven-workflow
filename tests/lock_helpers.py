"""全机测试锁各切片测试共用的工具（change machine-test-lock：S1 拥有，S3 / S4 / S5 的测试只读共用）。

用「开始文件 / 放行文件 / stderr 里的排队提示」作同步点，不靠 sleep 猜时序。"""
import json
import os
import subprocess
import sys
import time

from conftest import hook_path

# 被锁包住的命令：写开始文件 → 等放行文件出现（最多 30 秒）→ 以给定退出码结束
WAITER = (
    "import os, sys, time\n"
    "started, release, code = sys.argv[1], sys.argv[2], int(sys.argv[3])\n"
    "open(started, 'w').close()\n"
    "end = time.time() + 30\n"
    "while not os.path.exists(release) and time.time() < end:\n"
    "    time.sleep(0.02)\n"
    "sys.exit(code)\n"
)
QUEUED = "排队中"
INFO_PREFIX = "flight-lock: {"
DROP = ("FLIGHT_LOCK", "FLIGHT_LOCK_HELD", "FLIGHT_LOCK_MAX_HOLD_SEC")


def lock_env(lock_dir, **extra):
    """子进程环境：去掉外层的锁开关 / 重入标记 / 持有上限，锁目录指到 lock_dir，再叠加 extra。"""
    env = {k: v for k, v in os.environ.items() if k not in DROP}
    env["FLIGHT_LOCK_DIR"] = str(lock_dir)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def wait_for(pred, timeout=10.0, step=0.02):
    """轮询到 pred() 为真返回 True；超时返回 False。"""
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return bool(pred())


def last_info(text):
    """stderr 里最后一条 `flight-lock: {…}` 的 JSON；没有返回 None。"""
    for line in reversed((text or "").splitlines()):
        if line.startswith(INFO_PREFIX):
            return json.loads(line[len("flight-lock: "):])
    return None


class Run:
    """一次 `flight-lock.py run <mode> -- waiter`。"""

    def __init__(self, proc, started, release, err_path):
        self.proc, self._started, self._release, self._err = proc, started, release, err_path

    @property
    def pid(self):
        return self.proc.pid

    def running(self):
        """被包住的命令已经开始（= 已过锁这一关）。"""
        return os.path.exists(self._started)

    def stderr(self):
        with open(self._err, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def queued(self):
        return QUEUED in self.stderr()

    def exited(self):
        return self.proc.poll() is not None

    def release(self, timeout=10.0):
        """放行被包住的命令，等整个进程结束，返回退出码。"""
        open(self._release, "w").close()
        return self.proc.wait(timeout=timeout)

    def info(self):
        return last_info(self.stderr())

    def cleanup(self):
        try:
            open(self._release, "w").close()
        except OSError:
            pass
        if self.proc.poll() is None:
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)


class Locks:
    """一个临时锁目录 + 在其中起持有者 / 排队方的工厂；退出 with 时清掉所有子进程。"""

    def __init__(self, tmp_path):
        self.tmp = tmp_path
        self.dir = tmp_path / "lockdir"
        self.runs = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        for r in self.runs:
            r.cleanup()
        return False

    def env(self, **extra):
        return lock_env(self.dir, **extra)

    def spawn(self, name, mode="exclusive", change="", label="", code=0, env=None, command=None):
        """起一个 flight-lock.py run，不等它拿到锁。command 给了就包它（argv 列表），否则包 waiter。"""
        d = self.tmp / ("run-" + name)
        d.mkdir()
        script, started, release, err = d / "waiter.py", d / "started", d / "release", d / "stderr"
        script.write_text(WAITER, encoding="utf-8")
        args = [sys.executable, str(hook_path("flight-lock")), "run", mode, "--label", label or name]
        if change:
            args += ["--change", change]
        args += ["--"] + (list(command) if command else
                          [sys.executable, str(script), str(started), str(release), str(code)])
        with open(err, "w", encoding="utf-8") as ef:
            proc = subprocess.Popen(args, env=self.env(**(env or {})), stdout=subprocess.DEVNULL, stderr=ef)
        run = Run(proc, str(started), str(release), str(err))
        self.runs.append(run)
        return run

    def hold(self, name, **kw):
        """起一个持有者并等到它的命令开始（已持有锁）；起不来 / 没拿到就断言失败。"""
        run = self.spawn(name, **kw)
        wait_for(lambda: run.running() or run.exited())
        assert run.running(), "持有者 %s 没有开始：%s" % (name, run.stderr())
        return run

    def status(self):
        """`flight-lock.py status --json` 的解析结果。"""
        p = subprocess.run([sys.executable, str(hook_path("flight-lock")), "status", "--json"],
                           env=self.env(), capture_output=True, text=True)
        assert p.returncode == 0, p.stdout + p.stderr
        return json.loads(p.stdout)
