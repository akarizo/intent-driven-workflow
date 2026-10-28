#!/usr/bin/env python3
# test-tiers · /test-tiers 的重划分脚本（零 token）
#
# 子命令：
#   probe      [--cmd CMD] [--json PATH]
#              带单元层探针跑测试（缺省 `<python> -m pytest -q`），按文件汇总层级：全纯 = 单元、全不纯 = 集成、都有 = 混合；
#              stdout 每文件一行（首列层级标签）+ 末行合计；--json 写 {total, tests, files}
#   check      [--openspec-root DIR]
#              git 跟踪 / 未忽略的测试文件逐个按 <openspec 根>/test-tiers.json 归层，点名未归层与匹配多层的文件
#   allow-slow NODEID --reason TEXT [--openspec-root DIR] [--session PATH]
#              只认转录里**最新**一条人类消息（design D10）：同时含该用例函数名与放行词才写入 slow_allow
#   render     --probe PATH --plan PATH --out PATH
#              按划分稿（{tiers, moves}）推算每个探针用例的落点与所属层，写单文件审批页（内联 CSS、导出 Markdown / 复制）
#
# 退出码：0 成立 / 无问题；1 有问题（check 点名、render 落点不合规）；2 输入不可用（分层文件缺失或不合法、探针不可度量、
#         理由为空、文件读不了）；3 allow-slow 缺人类放行证据（找不到转录 / 最新人类消息未放行）。
#
# 复用 slice-gate.py 与 takeoff-gate.py 的判定（按路径加载），只读不改它们。兼容 Python 3.8+，只用标准库。
import argparse
import html
import importlib.util
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOW_WORD_RE = re.compile(r"放行|允许|allow|approve", re.IGNORECASE)


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sg = _load("slice-gate")
tg = _load("takeoff-gate")


