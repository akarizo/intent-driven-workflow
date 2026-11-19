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
#   budget(final, base, budgets, scope_of, allow=None, phase="final") -> 预算结论（G13 集成层单条 · G14 层总量）
#   budget_changes(old_budgets, new_budgets, old_allow, new_allow) -> [行]   （change tier-budgets D3、D5、D7）
#   violations(ledger, budgets, scope_of, allow=None) -> [超线行]   体检用的全量超线清单，线与 budget() 同源（change test-audit D4）
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
        if c.get("t") is not None and c.get("t") != UNIT_TIER:  # 区域用例的单次波动交给 G13 棘轮（tier-budgets D8）
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
        if t not in (UNIT_TIER, NO_TIER):  # 区域的总量走 G14（tier-budgets D8）
            continue
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
    if d.get("budget"):
        lines += _budget_lines(d["budget"])
    return "\n".join(lines)


# ---------- 预算（change tier-budgets D3、D5、D7；纯函数，不读文件、不取时间） ----------

def _g(v):
    return "%g" % v


def _gs(v, none="未设"):
    return none if v is None else "%gs" % v


def _part_label(scope):
    if scope == UNIT_TIER:
        return "单元层"
    if scope.endswith("/" + UNIT_TIER):
        return "部件 %s 的单元层" % scope[:-len(UNIT_TIER) - 1]
    return scope


def _top_text(top):
    return "、".join("%s %.1fs" % (cid, s) for cid, s in top)


def _case_line(spec, a):
    """单条用例的线：有效放行 → (放行上限, "allow")；否则 → (预算单条上限, "budget")。线为 None 表示不判。"""
    if a and not a.get("expired"):
        return a.get("limit"), "allow"
    return spec.get("case_sec"), "budget"


def violations(ledger, budgets, scope_of, allow=None):
    """账本 → 全部超线用例（不看 m、不截断），按 (-秒, 用例) 排序；线的取法与 budget() 同一处（_case_line）。"""
    allow = allow or {}
    amap = {_to_junit(k): v for k, v in allow.items()} if (ledger.get("id_form") or "nodeid") == "junit" else allow
    rows = []
    for cid, c in (ledger.get("cases") or {}).items():
        s, sc = c.get("s"), scope_of(cid, c.get("t"))
        if s is None or sc not in budgets:
            continue
        line, by = _case_line(budgets[sc], amap.get(cid))
        if line is None:
            continue
        kind = budgets[sc].get("kind")
        if (s >= line) if (kind == "unit" and by == "budget") else (s > line):
            rows.append({"case": cid, "scope": sc, "kind": kind, "sec": s, "line": line, "by": by})
    rows.sort(key=lambda r: (-r["sec"], r["case"]))
    return rows


