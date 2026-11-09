#!/usr/bin/env python3
# spec_html · 把 OpenSpec change 工件确定性渲染为单文件 HTML 审批面板（零 token，无 LLM 参与）
#
# CLI:
#   spec_html.py --change-dir DIR [--template PATH] [--out PATH] [--now ISO]
#
# 输入：<DIR>/proposal.md · specs/*/spec.md · design.md · tasks.md · slices.json ·
#       timeline.md · gate-report.md（均可缺）；<repo-root>/openspec/adr/*.md（可缺）
# 输出：--out（缺省 <DIR>/spec.html），用模板 <hooks 同级>/../skills/spec-html-render/templates/spec.html.tmpl
#       的 <!-- block:NAME -->…<!-- /block:NAME --> 占位块整段替换渲染。
# 幂等：同输入 + 同 --now（或 SPEC_HTML_NOW）两次渲染字节级一致。
# 兼容 Python 3.8+，只用标准库。
import argparse
import ast
import fnmatch
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.normpath(
    os.path.join(HOOKS_DIR, "..", "skills", "spec-html-render", "templates", "spec.html.tmpl")
)

MARK_RE = re.compile(r"xfail|skip", re.I)
JS_TEST_RE = re.compile(r"^\s*(?:test|it)\s*\(\s*['\"`](.+?)['\"`]")
DELTA_RE = re.compile(r"^(ADDED|MODIFIED|REMOVED)\s+Requirements$", re.I)
STEP_RE = re.compile(r"^\s*[-*]\s+\*\*(GIVEN|WHEN|THEN|AND|BUT)\*\*\s+(.*)$", re.I)
CAP_ITEM_RE = re.compile(r"^`?([^`:]+)`?\s*:\s*(.+)$")
TASK_ITEM_RE = re.compile(r"^\s*-\s+\[( |x|X)\]\s+(.*)$")
MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.S)
DECISION_RISK_RE = re.compile(r"decision|risk|trade", re.I)
ADR_STATUS_RE = re.compile(r"(?m)^Status:\s*(.+)$")
ADR_SUPERSEDES_RE = re.compile(r"(?m)^Supersedes:\s*(.+)$")
ADR_TITLE_RE = re.compile(r"(?m)^#\s+(.+)$")

BLOCK_NAMES = (
    "title", "change-name", "meta-chips", "why", "what", "capabilities",
    "specs", "design", "diagrams", "adrs", "tasks", "flight", "footer",
)


# ---------------------------------------------------------------- 基础

def now_iso(now_arg):
    if now_arg:
        return now_arg
    env = os.environ.get("SPEC_HTML_NOW")
    if env:
        return env
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path):
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def esc(s):
    return html.escape(s or "", quote=True)


def inline_md(text):
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def split_sections(text, level="##"):
    """按 markdown 标题切段：[(heading, body), ...]；标题前若有非空内容，首项 heading 为 ''。"""
    pattern = re.compile(r"(?m)^%s\s+(.+?)\s*$" % re.escape(level))
    matches = list(pattern.finditer(text))
    if not matches:
        return [("", text)]
    parts = []
    if matches[0].start() > 0:
        pre = text[:matches[0].start()].strip("\n")
        if pre.strip():
            parts.append(("", pre))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append((m.group(1).strip(), text[start:end]))
    return parts


def paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def list_items(text):
    items = []
    for line in text.splitlines():
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            items.append(m.group(1).strip())
    return items


def substitute_block(html_text, name, content):
    if content is None:
        return html_text
    pattern = re.compile(r"<!-- block:%s -->.*?<!-- /block:%s -->" % (re.escape(name), re.escape(name)), re.S)
    replacement = "<!-- block:%s -->\n%s\n<!-- /block:%s -->" % (name, content, name)
    return pattern.sub(lambda _m: replacement, html_text, count=1)


# ---------------------------------------------------------------- proposal.md：why / what / capabilities

