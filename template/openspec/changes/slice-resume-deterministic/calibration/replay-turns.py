#!/usr/bin/env python3
# 只读：回放历史飞行转录，给轮次分档找依据。
# 每个切片执行体一行：仓库、change、切片、轮次标签、实际轮数、是否交回结构化结果、
# owns 条数、计划提交时 owns 展开的现存文件数、scenario 数、门禁报告的改动文件数、
# 命中测试运行器正则的命令数、命中 verify / gate.test 路径记号的命令数。
# 用法：c3_calibrate.py <slice-gate.py 路径> [--rows]
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
SHOW_ROWS = "--rows" in sys.argv
TEST_RE = re.compile(r"\b(pytest|npm (run )?test|pnpm (run )?test|yarn test|vitest|jest|go test|cargo test|make test|tox|unittest|mocha)\b")
HOME = os.path.expanduser("~")
PROMPT_RE = re.compile(r"OpenSpec change \\?`([^`\\]+)\\?` 实现切片 (\S+?)。")


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
                out = (data, tree)
    PLAN_CACHE[key] = out
    return out


def path_tokens(cmds):
    toks = set()
    for c in cmds:
        for t in re.split(r"[\s;&|()'\"]+", c or ""):
            if "/" in t and not t.startswith("-") and re.search(r"\.(sh|py|js|ts|mjs)$", t):
                toks.add(t)
    return toks


rows = []
for f in glob.glob(os.path.join(HOME, ".claude/projects/*/*/subagents/workflows/wf_*/agent-*.jsonl")):
    try:
        meta = json.load(open(f[:-6] + ".meta.json", encoding="utf-8"))
    except (OSError, ValueError):
        continue
    label = meta.get("description") or ""
    if not re.match(r"^S\d+(:retry)?$", label):
        continue
    ids, cwd, change, sid, returned, changed, cmds = set(), "", None, None, False, None, []
    for line in open(f, encoding="utf-8", errors="replace"):
        if change is None:
            m = PROMPT_RE.search(line)
            if m:
                change, sid = m.group(1), m.group(2)
        try:
            o = json.loads(line)
        except ValueError:
            continue
        cwd = o.get("cwd") or cwd
        msg = o.get("message") or {}
        content = msg.get("content")
        if o.get("type") == "assistant":
            if msg.get("id"):
                ids.add(msg["id"])
            for c in content if isinstance(content, list) else []:
                if c.get("type") != "tool_use":
                    continue
                if c.get("name") == "StructuredOutput":
                    returned = True
                if c.get("name") == "Bash":
                    cmds.append(((c.get("input") or {}).get("command") or "").replace("\n", " "))
        for m in re.finditer(r"改动 (\d+) 个文件", line):
            changed = int(m.group(1))
    if not change:
        continue
    repo = repo_root(cwd)
    plan = find_plan(repo, change)
    owns_n = files_plan = scen = None
    tok_hits = None
    if plan:
        data, tree = plan
        sl = next((s for s in data.get("slices") or [] if s.get("id") == sid), None)
        if sl:
            owns = sl.get("owns") or []
            owns_n = len(owns)
            files_plan = sum(1 for p in tree if any(sg.glob_match(p, o) for o in owns))
            scen = len(sl.get("scenarios") or [])
            toks = path_tokens([sl.get("verify"), (data.get("gate") or {}).get("test")])
            tok_hits = sum(1 for c in cmds if not TEST_RE.search(c) and "slice-gate.py" not in c and any(t in c for t in toks))
    rows.append(dict(repo=os.path.basename(repo), change=change, slice=sid, label=label, turns=len(ids),
                     returned=returned, owns=owns_n, files=files_plan, scen=scen, changed=changed,
                     test_cmds=sum(1 for c in cmds if TEST_RE.search(c)), tok_cmds=tok_hits, run=f.split("/")[-2], atype=meta.get("agentType")))

rows.sort(key=lambda r: (r["repo"], r["change"], r["run"], r["slice"], r["label"]))
if SHOW_ROWS:
    for r in rows:
        print("%-22s %-34s %-4s %-9s turns=%-3d ret=%d owns=%s files=%s scen=%s changed=%s test=%d tok=%s" % (
            r["repo"][:22], r["change"][:34], r["slice"], r["label"], r["turns"], r["returned"], r["owns"], r["files"],
            r["scen"], r["changed"], r["test_cmds"], r["tok_cmds"]))

print("执行体样本 %d 个；其中找到计划的 %d 个；仓库 %d 个；change %d 个" % (
    len(rows), sum(1 for r in rows if r["files"] is not None), len(set(r["repo"] for r in rows)),
    len(set((r["repo"], r["change"]) for r in rows))))
by_repo = defaultdict(list)
for r in rows:
    by_repo[r["repo"]].append(r)
for repo, rs in sorted(by_repo.items()):
    print("  %-26s 样本 %3d · 未交回 %2d · 轮数 ≥40 的 %2d · 最大 %d" % (
        repo, len(rs), sum(1 for r in rs if not r["returned"]), sum(1 for r in rs if r["turns"] >= 40), max(r["turns"] for r in rs)))


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] if xs else None


