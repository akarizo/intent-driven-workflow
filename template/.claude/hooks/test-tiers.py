#!/usr/bin/env python3
# test-tiers · /test-tiers 的重划分脚本（零 token）
#
# 子命令：
#   run unit   [--part P] [--openspec-root DIR]
#              驱动（gate.test = TIER_DRIVER_CMD）：按名字依次在各部件 <顶层>/<root> 下运行 unit.cmd（简写形态 = root 为 .
#              的单个部件 main），输出直通，每部件末尾打印「部件 P：exit N · T s」；--part 只跑一个；
#              整个运行期间持全机测试锁（独占）
#   probe      [--root DIR] [--cmd CMD] [--adapter CMD] [--json PATH]
#              在 <顶层>/<root>（缺省 .）下带单元层探针跑测试（缺省 `<python> -m pytest -q`；有 --adapter 时按适配器契约运行），
#              按文件汇总层级：全纯 = 单元、全不纯 = 集成、都有 = 混合；用例 id 与文件路径都相对顶层；
#              stdout 每文件一行（首列层级标签）+ 末行合计；--json 写 {total, tests, files}；
#              整个运行期间持全机测试锁（独占）
#   check      [--openspec-root DIR]
#              git 跟踪 / 未忽略的测试文件逐个按 <openspec 根>/test-tiers.json 归层，点名未归层与匹配多层的文件；
#              部件形态另点名不属于任何部件 / 属于多个部件的文件（金丝雀文件不参与），层在所属部件内判
#   canary     (--part P | --root DIR --adapter CMD --canary CMD) [--openspec-root DIR]
#              金丝雀自检（design D7）：随机令牌 + 临时目录出题，在 root 下运行适配器并判四个金丝雀用例的触碰与令牌文件落盘；
#              --part 通过时把 probe.sha / probe.checked 写回分层文件，独立模式只打印
#   allow-slow NODEID --reason TEXT [--limit-sec SEC] [--expires YYYY-MM-DD] [--openspec-root DIR] [--session PATH]
#              只认转录里**最新**一条人类消息（design D10）：同时含该用例函数名与放行词才写入 slow_allow；
#              --limit-sec / --expires 写进条目的 limit_sec / expires（design D11），都没给时 stderr 提示一行
#   render     --probe PATH --plan PATH --out PATH
#              按划分稿（{tiers, moves}）推算每个探针用例的落点与所属层（部件形态标「部件/unit」或区域名），
#              写单文件审批页（内联 CSS、导出 Markdown / 复制）
#   audit      [--openspec-root DIR] [--change-dir DIR | --ledger PATH | --no-ledger] [--probe PATH]...
#              [--scope 范围]... [--category 类别]... [--top N] [--json] [--out PATH] [--compare 之前的体检JSON [--plan 整改稿JSON]]
#              只读体检（change test-audit）：分层文件 + 测试文件清单 + 一份测量（账本 ∪ 探针）按当前工作树重新归层，
#              按 AUDIT_RULES 列出不合规项、提示与未判项；不跑测试、不取测试锁、不写分层文件与账本（--out 除外）；
#              筛选顺序：--scope → --category → 计数与结论 → --top（每类至多 N 条，只截明细）；--out 与 --json 同一个对象；
#              --compare 按条目 id 比不合规项（已解决 / 仍在 / 新增），--plan 把稿里去向不是 keep 的旧不合规项当本轮目标
#
# 退出码：0 成立 / 无问题；1 有问题（run unit 有部件非 0、check 点名、canary 未通过、render 落点不合规、audit 有不合规项）；
#         2 输入不可用（分层文件缺失或不合法、部件不存在或没有 probe、probe.cmd 里没有仓库内文件、探针不可度量、
#         理由为空、--limit-sec / --expires 不合法、文件读不了；audit 的分层文件不合法、账本 / 探针 / change 目录读不了、
#         --compare / --plan 读不了或形状不对、--plan 没带 --compare）；
#         3 allow-slow 缺人类放行证据（找不到转录 / 最新人类消息未放行）；audit 没有不合规项但有未判项。
#         audit 带 --compare 时：有新增或有目标未解决 → 1；否则有未判项 → 3（未能确认）；否则 0（不在目标里的旧债不算失败）。
#
# 复用 slice-gate.py 与 takeoff-gate.py 的判定（按路径加载），只读不改它们。兼容 Python 3.8+，只用标准库。
import argparse
import datetime
import html
import importlib.util
import json
import math
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
tl = _load("test-ledger")


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
    hold = sg.flight_lock("exclusive", label="test-tiers probe")  # 校验之后取：校验失败不排队
    try:
        return _probe(args, top, root)
    finally:
        hold.release()