def fail(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        fail("%s %s 读不了：%s" % (what, path, e))


def tiers_path(args):
    return os.path.join(args.openspec_root or os.path.join(sg.toplevel(), "openspec"), sg.TIER_FILE)


def load_tiers(args):
    path = tiers_path(args)
    if not os.path.isfile(path):
        fail("缺少测试分层文件 %s" % path)
    tiers, errors = sg._load_tiers_file(path)
    if tiers is None:
        fail("测试分层文件 %s 不合法：\n%s" % (path, "\n".join(errors)))
    return path, tiers


# ---------------------------------------------------------------- probe

def cmd_probe(args):
    root = sg.toplevel()
    cmd = args.cmd or "%s -m pytest -q" % shlex.quote(sys.executable)
    res = sg.run_test_gate(cmd, root, probe=True)
    if res["probe"] is None:
        fail("探针不可度量：%s" % res["probe_why"])
    tests = res["probe"]
    files = {}
    for nid in sorted(tests):
        rec = tests[nid]
        f = files.setdefault(nid.split("::", 1)[0], {"unit": 0, "integration": 0, "max_sec": 0.0, "sample": ""})
        if rec["hits"]:
            f["integration"] += 1
            if not f["sample"]:
                kind = sorted(rec["hits"])[0]
                f["sample"] = "%s：%s" % (kind, rec["hits"][kind])
        else:
            f["unit"] += 1
        f["max_sec"] = max(f["max_sec"], rec["sec"])
    for f in files.values():
        f["tier"] = "单元" if not f["integration"] else ("集成" if not f["unit"] else "混合")
    for path in sorted(files):
        f = files[path]
        print("%s  %s  单元 %d · 集成 %d  最慢 %.2fs  %s"
              % (f["tier"], path, f["unit"], f["integration"], f["max_sec"], f["sample"] or "-"))
    n_unit = sum(1 for r in tests.values() if not r["hits"])
    slow = sum(1 for r in tests.values() if not r["hits"] and r["sec"] >= sg.UNIT_MAX_SEC)
    print("合计 %d：单元 %d · 集成 %d · ≥%gs 的单元候选 %d" % (len(tests), n_unit, len(tests) - n_unit, sg.UNIT_MAX_SEC, slow))
    if args.json:
        out = {"total": len(tests), "tests": tests,
               "files": {p: {k: f[k] for k in ("tier", "unit", "integration", "max_sec")} for p, f in files.items()}}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return 0


# ---------------------------------------------------------------- check

def cmd_check(args):
    _, tiers = load_tiers(args)
    root = sg.toplevel()
    listed = sg.git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    paths = sorted(p for p in set(listed) if sg.TEST_FILE_RE.search(p))
    problems = []
    for p in paths:
        layers = sg.tiers_matching(p, tiers)
        if not layers:
            problems.append("未归层：%s" % p)
        elif len(layers) > 1:
            problems.append("匹配多层：%s（%s）" % (p, "、".join(layers)))
    if problems:
        print("\n".join(problems))
        return 1
    print("全部 %d 个测试文件恰好归一层" % len(paths))
    return 0


# ---------------------------------------------------------------- allow-slow

def latest_human(session):
    """转录里时间最大的一条人类消息 → (datetime, 正文)；没有返回 None。"""
    with open(session, "r", encoding="utf-8", errors="replace") as fh:
        lines = fh.read().splitlines()
    best = None
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        text = tg.human_text(row)
        if not text:
            continue
        when = tg.parse_ts(row.get("timestamp"))
        if when and (best is None or when > best[0]):
            best = (when, text)
    return best


def cmd_allow_slow(args):
    path, tiers = load_tiers(args)
    reason = (args.reason or "").strip()
    if not reason:
        fail("--reason 不能为空")
    session = tg.locate_cli(args.session)
    if not session:
        fail("找不到会话转录（--session 或 CLAUDE_CODE_SESSION_ID）；放行慢用例需要人类在对话里明确批准", 3)
    func = args.nodeid.rsplit("::", 1)[-1].split("[", 1)[0]
    latest = latest_human(session)
    if latest is None:
        fail("转录 %s 里没有人类消息；请人类在对话里明确写出放行哪个用例及理由" % session, 3)
    when, text = latest
    if func not in text or not ALLOW_WORD_RE.search(text):
        fail("最新一条人类消息（%s · %s）里没有同时出现 %s 与放行词；请人类在对话里明确写出放行哪个用例及理由"
             % (tg.iso(when), tg.summarize(text), func), 3)
    entry = {"reason": reason, "approved": "%s · %s" % (tg.iso(when), tg.summarize(text))}
    tiers.setdefault("slow_allow", {})[args.nodeid] = entry
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(tiers, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps({args.nodeid: entry}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- render

PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>测试分层划分审批</title>
<style>
body{font-family:-apple-system,"PingFang SC",sans-serif;margin:2em;color:#222}
table{border-collapse:collapse;width:100%%;margin:1em 0}th,td{border:1px solid #ccc;padding:4px 8px;font-size:13px;text-align:left}
th{background:#f3f3f3}.bad{color:#b00020}.ok{color:#1b7f3b}textarea{width:100%%;height:8em}
button{margin-right:.5em;padding:.4em 1em}pre#summary{display:none}
</style></head><body>
<h1>测试分层划分审批</h1>
<h2>问题清单</h2>
%(problems)s
<h2>每层合计</h2>
<table><tr><th>所属层</th><th>用例数</th><th>耗时合计</th></tr>%(totals)s</table>
<h2>划分明细</h2>
<table><tr><th>源</th><th>目标</th><th>所属层</th><th>耗时</th><th>触碰样例</th></tr>%(rows)s</table>
<h2>批注</h2>
<textarea id="note" placeholder="写下对划分的意见"></textarea>
<p><button onclick="exportMd()">导出 Markdown</button><button onclick="copyMd()">复制</button></p>
<pre id="summary">%(summary)s</pre>
<script>
function md(){return document.getElementById("summary").textContent+"\\n## 批注\\n\\n"+document.getElementById("note").value+"\\n";}
function exportMd(){var a=document.createElement("a");a.href=URL.createObjectURL(new Blob([md()],{type:"text/markdown"}));a.download="test-tiers-review.md";a.click();}
function copyMd(){navigator.clipboard.writeText(md());}
</script>
</body></html>
"""


def cmd_render(args):
    probe = read_json(args.probe, "探针结果")
    plan = read_json(args.plan, "划分稿")
    tests = probe.get("tests") if isinstance(probe, dict) else None
    tiers = plan.get("tiers") if isinstance(plan, dict) else None
    if not isinstance(tests, dict) or not isinstance(tiers, dict) or not isinstance(tiers.get("unit"), dict):
        fail("探针结果须含 tests，划分稿须含 tiers.unit")
    moves = plan.get("moves") or {}
    rows, problems, totals = [], [], {}
    for nid in sorted(tests):
        rec = tests[nid]
        hits, sec = rec.get("hits") or {}, float(rec.get("sec") or 0.0)
        src = nid.split("::", 1)[0]
        dest = moves.get(nid) or moves.get(src) or src
        layers = sg.tiers_matching(dest, tiers)
        label = "+".join(layers) or "未归层"
        if len(layers) != 1:
            problems.append("%s：落点 %s %s" % (nid, dest, "未归层" if not layers else "匹配多层（%s）" % "、".join(layers)))
        if "unit" in layers and (hits or sec >= sg.UNIT_MAX_SEC):
            why = "触碰 %s" % "、".join(sorted(hits)) if hits else "耗时 %.2fs ≥ %gs" % (sec, sg.UNIT_MAX_SEC)
            problems.append("%s：落在单元层但%s" % (nid, why))
        t = totals.setdefault(label, [0, 0.0])
        t[0] += 1
        t[1] += sec
        sample = "；".join("%s：%s" % (k, hits[k]) for k in sorted(hits)) or "-"
        rows.append((nid, dest, label, sec, sample))
    esc = html.escape
    summary = ["# 测试分层划分", "", "## 问题", ""] + (["- %s" % p for p in problems] or ["无问题"])
    summary += ["", "## 每层合计", ""] + ["- %s：%d 个，%.2fs" % (k, v[0], v[1]) for k, v in sorted(totals.items())]
    summary += ["", "## 划分", ""] + ["- %s → %s（%s）" % (r[0], r[1], r[2]) for r in rows]
    page = PAGE % {
        "problems": ("<ul class=\"bad\">%s</ul>" % "".join("<li>%s</li>" % esc(p) for p in problems))
                    if problems else "<p class=\"ok\">无问题</p>",
        "totals": "".join("<tr><td>%s</td><td>%d</td><td>%.2fs</td></tr>" % (esc(k), v[0], v[1])
                          for k, v in sorted(totals.items())),
        "rows": "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%.2fs</td><td>%s</td></tr>"
                        % (esc(r[0]), esc(r[1]), esc(r[2]), r[3], esc(r[4])) for r in rows),
        "summary": esc("\n".join(summary) + "\n"),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    for p in problems:
        sys.stderr.write(p + "\n")
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="test-tiers.py")
    sub = ap.add_subparsers(dest="command")
    sub.required = True
    p = sub.add_parser("probe")
    p.add_argument("--cmd")
    p.add_argument("--json")
    p = sub.add_parser("check")
    p.add_argument("--openspec-root")
    p = sub.add_parser("allow-slow")
    p.add_argument("nodeid")
    p.add_argument("--reason", required=True)
    p.add_argument("--openspec-root")
    p.add_argument("--session")
    p = sub.add_parser("render")
    p.add_argument("--probe", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    handler = {"probe": cmd_probe, "check": cmd_check, "allow-slow": cmd_allow_slow, "render": cmd_render}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