# 只看首轮（重派轮从半成品接着干，轮数不代表整片工作量）；规模 = 现存文件数 + scenario 数
first = [r for r in rows if r["label"] == r["slice"] and r["files"] is not None]
print("首轮且有计划的样本 %d 个" % len(first))
for name, key in (("规模 = files + scen", lambda r: r["files"] + r["scen"]), ("files", lambda r: r["files"]),
                  ("scen", lambda r: r["scen"]), ("owns 条数", lambda r: r["owns"])):
    print("--", name)
    for lo, hi in ((0, 4), (5, 8), (9, 12), (13, 20), (21, 40), (41, 10 ** 6)):
        b = [r for r in first if lo <= key(r) <= hi]
        if not b:
            continue
        t = [r["turns"] for r in b]
        print("   %3d–%-7s n=%-3d 轮数 P50=%-3s P90=%-3s max=%-3s · ≥40 的 %d · 未交回 %d" % (
            lo, hi if hi < 10 ** 6 else "∞", len(b), pct(t, 0.5), pct(t, 0.9), max(t),
            sum(1 for x in t if x >= 40), sum(1 for r in b if not r["returned"])))
# 有上限（注册了 slice-executor 类型，40 轮截断）与无上限（默认 subagent 先读定义文件）分开看
print("agent 类型分布：", dict((k, sum(1 for r in first if r["atype"] == k)) for k in set(r["atype"] for r in first)))
size = lambda r: r["files"] + r["scen"]
for title, sub in (("有上限（slice-executor）", [r for r in first if r["atype"] == "slice-executor"]),
                   ("无上限（其他类型）", [r for r in first if r["atype"] != "slice-executor"])):
    print("--", title, "n=%d" % len(sub))
    for lo, hi in ((0, 8), (9, 12), (13, 16), (17, 24), (25, 40), (41, 80), (81, 10 ** 6)):
        b = [r for r in sub if lo <= size(r) <= hi]
        if not b:
            continue
        t = [r["turns"] for r in b]
        print("   规模 %3d–%-4s n=%-3d 轮数 P50=%-3s P90=%-3s P99=%-3s max=%-3s · ≥40 的 %d（%.0f%%）· 未交回 %d" % (
            lo, hi if hi < 10 ** 6 else "∞", len(b), pct(t, 0.5), pct(t, 0.9), pct(t, 0.99), max(t),
            sum(1 for x in t if x >= 40), 100.0 * sum(1 for x in t if x >= 40) / len(b), sum(1 for r in b if not r["returned"])))
# 候选阈值：规模 > T 判大片档时，被划进大片档的占比，以及标准档里仍撞 40 的占比
for T in (8, 10, 12, 14, 16, 20):
    big = [r for r in first if size(r) > T]
    small = [r for r in first if size(r) <= T]
    hit = lambda rs: sum(1 for r in rs if r["turns"] >= 40 or not r["returned"])
    print("   阈值 规模>%-2d：大片档 %3d 片（%.0f%%），其中撞 40 或未交回 %d；标准档 %d 片里仍撞 40 或未交回 %d（%.1f%%）" % (
        T, len(big), 100.0 * len(big) / len(first), hit(big), len(small), hit(small), 100.0 * hit(small) / max(1, len(small))))
capped = [r for r in first if r["atype"] == "slice-executor"]
for w in (0, 1):
    for T in (6, 8, 10, 12, 16, 20, 24):
        m = lambda r: r["files"] + w * r["scen"]
        big = [r for r in capped if m(r) > T]
        small = [r for r in capped if m(r) <= T]
        print("   有上限样本 · 量 = files%s > %-2d：大片 %3d（%2.0f%%）命中率 %4.1f%% · 标准 %3d 命中率 %4.1f%%" % (
            " + scen" if w else "       ", T, len(big), 100.0 * len(big) / len(capped), 100.0 * hit(big) / max(1, len(big)),
            len(small), 100.0 * hit(small) / max(1, len(small))))
# 重派轮：上一轮未交回后的接续轮要多少轮
retry = [r for r in rows if r["label"].endswith(":retry")]
t = [r["turns"] for r in retry]
print("重派轮 n=%d 轮数 P50=%s P90=%s max=%s · ≥40 的 %d · 未交回 %d" % (
    len(retry), pct(t, 0.5), pct(t, 0.9), max(t) if t else None, sum(1 for x in t if x >= 40), sum(1 for r in retry if not r["returned"])))
big_all = sorted((r for r in first if size(r) > 40), key=lambda r: -size(r))[:12]
for r in big_all:
    print("   大片样本 %-16s %-30s %-4s 规模=%-4d files=%-4d scen=%-2d 轮数=%-3d 交回=%d 类型=%s" % (
        r["repo"][:16], r["change"][:30], r["slice"], size(r), r["files"], r["scen"], r["turns"], r["returned"], r["atype"]))
# 留痕识别：一条测试运行器命令都没命中的执行体，其中有多少跑过 verify / gate.test 里的脚本
zero = [r for r in rows if r["test_cmds"] == 0]
print("留痕：命中运行器正则的命令数为 0 的执行体 %d / %d；其中跑过 verify / gate.test 路径记号的 %d 个" % (
    len(zero), len(rows), sum(1 for r in zero if r["tok_cmds"])))