def _probe(args, top, root):
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
    → (测试文件数, {恰落一层的文件: 层}, [(文件, 问题行)])。"""
    paths = sorted(p for p in set(listed)
                   if not sg.is_canary(tiers, p) and (sg.TIER_TEST_NAME_RE.search(p) or sg.parts_of(top, tiers, p)))
    placed, problems = {}, []
    for p in paths:
        owners = sg.parts_of(top, tiers, p)
        if not owners:
            problems.append((p, "不属于任何部件：%s" % p))
            continue
        if len(owners) > 1:
            problems.append((p, "属于多个部件：%s（%s）" % (p, "、".join(owners))))
            continue
        part = tiers["parts"][owners[0]]
        layers = [("unit", part["unit"])] + sorted((part.get("regions") or {}).items())
        try:
            hit = [n for n, layer in layers if sg.layer_matches(top, part, layer, p)]
        except RuntimeError as e:
            problems.append((p, "无法判定所在层：%s（list 失败：%s）" % (p, e)))
            continue
        if not hit:
            problems.append((p, "未归层：%s" % p))
        elif len(hit) > 1:
            problems.append((p, "匹配多层：%s（%s）" % (p, "、".join(hit))))
        else:
            placed[p] = hit[0]
    return len(paths), placed, problems


def layering(top, tiers, listed):
    """check 的判据（简写 / 部件两形态同一出口）→ (测试文件数, {恰落一层的文件: 层}, [(文件, 问题行)])。"""
    if sg.tiers_is_parts(tiers):
        return check_parts(top, tiers, listed)
    paths = sorted(p for p in set(listed) if sg.TEST_FILE_RE.search(p))
    placed, problems = {}, []
    for p in paths:
        layers = sg.tiers_matching(p, tiers)
        if not layers:
            problems.append((p, "未归层：%s" % p))
        elif len(layers) > 1:
            problems.append((p, "匹配多层：%s（%s）" % (p, "、".join(layers))))
        else:
            placed[p] = layers[0]
    return len(paths), placed, problems


def listed_files(root):
    return sg.git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()


def cmd_check(args):
    _, tiers = load_tiers(args)
    root = sg.toplevel()
    n, _, problems = layering(root, tiers, listed_files(root))
    if problems:
        print("\n".join(text for _, text in problems))
        return 1
    if sg.tiers_is_parts(tiers):
        print("全部 %d 个测试文件恰属一个部件、恰落一层" % n)
    else:
        print("全部 %d 个测试文件恰好归一层" % n)
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
    hold = sg.flight_lock("exclusive", label="test-tiers run")  # 校验之后取：校验失败不排队
    try:
        for name in names:
            part = parts[name]
            t0 = time.time()
            sys.stdout.flush()
            rc = subprocess.call(part["unit"]["cmd"], cwd=os.path.join(top, part["root"]), shell=True)
            print("部件 %s：exit %d · %.1fs" % (name, rc, time.time() - t0), flush=True)
            bad = bad or rc != 0
    finally:
        hold.release()
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
        probe["sha"], probe["checked"], probe["checked_cmd"] = sha, sg.now_iso(), adapter
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
    limit, expires = args.limit_sec, args.expires
    if limit is not None and not limit > 0:
        fail("--limit-sec 须大于 0（收到 %s）" % limit)
    if expires is not None:
        day = sg._iso_day(expires)
        if day is None:
            fail("--expires %s 不是真实日期（须为 YYYY-MM-DD）" % expires)
        if day < datetime.datetime.now(datetime.timezone.utc).date():
            fail("--expires %s 早于今天（UTC）" % expires)
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
    if limit is not None:
        entry["limit_sec"] = int(limit) if limit.is_integer() else limit
    if expires is not None:
        entry["expires"] = expires
    if limit is None and expires is None:
        sys.stderr.write("提示：这条放行没有上限也没有到期日（可加 --limit-sec / --expires）\n")
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


# ---------------------------------------------------------------- audit

AUDIT_RULES = {
    "no-tiers": {"rule": "R1", "level": "violation", "fix": [], "title": "没有分层文件"},
    "layering": {"rule": "R2", "level": "violation", "fix": ["move", "retier"], "title": "测试文件归层有误"},
    "unit-impure": {"rule": "R3", "level": "violation", "fix": ["purify", "move", "split"], "title": "单元层用例有触碰"},
    "unit-slow": {"rule": "R4", "level": "violation", "fix": ["speedup", "move", "allow"], "title": "单元层用例超线"},
    "no-case-limit": {"rule": "R5", "level": "violation", "fix": ["budget"], "title": "集成区域没写单条上限"},
    "region-slow": {"rule": "R6", "level": "violation", "fix": ["speedup", "allow", "delete"], "title": "集成区域用例超线"},
    "total-over": {"rule": "R7", "level": "violation", "fix": ["speedup", "delete", "budget"], "title": "范围合计超预算"},
    "allow-stale": {"rule": "R8", "level": "violation", "fix": ["drop-allow"], "title": "放行所指文件已不存在"},
    "allow-expired": {"rule": "R8", "level": "violation", "fix": ["allow", "speedup", "move", "drop-allow"],
                      "title": "放行已过期"},
    "allow-unbounded": {"rule": "R8", "level": "violation", "fix": ["allow", "drop-allow"], "title": "放行缺上限或期限"},
    "allow-soon": {"rule": None, "level": "advice", "fix": [], "title": "放行快到期"},
    "allow-unneeded": {"rule": None, "level": "advice", "fix": ["drop-allow"], "title": "放行已不需要"},
    "pure-in-region": {"rule": None, "level": "advice", "fix": ["move", "split"], "title": "区域里有无触碰的快用例"},
    "purity-unchecked": {"rule": None, "level": "advice", "fix": [], "title": "纯度未核对"},
    "gwt-missing": {"rule": None, "level": "advice", "fix": [], "title": "用例缺 Given / When / Then 注释"},
    "unjudged": {"rule": None, "level": "unjudged", "fix": [], "title": "判不了"},
}
LEVEL_TEXT = {"violation": "不合规", "advice": "提示", "unjudged": "未判"}
AUDIT_GLOBAL_IDS = ("no-tiers:", "unjudged:no-measure", "unjudged:ledger")


def audit_item(cat, key, text, scope=None, case=None, file=None, sec=None, line=None):
    r = AUDIT_RULES[cat]
    return {"id": "%s:%s" % (cat, key), "category": cat, "rule": r["rule"], "level": r["level"], "scope": scope,
            "case": case, "file": file, "sec": sec, "line": line, "text": text, "fix": list(r["fix"])}


def _looks_like_path(s):
    return "/" in s or bool(os.path.splitext(s)[1])


def _rank(xs, p):
    """最近秩分位数；xs 已排序。"""
    return xs[max(0, int(math.ceil(p * len(xs))) - 1)] if xs else None


def pick_ledger(args, top):
    """账本选取：--no-ledger > --ledger > --change-dir（收口，没有则基线）> 本机 at 最新 → (账本, change, phase)。"""
    if args.no_ledger:
        return None, None, None
    if args.ledger:
        led = read_json(args.ledger, "账本")
        if not isinstance(led, dict) or not isinstance(led.get("cases"), dict):
            fail("账本 %s 不是含 cases 的对象" % args.ledger)
        return led, led.get("change"), led.get("phase")
    if args.change_dir:
        if not os.path.isdir(args.change_dir):
            fail("--change-dir %s 不是存在的目录" % args.change_dir)
        name = os.path.basename(os.path.normpath(os.path.abspath(args.change_dir)))
        for phase in tl.PHASES:
            led = tl.load(top, name, phase)
            if led is not None:
                return led, name, phase
        return None, None, None
    try:
        names = sorted(os.listdir(tl.ledger_dir(top)))
    except (RuntimeError, OSError):
        return None, None, None
    best = (None, None, None)
    for name in names:
        for phase in tl.PHASES:
            led = tl.load(top, name, phase)
            if led is not None and (best[0] is None or str(led.get("at") or "") > str(best[0].get("at") or "")):
                best = (led, name, phase)
    return best


def load_probes(args):
    out = []
    for path in args.probe or []:
        obj = read_json(path, "探针结果")
        if not isinstance(obj, dict) or not isinstance(obj.get("tests"), dict):
            fail("探针结果 %s 不是含 tests 的对象" % path)
        out.append(obj["tests"])
    return out


def case_table(top, tiers, led, probes):
    """账本 ∪ 探针 → ({用例 id: {s, t, hits, file}}, id 形式, 丢弃的用例 id 集合)；层按当前分层文件由所在文件重新归层。"""
    form = (led or {}).get("id_form") or "nodeid"
    table, dropped = {}, set()

    def place(cid, cand, recorded):
        if cand and os.path.isfile(os.path.join(top, cand)):
            return (sg.tiers_matching(cand, tiers, top) or [None])[0], cand
        if cand and _looks_like_path(cand):
            dropped.add(cid)
            return None
        return (None if recorded == tl.NO_TIER else recorded), None

    for cid, c in sorted(((led or {}).get("cases") or {}).items()):
        cand = tl._file_of(cid, form, top) if form == "junit" else cid.split("::", 1)[0]
        got = place(cid, cand, c.get("t"))
        if got is not None:
            table[cid] = {"s": c.get("s"), "t": got[0], "hits": None, "file": got[1]}
    for tests in probes:
        for nid, rec in sorted(tests.items()):
            cid = tl._to_junit(nid) if form == "junit" else nid
            got = place(cid, nid.split("::", 1)[0], (table.get(cid) or {}).get("t"))
            if got is not None:
                table[cid] = {"s": rec.get("sec"), "t": got[0], "hits": rec.get("hits") or {}, "file": got[1]}
    return table, form, dropped


def _head(top):
    try:
        return sg.git(top, "rev-parse", "--verify", "-q", "HEAD") or None
    except RuntimeError:
        return None


def audit_report(top, tiers, led, probes):
    """体检主体（只读）→ (items, scopes, allow 段, source 的 cases / dropped)。"""
    table, form, dropped = case_table(top, tiers, led, probes)
    budgets, scope_of = sg.tier_budgets(tiers), sg.budget_scope_of(tiers)
    aview = sg.allow_view(tiers.get("slow_allow") or {})
    like = {"cases": {cid: {"s": c["s"], "t": c["t"], "m": 1} for cid, c in table.items()},
            "id_form": form, "complete": True, "mode": "full"}
    items = []
    _, placed, problems = layering(top, tiers, listed_files(top))
    items.extend(audit_item("layering", f, text, file=f) for f, text in problems)
    for v in tl.violations(like, budgets, scope_of, aview):
        cat = "unit-slow" if v["kind"] == "unit" else "region-slow"
        items.append(audit_item(cat, v["case"], "%s %.1fs，超出%s %ss"
                                % (v["case"], v["sec"], "放行上限" if v["by"] == "allow" else "单条上限", tl._g(v["line"])),
                                scope=v["scope"], case=v["case"], file=table[v["case"]]["file"],
                                sec=v["sec"], line=v["line"]))
    for sc in sorted(budgets):
        if budgets[sc]["kind"] == "region" and budgets[sc]["case_sec"] is None:
            items.append(audit_item("no-case-limit", sc, "区域 %s 没写单条上限 budget.case_sec" % sc, scope=sc))
    b = tl.budget(like, None, budgets, scope_of, aview, "baseline")
    secs = {}
    for cid, c in table.items():
        sc = scope_of(cid, c["t"])
        if sc in budgets and c["s"] is not None:
            secs.setdefault(sc, []).append(c["s"])
    scopes = {}
    for sc in sorted(b["totals"]):
        tot, xs = b["totals"][sc], sorted(secs.get(sc, []))
        scopes[sc] = {"kind": tot["kind"], "cases": tot["cases"], "sec": tot["sec"], "no_sec": tot["no_sec"],
                      "case_sec": budgets[sc]["case_sec"], "total_sec": tot["budget"], "over": tot["over"],
                      "p50": _rank(xs, 0.5), "p95": _rank(xs, 0.95), "max": xs[-1] if xs else None}
    unjudged, ledger_bad = audit_unjudged(table, placed, scopes, scope_of, led, probes)
    items.extend(unjudged)
    for sc in sorted(b["totals"]):
        tot = b["totals"][sc]
        if tot["over"] and not ledger_bad and "unjudged:scope:" + sc not in {it["id"] for it in unjudged}:
            label = "区域 %s" % sc if tot["kind"] == "region" else tl._part_label(sc)
            items.append(audit_item("total-over", sc, "%s 合计 %.1fs，超过总量预算 %ss"
                                    % (label, tot["sec"], tl._g(tot["budget"])),
                                    scope=sc, sec=tot["sec"], line=tot["budget"]))
    part_names = set(tiers["parts"]) if sg.tiers_is_parts(tiers) else set()
    for key in sorted(aview):
        a, head = aview[key], key.split("::", 1)[0]
        c = table.get(tl._to_junit(key) if form == "junit" else key)
        if _looks_like_path(head) and head not in part_names and not os.path.isfile(os.path.join(top, head)):
            cat, text = "allow-stale", "放行 %s 所指的测试文件 %s 已不存在" % (key, head)
        elif a["expired"]:
            cat, text = "allow-expired", "放行 %s 已于 %s 过期" % (key, a["expires"])
        elif a["limit"] is None or a["expires"] is None:
            miss = "、".join(n for n, v in (("limit_sec", a["limit"]), ("expires", a["expires"])) if v is None)
            cat, text = "allow-unbounded", "放行 %s 缺 %s" % (key, miss)
        else:
            cat = None
        sc = scope_of(key, c["t"]) if c else None
        found = [(cat, text)] if cat else []
        if not cat:  # 有效放行：快到期、已回到线内各自一条提示
            if a["soon"]:
                found.append(("allow-soon", "放行 %s 将于 %s 到期" % (key, a["expires"])))
            line = (budgets.get(sc) or {}).get("case_sec")
            if c and c["s"] is not None and line is not None \
                    and (c["s"] < line if budgets[sc]["kind"] == "unit" else c["s"] <= line):
                found.append(("allow-unneeded", "放行 %s 的用例 %.1fs 已回到单条上限 %ss 内，可撤销放行"
                              % (key, c["s"], tl._g(line))))
        for cat, text in found:
            items.append(audit_item(cat, key, text, scope=sc, case=key, file=c["file"] if c else None,
                                    sec=c["s"] if c else None))
    if probes:
        pure = {}
        for cid in sorted(table):
            c = table[cid]
            if c["hits"] is None:
                continue
            sc = scope_of(cid, c["t"])
            kind = (budgets.get(sc) or {}).get("kind")
            if c["hits"] and kind == "unit":
                k = sorted(c["hits"])[0]
                items.append(audit_item("unit-impure", cid, "%s 在单元层却有触碰：%s：%s" % (cid, k, c["hits"][k]),
                                        scope=sc, case=cid, file=c["file"], sec=c["s"]))
            elif not c["hits"] and kind == "region" and c["file"] and c["s"] is not None and c["s"] < sg.UNIT_MAX_SEC:
                pure.setdefault((c["file"], sc), []).append(cid)
        for (f, sc), cids in sorted(pure.items()):
            items.append(audit_item("pure-in-region", f, "区域 %s 的 %s 里有 %d 条用例无触碰且低于 %gs（如 %s）"
                                    % (sc, f, len(cids), sg.UNIT_MAX_SEC, cids[0]), scope=sc, file=f))
    else:
        items.append(audit_item("purity-unchecked", "", "没有探针结果，单元层纯度未在体检里核对"
                                                        "（可加 --probe <test-tiers.py probe --json 的结果>）"))
    gwt = sg.gwt_violations(top, [f for f in placed if f.endswith(".py")])
    if gwt:
        it = audit_item("gwt-missing", "", "%d 条用例缺 Given / When / Then 注释（如 %s）"
                        % (len(gwt), gwt[0].split(": ", 1)[-1]))
        it["count"] = len(gwt)
        items.append(it)
    items.sort(key=audit_sort_key)
    return items, scopes, b["allow"], len(table), len(dropped)


def audit_unjudged(table, placed, scopes, scope_of, led, probes):
    """未判三种 → ([条目], 来源账本是否不可判总量)。scopes 是已算好的各范围分布。"""
    if led is None and not probes:
        return [audit_item("unjudged", "no-measure", "没有测量：本机没有账本，也没给 --probe；时间类规则都判不了")], False
    out = []
    ledger_bad = led is not None and (led.get("complete") is False or led.get("mode") == "impacted")
    if ledger_bad:
        why = "不完整" if led.get("complete") is False else "来自选测（gate.impacted），只跑了部分用例"
        out.append(audit_item("unjudged", "ledger", "来源账本%s：各范围合计不可比，不判总量预算" % why))
    measured = {c["file"] for c in table.values() if c["file"]}
    fileless = {scope_of(cid, c["t"]) for cid, c in table.items() if c["file"] is None}
    missing = {}
    for f in sorted(placed):
        sc = scope_of(f + "::x", placed[f])
        if f not in measured and sc not in fileless:
            missing.setdefault(sc, []).append(f)
    for sc in sorted(set(missing) | set(scopes)):
        why = []
        if missing.get(sc):
            why.append("%d 个测试文件没有测量（如 %s）" % (len(missing[sc]), missing[sc][0]))
        s = scopes.get(sc)
        if s and s["cases"] > 0 and s["no_sec"] / s["cases"] > tl.NO_SEC_RATIO:
            why.append("%d 条用例无耗时（共 %d 条）" % (s["no_sec"], s["cases"]))
        if why:
            out.append(audit_item("unjudged", "scope:" + sc, "范围 %s 判不全：%s" % (sc, "；".join(why)), scope=sc))
    return out, ledger_bad


LEVEL_ORDER = {"violation": 0, "unjudged": 1, "advice": 2}


def audit_sort_key(it):
    """级别（不合规 → 未判 → 提示）、类别、耗时由大到小、id。"""
    return LEVEL_ORDER[it["level"]], list(AUDIT_RULES).index(it["category"]), -(it["sec"] or 0.0), it["id"]


def load_compare(args):
    """--compare / --plan 的输入 → (之前的体检, 整改稿 items | None)；不可用 → 退出 2。"""
    if args.plan and not args.compare:
        fail("--plan 要与 --compare 一起用")
    if not args.compare:
        return None, None
    prev = read_json(args.compare, "之前的体检")
    if not isinstance(prev, dict) or not isinstance(prev.get("items"), list):
        fail("之前的体检 %s 不是含 items 数组的体检 JSON" % args.compare)
    if not args.plan:
        return prev, None
    plan = read_json(args.plan, "整改稿")
    if not isinstance(plan, dict) or not isinstance(plan.get("items"), dict):
        fail("整改稿 %s 不是含 items 对象的 JSON" % args.plan)
    return prev, plan["items"]


def audit_compare(prev, plan_items, now):
    was = {it.get("id") for it in prev["items"] if isinstance(it, dict) and it.get("level") == "violation"}
    targets = {k for k, v in (plan_items or {}).items()
               if k in was and (v if isinstance(v, dict) else {}).get("action") != "keep"}
    return {"before": {"at": prev.get("at"), "head": prev.get("head")}, "resolved": sorted(was - now),
            "remaining": sorted(was & now), "new": sorted(now - was), "targets": len(targets),
            "targets_remaining": sorted(targets & now)}


def _secs(v):
    return "-" if v is None else "%gs" % v


def print_audit(rep, shown, code):
    counts, src, led = rep["counts"], rep["source"], rep["source"]["ledger"]
    print("测试体检：不合规 %d 条 · 提示 %d 条 · 未判 %d 项" % (counts["violation"], counts["advice"], counts["unjudged"]))
    if led is None and not src["probes"]:
        print("测量来源：没有测量")
    else:
        where = ("账本 %s · %s · %s · %s · %s" % (led["change"], led["phase"], (led["commit"] or "-")[:10], led["at"],
                                                 led["mode"]) if led else "无账本")
        print("测量来源：%s；探针 %d 份；用例 %d 条；丢弃 %d 条" % (where, src["probes"], src["cases"], src["dropped"]))
    for cat in dict.fromkeys(it["category"] for it in shown):  # 沿用 audit_sort_key 的次序
        rows = [it for it in shown if it["category"] == cat]
        n, r = counts["by_category"][cat], AUDIT_RULES[cat]
        more = "，列出 %d 条" % len(rows) if len(rows) < n else ""
        print("\n== %s %s（%d 条%s · %s）" % (cat, r["title"], n, more, r["rule"] or LEVEL_TEXT[r["level"]]))
        for it in rows:
            print("[%s] %s  %s" % (LEVEL_TEXT[it["level"]], it["id"], it["text"]))
    if rep["scopes"]:
        print()
    for sc, s in rep["scopes"].items():
        print("范围 %s（%s）：用例 %d 条 · 合计 %s · 单条上限 %s · 总量预算 %s · p50 %s / p95 %s / 最慢 %s"
              % (sc, "单元层" if s["kind"] == "unit" else "区域", s["cases"], _secs(s["sec"]), _secs(s["case_sec"]),
                 _secs(s["total_sec"]), _secs(s["p50"]), _secs(s["p95"]), _secs(s["max"])))
    cmp_ = rep.get("compare")
    if cmp_ is None:
        print("结论：%s" % {0: "合规", 1: "不合规", 3: "判不全"}[code])
        return
    print("前后对比：已解决 %d 条 · 仍在 %d 条 · 新增 %d 条；本轮目标 %d 条 · 未解决 %d 条（之前 %s · %s）"
          % (len(cmp_["resolved"]), len(cmp_["remaining"]), len(cmp_["new"]), cmp_["targets"],
             len(cmp_["targets_remaining"]), cmp_["before"]["at"], (cmp_["before"]["head"] or "-")[:10]))
    for i in cmp_["new"]:
        print("  新增：%s" % i)
    for i in cmp_["targets_remaining"]:
        print("  未解决的目标：%s" % i)
    print("结论：%s" % {0: "整改达标", 1: "整改未达标", 3: "未能确认（有未判项）"}[code])


def emit_audit(args, rep, prev=None, plan_items=None):
    """筛选（范围 → 类别）→ 计数与结论 → 对比 → 截断 → 输出；返回退出码。"""
    items = rep["items"]
    if args.scope:  # 没有分层文件与全局未判对每个范围都成立，不受 --scope 影响
        items = [it for it in items if it["scope"] in args.scope or it["id"] in AUDIT_GLOBAL_IDS]
        rep["scopes"] = {sc: v for sc, v in rep["scopes"].items() if sc in args.scope}
    if args.category:  # 未判与全局条目不受 --category 影响：没量到不能因筛选变成合规
        items = [it for it in items
                 if it["category"] in args.category or it["level"] == "unjudged" or it["id"] in AUDIT_GLOBAL_IDS]
    counts = {lv: sum(1 for it in items if it["level"] == lv) for lv in LEVEL_TEXT}
    by_cat = {}
    for it in items:
        by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
    counts["by_category"] = by_cat
    rep["counts"] = counts
    rep["verdict"] = "violations" if counts["violation"] else ("unjudged" if counts["unjudged"] else "compliant")
    code = {"violations": 1, "unjudged": 3, "compliant": 0}[rep["verdict"]]
    if prev is not None:
        cmp_ = rep["compare"] = audit_compare(prev, plan_items, {it["id"] for it in items if it["level"] == "violation"})
        code = 1 if cmp_["new"] or cmp_["targets_remaining"] else (3 if counts["unjudged"] else 0)
    if args.top is not None:  # items 已按 audit_sort_key 排好：每类留前 N 条
        seen, shown = {}, []
        for it in items:
            seen[it["category"]] = seen.get(it["category"], 0) + 1
            if seen[it["category"]] <= args.top:
                shown.append(it)
        items = shown
    rep["items"] = items
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print_audit(rep, items, code)
    return code


def cmd_audit(args):
    top = sg.toplevel()
    prev, plan_items = load_compare(args)
    led, change, phase = pick_ledger(args, top)
    probes = load_probes(args)
    meta = None if led is None else dict({"change": change, "phase": phase},
                                         **{k: led.get(k) for k in ("commit", "at", "mode", "complete", "id_form")})
    rep = {"v": 1, "at": sg.now_iso(), "head": _head(top), "form": "none", "verdict": None,
           "source": {"ledger": meta, "probes": len(probes), "cases": 0, "dropped": 0},
           "counts": None, "items": [], "scopes": {}, "allow": None}
    path = tiers_path(args)
    if not os.path.isfile(path):
        rep["items"] = [audit_item("no-tiers", "", "没有测试分层文件 %s：先跑 /test-tiers 划分测试层" % path)]
        return emit_audit(args, rep, prev, plan_items)
    _, tiers = load_tiers(args)
    rep["form"] = "parts" if sg.tiers_is_parts(tiers) else "shorthand"
    rep["items"], rep["scopes"], rep["allow"], rep["source"]["cases"], rep["source"]["dropped"] = \
        audit_report(top, tiers, led, probes)
    return emit_audit(args, rep, prev, plan_items)


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
    p.add_argument("--limit-sec", type=float)
    p.add_argument("--expires")
    p.add_argument("--openspec-root")
    p.add_argument("--session")
    p = sub.add_parser("render")
    p.add_argument("--probe", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("audit")
    p.add_argument("--openspec-root")
    p.add_argument("--change-dir")
    p.add_argument("--ledger")
    p.add_argument("--no-ledger", action="store_true")
    p.add_argument("--probe", action="append")
    p.add_argument("--scope", action="append")
    p.add_argument("--category", action="append")
    p.add_argument("--top", type=int)
    p.add_argument("--json", action="store_true")
    p.add_argument("--out")
    p.add_argument("--compare")
    p.add_argument("--plan")
    args = ap.parse_args(argv)
    handler = {"run": cmd_run, "probe": cmd_probe, "check": cmd_check, "canary": cmd_canary,
               "allow-slow": cmd_allow_slow, "render": cmd_render, "audit": cmd_audit}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
