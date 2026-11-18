#!/usr/bin/env python3
# test-ledger · 逐用例测试账本（change test-ledger design D1、D2、D4–D6）
#
# CLI:
#   test-ledger.py show --change-dir DIR [--phase baseline|final] [--tier 层] [--top N] [--json]
#       读 <git common dir>/flight-ledger/<change>/<phase>.json；--phase 缺省先 final 后 baseline
#       --json → {"summary": …, "cases": [{"id", "o", "s", "t", "m"}, …]}，用例按耗时由大到小（null 排最后）
#       退出码：0 有账本 · 1 没有账本 · 2 DIR 不存在或不在 git 仓库
#
# 模块接口（门禁 / flight-doctor 按路径加载）：
#   build(meta, observations, universe=None, source=None, rerun_files=None, root=None, tier_of=None) -> 账本
#   from_anchor(anchor) -> 来源 | None      secs_of(ledger) -> {id: 秒} | None      summary(ledger) -> 摘要
#   ledger_dir(root) · save(root, change, name, obj) · load(root, change, name)
# 只读仓库；只写 git common dir 下的 flight-ledger/，不改仓库文件。
# 不反向加载 slice-gate.py：层的归属由调用方传 tier_of(文件) -> 层名 | None。
# 纯标准库，兼容 Python 3.9。
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

LEDGER_DIR = "flight-ledger"
KEEP_CHANGES = 30  # 草案值（design D4）：只保留最近 30 个 change 的账本目录
NO_TIER = "-"
PHASES = ("final", "baseline")


# ---------- 合成 ----------

def _outcome(o):
    """结局统一小写：XFAIL → xfailed、XPASS → xpassed，其余转小写；空 → None。"""
    if not o:
        return None
    up = str(o).upper()
    if up == "XFAIL":
        return "xfailed"
    if up == "XPASS":
        return "xpassed"
    return str(o).lower()


def _sec(v):
    if v is None:
        return None
    try:
        return round(float(v), 3)
    except (TypeError, ValueError):
        return None


def _to_junit(nodeid):
    """nodeid → junit 的 classname::name：a/b/test_x.py::C::t[p] → a.b.test_x.C::t[p]。"""
    parts = nodeid.split("::")
    if len(parts) < 2:
        return nodeid
    path = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    classname = ".".join([path.replace("/", ".")] + parts[1:-1])
    return classname + "::" + parts[-1]


def _file_of(case_id, id_form, root):
    """用例所在的测试文件（仓库相对）；定不出 → None。"""
    if id_form == "nodeid":
        return case_id.split("::", 1)[0] if "::" in case_id else None
    classname = case_id.split("::", 1)[0]
    segs = classname.split(".")
    cands = ["/".join(segs[:n]) + ".py" for n in range(len(segs), 0, -1)]
    if root is None:
        return cands[0] if cands else None
    for c in cands:
        if os.path.isfile(os.path.join(root, c)):
            return c
    return None


def _id_form(observations, universe, source):
    if universe is not None:
        return "nodeid"
    if any(ob.get("form") == "junit" for ob in observations) or (source or {}).get("id_form") == "junit":
        return "junit"
    return "nodeid"


def build(meta, observations, universe=None, source=None, rerun_files=None, root=None, tier_of=None):
    observations = list(observations or [])
    form = _id_form(observations, universe, source)
    outcomes, secs, obs_tier, measured = {}, {}, {}, set()
    for ob in observations:
        ob_form = ob.get("form")
        if ob_form == form:
            conv = str
        elif form == "junit" and ob_form == "nodeid":
            conv = _to_junit
        else:
            continue  # nodeid 形式的账本不并 junit 观测（反向换算有损，design D2）
        for k, v in (ob.get("outcomes") or {}).items():
            cid = conv(k)
            outcomes[cid] = v
            measured.add(cid)
        for k, v in (ob.get("secs") or {}).items():
            cid = conv(k)
            secs[cid] = v
            measured.add(cid)
        if ob.get("tier"):
            for k in list(ob.get("outcomes") or {}) + list(ob.get("secs") or {}):
                obs_tier[conv(k)] = ob["tier"]

    src_cases = (source or {}).get("cases") or {}
    if universe is not None:
        ids = set(universe)
    else:
        ids = set(measured)
        if rerun_files is not None:
            rerun = set(rerun_files)
            for cid in src_cases:
                f = _file_of(cid, form, root)
                if f is None or f in rerun:
                    continue
                if root is not None and not os.path.isfile(os.path.join(root, f)):
                    continue
                ids.add(cid)

    cases = {}
    for cid in sorted(ids):
        if cid in measured:
            o = universe[cid] if universe is not None else outcomes.get(cid)
            s, m = _sec(secs.get(cid)), 1
        else:
            prev = src_cases.get(cid) or {}
            o = universe[cid] if universe is not None else prev.get("o")
            s, m = _sec(prev.get("s")), 0
        if cid in obs_tier:
            t = obs_tier[cid]
        elif tier_of is not None:
            f = _file_of(cid, form, root)
            t = tier_of(f) if f is not None else None
        else:
            t = None
        cases[cid] = {"o": _outcome(o), "s": s, "t": t, "m": m}

    if rerun_files is not None and source is None:
        complete = False
    else:
        complete = all(cid in src_cases for cid, c in cases.items() if c["m"] == 0)
    tiered = tier_of is not None or any(ob.get("tier") for ob in observations)
    return dict(meta, v=1, id_form=form, tiered=tiered, complete=complete, cases=cases)


