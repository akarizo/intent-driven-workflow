#!/usr/bin/env python3
# flight-doctor · 测试成本的预告 / 归因 / 体检（unified-test-result-reuse design D12；只读，恒 exit 0）
#
# CLI:
#   flight-doctor.py forecast --change-dir DIR [--json]   起飞前预告 baseline / final 走全量还是增量
#   flight-doctor.py cost --change-dir DIR [--json]       从 timeline.md 归因每一次全量（必要 / 可避免 / 未分类）
#   flight-doctor.py doctor [--openspec-root DIR]         项目级体检：[runner] [anchors] [gate.test] [declare]
#
# 判定逻辑不复制：经 importlib 按路径加载同目录的 slice-gate.py，只调用 _interfaces.md「S4 提供」列出的函数。
# 纯标准库，兼容 Python 3.9。
import argparse
import importlib.util
import json
import os
import re
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))

# cost 的全量原因归类表（design D12）：按序取第一个命中的关键词；认不出 → 未分类
COST_CLASSES = (
    ("依赖图未测", "可避免"),
    ("plugins-dropped", "可避免"),
    ("plugin-import-failed", "可避免"),
    ("not-pytest", "可避免"),
    ("incomplete", "可避免"),
    ("候选基线不是绿", "可避免"),
    ("预存红", "可避免"),
    ("cmd_key 不同", "可避免"),
    ("有非测试文件改动", "可避免"),
    ("--full", "必要"),
    ("全局文件", "必要"),
    ("全局路径", "必要"),
    ("锚点链已达上限", "必要"),
    ("恒全量", "必要"),
    ("多部件分层", "必要"),
    ("锚点池为空", "必要"),
    ("没有可用锚点", "必要"),
)
UNCLASSIFIED = "未分类"
DEFAULT_MAX_HOPS = 5
TIMELINE = "timeline.md"
BASELINE = "gate-baseline.json"
SCOPE_FILE = "gate-scope.json"
TIER_FILE = "test-tiers.json"
CHECKS_FILE = "gate-checks.json"
ANCHOR_DIR = "flight-anchors"
DECLARE_KEYS = ("global", "blind", "anchor_max_hops")
SEC_RE = re.compile(r"exit -?\d+, ([\d.]+)s")
INC_MARKS = ("增量", "同树沿用")
FULL_MARKS = ("全量：", "全量（")


