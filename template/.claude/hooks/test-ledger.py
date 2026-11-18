#!/usr/bin/env python3
# test-ledger · 逐用例测试账本（change test-ledger design D1、D2、D4–D6）
#
# CLI:
#   test-ledger.py show --change-dir DIR [--phase baseline|final] [--tier 层] [--top N] [--json]
#       读 <git common dir>/flight-ledger/<change>/<phase>.json；--phase 缺省先 final 后 baseline
#       --json → {"summary": …, "cases": [{"id", "o", "s", "t", "m"}, …]}，用例按耗时由大到小（null 排最后）
#       退出码：0 有账本 · 1 没有账本 · 2 DIR 不存在或不在 git 仓库
#   test-ledger.py delta --change-dir DIR [--markdown|--json]
#       读 <git common dir>/flight-ledger/<change>/delta.json（对账结果）；缺省与 --markdown 打印 Markdown，--json 打印原样
#       退出码：0 有 · 1 没有对账结果 · 2 DIR 不存在或不在 git 仓库
#
# 模块接口（门禁 / flight-doctor 按路径加载）：
#   build(meta, observations, universe=None, source=None, rerun_files=None, root=None, tier_of=None) -> 账本
#   from_anchor(anchor) -> 来源 | None      secs_of(ledger) -> {id: 秒} | None      summary(ledger) -> 摘要
#   ledger_dir(root) · save(root, change, name, obj) · load(root, change, name)
#   delta(base, final, rerun_files=None, root=None) -> (对账结果 | None, 原因 | None)
#   advice(d) -> [行]   segment(d) -> 片段   parse_segment(note) -> dict | None   render(d) -> Markdown
# 只读仓库；只写 git common dir 下的 flight-ledger/，不改仓库文件。
# 不反向加载 slice-gate.py：层的归属由调用方传 tier_of(文件) -> 层名 | None。
# 纯标准库，兼容 Python 3.9。
import argparse
import json
import os
import re
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


# ---------- 对账（design D7、D8、D11；只报告，不判红） ----------

SLOW_RATIO = 2.0  # 草案值：变慢 = 耗时至少翻倍
SLOW_MIN_SEC = 0.5  # 草案值：且至少多 0.5 秒
TIER_GROWTH_RATIO = 0.2  # 草案值：某层耗时涨 20% 以上
TIER_GROWTH_MIN_SEC = 5.0  # 草案值：且至少涨 5 秒
NO_SEC_RATIO = 0.1  # 草案值：无耗时用例超过一成才建议
TOP_N = 5  # 草案值：清单至多列 5 条
UNIT_TIER = "unit"
SEGMENT_RE = re.compile(r"用例 \+(\d+)/-(\d+)（新增 ([\d.]+)s）")


def _tier_totals(cases):
    out = {}
    for c in cases.values():
        slot = out.setdefault(c.get("t") or NO_TIER, [0, 0.0])
        slot[0] += 1
        if c.get("s") is not None:
            slot[1] += c["s"]
    return out


def delta(base, final, rerun_files=None, root=None):
    """final 账本对基线账本 → (对账结果, None)；基线缺失 → (None, 原因)。"""
    if base is None:
        return None, "基线账本不在本机（或基线早于测试账本）"
    if base.get("complete") is False:  # 没补跑的用例不在基线里，对账会把它们编成新增
        return None, "基线账本不完整（复用的基线没有可沿用的来源账本），不对账"
    form = final.get("id_form") or "nodeid"
    bc, fc = base.get("cases") or {}, final.get("cases") or {}
    if (base.get("id_form") or "nodeid") != form:
        form = "junit"
        if base.get("id_form") != "junit":
            bc = {_to_junit(k): v for k, v in bc.items()}
        else:
            fc = {_to_junit(k): v for k, v in fc.items()}

    rerun = set(rerun_files or ())
    by_mode = final.get("mode") in ("full", "parts")
    added_ids = [cid for cid in fc if cid not in bc]
    removed = unknown = 0
    for cid in bc:
        if cid in fc:
            continue
        gone = by_mode
        if not gone:
            f = _file_of(cid, form, root)
            gone = (root is not None and (f is None or not os.path.isfile(os.path.join(root, f)))) or \
                (f is not None and f in rerun)
        if gone:
            removed += 1
        else:
            unknown += 1

    slower = []
    for cid, c in fc.items():
        b = bc.get(cid)
        if b is None or c.get("m") != 1 or c.get("s") is None or b.get("s") is None:
            continue
        if c["s"] >= b["s"] * SLOW_RATIO and c["s"] - b["s"] >= SLOW_MIN_SEC:
            slower.append((cid, b["s"], c["s"], c.get("t") or NO_TIER))
    slower.sort(key=lambda x: (-(x[2] - x[1]), x[0]))

    added_by_tier, added_sec = {}, 0.0
    for cid in added_ids:
        s, t = fc[cid].get("s"), fc[cid].get("t") or NO_TIER
        if s is not None:
            added_sec += s
            added_by_tier[t] = added_by_tier.get(t, 0.0) + s
    top = sorted(added_ids, key=lambda cid: (fc[cid].get("s") is None, -(fc[cid].get("s") or 0.0), cid))

    before, after = _tier_totals(bc), _tier_totals(fc)
    tiers = {}
    for t in sorted(set(before) | set(after)):
        b, a = before.get(t, [0, 0.0]), after.get(t, [0, 0.0])
        tiers[t] = {"before": [b[0], round(b[1], 1)], "after": [a[0], round(a[1], 1)]}

    d = {"commit": final.get("commit"), "base_commit": base.get("commit"), "mode": final.get("mode"),
         "added": len(added_ids), "removed": removed, "unknown": unknown,
         "slower_n": len(slower), "slower": [[x[0], x[1], x[2]] for x in slower[:TOP_N]],
         # slower_tiers 与 slower 一一对应，供 advice 规则 2 按层挑用例
         "slower_tiers": [x[3] for x in slower[:TOP_N]],
         "added_sec": round(added_sec, 1),
         "top_added": [[cid, fc[cid].get("s"), fc[cid].get("t")] for cid in top[:TOP_N]],
         "added_by_tier": {t: round(v, 1) for t, v in added_by_tier.items()},
         "inherited": sum(1 for c in fc.values() if c.get("m") == 0),
         "no_sec": sum(1 for c in fc.values() if c.get("s") is None),
         "cases": len(fc), "complete": final.get("complete"), "tiers": tiers}
    d["advice"] = advice(d)
    return d, None