def from_anchor(anchor):
    """锚点 → 来源：{"cases": {nodeid: {"o", "s"}}, "id_form": "nodeid"}；没有 nodes → None。"""
    nodes = (anchor or {}).get("nodes")
    if not isinstance(nodes, dict):
        return None
    secs = anchor.get("secs")
    if not isinstance(secs, dict):
        secs = {}
    return {"cases": {n: {"o": o, "s": secs.get(n)} for n, o in nodes.items()}, "id_form": "nodeid"}


def secs_of(ledger):
    """{id: 秒}，只含有耗时的用例（锚点的 secs）；ledger 为 None → None。"""
    if ledger is None:
        return None
    return {cid: c["s"] for cid, c in (ledger.get("cases") or {}).items() if c.get("s") is not None}


def summary(ledger):
    cases = (ledger or {}).get("cases") or {}
    tiers = {}
    for c in cases.values():
        slot = tiers.setdefault(c.get("t") or NO_TIER, {"cases": 0, "sec": 0.0})
        slot["cases"] += 1
        if c.get("s") is not None:
            slot["sec"] += c["s"]
    for slot in tiers.values():
        slot["sec"] = round(slot["sec"], 1)
    measured = sum(1 for c in cases.values() if c.get("m") == 1)
    return {"cases": len(cases), "measured": measured, "inherited": len(cases) - measured,
            "no_sec": sum(1 for c in cases.values() if c.get("s") is None),
            "id_form": (ledger or {}).get("id_form"), "complete": (ledger or {}).get("complete"), "tiers": tiers}


# ---------- 存取 ----------

def ledger_dir(root):
    """<git common dir>/flight-ledger；不在 git 仓库 → RuntimeError。"""
    try:
        p = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True)
    except OSError as e:
        raise RuntimeError("git 不可用：%s" % e)
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError("不在 git 仓库：%s" % root)
    common = p.stdout.strip()
    if not os.path.isabs(common):
        common = os.path.join(root, common)
    return os.path.join(common, LEDGER_DIR)


def _newest_mtime(d):
    best = 0.0
    try:
        for e in os.scandir(d):
            if e.is_file():
                best = max(best, e.stat().st_mtime)
    except OSError:
        pass
    return best


def _prune(base):
    try:
        dirs = [e.path for e in os.scandir(base) if e.is_dir()]
    except OSError:
        return
    dirs.sort(key=_newest_mtime, reverse=True)
    for d in dirs[KEEP_CHANGES:]:
        shutil.rmtree(d, ignore_errors=True)


def save(root, change, name, obj):
    base = ledger_dir(root)
    d = os.path.join(base, change)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name + ".json")
    fd, tmp = tempfile.mkstemp(dir=d, prefix="." + name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _prune(base)
    return path


def load(root, change, name):
    try:
        with open(os.path.join(ledger_dir(root), change, name + ".json"), encoding="utf-8") as f:
            obj = json.load(f)
    except (RuntimeError, OSError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


# ---------- CLI ----------

def _sort_key(item):
    cid, c = item
    s = c.get("s")
    return (s is None, -(s or 0.0), cid)


def _show(args):
    d = os.path.abspath(args.change_dir)
    if not os.path.isdir(d):
        print("目录不存在：%s" % d, file=sys.stderr)
        return 2
    p = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        print("不在 git 仓库：%s" % d, file=sys.stderr)
        return 2
    root, change = p.stdout.strip(), os.path.basename(d.rstrip(os.sep))
    phases = (args.phase,) if args.phase else PHASES
    led, phase = None, None
    for ph in phases:
        led = load(root, change, ph)
        if led is not None:
            phase = ph
            break
    if led is None:
        print("change %s 没有账本（%s）" % (change, " / ".join(phases)))
        return 1

    items = sorted((led.get("cases") or {}).items(), key=_sort_key)
    if args.tier:
        items = [it for it in items if (it[1].get("t") or NO_TIER) == args.tier]
    if args.top is not None:
        items = items[:max(args.top, 0)]
    summ = summary(led)

    if args.json:
        rows = [{"id": cid, "o": c.get("o"), "s": c.get("s"), "t": c.get("t"), "m": c.get("m")} for cid, c in items]
        print(json.dumps({"summary": summ, "cases": rows}, ensure_ascii=False))
        return 0

    print("账本：change %s · %s · commit %s · 模式 %s" % (change, phase, str(led.get("commit") or "-")[:10],
                                                     led.get("mode") or "-"))
    for t, slot in summ["tiers"].items():
        if args.tier and t != args.tier:
            continue
        print("%s：%d 条 · %.1f 秒" % (t, slot["cases"], slot["sec"]))
    for cid, c in items:
        s = c.get("s")
        print("%s  %s（%s）" % ("%.3fs" % s if s is not None else "-", cid, c.get("t") or NO_TIER))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="test-ledger.py", description="逐用例测试账本（只读）")
    sub = ap.add_subparsers(dest="cmd")
    sp = sub.add_parser("show", help="列出某 change 的账本")
    sp.add_argument("--change-dir", required=True)
    sp.add_argument("--phase", choices=("baseline", "final"))
    sp.add_argument("--tier")
    sp.add_argument("--top", type=int)
    sp.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "show":
        return _show(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
