#!/usr/bin/env python3
# 只读：回放本机历史飞行，给 C4（wave-integration-guard）的三个阈值找依据。
#   A. 每片 owns 条数的分布，按轮次档（计划提交时 owns 展开的现存文件数 > 8 为大片档）分开，看 12 条上限压住了多少片
#   B. 带通配的单条 owns 展开出多少现存文件
#   C. 首轮门禁报过 G6 ownership（写了 owns 之外的文件）的切片占比，按 owns 条数分组
#   D. 时间线里增量 baseline / final 的测试秒数分布（wave 集成检查的测试那一半与增量 final 同一选法）
# 用法：python3 replay-owns.py <slice-gate.py 路径>（只读；仓库名在输出里已换成代号）
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

spec = importlib.util.spec_from_file_location("sg", sys.argv[1])
sg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg)
HOME = os.path.expanduser("~")
PROMPT_RE = re.compile(r"OpenSpec change \\?`([^`\\]+)\\?` 实现切片 (\S+?)。")
WILD = re.compile(r"[*?\[]")
G6_RE = re.compile(r'G6 ownership: [^\s"\\]+ 不在 owns 内')


def git(cwd, *a):
    p = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def repo_root(cwd):
    for mark in ("/.claude/worktrees/", "/.worktrees/"):
        if mark in cwd:
            return cwd.split(mark)[0]
    return cwd


PLAN_CACHE = {}


def find_plan(repo, change):
    key = (repo, change)
    if key in PLAN_CACHE:
        return PLAN_CACHE[key]
    pats = ["openspec/changes/%s/slices.json", "openspec/changes/archive/*%s/slices.json",
            "template/openspec/changes/%s/slices.json", "template/openspec/changes/archive/*%s/slices.json",
            ".worktrees/*/openspec/changes/%s/slices.json", ".worktrees/*/template/openspec/changes/%s/slices.json",
            ".worktrees/*/openspec/changes/archive/*%s/slices.json",
            "*/openspec/changes/%s/slices.json", "*/openspec/changes/archive/*%s/slices.json",
            ".worktrees/*/*/openspec/changes/%s/slices.json"]
    hit = None
    for pat in pats:
        got = sorted(glob.glob(os.path.join(repo, pat % change)))
        if got:
            hit = got[0]
            break
    out = None
    if hit:
        top = git(os.path.dirname(hit), "rev-parse", "--show-toplevel").strip()
        if top:
            rel = os.path.relpath(os.path.realpath(hit), os.path.realpath(top))
            adds = git(top, "log", "--diff-filter=A", "--format=%H", "--", rel).split()
            commit = adds[-1] if adds else "HEAD"
            tree = [x for x in git(top, "ls-tree", "-r", "--name-only", commit).splitlines() if x]
            try:
                data = json.load(open(hit, encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if data:
                out = (data, tree, os.path.dirname(hit))
    PLAN_CACHE[key] = out
    return out


def pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(len(vals) * q))] if vals else None


def dist(vals):
    return "n=%d P50=%s P90=%s P95=%s P99=%s max=%s" % (len(vals), pct(vals, .5), pct(vals, .9), pct(vals, .95),
                                                       pct(vals, .99), max(vals) if vals else None)


# ---- 转录：(仓库, change, 切片) → 首轮门禁有没有报 G6 ownership
g6 = {}
seen_change = set()
for f in glob.glob(os.path.join(HOME, ".claude/projects/*/*/subagents/workflows/wf_*/agent-*.jsonl")):
    try:
        meta = json.load(open(f[:-6] + ".meta.json", encoding="utf-8"))
    except (OSError, ValueError):
        continue
    label = meta.get("description") or ""
    if not re.match(r"^S\d+(:retry)?$", label):
        continue
    cwd, change, sid, hit = "", None, None, False
    for line in open(f, encoding="utf-8", errors="replace"):
        if change is None:
            m = PROMPT_RE.search(line)
            if m:
                change, sid = m.group(1), m.group(2)
        if not cwd:
            m = re.search(r'"cwd":"([^"]+)"', line)
            if m:
                cwd = m.group(1)
        if G6_RE.search(line):
            hit = True
    if not change or not cwd:
        continue
    repo = repo_root(cwd)
    seen_change.add((repo, change))
    key = (repo, change, sid)
    g6[key] = g6.get(key, False) or hit

# ---- 计划：owns 条数与单条展开
slices = []   # (repo, change, sid, owns_n, files, per_entry[(glob, n)])
for repo, change in sorted(seen_change):
    plan = find_plan(repo, change)
    if not plan:
        continue
    data, tree, _ = plan
    for sl in data.get("slices") or []:
        owns = sl.get("owns") or []
        per = [(o, sum(1 for p in tree if sg.glob_match(p, o))) for o in owns]
        files = sum(1 for p in tree if any(sg.glob_match(p, o) for o in owns))
        slices.append((repo, change, sl.get("id"), len(owns), files, per))

repos = sorted({r for r, *_ in slices})
print("样本：%d 个仓库、%d 个 change、%d 个切片（能在本机找到计划的）" % (len(repos), len({(r, c) for r, c, *_ in slices}), len(slices)))

print("\nA. 每片 owns 条数")
for name, pick in (("标准档（现存文件 ≤ 8）", lambda s: s[4] <= 8), ("大片档（现存文件 > 8）", lambda s: s[4] > 8)):
    vals = [s[3] for s in slices if pick(s)]
    at_cap = sum(1 for v in vals if v == 12)
    near = sum(1 for v in vals if 10 <= v <= 12)
    over = sum(1 for v in vals if v > 12)
    print("   %s：%s · 恰为 12 条 %d（%.1f%%）· 10–12 条 %d（%.1f%%）· 超过 12 条 %d" % (
        name, dist(vals), at_cap, 100.0 * at_cap / max(1, len(vals)), near, 100.0 * near / max(1, len(vals)), over))