def render_why(proposal_text):
    if not proposal_text:
        return None
    sections = dict(split_sections(proposal_text))
    why = sections.get("Why")
    paras = paragraphs(why) if why is not None else []
    if not paras:
        return None
    out = ['<p class="why-statement">%s</p>' % inline_md(paras[0])]
    out += ['<p class="why-body">%s</p>' % inline_md(p) for p in paras[1:]]
    return "".join(out)


def render_what(proposal_text):
    if not proposal_text:
        return None
    sections = dict(split_sections(proposal_text))
    changes, impact = sections.get("What Changes"), sections.get("Impact")
    if changes is None and impact is None:
        return None
    out = []
    if changes is not None:
        items = list_items(changes)
        if items:
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline_md(i) for i in items))
    if impact is not None:
        items = list_items(impact)
        if items:
            out.append('<div class="impact">%s</div>' % "".join('<span class="tag">%s</span>' % inline_md(i) for i in items))
    return "".join(out) if out else None


def render_capabilities(proposal_text):
    if not proposal_text:
        return None
    sections = dict(split_sections(proposal_text))
    cap_section = sections.get("Capabilities")
    if cap_section is None:
        return None
    sub = dict(split_sections(cap_section, level="###"))
    cards = []
    for heading, kind in (("New Capabilities", "new"), ("Modified Capabilities", "modified")):
        body = sub.get(heading)
        if not body:
            continue
        for item in list_items(body):
            m = CAP_ITEM_RE.match(item)
            name, desc = (m.group(1).strip(), m.group(2).strip()) if m else (item, "")
            cards.append(
                '<div class="cap-card" data-kind="%s"><span class="cap-kind">%s</span><h4>%s</h4><p>%s</p></div>'
                % (kind, kind.capitalize(), inline_md(name), inline_md(desc))
            )
    if not cards:
        return None
    return '<div class="cap-grid">%s</div>' % "".join(cards)


# ---------------------------------------------------------------- specs/*/spec.md

def render_scenario(name, body):
    steps = []
    for line in body.splitlines():
        m = STEP_RE.match(line)
        if m:
            kw, txt = m.group(1).upper(), m.group(2).strip()
            steps.append('<li><span class="step-key" data-kw="%s">%s</span><span>%s</span></li>' % (kw, kw, inline_md(txt)))
    steps_html = "<ul class=\"steps\">%s</ul>" % "".join(steps) if steps else ""
    return '<div class="scenario"><p class="scenario-name">Scenario: %s</p>%s</div>' % (inline_md(name), steps_html)


def render_requirement(heading, body):
    name = re.sub(r"(?i)^Requirement:\s*", "", heading).strip()
    scen_sections = split_sections(body, level="####")
    desc = scen_sections[0][1] if scen_sections and scen_sections[0][0] == "" else ""
    desc_html = "".join("<p>%s</p>" % inline_md(p) for p in paragraphs(desc))
    scenarios_html = "".join(
        render_scenario(re.sub(r"(?i)^Scenario:\s*", "", h).strip(), b)
        for h, b in scen_sections if h.lower().startswith("scenario:")
    )
    return '<div class="requirement"><p class="requirement-name">Requirement: %s</p>%s%s</div>' % (
        inline_md(name), desc_html, scenarios_html
    )


def render_specs(change_dir):
    specs_dir = os.path.join(change_dir, "specs")
    if not os.path.isdir(specs_dir):
        return None
    cards = []
    for cap in sorted(os.listdir(specs_dir)):
        text = read_text(os.path.join(specs_dir, cap, "spec.md"))
        if not text:
            continue
        for heading, body in split_sections(text, level="##"):
            m = DELTA_RE.match(heading)
            if not m:
                continue
            op = m.group(1).upper()
            reqs = [
                render_requirement(h, b)
                for h, b in split_sections(body, level="###")
                if h.lower().startswith("requirement:")
            ]
            cards.append(
                '<div class="spec-card"><h3>%s <span class="delta" data-op="%s">%s</span></h3>%s</div>'
                % (esc(cap), op.lower(), op, "".join(reqs))
            )
    if not cards:
        return None
    return "".join(cards)


