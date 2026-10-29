#!/usr/bin/env python3
# test-tiers · /test-tiers 的重划分脚本（零 token）
#
# 子命令：
#   run unit   [--part P] [--openspec-root DIR]
#              驱动（gate.test = TIER_DRIVER_CMD）：按名字依次在各部件 <顶层>/<root> 下运行 unit.cmd（简写形态 = root 为 .
#              的单个部件 main），输出直通，每部件末尾打印「部件 P：exit N · T s」；--part 只跑一个
#   probe      [--root DIR] [--cmd CMD] [--adapter CMD] [--json PATH]
#              在 <顶层>/<root>（缺省 .）下带单元层探针跑测试（缺省 `<python> -m pytest -q`；有 --adapter 时按适配器契约运行），
#              按文件汇总层级：全纯 = 单元、全不纯 = 集成、都有 = 混合；用例 id 与文件路径都相对顶层；
#              stdout 每文件一行（首列层级标签）+ 末行合计；--json 写 {total, tests, files}
#   check      [--openspec-root DIR]
#              git 跟踪 / 未忽略的测试文件逐个按 <openspec 根>/test-tiers.json 归层，点名未归层与匹配多层的文件；
#              部件形态另点名不属于任何部件 / 属于多个部件的文件（金丝雀文件不参与），层在所属部件内判
#   canary     (--part P | --root DIR --adapter CMD --canary CMD) [--openspec-root DIR]
#              金丝雀自检（design D7）：随机令牌 + 临时目录出题，在 root 下运行适配器并判四个金丝雀用例的触碰与令牌文件落盘；
#              --part 通过时把 probe.sha / probe.checked 写回分层文件，独立模式只打印
#   allow-slow NODEID --reason TEXT [--openspec-root DIR] [--session PATH]
#              只认转录里**最新**一条人类消息（design D10）：同时含该用例函数名与放行词才写入 slow_allow
#   render     --probe PATH --plan PATH --out PATH
#              按划分稿（{tiers, moves}）推算每个探针用例的落点与所属层（部件形态标「部件/unit」或区域名），
#              写单文件审批页（内联 CSS、导出 Markdown / 复制）
#
# 退出码：0 成立 / 无问题；1 有问题（run unit 有部件非 0、check 点名、canary 未通过、render 落点不合规）；
#         2 输入不可用（分层文件缺失或不合法、部件不存在或没有 probe、probe.cmd 里没有仓库内文件、探针不可度量、
#         理由为空、文件读不了）；3 allow-slow 缺人类放行证据（找不到转录 / 最新人类消息未放行）。
#
# 复用 slice-gate.py 与 takeoff-gate.py 的判定（按路径加载），只读不改它们。兼容 Python 3.8+，只用标准库。
import argparse
import html
import importlib.util
import json
import os
import posixpath
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

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
    top = sg.toplevel()
    root = posixpath.normpath(args.root or ".")
    if not os.path.isdir(os.path.join(top, root)):
        fail("--root %s 不是 git 顶层下存在的目录" % root)
    cmd = args.cmd or "%s -m pytest -q" % shlex.quote(sys.executable)
    unit = {"paths": ["**"], "cmd": cmd}
    if args.adapter:
        unit["probe"] = {"cmd": args.adapter}
    res = sg.run_part(top, "probe", {"root": root, "unit": unit})  # 用例 id 已换成相对顶层
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

def check_parts(top, tiers, listed):
    """部件形态（design D4）：全仓测试文件 = 内置命名 ∪ 各部件测试文件，去掉金丝雀；逐个判恰属一个部件、在该部件内恰落一层。
    → (测试文件数, 问题行)。"""
    paths = sorted(p for p in set(listed)
                   if not sg.is_canary(tiers, p) and (sg.TIER_TEST_NAME_RE.search(p) or sg.parts_of(top, tiers, p)))
    problems = []
    for p in paths:
        owners = sg.parts_of(top, tiers, p)
        if not owners:
            problems.append("不属于任何部件：%s" % p)
            continue
        if len(owners) > 1:
            problems.append("属于多个部件：%s（%s）" % (p, "、".join(owners)))
            continue
        part = tiers["parts"][owners[0]]
        layers = [("unit", part["unit"])] + sorted((part.get("regions") or {}).items())
        try:
            hit = [n for n, layer in layers if sg.layer_matches(top, part, layer, p)]
        except RuntimeError as e:
            problems.append("无法判定所在层：%s（list 失败：%s）" % (p, e))
            continue
        if not hit:
            problems.append("未归层：%s" % p)
        elif len(hit) > 1:
            problems.append("匹配多层：%s（%s）" % (p, "、".join(hit)))
    return len(paths), problems