def budget(final, base, budgets, scope_of, allow=None, phase="final"):
    """收口（或基线）账本 → 预算结论：集成层单条棘轮（G13）与层总量（G14）。"""
    budgets = budgets or {}
    raw = final.get("cases") or {}
    form = final.get("id_form") or "nodeid"
    conv = str
    base_ok = base is not None and base.get("complete") is not False
    bc = (base or {}).get("cases") or {}
    if base is not None and (base.get("id_form") or "nodeid") != form:  # 同 delta()：nodeid 那一份换成 junit
        if base.get("id_form") != "junit":
            bc = {_to_junit(k): v for k, v in bc.items()}
        else:
            conv, form = _to_junit, "junit"
    allow = allow or {}
    amap = {_to_junit(k): v for k, v in allow.items()} if form == "junit" else allow
    judged, why = True, None
    if phase != "baseline" and not base_ok:
        judged, why = False, "基线账本不在本机" if base is None else "基线账本不完整"

    failed, warnings, allowed_n = [], [], 0
    groups = {"new": [], "debt": [], "cross": [], "unjudged": []}
    totals = {sc: {"kind": spec.get("kind"), "cases": 0, "sec": 0.0, "no_sec": 0, "budget": spec.get("total_sec"),
                   "over": None, "added_sec": None if (phase == "baseline" or not base_ok) else 0.0, "top": []}
              for sc, spec in budgets.items()}
    for orig in sorted(raw):
        c = raw[orig]
        sc = scope_of(orig, c.get("t"))
        if sc not in budgets:
            continue
        cid, spec, s, tot = conv(orig), budgets[sc], c.get("s"), totals[sc]
        tot["cases"] += 1
        if s is None:
            tot["no_sec"] += 1
        else:
            tot["sec"] += s
            tot["top"].append([cid, s])
            if tot["added_sec"] is not None and cid not in bc:
                tot["added_sec"] += s
        if spec.get("kind") != "region" or c.get("m") != 1 or s is None:
            continue
        case_sec, a = spec.get("case_sec"), amap.get(cid)
        line, by = _case_line(spec, a)
        via_allow = by == "allow"
        if via_allow and case_sec is not None and s > case_sec and (line is None or s <= line):
            allowed_n += 1
            warnings.append("G13 已放行：%s %.1fs（%s）" % (cid, s, a.get("approved") or "-"))
        if line is None or s <= line:
            continue
        row = [cid, s, sc, line]
        if phase == "baseline":
            groups["debt"].append(row)
        elif not base_ok:
            groups["unjudged"].append(row)
        elif cid not in bc:
            groups["new"].append(row)
            failed.append("G13 slow integration test: %s %.1fs（区域 %s %s %gs，本 change 新增）："
                          "提速、拆小，或由人类放行（test-tiers.py allow-slow --limit-sec）"
                          % (cid, s, sc, "放行上限" if via_allow else "单条上限", line))
        elif bc[cid].get("s") is not None and case_sec is not None and bc[cid]["s"] > case_sec:
            groups["debt"].append(row)
        else:
            groups["cross"].append(row)

    for rows in groups.values():
        rows.sort(key=lambda r: (-r[1], r[0]))
    for key, fmt in (("unjudged", "G13 未判：%s（集成层超线只警告）：区域 %s 有 %d 条超线，最慢 %s %.1fs"),
                     ("debt", "G13 老债：区域 %s 有 %d 条用例基线时已超线（单条上限 %s，未判红）：最慢 %s %.1fs"),
                     ("cross", "G13 本次量到超线：区域 %s 有 %d 条用例基线时未超线（单次测量不足以区分噪声，未判红）：%s %.1fs")):
        by_scope = {}
        for r in groups[key]:
            by_scope.setdefault(r[2], []).append(r)
        for sc in sorted(by_scope):
            rs = by_scope[sc]
            if key == "unjudged":
                warnings.append(fmt % (why, sc, len(rs), rs[0][0], rs[0][1]))
            elif key == "debt":
                warnings.append(fmt % (sc, len(rs), _gs(rs[0][3]), rs[0][0], rs[0][1]))
            else:
                warnings.append(fmt % (sc, len(rs), rs[0][0], rs[0][1]))

    for sc in sorted(totals):
        tot = totals[sc]
        tot["sec"] = round(tot["sec"], 1)
        if tot["added_sec"] is not None:
            tot["added_sec"] = round(tot["added_sec"], 1)
        tot["top"] = sorted(tot["top"], key=lambda x: (-x[1], x[0]))[:3]
        limit = tot["budget"]
        if limit is None:
            continue
        if final.get("complete") is False:
            warnings.append("G14 未判：%s 的账本不完整" % sc)
            continue
        if final.get("mode") == "impacted":  # 选测只落实测的那部分用例，合计不是整层的量
            warnings.append("G14 未判：%s 选测（gate.impacted）只跑了部分用例，合计不可比" % sc)
            continue
        if tot["cases"] > 0 and tot["no_sec"] / tot["cases"] > NO_SEC_RATIO:
            warnings.append("G14 未判：%s 有 %d 条用例无耗时（共 %d 条）" % (sc, tot["no_sec"], tot["cases"]))
            continue
        tot["over"] = tot["sec"] > limit
        if not tot["over"]:
            continue
        if tot["kind"] == "region":
            added = "" if tot["added_sec"] is None else "本 change 新增 %.1fs；" % tot["added_sec"]
            warnings.append("G14 区域 %s 合计 %.1fs，超过总量预算 %ss（只警告）：%s最慢 %s"
                            % (sc, tot["sec"], _g(limit), added, _top_text(tot["top"])))
        else:
            failed.append("G14 tier budget: %s 合计 %.1fs，超过总量预算 %ss：最慢 %s"
                          % (_part_label(sc), tot["sec"], _g(limit), _top_text(tot["top"])))

    keys = sorted(allow)
    out = {"judged": judged, "why": why, "failed": failed, "warnings": warnings, "allowed_n": allowed_n,
           "totals": totals,
           "allow": {"total": len(keys), "expired": [k for k in keys if allow[k].get("expired")],
                     "soon": [[k, allow[k].get("expires")] for k in keys if allow[k].get("soon")],
                     "unlimited": sum(1 for k in keys if not allow[k].get("expired") and allow[k].get("limit") is None)}}
    for key in ("new", "debt", "cross"):
        out[key + "_n"], out[key] = len(groups[key]), groups[key][:TOP_N]
    return out