# ---------------------------------------------------------------- design.md / diagrams

def extract_diagrams(design_text):
    if not design_text:
        return []
    diagrams, last_end = [], 0
    for m in MERMAID_RE.finditer(design_text):
        pre = design_text[last_end:m.start()]
        caption = ""
        for para in reversed(paragraphs(pre)):
            caption = para.splitlines()[-1].strip()
            break
        diagrams.append((caption, m.group(1).strip()))
        last_end = m.end()
    return diagrams


def render_diagrams(design_text):
    diagrams = extract_diagrams(design_text)
    if not diagrams:
        return None
    out = []
    for caption, src in diagrams:
        out.append(
            '<div class="diagram-frame"><div class="mermaid">%s</div>'
            '<pre class="diagram-fallback">%s</pre><div class="caption">%s</div></div>'
            % (esc(src), esc(src), inline_md(caption))
        )
    return "".join(out)


def strip_mermaid(text):
    return MERMAID_RE.sub("", text)


def render_generic_md(text):
    out, buf_list = [], []

    def flush_list():
        if buf_list:
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % inline_md(i) for i in buf_list))
            del buf_list[:]

    for para in paragraphs(text):
        lines = para.splitlines()
        if lines and all(re.match(r"^\s*[-*]\s+", l) for l in lines):
            buf_list.extend(re.sub(r"^\s*[-*]\s+", "", l).strip() for l in lines)
            continue
        flush_list()
        out.append("<p>%s</p>" % inline_md(" ".join(l.strip() for l in lines)))
    flush_list()
    return "".join(out)


def render_design(design_text):
    if not design_text:
        return None
    blocks = []
    for heading, body in split_sections(design_text, level="##"):
        if not heading:
            continue
        body_wo_mermaid = strip_mermaid(body)
        if DECISION_RISK_RE.search(heading):
            details = []
            for item in list_items(body_wo_mermaid):
                if "：" in item:
                    summary, rest = item.split("：", 1)
                else:
                    summary, rest = item, ""
                details.append(
                    "<details><summary>%s</summary>%s</details>"
                    % (inline_md(summary.strip()), ("<p>%s</p>" % inline_md(rest.strip())) if rest.strip() else "")
                )
            content = "".join(details) if details else render_generic_md(body_wo_mermaid)
        else:
            content = render_generic_md(body_wo_mermaid)
        blocks.append('<div class="design-block"><h3>%s</h3>%s</div>' % (esc(heading), content))
    return "".join(blocks) if blocks else None


# ---------------------------------------------------------------- adrs

def project_root(change_dir):
    d = os.path.abspath(change_dir)
    return os.path.dirname(os.path.dirname(os.path.dirname(d)))


def scan_adrs(change_dir):
    adr_dir = os.path.join(project_root(change_dir), "openspec", "adr")
    if not os.path.isdir(adr_dir):
        return None
    entries, superseded = [], set()
    for fname in sorted(os.listdir(adr_dir)):
        if not fname.endswith(".md"):
            continue
        text = read_text(os.path.join(adr_dir, fname)) or ""
        status_m = ADR_STATUS_RE.search(text)
        status = status_m.group(1).strip() if status_m else "unknown"
        sup_m = ADR_SUPERSEDES_RE.search(text)
        if sup_m:
            superseded.update(re.findall(r"\d{4}", sup_m.group(1)))
        title_m = ADR_TITLE_RE.search(text)
        title = title_m.group(1).strip() if title_m else fname
        num_m = re.match(r"(DRAFT|\d{4})", fname)
        num = num_m.group(1) if num_m else fname
        entries.append({"num": num, "title": title, "status": status, "fname": fname})
    if not entries:
        return None

    def li(e):
        return (
            '<li><span class="adr-num">%s</span><a href="../../adr/%s">%s</a>'
            '<span class="adr-status">%s</span></li>'
        ) % (esc(e["num"]), esc(e["fname"]), inline_md(e["title"]), esc(e["status"]))

    in_force = [e for e in entries if e["num"] != "DRAFT" and e["num"] not in superseded and e["status"].lower().startswith("accept")]
    drafts = [e for e in entries if e["num"] == "DRAFT"]
    parts = []
    if in_force:
        parts.append("<ul>%s</ul>" % "".join(li(e) for e in in_force))
    if drafts:
        parts.append('<h3>待定号（本次新增）</h3><ul>%s</ul>' % "".join(li(e) for e in drafts))
    return "".join(parts) if parts else None