def cmd_check(args):
    _, tiers = load_tiers(args)
    root = sg.toplevel()
    listed = sg.git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
    if sg.tiers_is_parts(tiers):
        n, problems = check_parts(root, tiers, listed)
        if problems:
            print("\n".join(problems))
            return 1
        print("全部 %d 个测试文件恰属一个部件、恰落一层" % n)
        return 0
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


# ---------------------------------------------------------------- run unit

def cmd_run(args):
    _, tiers = load_tiers(args)
    top = sg.toplevel()
    parts = sg.tier_parts(tiers)
    names = sorted(parts)
    if args.part:
        if args.part not in parts:
            fail("分层文件里没有部件 %s（有：%s）" % (args.part, "、".join(names)))
        names = [args.part]
    bad = False
    for name in names:
        part = parts[name]
        t0 = time.time()
        sys.stdout.flush()
        rc = subprocess.call(part["unit"]["cmd"], cwd=os.path.join(top, part["root"]), shell=True)
        print("部件 %s：exit %d · %.1fs" % (name, rc, time.time() - t0), flush=True)
        bad = bad or rc != 0
    return 1 if bad else 0


# ---------------------------------------------------------------- canary

CANARY_CASES = (("pure", None), ("file", "文件"), ("proc", "子进程"), ("net", "网络"))


def canary_problems(probe, why, token, d):
    """金丝雀判定（design D7）→ 未满足的条件（每条一行）；空列表 = 通过。"""
    if probe is None:
        return ["适配器输出没有开跑记录（%s）" % why]
    cases = {}
    for nid in sorted(probe):
        key = re.sub(r"[^0-9a-z]", "", nid.rsplit("::", 1)[-1].lower())
        for case, _ in CANARY_CASES:
            if "flightcanary" + case in key:
                cases.setdefault(case, probe[nid].get("hits") or {})
    problems = []
    for case, kind in CANARY_CASES:
        hits = cases.get(case)
        if hits is None:
            problems.append("缺少金丝雀用例 flightcanary%s 的记录" % case)
        elif kind is None and hits:
            problems.append("pure 用例不应有触碰，却报了 %s" % "、".join(sorted(hits)))
        elif kind is not None and kind not in hits:
            problems.append("%s 用例没有报「%s」触碰" % (case, kind))
        elif case == "file" and token not in str(hits[kind]):
            problems.append("file 用例的「文件」触碰样例不含令牌 %s（%s）" % (token, hits[kind]))
    if not os.path.isfile(os.path.join(d, token)):
        problems.append("令牌文件 $FLIGHT_CANARY_DIR/%s 没有落盘（适配器没有执行 $FLIGHT_UNIT_CMD？）" % token)
    return problems


