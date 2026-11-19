#!/usr/bin/env python3
# test-audit · /test-audit 的整改稿脚本（零 token）
#
# 子命令：
#   render  --audit 体检JSON --plan 整改稿JSON --out HTML [--openspec-root DIR]
#           逐条校验整改稿（条目在不在体检结果里、去向是否适用、keep 理由、move / split 落点是否恰落一层且方向对、
#           budget 是否真给了 case_sec、稿里的 tiers 是否合法），按去向归轨道（ACTIONS），写单文件审批页
#           （内联样式、每条一个勾选框、批注框、导出 Markdown / 复制）；stdout 一行 {tracks, problems, out}
#   verify  --plan 整改稿JSON --base COMMIT [--openspec-root DIR] [--json]
#           整改护栏：核对工作树相对 --base 的改动守住改动范围、用例与断言不变、分层文件改动与稿一致
#
# 退出码：0 无问题 / 通过；1 有问题 / 有违反；2 输入读不了。
#
# 复用 slice-gate.py 的分层判定（按路径加载），只读不改它。兼容 Python 3.8+，只用标准库。
import argparse
import html
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# 去向 → 轨道（design D6）；S7 的对账测试拿它对文档
ACTIONS = {"move": "mechanical", "split": "mechanical", "retier": "mechanical", "budget": "mechanical",
           "drop-allow": "mechanical", "allow": "human", "speedup": "change", "purify": "change",
           "delete": "change", "keep": "keep"}
TRACK_TITLES = (("mechanical", "命令内执行"), ("human", "交人放行"), ("change", "转 change"), ("keep", "保留"),
                ("unplanned", "未安排"))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sg = _load("slice-gate")


