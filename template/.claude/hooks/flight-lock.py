#!/usr/bin/env python3
# flight-lock · 全机测试锁（读写锁，change machine-test-lock design D1–D5、D7）
#   run <exclusive|shared> [--change NAME] [--label TEXT] [--expect-sec N] -- CMD [ARG…]
#       取锁 → 不经 shell 运行 CMD → 放锁 → stderr 末行 `flight-lock: <info JSON>` → 以 CMD 的退出码退出
#   status [--json]      锁目录、是否启用、在世持有者；恒退出 0
# 模块接口（门禁按路径加载）：acquire / holders / note / lock_dir，任何函数都不抛异常。
# 锁目录 FLIGHT_LOCK_DIR，缺省 ~/.claude/flight-lock：gate.lock（闸口）· main.lock（主锁）· holders/<pid>.json
# FLIGHT_LOCK=off 关闭；FLIGHT_LOCK_MAX_HOLD_SEC 覆盖持有上限；FLIGHT_LOCK_HELD 是重入标记。
# 兼容 Python 3.8+，只用标准库。
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:  # 没有 flock 的平台：状态 unavailable
    fcntl = None

HELD_ENV = "FLIGHT_LOCK_HELD"
DEFAULT_CAP = 1800.0
MIN_CAP = 300.0
REPORT_EVERY = 30.0
MODE_CN = {"exclusive": "独占", "shared": "共享"}


