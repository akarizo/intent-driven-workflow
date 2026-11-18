#!/usr/bin/env python3
# 只读：「从线下涨到线上」若判红，在没有针对性代码改动的两次运行之间会命中多少条（集成层）
import json
import os
import xml.etree.ElementTree as ET

runs = json.load(open("/tmp/tiers_audit/junit_runs.json"))
full = {c: r for c, r in runs.items() if sum(1 for _, t in r.values() if t == "集成") > 1500}
names = list(full)
D = os.path.expanduser("~/afa-ops/test-tiers-audit-20261118/int_run/")


def load(name):
    out = {}
    for tc in ET.parse(D + name).getroot().iter("testcase"):
        k = "%s::%s" % (tc.get("classname") or "", tc.get("name") or "")
        out[k] = max(out.get(k, 0.0), float(tc.get("time") or 0.0))
    return out


pairs = []
for i in range(len(names) - 1):
    a = {k: t for k, (t, tr) in full[names[i]].items() if tr == "集成"}
    b = {k: t for k, (t, tr) in full[names[i + 1]].items() if tr == "集成"}
    pairs.append(("门禁 %d→%d" % (i, i + 1), a, b))
pairs.append(("同树 warm1→warm2", load("warm1-junit.xml"), load("warm2-junit.xml")))
pairs.append(("同树 warm2→warm1", load("warm2-junit.xml"), load("warm1-junit.xml")))
for line in (10.0, 30.0, 60.0):
    print("线 %.0fs" % line)
    for label, a, b in pairs:
        row = []
        for k_ in (1.0, 2.0, 3.0):
            n = sum(1 for k, t in b.items() if k in a and t > line and a[k] <= line / k_)
            row.append(n)
        print("   %-18s 基线 ≤ 线 且 本次 > 线：%d 条 · 基线 ≤ 线/2：%d 条 · 基线 ≤ 线/3：%d 条" % (label, row[0], row[1], row[2]))