def fail(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def read_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        fail("%s %s 读不了：%s" % (what, path, e))


# ---------------------------------------------------------------- render

PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>测试整改稿审批</title>
<style>
body{font-family:-apple-system,"PingFang SC",sans-serif;margin:2em;color:#222}
table{border-collapse:collapse;width:100%%;margin:1em 0}th,td{border:1px solid #ccc;padding:4px 8px;font-size:13px;text-align:left}
th{background:#f3f3f3}.bad{color:#b00020}.ok{color:#1b7f3b}textarea{width:100%%;height:8em}
button{margin-right:.5em;padding:.4em 1em}pre#summary{display:none}
</style></head><body>
<h1>测试整改稿审批</h1>
<h2>问题清单</h2>
%(problems)s
<h2>轨道汇总</h2>
<p id="tracks">%(tracks)s</p>
%(support)s
<h2>整改明细</h2>
<table><tr><th>批准</th><th>条目</th><th>类别</th><th>现状（秒 / 线）</th><th>去向</th><th>目标</th><th>轨道</th><th>备注</th></tr>%(rows)s</table>
<h2>批注</h2>
<textarea id="note" placeholder="写下对整改稿的意见"></textarea>
<p><button onclick="exportMd()">导出 Markdown</button><button onclick="copyMd()">复制</button></p>
<pre id="summary">%(summary)s</pre>
<script>
function md(){
  var out=document.getElementById("summary").textContent+"\\n## 逐条\\n\\n";
  document.querySelectorAll("tr.item").forEach(function(tr){
    out+="- ["+(tr.querySelector("input").checked?"x":" ")+"] "+tr.getAttribute("data-line")+"\\n";});
  return out+"\\n## 批注\\n\\n"+document.getElementById("note").value+"\\n";}
function exportMd(){var a=document.createElement("a");a.href=URL.createObjectURL(new Blob([md()],{type:"text/markdown"}));a.download="test-audit-plan.md";a.click();}
function copyMd(){navigator.clipboard.writeText(md());}
</script>
</body></html>
"""


def _num(v):
    return "-" if v is None else "%gs" % v


def _target_tiers(plan, args, problems):
    """→ (目标分层文件 | None, 稿里是否给了 tiers)。稿里有 tiers → 落临时文件按 slice-gate 校验；没有 → 现行分层文件。"""
    if "tiers" in plan:
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(plan["tiers"], fh, ensure_ascii=False)
            tiers, errors = sg._load_tiers_file(path)
        finally:
            os.unlink(path)
        if tiers is None:
            problems.append("稿里的分层文件不合法：%s" % "；".join(errors))
        return tiers, True
    path = os.path.join(args.openspec_root or os.path.join(sg.toplevel(), "openspec"), sg.TIER_FILE)
    tiers, errors = sg._load_tiers_file(path)
    if errors:
        problems.append("现行分层文件 %s 不合法：%s" % (path, "；".join(errors)))
    return tiers, False


def _check_item(iid, rec, entry, tiers, has_tiers, top):
    """单条整改 → (问题文本列表, 去向是否合法)。"""
    if not isinstance(rec, dict):
        return ["%s：整改条目须是对象（action / dest / note）" % iid], False
    if entry is None:
        return ["%s：稿里的条目不在体检结果里" % iid], False
    action, cat = rec.get("action"), entry.get("category")
    fix = list(entry.get("fix") or [])
    if action not in ACTIONS or (action != "keep" and action not in fix):
        return ["%s：去向 %s 不适用于 %s（可选：%s）" % (iid, action, cat, "、".join(fix + ["keep"]))], False
    out = []
    note, dest = rec.get("note"), rec.get("dest")
    if action == "keep" and not (isinstance(note, str) and note.strip()):
        out.append("%s：保留须写理由" % iid)
    if action in ("move", "split"):
        if not (isinstance(dest, str) and dest.strip()):
            out.append("%s：去向 %s 缺目标" % (iid, action))
        else:
            layers = sg.tiers_matching(dest, tiers, top) if tiers is not None else []
            if not layers:
                out.append("%s：落点 %s 未归层" % (iid, dest))
            elif len(layers) > 1:
                out.append("%s：落点 %s 匹配多层（%s）" % (iid, dest, "、".join(layers)))
            elif cat in ("unit-slow", "unit-impure") and layers == ["unit"]:
                out.append("%s：落点 %s 仍在单元层" % (iid, dest))
            elif cat == "pure-in-region" and layers != ["unit"]:
                out.append("%s：落点 %s 不在单元层" % (iid, dest))
    if action == "budget":
        if not has_tiers:
            out.append("%s：去向 budget 须在稿里给出 tiers" % iid)
        elif cat == "no-case-limit" and tiers is not None:
            scope = entry.get("scope") or iid.split(":", 1)[1]
            if (sg.tier_budgets(tiers).get(scope) or {}).get("case_sec") is None:
                out.append("%s：区域 %s 在稿的 tiers 里仍没有 case_sec" % (iid, scope))
    return out, True


def cmd_render(args):
    audit = read_json(args.audit, "体检结果")
    plan = read_json(args.plan, "整改稿")
    if not isinstance(audit, dict) or not isinstance(audit.get("items"), list):
        fail("体检结果须是含 items 数组的对象")
    if not isinstance(plan, dict) or not isinstance(plan.get("items", {}), dict):
        fail("整改稿须是对象（items 为 条目 id → 整改）")
    entries = {it["id"]: it for it in audit["items"] if isinstance(it, dict) and isinstance(it.get("id"), str)}
    planned = plan.get("items", {})
    problems = []
    tiers, has_tiers = _target_tiers(plan, args, problems)
    top = sg.toplevel() if sg.tiers_is_parts(tiers) else None
    tracks = {k: 0 for k, _ in TRACK_TITLES}
    rows = []
    for iid in sorted(planned):
        rec, entry = planned[iid], entries.get(iid)
        found, legal = _check_item(iid, rec, entry, tiers, has_tiers, top)
        problems.extend(found)
        rec = rec if isinstance(rec, dict) else {}
        action = rec.get("action")
        track = ACTIONS[action] if legal else "-"
        if legal:
            tracks[track] += 1
        entry = entry or {}
        rows.append((iid, entry.get("category") or "-", "%s / %s" % (_num(entry.get("sec")), _num(entry.get("line"))),
                     str(action) if action is not None else "-", str(rec.get("dest") or "-"), track,
                     str(rec.get("note") or "")))
    tracks["unplanned"] = sum(1 for iid, e in entries.items() if e.get("level") == "violation" and iid not in planned)
    track_line = " · ".join("%s %d 条" % (title, tracks[k]) for k, title in TRACK_TITLES)
    support = [str(s) for s in plan.get("support") or []]
    esc = html.escape
    summary = ["# 测试整改稿", "", "## 问题", ""] + (["- %s" % p for p in problems] or ["无问题"])
    summary += ["", "## 轨道", "", track_line]
    if support:
        summary += ["", "## 随迁文件", ""] + ["- %s" % s for s in support]
    page = PAGE % {
        "problems": ("<ul class=\"bad\">%s</ul>" % "".join("<li>%s</li>" % esc(p) for p in problems))
                    if problems else "<p class=\"ok\">无问题</p>",
        "tracks": esc(track_line),
        "support": ("<h2>随迁文件</h2><ul>%s</ul>" % "".join("<li>%s</li>" % esc(s) for s in support))
                   if support else "",
        "rows": "".join("<tr class=\"item\" data-line=\"%s\"><td><input type=\"checkbox\" checked></td>%s</tr>"
                        % (esc("%s → %s（%s）%s" % (r[0], r[3], r[5], " 目标 " + r[4] if r[4] != "-" else "")),
                           "".join("<td>%s</td>" % esc(c) for c in r)) for r in rows),
        "summary": esc("\n".join(summary) + "\n"),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(page)
    for p in problems:
        sys.stderr.write(p + "\n")
    print(json.dumps({"tracks": tracks, "problems": len(problems), "out": args.out}, ensure_ascii=False))
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="test-audit.py")
    sub = ap.add_subparsers(dest="command")
    sub.required = True
    p = sub.add_parser("render")
    p.add_argument("--audit", required=True)
    p.add_argument("--plan", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--openspec-root")
    args = ap.parse_args(argv)
    handler = {"render": cmd_render}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
