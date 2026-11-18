#!/usr/bin/env python3
# 只读：afa 体检收集的多次门禁 junit（/tmp/tiers_audit/junit_runs.json，{运行: {用例: [秒, 层]}}），
# 量同一条用例在多次真实门禁运行之间的耗时稳定性，以及层总耗时的波动
import json

runs = json.load(open("/tmp/tiers_audit/junit_runs.json"))
print("运行数 %d" % len(runs))
full = {c: r for c, r in runs.items() if sum(1 for _, t in r.values() if t == "集成") > 1500}
print("全范围运行 %d 次" % len(full))


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else None


for tier in ("单元", "集成"):
    per = {}
    tots = []
    for r in full.values():
        s = 0.0
        for k, (t, tr) in r.items():
            if tr == tier:
                per.setdefault(k, []).append(t)
                s += t
        tots.append(s)
    allin = {k: v for k, v in per.items() if len(v) == len(full)}
    print("== %s：%d 条（每次都在的 %d 条）" % (tier, len(per), len(allin)))
    print("   层合计（逐用例之和）各次：%s · 最大/最小 = %.2f" % (
        " ".join("%.0f" % x for x in sorted(tots)), max(tots) / max(min(tots), 1e-9)))
    for line in ((1.0, 3.0) if tier == "单元" else (3.0, 10.0, 30.0, 60.0)):
        always = sum(1 for v in allin.values() if min(v) > line)
        never = sum(1 for v in allin.values() if max(v) <= line)
        flip = len(allin) - always - never
        # 中位数超线而最小值不超线：靠「重跑取小」能排除的
        med_over = sum(1 for v in allin.values() if pct(v, .5) > line)
        print("   线 %.0fs：始终超线 %d · 始终不超 %d · 时超时不超 %d（中位数超线 %d）" % (line, always, never, flip, med_over))
    big = [v for v in allin.values() if min(v) >= (0.5 if tier == "单元" else 3.0)]
    rs = [max(v) / max(min(v), 1e-3) for v in big]
    if rs:
        print("   最小值不低于 %s 的 %d 条：最大/最小 p50 %.2f p90 %.2f p95 %.2f p99 %.2f" % (
            "0.5s" if tier == "单元" else "3s", len(rs), pct(rs, .5), pct(rs, .9), pct(rs, .95), pct(rs, .99)))
    # 相邻两次运行之间「翻倍且多 0.5 秒」命中数（C5a 的变慢阈值在没有代码差异假设下的噪声命中；注意各次运行的代码树不同）
    names = list(full)
    hits = []
    for i in range(len(names) - 1):
        a, b = full[names[i]], full[names[i + 1]]
        n = 0
        for k, (t, tr) in b.items():
            if tr == tier and k in a and t >= a[k][0] * 2 and t - a[k][0] >= 0.5:
                n += 1
        hits.append(n)
    print("   相邻两次之间「翻倍且多 0.5 秒」命中：%s" % hits)