def advice(d):
    """固定规则的建议行（零 token）；都不满足 → []。"""
    out = []
    abt = d.get("added_by_tier") or {}
    unit = abt.get(UNIT_TIER, 0.0)
    integ = sum(v for t, v in abt.items() if t not in (UNIT_TIER, NO_TIER))
    if integ > unit:
        line = "新增耗时主要在集成层（集成 %.1fs · 单元 %.1fs）" % (integ, unit)
        top = next((x for x in d.get("top_added") or [] if (x[2] or NO_TIER) not in (UNIT_TIER, NO_TIER)
                    and x[1] is not None), None)
        if top is not None:
            line += "：最慢 %s %.1fs" % (top[0], top[1])
        out.append(line)
    slower_tiers = d.get("slower_tiers") or []
    for t, slot in (d.get("tiers") or {}).items():
        b, a = slot["before"][1], slot["after"][1]
        if a - b >= TIER_GROWTH_MIN_SEC and a >= b * (1 + TIER_GROWTH_RATIO):
            ids = [x[0] for x in d.get("top_added") or [] if (x[2] or NO_TIER) == t]
            ids += [x[0] for i, x in enumerate(d.get("slower") or [])
                    if i < len(slower_tiers) and slower_tiers[i] == t and x[0] not in ids]
            line = "%s 层耗时 %.1fs → %.1fs" % (t, b, a)
            if ids:
                line += "：" + "、".join(ids[:3])
            out.append(line)
    cases, no_sec = d.get("cases") or 0, d.get("no_sec") or 0
    if cases > 0 and no_sec / cases > NO_SEC_RATIO:
        out.append("%d 条用例无耗时（沿用自没有账本的锚点，或 junit 缺 time）：跑一次全量即可补齐" % no_sec)
    return out


def segment(d):
    """时间线备注片段（不含 ` · `）。"""
    return "用例 +%d/-%d（新增 %.1fs）" % (d["added"], d["removed"], d["added_sec"])


def parse_segment(note):
    m = SEGMENT_RE.search(note or "")
    if not m:
        return None
    return {"added": int(m.group(1)), "removed": int(m.group(2)), "added_sec": float(m.group(3))}


def _fmt_sec(s):
    return "%.1fs" % s if s is not None else "-"


def render(d):
    """对账结果 → Markdown（脚本生成，不经模型）。"""
    head = "- 新增 %d 条（+%.1fs）· 删除 %d 条 · 变慢 %d 条" % (d["added"], d["added_sec"], d["removed"], d["slower_n"])
    if d.get("unknown"):
        head += " · 未重测 %d 条" % d["unknown"]
    second = "- 沿用未实测 %d 条 · 无耗时 %d 条" % (d.get("inherited") or 0, d.get("no_sec") or 0)
    if d.get("complete") is False:
        second += " · 账本不完整"
    lines = ["## 测试变更", "", head, second]
    tiers = d.get("tiers") or {}
    if tiers:
        lines.append("- 各层：" + "；".join("%s %d 条 %.1fs → %d 条 %.1fs" % (
            t, s["before"][0], s["before"][1], s["after"][0], s["after"][1]) for t, s in tiers.items()))
    if d.get("top_added"):
        lines.append("- 最慢新增：")
        for cid, s, t in d["top_added"][:TOP_N]:
            lines.append("  - %s %s（%s）" % (cid, _fmt_sec(s), t or NO_TIER))
    if d.get("slower"):
        lines.append("- 变慢：")
        for cid, b, a in d["slower"][:TOP_N]:
            lines.append("  - %s %s → %s" % (cid, _fmt_sec(b), _fmt_sec(a)))
    for line in d.get("advice") or []:
        lines.append("- 建议：" + line)
    return "\n".join(lines)


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


def _root_change(change_dir):
    """--change-dir → (仓库根, change 名)；不可用 → None（已打印原因）。"""
    d = os.path.abspath(change_dir)
    if not os.path.isdir(d):
        print("目录不存在：%s" % d, file=sys.stderr)
        return None
    p = subprocess.run(["git", "-C", d, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        print("不在 git 仓库：%s" % d, file=sys.stderr)
        return None
    return p.stdout.strip(), os.path.basename(d.rstrip(os.sep))


def _delta_cmd(args):
    rc = _root_change(args.change_dir)
    if rc is None:
        return 2
    root, change = rc
    d = load(root, change, "delta")
    if d is None:
        print("change %s 没有对账结果" % change)
        return 1
    print(json.dumps(d, ensure_ascii=False) if args.json else render(d))
    return 0


def _show(args):
    rc = _root_change(args.change_dir)
    if rc is None:
        return 2
    root, change = rc
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
    dp = sub.add_parser("delta", help="打印某 change 的测试变更（对账结果）")
    dp.add_argument("--change-dir", required=True)
    fmt = dp.add_mutually_exclusive_group()
    fmt.add_argument("--markdown", action="store_true")
    fmt.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "show":
        return _show(args)
    if args.cmd == "delta":
        return _delta_cmd(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