def budget_changes(old_budgets, new_budgets, old_allow, new_allow):
    """两版预算与原样的 slow_allow → 变动行；没有变动 → []。"""
    old_budgets, new_budgets = old_budgets or {}, new_budgets or {}
    out = []
    for sc in sorted(set(old_budgets) | set(new_budgets)):
        ob, nb = old_budgets.get(sc) or {}, new_budgets.get(sc) or {}
        for key, label in (("case_sec", "单条上限"), ("total_sec", "总量预算")):
            o, n = ob.get(key), nb.get(key)
            if o == n:
                continue
            loose = n is None or (o is not None and n > o)
            out.append("%s %s %s → %s（%s）" % (sc, label, _gs(o), _gs(n), "放宽" if loose else "收紧"))
    old_allow, new_allow = old_allow or {}, new_allow or {}
    for cid in sorted(set(old_allow) | set(new_allow)):
        o, n = old_allow.get(cid), new_allow.get(cid)
        if o is None:
            out.append("放行新增 %s（上限 %s · 到期 %s）" % (cid, _gs(n.get("limit_sec"), "无上限"),
                                                     n.get("expires") or "不过期"))
        elif n is None:
            out.append("放行移除 %s" % cid)
        else:
            parts = []
            if o.get("limit_sec") != n.get("limit_sec"):
                parts.append("上限 %s → %s" % (_gs(o.get("limit_sec"), "无上限"), _gs(n.get("limit_sec"), "无上限")))
            if o.get("expires") != n.get("expires"):
                parts.append("到期 %s → %s" % (o.get("expires") or "不过期", n.get("expires") or "不过期"))
            if parts:
                out.append("放行改动 %s：%s" % (cid, "；".join(parts)))
    return out


def _budget_lines(b):
    """render 的预算段（只追加在原有输出之后）。"""
    lines = []
    for cid, s, sc, line in b.get("new") or []:
        lines.append("- 新增超线：%s %.1fs（%s 上限 %s）" % (cid, s, sc, _gs(line)))
    more = (b.get("new_n") or 0) - len(b.get("new") or [])
    if more > 0:
        lines.append("- 新增超线另有 %d 条" % more)
    if b.get("debt_n") or b.get("cross_n"):
        lines.append("- 老债 %d 条 · 本次量到超线 %d 条（未判红）" % (b.get("debt_n") or 0, b.get("cross_n") or 0))
    for sc, tot in (b.get("totals") or {}).items():
        if tot.get("budget") is None:
            continue
        line = "- 预算 %s：%.1fs / %ss" % (sc, tot.get("sec") or 0.0, _g(tot["budget"]))
        if tot.get("over") is None:
            line += "（未判）"
        elif tot["over"]:
            line += "（超预算）"
        if tot.get("added_sec") is not None and tot["added_sec"] > 0:
            line += " · 本 change 新增 %.1fs" % tot["added_sec"]
        lines.append(line)
    al = b.get("allow") or {}
    if al.get("total"):
        expired = al.get("expired") or []
        line = "- 放行：共 %d 条 · 已过期 %d 条" % (al["total"], len(expired))
        if expired:
            line += "（%s）" % "、".join(expired)
        line += " · 14 天内到期 %d 条 · 无上限 %d 条" % (len(al.get("soon") or []), al.get("unlimited") or 0)
        lines.append(line)
    if b.get("changes"):
        lines.append("- 预算变更：")
        lines += ["  - " + x for x in b["changes"]]
    if b.get("judged") is False:
        lines.append("- 集成层单条未判：%s" % (b.get("why") or "-"))
    return lines


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