# ---------------------------------------------------------------- tasks.md

def render_tasks(tasks_text):
    if not tasks_text:
        return None
    groups, total = [], 0
    for heading, body in split_sections(tasks_text, level="##"):
        items = []
        for line in body.splitlines():
            m = TASK_ITEM_RE.match(line)
            if not m:
                continue
            checked = m.group(1).lower() == "x"
            total += 1
            box = 'type="checkbox" disabled checked>' if checked else 'type="checkbox" disabled>'
            items.append(
                '<li data-done="%s"><input %s<span>%s</span></li>'
                % ("true" if checked else "false", box, inline_md(m.group(2).strip()))
            )
        if not items:
            continue
        groups.append(
            '<details class="task-group" open><summary>%s</summary><ul>%s</ul></details>'
            % (esc(heading or "任务"), "".join(items))
        )
    if not groups:
        return None
    return "".join(groups), total


# ---------------------------------------------------------------- flight（slices.json / timeline.md / gate-report.md）

def compute_waves(slices):
    ids = [s["id"] for s in slices]
    deps = {s["id"]: list(s.get("deps") or []) for s in slices}
    placed, waves = set(), []
    while len(placed) < len(ids):
        wave = [i for i in ids if i not in placed and all(d in placed for d in deps[i])]
        if not wave:
            waves.append([i for i in ids if i not in placed])
            break
        waves.append(wave)
        placed.update(wave)
    return waves


def find_def_line(lines, func):
    py_re = re.compile(r"^\s*(?:async\s+)?def\s+%s\s*\(" % re.escape(func))
    for i, line in enumerate(lines):
        if py_re.match(line):
            return i
        m = JS_TEST_RE.match(line)
        if m and m.group(1) == func:
            return i
    return None