def load_gate():
    spec = importlib.util.spec_from_file_location("slice_gate", os.path.join(HOOKS_DIR, "slice-gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _err(e):
    """异常 → 人话（slice-gate 的 die 以 SystemExit 退出，原因已写在 stderr）。"""
    if isinstance(e, SystemExit):
        return "slice-gate 退出（%s）" % e.code
    return "%s: %s" % (type(e).__name__, e)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- forecast

def _baseline_part(sg, change_dir):
    bl = sg.load_baseline(change_dir)
    if bl is None:
        return {"mode": "missing", "why": "未跑 baseline" if not os.path.exists(os.path.join(change_dir, BASELINE))
                else "gate-baseline.json 读不了", "sec": None}, None
    if bl.get("running") is True:
        return {"mode": "pending", "why": "baseline 运行中（始于 %s）" % bl.get("started"), "sec": None}, None
    skipped = bl.get("reuse_skipped") or []
    why = skipped[0].get("reason") if skipped and isinstance(skipped[0], dict) else ""
    return {"mode": bl.get("mode") or "full", "why": why or "", "sec": (bl.get("test") or {}).get("sec")}, bl


def _final_part(sg, change_dir, data, baseline):
    gate = data.get("gate") or {}
    if gate.get("impacted"):
        return "impacted", "gate.impacted 自己选测"
    tiers = sg._load_tiers(change_dir)[0]
    if sg.tiers_is_parts(tiers):
        return "full", "多部件分层：部件恒全量"
    test_cmd = gate.get("test")
    if not test_cmd:
        return "unknown", "gate.test 未配置（final 将探测测试命令）"
    root = sg.toplevel(change_dir)
    change_rel = sg._change_rel(root, change_dir)
    name = os.path.basename(os.path.realpath(change_dir))
    akey = sg._anchor_key(root, change_rel, test_cmd, gate)
    tkey = sg._tiers_key(root, change_dir, tiers)
    snap_why, pick = None, None
    try:
        snap = sg._snapshot(root, change_rel)
    except RuntimeError as e:
        snap, snap_why = None, "内容快照失败：%s" % e
    if snap is not None:
        head = sg.git(root, "rev-parse", "HEAD")
        if hasattr(sg, "_scope_extras"):  # S2 合入后才有：按项目声明的 anchor_max_hops 滤锚点
            hops = sg._scope_extras(change_dir).get("anchor_max_hops") or DEFAULT_MAX_HOPS
            pick = sg._pick_anchor(root, akey, tkey, snap, head, change_rel, name, max_hops=hops)
        else:
            pick = sg._pick_anchor(root, akey, tkey, snap, head, change_rel, name)
    base = os.path.dirname(os.path.dirname(os.path.abspath(change_dir)))
    tier_rel = sg._change_rel(root, os.path.join(base, TIER_FILE))
    decl = [sg._change_rel(root, os.path.join(base, n)) for n in (SCOPE_FILE, CHECKS_FILE)]
    bl = baseline if isinstance(baseline, dict) and baseline.get("running") is not True else None
    why, _ = sg._full_why(root, False, pick, bl, snap_why, gate=gate, tier_rel=tier_rel, decl_rels=decl)
    un = (bl or {}).get("deps_unmeasured")
    if why and pick is None and isinstance(un, dict):
        why = "依赖图未测（%s）：%s" % (un.get("kind"), un.get("why"))
    if why:
        return "full", why
    return "incremental", "锚点 %s，Δ %d 个文件" % (str(pick[0].get("commit") or "")[:10], len(pick[1]))


def forecast(change_dir):
    out = {"baseline": {"mode": "unknown", "why": "", "sec": None},
           "final": {"mode": "unknown", "why": "", "sec": None}, "checks": []}
    try:
        sg = load_gate()
    except (Exception, SystemExit) as e:
        out["baseline"]["why"] = out["final"]["why"] = "slice-gate.py 加载失败：%s" % _err(e)
        return out
    data, baseline = {}, None
    try:
        data = sg.load_plan(change_dir)
        gate = data.get("gate") or {}
        out["final"]["sec"] = gate.get("full_suite_sec")
        checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
        out["checks"] = [c.get("name") for c in checks if isinstance(c, dict) and c.get("name")]
    except (Exception, SystemExit) as e:
        out["final"]["why"] = "slices.json 读不了：%s" % _err(e)
        data = None
    try:
        out["baseline"], baseline = _baseline_part(sg, change_dir)
    except (Exception, SystemExit) as e:
        out["baseline"]["why"] = _err(e)
    if data is not None:
        try:
            out["final"]["mode"], out["final"]["why"] = _final_part(sg, change_dir, data, baseline)
        except (Exception, SystemExit) as e:
            out["final"]["mode"], out["final"]["why"] = "unknown", _err(e)
    return out


def _paren(why):
    return "（%s）" % why if why else ""


def forecast_line(fc):
    b, f = fc["baseline"], fc["final"]
    fwhy = "，".join(x for x in (f["why"], "约 %s 秒" % f["sec"] if f.get("sec") is not None else "") if x)
    return "测试成本预告：baseline %s%s · final %s%s · 检查 %d 项" % (
        b["mode"], _paren(b["why"]), f["mode"], _paren(fwhy), len(fc["checks"]))


# ---------------------------------------------------------------- cost

def _balanced(text, start):
    """text[start] 是「（」：取到与之配对的「）」之间的文字（不配对取到末尾）。"""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "（":
            depth += 1
        elif text[i] == "）":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]


def _first(note, marks):
    hits = [note.find(m) for m in marks if m in note]
    return min(hits) if hits else -1


def classify(reason):
    for kw, cls in COST_CLASSES:
        if kw in reason:
            return cls
    return UNCLASSIFIED


def parse_note(note):
    """timeline 备注 → ("full", 原因, 秒数 | None) | ("incremental", None, None) | None（认不出）。"""
    fi, ii = _first(note, FULL_MARKS), _first(note, INC_MARKS)
    if fi < 0 and ii < 0:
        return None
    if ii >= 0 and (fi < 0 or ii < fi):
        return "incremental", None, None
    if note.startswith("全量：", fi):
        reason = note[fi + len("全量："):].split("；", 1)[0]
    else:
        reason = _balanced(note, fi + len("全量"))
    m = SEC_RE.search(note[:fi])
    return "full", reason.strip(), (float(m.group(1)) if m else None)


def cost(change_dir):
    out = {ev: {"full": 0, "incremental": 0, "full_sec": 0.0} for ev in ("baseline", "final")}
    out["full_runs"] = []
    try:
        with open(os.path.join(change_dir, TIMELINE), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 3 or cols[1] not in ("baseline", "final"):
            continue
        parsed = parse_note(cols[2])
        if parsed is None:
            continue
        kind, reason, sec = parsed
        out[cols[1]][kind] += 1
        if kind == "full":
            out[cols[1]]["full_sec"] += sec or 0.0
            out["full_runs"].append({"event": cols[1], "reason": reason, "class": classify(reason), "sec": sec})
    return out


def cost_text(c):
    lines = ["测试成本归因："]
    for ev in ("baseline", "final"):
        s = c[ev]
        lines.append("  %s：全量 %d 次（%.1f 秒）· 增量 %d 次" % (ev, s["full"], s["full_sec"], s["incremental"]))
    for r in c["full_runs"]:
        lines.append("  - %s 全量 [%s]：%s%s" % (r["event"], r["class"], r["reason"] or "（无原因）",
                                               "（%s 秒）" % r["sec"] if r["sec"] is not None else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------- doctor

def _changes(openspec_root):
    """在途 change 目录（不含 archive/）：[(名, 目录)]，按名排序。"""
    base = os.path.join(openspec_root, "changes")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    return [(n, os.path.join(base, n)) for n in names if n != "archive" and os.path.isdir(os.path.join(base, n))]


def _baselines(changes):
    out = []
    for name, d in changes:
        bl = _read_json(os.path.join(d, BASELINE))
        if isinstance(bl, dict) and bl.get("running") is not True:
            out.append((name, bl))
    return out


def doctor_runner(baselines):
    lines = ["[runner]"]
    kinds = {}
    for name, bl in baselines:
        un = bl.get("deps_unmeasured")
        if isinstance(un, dict) and un.get("kind"):
            kinds.setdefault(un["kind"], [un.get("why") or "", []])[1].append(name)
    if not kinds:
        lines.append("  在途 %d 份基线，依赖图均已测到（或尚无基线）" % len(baselines))
        return lines
    for kind in sorted(kinds):
        why, names = kinds[kind]
        lines.append("  %d 份基线是 %s：%s" % (len(names), kind, ", ".join(names)))
        if why:
            lines.append("    修法：%s" % why)
    if any(k in kinds for k in ("plugins-dropped", "plugin-import-failed")):
        lines.append("  包装脚本须转发 $FLIGHT_PLUGIN_PATH 与 $FLIGHT_PYTEST_ARGS（见 .claude/flight-runner-contract.md）")
    return lines


def doctor_anchors(sg, openspec_root):
    lines = ["[anchors]"]
    try:
        root = sg.git(openspec_root, "rev-parse", "--show-toplevel")
        common = sg.git(root, "rev-parse", "--git-common-dir")
    except (Exception, SystemExit):
        lines.append("  不在 git 仓库，跳过")
        return lines
    pdir = os.path.join(common if os.path.isabs(common) else os.path.join(root, common), ANCHOR_DIR)
    try:
        names = sorted(n for n in os.listdir(pdir) if n.endswith(".json") and not n.startswith(".tmp-"))
    except OSError:
        names = []
    entries = [e for e in (_read_json(os.path.join(pdir, n)) for n in names) if isinstance(e, dict)]
    if not entries:
        lines.append("  锚点池为空（首次 final 全量属正常）")
    else:
        measured = sum(1 for e in entries if e.get("measured") is True)
        hops = {}
        for e in entries:
            h = e.get("hops")
            k = "%d 代" % h if isinstance(h, int) else "未记录"
            hops[k] = hops.get(k, 0) + 1
        lines.append("  锚点 %d 条，测到依赖图 %d 条（%d%%）" % (len(entries), measured, 100 * measured // len(entries)))
        lines.append("  hops 分布：%s" % "、".join("%s %d 条" % (k, v) for k, v in sorted(hops.items())))
    lines.append("  注：cmd_key 算法变化后（design D9），旧锚点匹配不到，首次全量属正常")
    return lines


def doctor_gate_test(changes, baselines):
    lines = ["[gate.test]"]
    bmap = dict(baselines)
    hit = []
    for name, d in changes:
        plan = _read_json(os.path.join(d, "slices.json"))
        if not isinstance(plan, dict):
            continue
        gate = plan.get("gate") or {}
        if gate.get("impacted"):
            continue
        un = (bmap.get(name) or {}).get("deps_unmeasured")
        if name in bmap:
            not_pytest = isinstance(un, dict) and un.get("kind") == "not-pytest"
        else:
            not_pytest = bool(gate.get("test")) and "pytest" not in gate["test"]
        if not_pytest:
            hit.append(name)
    if hit:
        lines.append("  %d 个在途 change 的 gate.test 不是 pytest、又没配 gate.impacted（final 恒全量）：%s"
                     % (len(hit), ", ".join(hit)))
        lines.append("    修法：改用 pytest，或配 gate.impacted 自己选测")
    else:
        lines.append("  无：在途 change 都是 pytest 或已配 gate.impacted")
    return lines


def doctor_declare(openspec_root):
    lines = ["[declare]"]
    path = os.path.join(openspec_root, SCOPE_FILE)
    if not os.path.isfile(path):
        lines.append("  未找到 %s" % path)
        return lines
    decl = _read_json(path)
    if not isinstance(decl, dict):
        lines.append("  %s 无法解析为 JSON 对象" % path)
        return lines
    for k in DECLARE_KEYS:
        lines.append("  %s：%s" % (k, json.dumps(decl[k], ensure_ascii=False) if k in decl else "未声明（取缺省）"))
    return lines


def doctor(openspec_root):
    openspec_root = os.path.abspath(openspec_root)
    changes = _changes(openspec_root)
    baselines = _baselines(changes)
    out = doctor_runner(baselines)
    try:
        out += doctor_anchors(load_gate(), openspec_root)
    except (Exception, SystemExit) as e:
        out += ["[anchors]", "  slice-gate.py 加载失败：%s" % _err(e)]
    out += doctor_gate_test(changes, baselines)
    out += doctor_declare(openspec_root)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="flight-doctor：测试成本的预告 / 归因 / 体检（只读，恒 exit 0）")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("forecast", "cost"):
        p = sub.add_parser(name)
        p.add_argument("--change-dir", required=True)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("doctor")
    p.add_argument("--openspec-root", default=os.path.join(os.getcwd(), "openspec"))
    try:
        args = ap.parse_args()
    except SystemExit:
        sys.exit(0)
    try:
        if args.cmd == "forecast":
            fc = forecast(args.change_dir)
            print(json.dumps(fc, ensure_ascii=False) if args.json else forecast_line(fc))
        elif args.cmd == "cost":
            c = cost(args.change_dir)
            print(json.dumps(c, ensure_ascii=False) if args.json else cost_text(c))
        elif args.cmd == "doctor":
            print(doctor(args.openspec_root))
        else:
            ap.print_help()
    except Exception as e:  # 恒 exit 0：只读报告不阻断任何流程
        print("flight-doctor %s 失败：%s" % (args.cmd, _err(e)))
    sys.exit(0)


if __name__ == "__main__":
    main()