def cmd_canary(args):
    top = sg.toplevel()
    if args.part:
        path, tiers = load_tiers(args)
        parts = sg.tier_parts(tiers)
        if args.part not in parts:
            fail("分层文件里没有部件 %s" % args.part)
        root = parts[args.part]["root"]
        probe = parts[args.part]["unit"].get("probe")
        if not probe:
            fail("部件 %s 没有 unit.probe（内置 pytest 探针无需自检）" % args.part)
        adapter, canary = probe["cmd"], probe["canary"]
        try:
            sha = sg.probe_files(top, root, adapter)
        except ValueError as e:
            fail("部件 %s 的 probe.cmd 无法按 shell 词法拆分：%s" % (args.part, e))
        if not sha:
            fail("部件 %s 的 probe.cmd 里没有仓库内文件，无从锁定适配器（design D6）" % args.part)
    elif args.root and args.adapter and args.canary:
        root, adapter, canary = posixpath.normpath(args.root), args.adapter, args.canary
    else:
        fail("canary 须给 --part P，或同时给 --root / --adapter / --canary")
    token = secrets.token_hex(8)
    d = tempfile.mkdtemp(prefix="flight-canary-")
    work = tempfile.mkdtemp(prefix="flight-canary-out-")
    try:
        tier_out = os.path.join(work, "tier-probe.jsonl")
        env = dict(os.environ)
        sg._drop_inherited(env)
        env.update({"FLIGHT_UNIT_CMD": canary, "FLIGHT_CANARY_TOKEN": token, "FLIGHT_CANARY_DIR": d,
                    "FLIGHT_TIER_OUT": tier_out, "FLIGHT_JUNIT": os.path.join(work, "junit-part.xml")})
        p = subprocess.run(adapter, cwd=os.path.join(top, root), shell=True, capture_output=True, text=True, env=env)
        raw, why = sg._read_probe(tier_out)
        problems = canary_problems(raw, why, token, d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
    if problems:
        print("\n".join(problems))
        sys.stderr.write("适配器 exit %d：\n%s\n" % (p.returncode, sg._tail((p.stdout or "") + (p.stderr or ""))))
        return 1
    if args.part:
        probe["sha"], probe["checked"] = sha, sg.now_iso()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(tiers, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("金丝雀自检通过：部件 %s（root %s）；已锁定 %s" % (args.part, root, "、".join(sorted(sha))))
    else:
        print("金丝雀自检通过：root %s · 适配器 %s" % (root, adapter))
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


def dest_layers(top, tiers, path):
    """落点所属层：简写形态 unit / 区域名；部件形态「部件/unit」/ 区域名（区域名全仓唯一），list 跑不出按不命中。"""
    if not sg.tiers_is_parts(tiers):
        return sg.tiers_matching(path, tiers)
    out = []
    for name in sorted(tiers["parts"]):
        part = tiers["parts"][name]
        if sg._layer_hit(top, part, part["unit"], path):
            out.append("%s/unit" % name)
        regions = part.get("regions") or {}
        out.extend(r for r in sorted(regions) if sg._layer_hit(top, part, regions[r], path))
    return out


def cmd_render(args):
    probe = read_json(args.probe, "探针结果")
    plan = read_json(args.plan, "划分稿")
    tests = probe.get("tests") if isinstance(probe, dict) else None
    tiers = plan.get("tiers") if isinstance(plan, dict) else None
    if not isinstance(tests, dict) or not isinstance(tiers, dict) or \
            not (sg.tiers_is_parts(tiers) or isinstance(tiers.get("unit"), dict)):
        fail("探针结果须含 tests，划分稿须含 tiers.unit 或 tiers.parts")
    top = None
    if sg.tiers_is_parts(tiers):
        errors = sg._parts_shape(tiers)
        if errors:
            fail("划分稿的 tiers.parts 不合法：\n%s" % "\n".join(errors))
        top = sg.toplevel()
    moves = plan.get("moves") or {}
    rows, problems, totals = [], [], {}
    for nid in sorted(tests):
        rec = tests[nid]
        hits, sec = rec.get("hits") or {}, float(rec.get("sec") or 0.0)
        src = nid.split("::", 1)[0]
        dest = moves.get(nid) or moves.get(src) or src
        layers = dest_layers(top, tiers, dest)
        label = "+".join(layers) or "未归层"
        if len(layers) != 1:
            problems.append("%s：落点 %s %s" % (nid, dest, "未归层" if not layers else "匹配多层（%s）" % "、".join(layers)))
        if any(x == "unit" or x.endswith("/unit") for x in layers) and (hits or sec >= sg.UNIT_MAX_SEC):
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
    p = sub.add_parser("run")
    p.add_argument("layer", choices=["unit"])
    p.add_argument("--part")
    p.add_argument("--openspec-root")
    p = sub.add_parser("probe")
    p.add_argument("--root")
    p.add_argument("--cmd")
    p.add_argument("--adapter")
    p.add_argument("--json")
    p = sub.add_parser("check")
    p.add_argument("--openspec-root")
    p = sub.add_parser("canary")
    p.add_argument("--part")
    p.add_argument("--root")
    p.add_argument("--adapter")
    p.add_argument("--canary")
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
    handler = {"run": cmd_run, "probe": cmd_probe, "check": cmd_check, "canary": cmd_canary,
               "allow-slow": cmd_allow_slow, "render": cmd_render}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