def decorator_source(source, func):
    """按 AST 取函数 func 完整的 decorator_list 源文本（支持跨行装饰器调用）；解析失败返回 None。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            segs = [ast.get_source_segment(source, d) for d in node.decorator_list]
            return "\n".join(s for s in segs if s)
    return None


def scenario_flight_status(root, rel, func):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        alt = os.path.join(os.getcwd(), rel)
        if os.path.isfile(alt):
            path = alt
    if not os.path.isfile(path):
        return "missing"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()
    lines = source.splitlines()
    idx = find_def_line(lines, func)
    if idx is None:
        return "missing"
    if rel.endswith(".py"):
        dec_src = decorator_source(source, func)
        if dec_src is not None:
            return "pending" if MARK_RE.search(dec_src) else "unlocked"
    k, marked = idx - 1, False
    while k >= 0 and lines[k].strip().startswith("@"):
        if MARK_RE.search(lines[k]):
            marked = True
        k -= 1
    return "pending" if marked else "unlocked"


def gate_report_passed_slices(change_dir):
    text = read_text(os.path.join(change_dir, "gate-report.md"))
    passed = set()
    if not text:
        return passed
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 3 or cols[0] in ("时间", "---") or set(cols[0]) <= {"-"}:
            continue
        if cols[2] == "ok":
            passed.add(cols[1])
    return passed


def load_timeline_rows(change_dir):
    text = read_text(os.path.join(change_dir, "timeline.md"))
    rows = []
    if not text:
        return rows
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("<!--"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip() if len(parts) > 2 else ""))
    return rows


def scope_provider(gate, change_dir):
    """与 slice-gate D1 同口径的只读解析：gate.scope（cmd）> <openspec 根>/gate-scope.json（cmd | builtin）> 未声明。
    返回 (kind: "cmd" | "builtin" | None, cmd, source)；读不了 / 形状不对当作未声明（校验归 lint）。"""
    cmd = gate.get("scope")
    if isinstance(cmd, str) and cmd.strip():
        return "cmd", cmd, "计划 gate.scope"
    openspec_root = os.path.dirname(os.path.dirname(os.path.abspath(change_dir)))
    try:
        decl = json.loads(read_text(os.path.join(openspec_root, "gate-scope.json")) or "null")
    except ValueError:
        decl = None
    if not isinstance(decl, dict) or len(decl) != 1:
        return None, None, None
    if decl.get("builtin") is True:
        return "builtin", None, "仓库声明 gate-scope.json"
    if isinstance(decl.get("cmd"), str) and decl["cmd"].strip():
        return "cmd", decl["cmd"], "仓库声明 gate-scope.json"
    return None, None, None


def establishes_scope_decl(gate_owns, change_dir):
    """任一 owns glob 匹配 <openspec 根>/gate-scope.json 的仓库相对路径（git 顶层取不到时相对 openspec 根的上一级）。"""
    decl = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(change_dir))), "gate-scope.json")
    top = project_root(change_dir)
    try:
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=os.path.dirname(decl),
                           capture_output=True, text=True, timeout=10)
        if p.returncode == 0 and p.stdout.strip():
            top = p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    rel = os.path.relpath(os.path.realpath(decl), os.path.realpath(top)).replace(os.sep, "/")
    return any(isinstance(g, str) and (rel == g or fnmatch.fnmatchcase(rel, g)
                                       or (g.endswith("/**") and rel.startswith(g[:-3] + "/")))
               for g in gate_owns)


def render_scope(gate, change_dir, owns=()):
    """选测范围小节（design D13）：恒输出；只读文件、不运行选测命令。owns：各片 owns（判本 change 是否建立仓库声明）。"""
    gate = gate if isinstance(gate, dict) else {}
    kind, cmd, source = scope_provider(gate, change_dir)
    parts = ['<h3>选测范围</h3>']
    if kind == "cmd":
        parts.append('<p>选测命令（%s）：<code>%s</code></p>' % (esc(source), esc(cmd)))
    elif kind == "builtin":
        parts.append('<p>模板内建（builtin）（%s）</p>' % esc(source))
    else:
        note = "：本 change 建立仓库选测声明" if establishes_scope_decl(owns, change_dir) else ""
        parts.append('<p class="placeholder">未声明选测范围%s</p>' % esc(note))
    reasons = gate.get("scope_full_reason")
    if isinstance(reasons, dict) and reasons:
        rows = "".join('<tr><td><code>%s</code></td><td>%s</td></tr>' % (esc(k), esc(v))
                       for k, v in reasons.items())
        parts.append('<table class="flight-table"><thead><tr><th>触发项</th><th>理由</th></tr></thead>'
                     '<tbody>%s</tbody></table>' % rows)
    return "".join(parts)


FORECAST_TIMEOUT = 30  # 秒


def render_forecast(change_dir):
    """测试成本预告小节（design D14）：子进程取 flight-doctor.py forecast --json；失败 / 超时 / 非 JSON → 占位（铁律 10）。"""
    head = '<h3>测试成本预告</h3>'
    cmd = [sys.executable, os.path.join(HOOKS_DIR, "flight-doctor.py"), "forecast", "--change-dir", change_dir, "--json"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=FORECAST_TIMEOUT)
        fc = json.loads(p.stdout)
        b, f = fc["baseline"], fc["final"]
        checks = fc.get("checks") or []
    except subprocess.TimeoutExpired:
        return head + '<p class="placeholder">预告不可用：超时（%d 秒）</p>' % FORECAST_TIMEOUT
    except (OSError, ValueError, KeyError, TypeError) as e:
        return head + '<p class="placeholder">预告不可用：%s</p>' % esc("%s: %s" % (type(e).__name__, e))

    def row(label, part, extra=""):
        sec = part.get("sec")
        return '<tr><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td></tr>' % (
            label, esc(part.get("mode")), esc(part.get("why") or "-"), esc("-" if sec is None else "%s%s" % (sec, extra)))

    return head + (
        '<table class="flight-table"><thead><tr><th>阶段</th><th>模式</th><th>原因</th><th>秒数</th></tr></thead>'
        '<tbody>%s%s</tbody></table><p>检查 %d 项%s（只预告，不阻断）</p>'
        % (row("baseline", b), row("final", f, "（约）"), len(checks),
           "：" + esc(", ".join(str(c) for c in checks)) if checks else ""))


def render_flight(change_dir):
    text = read_text(os.path.join(change_dir, "slices.json"))
    if not text:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    slices = data.get("slices") or []
    if not slices:
        return None
    waves = compute_waves(slices)
    wave_of = {sid: wi for wi, wave in enumerate(waves, start=1) for sid in wave}
    root = project_root(change_dir)
    scenario_tests = data.get("scenario_tests") or {}
    passed_slices = gate_report_passed_slices(change_dir)

    slice_rows, scenario_rows = [], []
    for s in slices:
        sid = s.get("id", "?")
        owns_html = "<br>".join(esc(o) for o in (s.get("owns") or []))
        slice_rows.append(
            '<tr><td class="mono">%s</td><td>%s</td><td>wave %d</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>'
            % (esc(sid), inline_md(s.get("title", "")), wave_of.get(sid, 0),
               esc(", ".join(s.get("deps") or []) or "-"), owns_html, esc(s.get("verify", "")))
        )
        for scen_id in s.get("scenarios") or []:
            target = scenario_tests.get(scen_id, "")
            if target and "::" in target:
                rel, func = target.split("::", 1)
                status = scenario_flight_status(root, rel, func)
                if status == "unlocked" and sid in passed_slices:
                    status = "passed"
            else:
                status = "missing"
            scenario_rows.append(
                '<tr><td>%s</td><td><code>%s</code></td><td><span class="chip" data-state="%s">%s</span></td></tr>'
                % (esc(scen_id), esc(target or "-"), status, status)
            )

    timeline_rows = load_timeline_rows(change_dir)
    if timeline_rows:
        rows = "".join(
            '<tr><td class="mono">%s</td><td>%s</td><td>%s</td></tr>' % (esc(ts), esc(ev), esc(note))
            for ts, ev, note in timeline_rows
        )
        timeline_html = (
            '<h3>飞行记录</h3><table class="flight-table"><thead><tr><th>时间</th><th>事件</th><th>备注</th></tr></thead>'
            '<tbody>%s</tbody></table>' % rows
        )
    else:
        timeline_html = '<h3>飞行记录</h3><p class="placeholder">尚无飞行记录事件。</p>'

    return (
        '<h3>切片</h3><table class="flight-table"><thead><tr><th>切片</th><th>标题</th><th>wave</th>'
        '<th>deps</th><th>owns</th><th>verify</th></tr></thead><tbody>%s</tbody></table>%s'
        '<h3>Scenario 状态</h3><table class="flight-table"><thead><tr><th>scenario</th><th>test</th>'
        '<th>状态</th></tr></thead><tbody>%s</tbody></table>%s%s'
        % ("".join(slice_rows), render_scope(data.get("gate"), change_dir,
                                                        [o for s in slices for o in (s.get("owns") or [])]),
           "".join(scenario_rows), render_forecast(change_dir), timeline_html)
    )


# ---------------------------------------------------------------- meta-chips / footer

def compute_meta_chips(change_dir, change_name):
    chips = None
    try:
        p = subprocess.run(
            ["openspec", "status", "--change", change_name, "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode == 0 and p.stdout.strip():
            data = json.loads(p.stdout)
            artifacts = data.get("artifacts")
            if artifacts:
                chips = []
                for a in artifacts:
                    aid = a.get("id") or a.get("name") or "?"
                    state = a.get("status") or a.get("state") or "blocked"
                    if state not in ("done", "ready", "blocked"):
                        state = "done" if state in ("complete", "completed") else "blocked"
                    chips.append('<span class="chip" data-state="%s">%s</span>' % (esc(state), esc(aid)))
    except (OSError, ValueError, subprocess.SubprocessError):
        chips = None
    if chips is None:
        fallback = [
            ("proposal", os.path.join(change_dir, "proposal.md")),
            ("design", os.path.join(change_dir, "design.md")),
            ("tasks", os.path.join(change_dir, "tasks.md")),
        ]
        specs_dir = os.path.join(change_dir, "specs")
        if os.path.isdir(specs_dir):
            for cap in sorted(os.listdir(specs_dir)):
                fallback.append(("specs/%s" % cap, os.path.join(specs_dir, cap, "spec.md")))
        chips = [
            '<span class="chip" data-state="%s">%s</span>' % (
                "done" if os.path.isfile(path) and os.path.getsize(path) > 0 else "blocked", esc(aid)
            )
            for aid, path in fallback
        ]
    return "".join(chips) if chips else None


def render_footer(now, section_count, diagram_count, task_count):
    stamp = now
    try:
        parsed = datetime.strptime(now.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
        stamp = parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    return "生成于 %s · 章节 %d · 图示 %d · 任务 %d" % (esc(stamp), section_count, diagram_count, task_count)


# ---------------------------------------------------------------- 渲染入口

def render(change_dir, template_path, out_path, now_arg):
    if not os.path.isdir(change_dir):
        sys.stderr.write("change-dir 不存在: %s\n" % change_dir)
        return 1

    tmpl = read_text(template_path)
    if tmpl is None:
        sys.stderr.write("模板不存在: %s\n" % template_path)
        return 1

    change_name = os.path.basename(os.path.normpath(change_dir))
    proposal = read_text(os.path.join(change_dir, "proposal.md"))
    design_text = read_text(os.path.join(change_dir, "design.md"))
    tasks_text = read_text(os.path.join(change_dir, "tasks.md"))

    blocks = {name: None for name in BLOCK_NAMES}
    blocks["title"] = "%s · 意图审批面板" % esc(change_name)
    blocks["change-name"] = esc(change_name)
    blocks["meta-chips"] = compute_meta_chips(change_dir, change_name)
    blocks["why"] = render_why(proposal)
    blocks["what"] = render_what(proposal)
    blocks["capabilities"] = render_capabilities(proposal)
    blocks["specs"] = render_specs(change_dir)
    blocks["design"] = render_design(design_text)
    blocks["diagrams"] = render_diagrams(design_text)
    blocks["adrs"] = scan_adrs(change_dir)
    task_count = 0
    tasks_result = render_tasks(tasks_text)
    if tasks_result:
        blocks["tasks"], task_count = tasks_result
    blocks["flight"] = render_flight(change_dir)

    diagram_count = len(extract_diagrams(design_text))
    section_count = sum(1 for k in ("why", "what", "capabilities", "specs", "design", "diagrams", "adrs", "tasks", "flight") if blocks.get(k))
    if section_count == 0:
        sys.stderr.write("change-dir 无可渲染工件（0 个 section），不写出空壳 spec.html: %s\n" % change_dir)
        return 1
    blocks["footer"] = render_footer(now_iso(now_arg), section_count, diagram_count, task_count)

    out_html = tmpl
    for name in BLOCK_NAMES:
        out_html = substitute_block(out_html, name, blocks[name])

    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out_html)
    return 0


def main():
    ap = argparse.ArgumentParser(description="spec_html：把 OpenSpec change 工件确定性渲染为 spec.html")
    ap.add_argument("--change-dir", required=True)
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    ap.add_argument("--out", default=None)
    ap.add_argument("--now", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(args.change_dir, "spec.html")
    sys.exit(render(args.change_dir, args.template, out, args.now))


if __name__ == "__main__":
    main()