buckets = ((1, 4), (5, 8), (9, 11), (12, 12))
for lo, hi in buckets:
    grp = [s for s in slices if lo <= s[3] <= hi]
    wild = [s for s in grp if any(WILD.search(o) for o, _ in s[5])]
    print("   owns %2d–%-2d 条：%4d 片 · 其中含通配的 %4d（%.0f%%）· 现存文件数 %s" % (
        lo, hi, len(grp), len(wild), 100.0 * len(wild) / max(1, len(grp)), dist([s[4] for s in grp])))

cap = [s for s in slices if s[3] == 12]
for th in (16, 20, 30, 40):
    k = sum(1 for s in cap if s[4] <= th)
    print("   恰为 12 条的 %d 片里，现存文件数 ≤ %d 的 %d（%.0f%%）：把每个文件各写一条也不超过 %d 条" % (len(cap), th, k, 100.0 * k / max(1, len(cap)), th))

print("\nB. 带通配的单条 owns 展开出的现存文件数")
wide = [n for s in slices for o, n in s[5] if WILD.search(o)]
lit = [n for s in slices for o, n in s[5] if not WILD.search(o)]
print("   通配条目：%s" % dist(wide))
for th in (5, 10, 20, 30, 50, 100):
    k = sum(1 for n in wide if n > th)
    ks = len({(s[0], s[1], s[2]) for s in slices if any(WILD.search(o) and n > th for o, n in s[5])})
    print("   展开 > %-3d 的通配条目 %4d（%.1f%%），涉及 %d 片（%.1f%%）" % (th, k, 100.0 * k / max(1, len(wide)), ks, 100.0 * ks / max(1, len(slices))))
print("   字面条目：n=%d，其中计划时已存在的 %d（%.0f%%）" % (len(lit), sum(1 for n in lit if n), 100.0 * sum(1 for n in lit if n) / max(1, len(lit))))

print("\nC. 门禁报过 G6 ownership（执行体写了 owns 之外的文件）的切片")
have = [s for s in slices if (s[0], s[1], s[2]) in g6]
for lo, hi in buckets:
    grp = [s for s in have if lo <= s[3] <= hi]
    hit = sum(1 for s in grp if g6[(s[0], s[1], s[2])])
    print("   owns %2d–%-2d 条：%4d 片 · 报过 G6 的 %3d（%.1f%%）" % (lo, hi, len(grp), hit, 100.0 * hit / max(1, len(grp))))
for name, pick in (("最宽通配展开 ≤ 20", lambda s: max([n for o, n in s[5] if WILD.search(o)] or [0]) <= 20),
                   ("最宽通配展开 > 20", lambda s: max([n for o, n in s[5] if WILD.search(o)] or [0]) > 20)):
    grp = [s for s in have if pick(s)]
    hit = sum(1 for s in grp if g6[(s[0], s[1], s[2])])
    print("   %s：%4d 片 · 报过 G6 的 %3d（%.1f%%）" % (name, len(grp), hit, 100.0 * hit / max(1, len(grp))))

# ---- 时间线：增量运行的测试秒数
print("\nD. 时间线里增量运行的测试秒数（wave 集成检查的测试那一半与增量 final 同一选法）")
inc_final, inc_base, full = defaultdict(list), defaultdict(list), defaultdict(list)
tl_seen = set()
for repo in repos:
    for pat in ("openspec/changes/*/timeline.md", "template/openspec/changes/*/timeline.md",
                ".worktrees/*/openspec/changes/*/timeline.md", ".worktrees/*/template/openspec/changes/*/timeline.md",
                "openspec/changes/archive/*/timeline.md", "*/openspec/changes/*/timeline.md"):
        for f in glob.glob(os.path.join(repo, pat)):
            for line in open(f, encoding="utf-8", errors="replace"):
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 3 or (cols[0], cols[1], cols[2]) in tl_seen:
                    continue
                tl_seen.add((cols[0], cols[1], cols[2]))
                ev, note = cols[1], cols[2]
                if ev == "baseline":
                    m = re.search(r"增量（.*?补跑 (\d+) 个测试文件 ([\d.]+)s", note)
                    if m:
                        inc_base[repo].append((float(m.group(2)), int(m.group(1))))
                elif ev == "final":
                    t = re.search(r"测试 ([\d.]+)s", note)
                    if t and note.startswith("增量"):
                        inc_final[repo].append((float(t.group(1)), 0))
                    elif t and note.startswith("全量"):
                        full[repo].append((float(t.group(1)), 0))
for i, repo in enumerate(repos):
    tag = "本仓" if os.path.basename(repo) == "intent-driven-workflow" else "仓库 %s" % chr(ord("A") + i)
    for name, d in (("增量 baseline", inc_base), ("增量 final", inc_final), ("全量 final", full)):
        vals = [v for v, _ in d[repo]]
        if vals:
            print("   %-6s %-12s 秒数 %s · ≤60s %d · ≤120s %d · ≤300s %d" % (
                tag, name, dist([round(v) for v in vals]), sum(1 for v in vals if v <= 60), sum(1 for v in vals if v <= 120),
                sum(1 for v in vals if v <= 300)))
allinc = [v for d in (inc_base, inc_final) for r in d for v, _ in d[r]]
print("   全部增量运行：秒数 %s" % dist([round(v) for v in allinc]))
for th in (60, 120, 180, 300, 600):
    print("   ≤ %3ds 的占 %.0f%%" % (th, 100.0 * sum(1 for v in allinc if v <= th) / max(1, len(allinc))))
