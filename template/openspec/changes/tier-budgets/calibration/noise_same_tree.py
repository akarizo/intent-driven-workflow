#!/usr/bin/env python3
# 只读：用 afa 体检留下的三次集成层 junit（cold1 / warm1 / warm2）量「同一条用例两次运行之间的耗时噪声」
import os
import sys
import xml.etree.ElementTree as ET

D = os.path.expanduser("~/afa-ops/test-tiers-audit-20261118/int_run/")


def load(name):
    out = {}
    for tc in ET.parse(D + name).getroot().iter("testcase"):
        k = "%s::%s" % (tc.get("classname") or "", tc.get("name") or "")
        try:
            out[k] = max(out.get(k, 0.0), float(tc.get("time") or 0.0))
        except ValueError:
            pass
    return out


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else None


runs = {n: load(n + "-junit.xml") for n in ("cold1", "warm1", "warm2")}
# summary.txt（各次运行的墙钟、负载、新建缓存产物数）含本机临时路径，不原样打印；要点已写进 noise-20261118.txt 的说明
for n, r in runs.items():
    v = list(r.values())
    print("%s: %d 条 · 合计 %.0fs · p50 %.2f p90 %.2f p99 %.2f max %.1f · >=3s %d · >=10s %d · >=30s %d · >=60s %d" % (
        n, len(v), sum(v), pct(v, .5), pct(v, .9), pct(v, .99), max(v),
        sum(x >= 3 for x in v), sum(x >= 10 for x in v), sum(x >= 30 for x in v), sum(x >= 60 for x in v)))
    top = sorted(v, reverse=True)
    print("   最慢 20 条占 %.0f%% · 最慢 100 条占 %.0f%%" % (100 * sum(top[:20]) / sum(v), 100 * sum(top[:100]) / sum(v)))

for a, b in (("warm1", "warm2"), ("cold1", "warm1")):
    A, B = runs[a], runs[b]
    common = [k for k in A if k in B]
    print("== %s 对 %s：共同 %d 条" % (a, b, len(common)))
    for lo in (0.5, 3.0, 10.0):
        rs = [max(A[k], B[k]) / max(min(A[k], B[k]), 1e-3) for k in common if min(A[k], B[k]) >= lo]
        ds = [abs(A[k] - B[k]) for k in common if min(A[k], B[k]) >= lo]
        if rs:
            print("   两次都 >= %.1fs 的 %d 条：比值 p50 %.2f p90 %.2f p95 %.2f p99 %.2f max %.2f · 差值 p95 %.2fs max %.2fs" % (
                lo, len(rs), pct(rs, .5), pct(rs, .9), pct(rs, .95), pct(rs, .99), max(rs), pct(ds, .95), max(ds)))
    for line in (3.0, 5.0, 10.0, 30.0):
        over_a = [k for k in common if A[k] > line]
        cross = [k for k in common if (A[k] > line) != (B[k] > line)]
        for m in (1.0, 1.1, 1.2, 1.5):
            # 判「涨过线」要求 后一次 > line 且 后一次 >= 前一次 * m：纯噪声下会误判多少条
            fp = [k for k in common if A[k] <= line and B[k] > line and B[k] >= A[k] * m] + \
                 [k for k in common if B[k] <= line and A[k] > line and A[k] >= B[k] * m]
            if m == 1.0:
                print("   线 %.0fs：超线 %d 条 · 两次判定不一致 %d 条" % (line, len(over_a), len(cross)), end="")
            else:
                print(" · 余量 x%.1f 后 %d" % (m, len(fp)), end="")
        print()
    # C5a 的「变慢」阈值（翻倍且多 0.5 秒）在纯噪声下的误报
    slow = [k for k in common if B[k] >= A[k] * 2 and B[k] - A[k] >= 0.5] + \
           [k for k in common if A[k] >= B[k] * 2 and A[k] - B[k] >= 0.5]
    print("   「翻倍且多 0.5 秒」在两次同树运行之间命中 %d 条" % len(slow))
sys.exit(0)