def lock_dir():
    return os.environ.get("FLIGHT_LOCK_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "flight-lock")


def _switched_off():
    return os.environ.get("FLIGHT_LOCK", "").strip().lower() == "off"


def _loadavg():
    try:
        return round(os.getloadavg()[0], 1)
    except (AttributeError, OSError):
        return None


def _cap_sec(expect_sec):
    """持有上限（D5）：FLIGHT_LOCK_MAX_HOLD_SEC > max(300, 3 × expect_sec) > 1800。"""
    raw = os.environ.get("FLIGHT_LOCK_MAX_HOLD_SEC", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    try:
        if expect_sec and float(expect_sec) > 0:
            return max(MIN_CAP, 3.0 * float(expect_sec))
    except (TypeError, ValueError):
        pass
    return DEFAULT_CAP


def _sec(x):
    return "%.1f" % float(x)


def _who(h):
    """持有者的「<change> · <标签>」，空的段省略。"""
    return " · ".join(x for x in (h.get("change"), h.get("label")) if x) or "pid %s" % h.get("pid")


class Hold:
    """acquire 的返回：.info 与幂等的 .release()。"""

    def __init__(self, mode, state, waited=0.0, why=""):
        start = _loadavg()
        self.info = {"mode": mode, "state": state, "waited": round(max(0.0, waited), 1), "why": str(why or ""),
                     "load": None if start is None else [start, None], "cores": os.cpu_count()}
        self._fd = None
        self._holder_file = None
        self._env_prev = None
        self._env_set = False
        self._released = False

    def release(self):
        if self._released:
            return
        self._released = True
        if self._holder_file:
            try:
                os.unlink(self._holder_file)
            except OSError:
                pass
        if self._fd is not None:
            try:
                os.close(self._fd)  # 关描述符即放 flock
            except OSError:
                pass
            self._fd = None
        if self._env_set:
            if self._env_prev is None:
                os.environ.pop(HELD_ENV, None)
            else:
                os.environ[HELD_ENV] = self._env_prev
        if self.info.get("load") is not None:
            self.info["load"][1] = _loadavg()


def _alive(pid):
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _holders_raw():
    hd = os.path.join(lock_dir(), "holders")
    try:
        names = os.listdir(hd)
    except OSError:
        return []
    now = time.time()
    out = []
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(hd, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                rec = json.load(f)
            pid = int(rec["pid"])
            since = float(rec.get("since") or now)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if not _alive(pid):
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        out.append((since, {"pid": pid, "mode": rec.get("mode", ""), "change": rec.get("change", ""),
                            "label": rec.get("label", ""), "started": rec.get("started", ""),
                            "held_sec": round(max(0.0, now - since), 1),
                            "cap_sec": float(rec.get("cap_sec") or DEFAULT_CAP)}))
    out.sort(key=lambda t: t[0])
    return [h for _, h in out]


def holders():
    """在世持有者，持有最久的在前；pid 已不在的持有者文件顺手删掉。"""
    try:
        return _holders_raw()
    except Exception:
        return []


class _Wait:
    """一次 acquire 的排队状态：排队提示与放弃判定（D2、D5）。"""

    def __init__(self, mode, cap, t0):
        self.mode, self.cap, self.t0 = mode, cap, t0
        self.last_report = None
        self.why = ""

    def after_miss(self):
        """一次失败的轮询之后调用；返回 True = 放弃等待。"""
        now = time.time()
        hs = holders()
        top = hs[0] if hs else None
        if self.last_report is None or now - self.last_report >= REPORT_EVERY:
            self.last_report = now
            if top is None:
                who = "（持有者信息尚未写入）"
            else:
                who = "等 %s · pid %d · 已持有 %ds" % (_who(top), top["pid"], int(top["held_sec"]))
            sys.stderr.write("flight-lock: 排队中（%s），%s\n" % (MODE_CN[self.mode], who))
            sys.stderr.flush()
        if top is not None:
            if top["held_sec"] > top["cap_sec"]:
                self.why = "%s 已持有 %s 秒，超过上限 %s 秒" % (_who(top), _sec(top["held_sec"]), _sec(top["cap_sec"]))
                return True
        elif now - self.t0 > self.cap:
            self.why = "读不到持有者信息，已排队 %s 秒，超过上限 %s 秒" % (_sec(now - self.t0), _sec(self.cap))
            return True
        return False


def _take(fd, op, wait):
    """LOCK_NB 轮询取锁，0.2 秒起逐步加到 1 秒；拿到 True，放弃 False。"""
    delay = 0.2
    while True:
        try:
            fcntl.flock(fd, op | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            pass
        if wait.after_miss():
            return False
        time.sleep(delay)
        delay = min(1.0, delay + 0.2)


def _clear_stale_holders(hd):
    """独占拿到 main.lock 之后调用：flock 保证此刻没有别的合法持有者，本进程以外的持有者文件都是残留
    （持有者被强杀且 pid 被无关进程复用时，_holders_raw 的在世判断清不掉它）。删除失败静默忽略。"""
    mine = "%d.json" % os.getpid()
    try:
        names = os.listdir(hd)
    except OSError:
        return
    for name in names:
        if name.endswith(".json") and name != mine:
            try:
                os.unlink(os.path.join(hd, name))
            except OSError:
                pass


def _write_holder(d, rec):
    path = os.path.join(d, "holders", "%d.json" % os.getpid())
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def _acquire(mode, change, label, expect_sec):
    if mode not in MODE_CN:
        raise ValueError("未知的锁方式 %r" % (mode,))
    if _switched_off():
        return Hold(mode, "off", why="FLIGHT_LOCK=off")
    if fcntl is None:
        return Hold(mode, "unavailable", why="当前平台没有 fcntl.flock")
    d = lock_dir()
    real = os.path.realpath(d)
    if os.environ.get(HELD_ENV, "").split(":", 2)[2:] == [real]:
        return Hold(mode, "nested")
    hd = os.path.join(d, "holders")
    try:
        os.makedirs(hd, exist_ok=True)
    except OSError as e:
        return Hold(mode, "unavailable", why="锁目录建不了：%s" % e)
    if not (os.access(d, os.W_OK) and os.access(hd, os.W_OK)):
        return Hold(mode, "unavailable", why="锁目录不可写：%s" % d)

    cap = _cap_sec(expect_sec)
    t0 = time.time()
    wait = _Wait(mode, cap, t0)
    fds = []
    try:
        gate = os.open(os.path.join(d, "gate.lock"), os.O_RDWR | os.O_CREAT, 0o644)  # 缺省不可继承
        fds.append(gate)
        if not _take(gate, fcntl.LOCK_EX, wait):
            return Hold(mode, "timeout", waited=time.time() - t0, why=wait.why)
        main = os.open(os.path.join(d, "main.lock"), os.O_RDWR | os.O_CREAT, 0o644)
        fds.append(main)
        if not _take(main, fcntl.LOCK_EX if mode == "exclusive" else fcntl.LOCK_SH, wait):
            return Hold(mode, "timeout", waited=time.time() - t0, why=wait.why)
        os.close(gate)  # 放闸口
        fds.remove(gate)
        if mode == "exclusive":
            _clear_stale_holders(hd)
        now = time.time()
        holder_file = _write_holder(d, {
            "pid": os.getpid(), "mode": mode, "change": change, "label": label,
            "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "since": now, "cap_sec": cap})
        hold = Hold(mode, "held", waited=now - t0)
        hold._fd, hold._holder_file = main, holder_file
        fds.remove(main)
        hold._env_prev = os.environ.get(HELD_ENV)
        os.environ[HELD_ENV] = "%s:%d:%s" % (mode, os.getpid(), real)
        hold._env_set = True
        return hold
    finally:
        for fd in fds:
            try:
                os.close(fd)
            except OSError:
                pass


def acquire(mode, change="", label="", expect_sec=None):
    """阻塞到拿到、放弃或判定不取；返回 Hold。不抛异常：内部异常 → unavailable。"""
    try:
        return _acquire(mode, change or "", label or "", expect_sec)
    except Exception as e:
        return Hold(mode, "unavailable", why="flight-lock 异常：%s: %s" % (type(e).__name__, e))


def note(info):
    """时间线锁片段（D8）。"""
    try:
        st = info.get("state")
        why = info.get("why") or ""
        if st == "held":
            s = "排队 %ss" % _sec(info.get("waited") or 0)
        elif st == "timeout":
            s = "排队 %ss 后放弃（%s）" % (_sec(info.get("waited") or 0), why)
        elif st == "nested":
            s = "重入"
        elif st == "off":
            s = "未加锁（FLIGHT_LOCK=off）"
        else:
            s = "未加锁（%s）" % (why or "锁不可用")
        load = info.get("load")
        if load and load[0] is not None:
            s += " · 负载 " + _sec(load[0])
            if len(load) > 1 and load[1] is not None:
                s += "→" + _sec(load[1])
            if info.get("cores"):
                s += "/%d" % int(info["cores"])
        return s
    except Exception:
        return ""


def _cmd_run(argv):
    if "--" not in argv:
        sys.stderr.write("flight-lock: run 需要 `-- CMD [ARG…]`\n")
        return 2
    i = argv.index("--")
    head, cmd = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(prog="flight-lock.py run")
    p.add_argument("mode", choices=sorted(MODE_CN))
    p.add_argument("--change", default="")
    p.add_argument("--label", default="")
    p.add_argument("--expect-sec", type=float, default=None)
    a = p.parse_args(head)
    if not cmd:
        sys.stderr.write("flight-lock: `--` 之后缺命令\n")
        return 2
    hold = acquire(a.mode, a.change, a.label, a.expect_sec)
    try:
        try:
            rc = subprocess.call(cmd)
        except OSError as e:
            sys.stderr.write("flight-lock: 命令起不来：%s\n" % e)
            rc = 127
    finally:
        hold.release()
    sys.stderr.write("flight-lock: %s\n" % json.dumps(hold.info, ensure_ascii=False))
    sys.stderr.flush()
    return rc


def _cmd_status(argv):
    p = argparse.ArgumentParser(prog="flight-lock.py status")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    data = {"dir": lock_dir(), "enabled": not _switched_off() and fcntl is not None, "holders": holders()}
    if a.json:
        print(json.dumps(data, ensure_ascii=False))
        return 0
    print("锁目录：%s" % data["dir"])
    print("启用：%s" % ("是" if data["enabled"] else "否"))
    if not data["holders"]:
        print("持有者：空闲")
    for h in data["holders"]:
        print("持有者：%s · %s · pid %d · 已持有 %ss / 上限 %ss"
              % (MODE_CN.get(h["mode"], h["mode"]), _who(h), h["pid"], _sec(h["held_sec"]), _sec(h["cap_sec"])))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmds = {"run": _cmd_run, "status": _cmd_status}
    if not argv or argv[0] not in cmds:
        sys.stderr.write("用法：flight-lock.py run <exclusive|shared> [--change N] [--label T] [--expect-sec S] -- CMD …\n"
                         "      flight-lock.py status [--json]\n")
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
