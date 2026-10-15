#!/usr/bin/env python3
# slice-gate · 切片规划 lint 与切片门禁（零 token）
#
# 子命令：
#   lint     --change-dir DIR                 校验 slices.json；stdout 打印 waves JSON；违规 exit 2 并在 stderr 点名规则
#   waves    --change-dir DIR                 只打印 waves JSON
#   start    S --change-dir DIR [--base REF] [--expect-branch BRANCH]
#                                              在 git toplevel 写 .openspec-slice 标记（slice / change_dir / base / started）；
#                                              标记已是同一切片时不改（resume），保住区间与 red_count；
#                                              给了 --expect-branch 先校验 HEAD 是该分支最新 commit 的后代，否则打印 G0 JSON、exit 1、不写标记
#                                              无同片标记时：带 --resume-checkpoint 恢复 refs/flight/<change>/<S> 快照（stdout 追加 checkpoint），
#                                              不带则清掉本片旧快照
#   checkpoint                                 PostToolUse hook：有标记时把本片 owns 内改动快照到 refs/flight/<change>/<S>；静默、恒 exit 0
#   gate     S --change-dir DIR [--base REF]  跑 G1–G8；stdout 打印 JSON（含 base）；追加 gate-report.md；ok 时删标记，红时标记 red_count+1
#   record   --change-dir DIR --json '<gate JSON>' | --slice S --commit SHA [--red] [--failed ...] [--warnings ...]
#                                              把（临时 worktree 里跑出的）门禁结论幂等写回分支的 gate-report.md / timeline.md
#   final    --change-dir DIR                 先 G7（全部 scenario 状态），再 lint / typecheck，最后全量 test（均按基线差分）；
#                                              G7 红不跑全量
#   baseline --change-dir DIR [--full]        起飞前预检：先把 gate-baseline.json 写成运行标记 {running, pid, started}，
#                                              再跑 gate.test / lint / typecheck 与每片 verify，结束时整体覆盖为结果；
#                                              耗时写回 slices.json.gate.full_suite_sec；退出码按 ok；
#                                              结果带 change / mode / snapshot / cmd_key / byproducts；旧基线可复用（cmd_key 相同、
#                                              Δ 只有 test_*.py 且补跑不红）→ mode incremental：不跑 gate.test，verify 只重跑受影响的片；
#                                              --full 不复用；运行期间已有文件或测试文件被改 → 红，新出现的非测试文件 → 副产物只警告；
#                                              走全量且判过候选时记 reuse_skipped（≤5 条）；开跑前内容快照失败 → 停下、不写运行标记
#   preflight --change-dir DIR                lint_plan + 运行标记识别（仍在跑 / 已中断）+ 基线四项校验（存在 / ok / plan_sha /
#                                              commit 在分支历史）；基线带 snapshot 且 timeline.md 无 approve 事件时再按内容判过期
#                                              （Δ 非空 → 基线过期）；通过打印 waves
#
# G2 差分：gate / final 的 lint / typecheck 非 0 时，与 gate-baseline.json 里规范化后的输出行比对，只为新增行判红；
#          无基线或该项基线为 null 时行为不变（直接判红）。
#          gate.test 经 PYTEST_ADDOPTS 注入 --junitxml，可度量的 exit 1 按失败用例标识（classname::name）逐条差分：
#          baseline 记 test.failed，final 只为基线外的失败判红；不可度量（非 pytest / 多次 pytest / 计数不一致 / exit≠1）按退出码判。
#
# JSON 契约：{"slice", "ok", "commit", "failed": [...], "warnings": [...],
#             "ceilings": [[路径, 行号, 限制, 升级路径], ...], "summary"}；failed 每项以 G<n> 开头并点名对象。
#             ceilings 由执行体转写后经 record --json 回流，形状不可信：解析见 ceiling_rows_from_json，绝不抛异常。
# 兼容 Python 3.8+，只用标准库。
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

MAX_SLICES = 9
MAX_DEPTH = 3
MAX_OWNS = 12
MARKER = ".openspec-slice"
REPORT = "gate-report.md"
EVIDENCE = "evidence.log"
TIMELINE = "timeline.md"
BASELINE = "gate-baseline.json"
# verify 只跑测试；typecheck / lint 工具放 gate.typecheck / gate.lint，由门禁按基线差分
VERIFY_TOOL_RE = re.compile(r"\b(tsc|typecheck|eslint|rustfmt|clippy|ruff|mypy|flake8|golangci)\b")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# pytest-cov 覆盖率未达标的输出标记（pytest-cov 7.1.0 pytest_cov/plugin.py：
# 前者在 pytest_runtestloop 收尾打印，后者在 pytest_terminal_summary 打印）
COVERAGE_FAIL_MARKS = ("Coverage failure: total of", "FAIL Required test coverage of")

TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec"}
TEST_FILE_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|[^/]*\.test\.[^/]+|[^/]*\.spec\.[^/]+)$")
DOC_EXT = {".md", ".mdx", ".markdown", ".txt", ".rst", ".html"}
CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".ini", ".lock", ".cfg"}
NON_SOURCE_PREFIX = (".claude/", "openspec/", "docs/")
PY_TEST_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(test_\w+)\s*\(")
JS_TEST_DEF = re.compile(r"^\s*(?:test|it)\s*\(\s*[\'\"`](.+?)[\'\"`]")
JS_BLOCK_START = re.compile(r"^\s*(?:test|it|describe)\s*\(")
MARK_RE = re.compile(r"xfail|skip", re.I)
# G7 实跑用的临时 pytest 插件：直接记每个 report 的 nodeid 与结果，不依赖终端输出（addopts 含 -q / xdist 的 -n 都会改掉 -v 的逐条行）
# junitxml 区分不出非 strict 的 XPASS（与 PASSED 同形），所以不用它
G7_PLUGIN = '''import json, os


def pytest_runtest_logreport(report):
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            out = "XPASS" if report.passed else "XFAIL"
        elif report.failed and isinstance(report.longrepr, str) and report.longrepr.startswith("[XPASS(strict)]"):
            out = "XPASS"  # 严格 xfail 意外通过：pytest 记 failed、longrepr 带此前缀、不设 wasxfail
        else:
            out = report.outcome.upper()
    elif report.failed:
        out = "ERROR"
    elif report.skipped:
        out = "XFAIL" if hasattr(report, "wasxfail") else "SKIPPED"
    else:
        return
    with open(os.environ["FLIGHT_G7_OUT"], "a", encoding="utf-8") as f:
        f.write(json.dumps([report.nodeid, out]) + "\\n")
'''
# G8 天花板标记：行首注释紧跟标记，两段用 -> 或 → 分隔（形如 `限制 -> 升级条件/路径`）
CEILING_RE = re.compile(r"^\s*(?:#|//|--|\*)+\s*ceiling\s*:\s*(.*)$", re.I)
CEILING_SPLIT = re.compile(r"->|→")
CEILING_MIN = 4
CEILING_HEAD = "## 天花板"
CEILING_COLS = "| 时间 | 切片 | 位置 | 限制 | 升级路径 |"
CEILING_SEP = "|---|---|---|---|---|"
DIFF_HUNK_RE = re.compile(r"^@@ .*?\+(\d+)")


# ---------------------------------------------------------------- 基础

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def die(msg, code=2):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args), p.stderr.strip()))
    return p.stdout.strip()


def toplevel(cwd=None):
    try:
        return git(cwd or os.getcwd(), "rev-parse", "--show-toplevel")
    except RuntimeError as e:
        die("不在 git 仓库内：%s" % e)


def load_plan(change_dir):
    path = os.path.join(change_dir, "slices.json")
    if not os.path.isfile(path):
        die("缺少 %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_plan(change_dir, data):
    with open(os.path.join(change_dir, "slices.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def run_cmd_full(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _tail(out, n=6):
    return "\n".join(out.strip().splitlines()[-n:])


def run_cmd(cmd, cwd):
    rc, out = run_cmd_full(cmd, cwd)
    return rc, _tail(out)


# pytest 汇总行：`1 failed, 2 passed in 0.03s`，可带 `=` 包围与 `(0:01:02)` 时长
PYTEST_SUMMARY_RE = re.compile(r"^=*\s*(\d+ [a-z]+(?:, \d+ [a-z]+)*) in [\d.]+s(?: \([^)]*\))?\s*=*$")


def _summary_failed(line):
    """汇总行里 failed + error(s) 的合计。"""
    n = 0
    for part in PYTEST_SUMMARY_RE.match(line).group(1).split(", "):
        count, word = part.split(" ", 1)
        if word in ("failed", "error", "errors"):
            n += int(count)
    return n


def run_test_gate(cmd, root):
    """跑 gate.test，经 PYTEST_ADDOPTS 注入 --junitxml。
    返回 {"rc", "out", "failed": [classname::name, ...] | None, "why": str | None, "cases": set | None}；
    failed 非 None ⇔ 可度量（rc 1、junit 可解析、汇总行恰一行、汇总与 junit 计数一致且非 0，
    且输出不含 pytest-cov 覆盖率失败标记），why 是不可度量的理由。
    cases = junit 全部 testcase 的 classname 集合：只在 rc 0（junit 可解析）与可度量的 rc 1 时给出，否则 None（design D11）。"""
    with tempfile.TemporaryDirectory() as tmp:
        junit = os.path.join(tmp, "junit.xml")
        env = dict(os.environ)
        env["PYTEST_ADDOPTS"] = (env.get("PYTEST_ADDOPTS", "") + " --junitxml=" + shlex.quote(junit)).strip()
        p = subprocess.run(cmd, cwd=root, shell=True, capture_output=True, text=True, env=env)
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        res = {"rc": rc, "out": out, "failed": None, "why": None, "cases": None}
        if rc == 0:
            try:
                res["cases"] = {tc.get("classname") or "" for tc in ET.parse(junit).getroot().iter("testcase")}
            except (ET.ParseError, OSError):
                pass
            return res
        if rc != 1:
            res["why"] = "exit %d" % rc
            return res
        if any(m in l for l in ANSI_RE.sub("", out).splitlines() for m in COVERAGE_FAIL_MARKS):
            res["why"] = "覆盖率未达标（pytest-cov fail-under）；门禁不判覆盖率时在 gate.test 加 --no-cov"
            return res
        if not os.path.isfile(junit):
            res["why"] = "没有 junit 输出（不是 pytest？）"
            return res
        try:
            tree = ET.parse(junit).getroot()
        except (ET.ParseError, OSError):
            res["why"] = "junit 无法解析"
            return res
    summaries = [l.strip() for l in ANSI_RE.sub("", out).splitlines() if PYTEST_SUMMARY_RE.match(l.strip())]
    if len(summaries) != 1:
        res["why"] = "汇总行 %d 行（调用了多次 pytest？）" % len(summaries)
        return res
    junit_n = sum(int(s.get("failures") or 0) + int(s.get("errors") or 0) for s in tree.iter("testsuite"))
    summary_n = _summary_failed(summaries[0])
    if junit_n != summary_n:
        res["why"] = "计数不一致（汇总行 %d，junit %d）" % (summary_n, junit_n)
        return res
    ids = set()
    for tc in tree.iter("testcase"):
        if tc.find("failure") is not None or tc.find("error") is not None:
            ids.add("%s::%s" % (tc.get("classname") or "", tc.get("name") or ""))
    if summary_n == 0 or not ids:
        res["why"] = "exit 1 但没有失败用例（覆盖率门槛 / 插件判失败？）"
        return res
    res["failed"] = sorted(ids)
    res["cases"] = {tc.get("classname") or "" for tc in tree.iter("testcase")}
    return res


def normalize_lines(text):
    """去 ANSI、数字折成 #（行列号 / 错误码漂移不算新问题）、strip、丢空行，保序去重。"""
    seen, out = set(), []
    for raw in ANSI_RE.sub("", text or "").splitlines():
        line = re.sub(r"\d+", "#", raw).strip()
        if line and line not in seen:
            seen.add(line)
            out.append(line)
    return out


def plan_sha(data):
    """基线只对 gate 命令与每片 verify 负责：这些变了基线就过期，其余（owns / 耗时）不影响。"""
    gate = data.get("gate") or {}
    key = [gate.get("test"), gate.get("lint"), gate.get("typecheck"),
           [[s.get("id"), s.get("verify")] for s in data.get("slices") or []]]
    return hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def load_baseline(change_dir):
    path = os.path.join(change_dir, BASELINE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def gate_cmd_verdict(kind, cmd, root, baseline):
    """跑 gate.<kind>，返回 (failed_item, warning_item)，至多一个非 None。

    有基线且该项非 null：只有规范化后不在基线里的输出行才判红；全在基线里则降为警告。
    两条守卫先于差分：基线为绿时任何非 0 直接红；本次无输出（静默型检查器）无法比对也直接红。
    """
    rc, out = run_cmd_full(cmd, root)
    if rc == 0:
        return None, None
    known = (baseline or {}).get(kind)
    if not known:
        return "G2 %s: exit %d\n%s" % (kind, rc, _tail(out)), None
    if known.get("exit") == 0:
        return "G2 %s: exit %d（基线为绿）\n%s" % (kind, rc, _tail(out)), None
    lines = normalize_lines(out)
    if not lines:
        return "G2 %s: exit %d（无输出可与基线比对）" % (kind, rc), None
    old = set(known.get("lines") or [])
    new = [l for l in lines if l not in old]
    if not new:
        return None, "G2 %s: exit %d，输出与基线一致（既有 %d 行已按基线排除）" % (kind, rc, len(old))
    return "G2 %s: exit %d（新增 %d 行）\n%s" % (kind, rc, len(new), "\n".join(new[:6])), None


def full_suite_verdict(cmd, root, baseline):
    """跑 gate.test，返回 (failed_item, warning_item)。可度量的 exit 1 按基线 test.failed 逐条差分（缺失视为空集）。"""
    tg = run_test_gate(cmd, root)
    rc = tg["rc"]
    if rc == 0:
        return None, None
    if tg["failed"] is None:
        return "G2 test: exit %d（按退出码判：%s）\n%s" % (rc, tg["why"], _tail(tg["out"])), None
    old = set(((baseline or {}).get("test") or {}).get("failed") or [])
    new = [t for t in tg["failed"] if t not in old]
    if not new:
        return None, "G2 test: exit 1，失败均为基线预存红（%d 条已按基线排除）" % len(tg["failed"])
    return "G2 test: exit 1（新增 %d 条失败）\n%s" % (len(new), "\n".join(new[:6])), None


def glob_match(path, pattern):
    if path == pattern or fnmatch.fnmatchcase(path, pattern):
        return True
    if pattern.endswith("/**") and path.startswith(pattern[:-3] + "/"):
        return True
    return False


def globs_intersect(a, b):
    if a == b or glob_match(a, b) or glob_match(b, a):
        return True
    for x, y in ((a, b), (b, a)):
        if x.endswith("/**") and (y.startswith(x[:-3] + "/") or y == x[:-3]):
            return True
    return False


# ---------------------------------------------------------------- lint / waves

def compute_waves(slices):
    ids = [s["id"] for s in slices]
    deps = {s["id"]: list(s.get("deps") or []) for s in slices}
    placed, waves = set(), []
    while len(placed) < len(ids):
        wave = [i for i in ids if i not in placed and all(d in placed for d in deps[i])]
        if not wave:
            return waves, [i for i in ids if i not in placed]
        waves.append(wave)
        placed.update(wave)
    return waves, []


def lint_plan(data):
    errors = []
    if not ((data.get("gate") or {}).get("test") or "").strip():
        errors.append("gate: gate.test 缺失（须显式写出，baseline 不再自动探测写回）")
    slices = data.get("slices") or []
    ids = [s.get("id") for s in slices]
    if len(ids) != len(set(ids)):
        errors.append("ids: 切片 id 重复")
    if not (1 <= len(slices) <= MAX_SLICES):
        errors.append("count: 切片数 %d 不在 1–%d 内" % (len(slices), MAX_SLICES))
    for s in slices:
        owns = s.get("owns") or []
        if not (1 <= len(owns) <= MAX_OWNS):
            errors.append("owns: %s 的 owns 有 %d 条，须在 1–%d 内" % (s.get("id"), len(owns), MAX_OWNS))
        if not (s.get("verify") or "").strip():
            errors.append("verify: %s 缺少 verify 命令" % s.get("id"))
        elif VERIFY_TOOL_RE.search(s.get("verify") or ""):
            errors.append("verify: %s 含 typecheck/lint 工具，verify 只跑测试；typecheck 放 gate.typecheck、lint 放 gate.lint（门禁按基线差分）" % s.get("id"))
        for d in s.get("deps") or []:
            if d not in ids:
                errors.append("deps: %s 依赖的 %s 不存在" % (s.get("id"), d))
    waves, leftover = compute_waves(slices)
    if leftover:
        errors.append("cycle: 依赖成环 %s" % ", ".join(leftover))
    if len(waves) > MAX_DEPTH:
        errors.append("depth: DAG 深度 %d > %d" % (len(waves), MAX_DEPTH))
    by_id = {s["id"]: s for s in slices if "id" in s}
    for wave in waves:
        for i, a in enumerate(wave):
            for b in wave[i + 1:]:
                for pa in by_id[a].get("owns") or []:
                    for pb in by_id[b].get("owns") or []:
                        if globs_intersect(pa, pb):
                            errors.append("overlap: 同一 wave 的 %s 与 %s 都覆盖 %s / %s" % (a, b, pa, pb))
    return errors, waves


# ---------------------------------------------------------------- 留痕

def timeline_record(change_dir, event, note=""):
    path = os.path.join(change_dir, TIMELINE)
    try:
        new = not os.path.isfile(path)
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write("<!-- timeline: ISO时间\\t事件\\t备注（由 hooks 自动追加） -->\n")
            f.write("%s\t%s\t%s\n" % (now_iso(), event, note.replace("\n", " ")))
    except OSError:
        pass


def append_report(change_dir, result):
    path = os.path.join(change_dir, REPORT)
    try:
        new = not os.path.isfile(path)
        with open(path, "a", encoding="utf-8") as f:
            if new:
                f.write("# Gate Report\n\n| 时间 | 切片 | 结论 | commit | failed | warnings |\n|---|---|---|---|---|---|\n")
            f.write("| %s | %s | %s | %s | %s | %s |\n" % (
                now_iso(), result["slice"], "ok" if result["ok"] else "red", result.get("commit", "")[:10],
                "; ".join(result["failed"]).replace("|", "/").replace("\n", " ") or "-",
                "; ".join(result["warnings"]).replace("|", "/").replace("\n", " ") or "-",
            ))
    except OSError:
        pass


def _cell(text):
    return text.replace("|", "/").replace("\n", " ")


def ceiling_rows_from_json(raw):
    """门禁 JSON 的 ceilings 字段 → record_ceilings 可用的行；形状不对的整条丢掉，行号不可信降级为 0。

    这个字段全程由执行体的结构化输出转写，不可信。解析绝不抛异常：留痕失败不得中断飞行。
    """
    if not isinstance(raw, (list, tuple)):
        return []  # 非可迭代标量 / dict：整段丢掉，不让迭代自己抛 TypeError
    out = []
    for r in raw:
        if not isinstance(r, (list, tuple)) or len(r) < 4:
            continue
        try:
            ln = int(str(r[1]).strip())
        except (TypeError, ValueError):
            ln = 0
        out.append((str(r[0]), ln, str(r[2]), str(r[3])))
    return out


def record_ceilings(change_dir, slice_id, rows):
    """把合规天花板标记汇总进 gate-report.md 的「天花板」表。

    表插在 Gate Report 表之前，这样 append_report 继续往文件尾追加的门禁行仍落在 gate 表里。
    """
    if not rows:
        return
    path = os.path.join(change_dir, REPORT)
    new = ["| %s | %s | %s:%d | %s | %s |" % (now_iso(), slice_id, rel, ln, _cell(limit), _cell(up))
           for rel, ln, limit, up in rows]
    try:
        lines = []
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        if CEILING_HEAD in lines:
            at = lines.index(CEILING_HEAD) + 1
            while at < len(lines) and not lines[at].strip():  # 表头前的空行
                at += 1
            while at < len(lines) and lines[at].startswith("|"):  # 表头与已有行，停在表尾空行
                at += 1
        else:
            at = 1 if lines and lines[0].startswith("#") else 0
            lines[at:at] = ["", CEILING_HEAD, "", CEILING_COLS, CEILING_SEP]
            at += 5
        lines[at:at] = new
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


def evidence_state(change_dir, slice_id):
    """返回 'missing_file' | 'no_rows' | 'red_first' | 'no_red'。"""
    path = os.path.join(change_dir, EVIDENCE)
    if not os.path.isfile(path):
        return "missing_file"
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 3 and parts[1] == slice_id:
                rows.append(parts[2])
    if not rows:
        return "no_rows"
    if "PASS" not in rows:
        return "no_red"
    last_pass = max(i for i, r in enumerate(rows) if r == "PASS")
    return "red_first" if any(r == "FAIL" for r in rows[:last_pass]) else "no_red"


def report_has_row(change_dir, slice_id, commit):
    path = os.path.join(change_dir, REPORT)
    if not os.path.isfile(path):
        return False
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) >= 4 and cols[1] == slice_id and cols[3] == (commit or "")[:10]:
                return True
    return False


# ---------------------------------------------------------------- 文件分类与检查

def is_test_path(path):
    parts = path.split("/")
    if any(p in TEST_DIR_NAMES for p in parts[:-1]):
        return True
    return bool(TEST_FILE_RE.search(path))


def is_doc_or_config(path):
    if path.startswith(NON_SOURCE_PREFIX):
        return True
    _, ext = os.path.splitext(path)
    return ext.lower() in DOC_EXT or ext.lower() in CONFIG_EXT


def source_files(files, change_rel):
    """改动里的源码：非测试、非文档 / 配置、不在 change 目录内、不是切片标记。"""
    return [f for f in files if not is_test_path(f) and not is_doc_or_config(f)
            and not f.startswith(change_rel + "/") and f != MARKER]


def is_bytecode(path):
    """Python 字节码（__pycache__ 目录或 .pyc）：未提交时是跑测试的副产物，不算切片改动；已提交的照常受所有权检查。"""
    return "__pycache__" in path.split("/") or path.endswith(".pyc")


def changed_files(root, base):
    head = git(root, "rev-parse", "HEAD")
    committed = set()
    if base and base != head:
        committed = set(x for x in git(root, "diff", "--name-only", "%s..HEAD" % base).splitlines() if x)
    uncommitted = set()
    # 不能用 git()：它会 strip() 掉首行的前导空格（" M path" 会被截成 "M path"）
    porcelain = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout
    for line in porcelain.splitlines():
        if len(line) > 3:
            uncommitted.add(line[3:].split(" -> ")[-1].strip())
    return committed, set(f for f in uncommitted if not is_bytecode(f))


def added_lines(root, base):
    """产出 base..HEAD 里新增的 (rel_path, lineno, text)。

    注意：`+++ b/<path>` 也以 `+` 开头，必须先判文件头再判内容行。
    """
    try:
        diff = git(root, "diff", "--unified=0", "%s..HEAD" % base)
    except RuntimeError:
        return
    rel, lineno = None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            rel = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
        elif line.startswith("@@"):
            m = DIFF_HUNK_RE.match(line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith(("--- ", "diff ", "index ", "old mode", "new mode", "similarity ", "rename ")):
            continue
        elif line.startswith("+") and rel:
            yield rel, lineno, line[1:]
            lineno += 1


def ceiling_rows(root, base):
    """扫新增源码行里的天花板标记，返回 (failed, rows)；rows 每项 = (rel, lineno, 限制, 升级路径)。

    无标记既不判红也不警告：判据只管标了的完整性，不管该不该标。
    """
    failed, rows = [], []
    for rel, lineno, text in added_lines(root, base):
        if is_doc_or_config(rel) or rel.startswith(NON_SOURCE_PREFIX):
            continue
        m = CEILING_RE.match(text)
        if not m:
            continue
        parts = CEILING_SPLIT.split(m.group(1), 1)
        limit = parts[0].strip().strip("`").strip()
        upgrade = parts[1].strip().strip("`").strip() if len(parts) > 1 else ""
        if len(limit) < CEILING_MIN or len(upgrade) < CEILING_MIN:
            failed.append("G8 ceiling: %s:%d 缺%s（期望形状 `限制 -> 升级条件/路径`，两段各不少于 %d 字符）" % (
                rel, lineno, "限制段" if len(limit) < CEILING_MIN else "升级路径段", CEILING_MIN))
        else:
            rows.append((rel, lineno, limit, upgrade))
    return failed, rows


def gwt_violations(root, test_files):
    out = []
    for rel in sorted(test_files):
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for name, body in _test_bodies(rel, lines):
            pos = {}
            for kw in ("Given:", "When:", "Then:"):
                m = re.search(r"(?m)^\s*(?:#|//|\*)\s*%s" % kw, body)
                pos[kw] = m.start() if m else -1
            g, w, t = pos["Given:"], pos["When:"], pos["Then:"]
            if min(g, w, t) < 0 or not (g < w < t):
                missing = [k for k, i in pos.items() if i < 0] or ["顺序不是 Given→When→Then"]
                out.append("G4 GWT: %s::%s 缺 %s" % (rel, name, " ".join(missing)))
    return out


def _py_test_bodies(lines):
    """用 AST 找 test_* 函数，避免把字符串常量里的 def 误判为测试。"""
    import ast
    src = "\n".join(lines)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            end = getattr(node, "end_lineno", None) or node.lineno
            out.append((node.name, "\n".join(lines[node.lineno - 1:end])))
    return out


def _test_bodies(rel, lines):
    if rel.endswith(".py"):
        bodies = _py_test_bodies(lines)
        if bodies is not None:
            for item in bodies:
                yield item
            return
        i = 0
        while i < len(lines):
            m = PY_TEST_DEF.match(lines[i])
            if not m:
                i += 1
                continue
            indent, name = len(m.group(1)), m.group(2)
            j = i + 1
            while j < len(lines):
                s = lines[j]
                if s.strip() and (len(s) - len(s.lstrip())) <= indent and not s.lstrip().startswith(("#", "@")):
                    break
                j += 1
            yield name, "\n".join(lines[i:j])
            i = j
    else:
        starts = [k for k, s in enumerate(lines) if JS_BLOCK_START.match(s)]
        for idx, k in enumerate(starts):
            m = JS_TEST_DEF.match(lines[k])
            if not m:
                continue
            end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
            yield m.group(1), "\n".join(lines[k:end])


FLIGHT_RECORDS = (TIMELINE, REPORT, EVIDENCE)


def ownership_violations(files, owns, change_rel, committed=()):
    out = []
    prefix = change_rel.rstrip("/") + "/"
    for f in sorted(files):
        if f == MARKER:
            continue
        if f.startswith(prefix):
            # 飞行记录由 hook 追加、由 integrator / 主会话单独提交；执行体把它们裹进切片 commit 会在合回时冲突
            if f in committed and f[len(prefix):] in FLIGHT_RECORDS:
                out.append("G6 flight-record: %s 属飞行记录，执行体不得提交（由 integrator 单独 commit）" % f)
            continue
        if not any(glob_match(f, o) for o in owns):
            out.append("G6 ownership: %s 不在 owns 内" % f)
    return out


def _py_decorators(source, func):
    """用 AST 取函数 func 的完整装饰器源文本（支持跨行）；解析失败或找不到返回 None。"""
    import ast
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            segs = [ast.get_source_segment(source, d) or "" for d in node.decorator_list]
            return "\n".join(segs)
    return None


def _pytest_head(cmd):
    """命令切成 (pytest 前缀词, 其后的词)：前缀止于第一个 pytest / py.test 词（或 -m pytest），
    其前不能有 &&、||、;、|、cd、VAR= 赋值；认不出 / 切词失败 → None。"""
    try:
        toks = shlex.split(cmd or "")
    except ValueError:
        return None
    for i, tok in enumerate(toks):
        if os.path.basename(tok) in ("pytest", "py.test") or (tok == "pytest" and i > 0 and toks[i - 1] == "-m"):
            head = toks[:i + 1]
            if not any(t in ("&&", "||", ";", "|", "cd") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t) for t in head):
                return head, toks[i + 1:]
            return None
    return None


# verify 推导（design D11）：pytest 前缀之后只允许这些词与路径；成对的 -p no:cacheprovider 另认
DERIVE_WHITELIST = {"-q", "-qq", "-v", "-vv", "-x", "-s", "--no-header"}
# 路径词里出现这些字符就不当路径（shell 运算符 / 重定向 / 展开 / 赋值），一律照跑
DERIVE_UNSAFE = re.compile(r"[;&|<>$`()*?!{}\[\]=~\\]")


def _derive_paths(rest):
    """rest 只含白名单与路径 → 路径列表；含其他词 → None。"""
    paths, i = [], 0
    while i < len(rest):
        t = rest[i]
        if t == "-p" and i + 1 < len(rest) and rest[i + 1] == "no:cacheprovider":
            i += 1
        elif t in DERIVE_WHITELIST or t.startswith("--tb="):
            pass
        elif t and not t.startswith("-") and not DERIVE_UNSAFE.search(t):
            paths.append(t)
        else:
            return None
        i += 1
    return paths


def _derive_verify(root, full_head, vcmd, cases, failed):
    """全量 junit 能否替这片 verify 判绿：前缀与全量逐词相同、rest 只含白名单与至少一个测试文件路径（不含 ::），
    且每个文件对应的模块在全量里有用例、没有失败。任何不确定 → False（照跑）。"""
    if full_head is None or cases is None:
        return False
    h = _pytest_head(vcmd)
    if h is None or h[0] != full_head:
        return False
    paths = _derive_paths(h[1])
    if not paths:
        return False
    failed_mods = [str(f).split("::", 1)[0] for f in failed or []]
    for p in paths:
        name = p.rsplit("/", 1)[-1]
        if "::" in p or not os.path.isfile(os.path.join(root, p)) or not (
                fnmatch.fnmatchcase(name, "test_*.py") or fnmatch.fnmatchcase(name, "*_test.py")):
            return False
        m = p[:-3].replace("/", ".")
        if not any(c == m or c.startswith(m + ".") for c in cases):
            return False
        if any(c == m or c.startswith(m + ".") for c in failed_mods):
            return False
    return True


def _g7_runner(gate):
    """G7 实跑用的 pytest 命令前缀：gate.pytest > 从 gate.test 推导 > 退回本解释器（附 warning）。"""
    if gate.get("pytest"):
        return shlex.split(gate["pytest"]), None
    h = _pytest_head(gate.get("test") or "")
    if h is not None:
        return h[0], None
    return [sys.executable, "-m", "pytest"], (
        "G7：无法从 gate.test 推导 pytest 运行方式，已退回 %s -m pytest；可在 slices.json 的 gate.pytest 指定" % sys.executable)


def _g7_timeout(gate):
    try:
        return float(os.environ["FLIGHT_G7_TIMEOUT"])
    except (KeyError, ValueError):
        pass
    sec = gate.get("full_suite_sec")
    if isinstance(sec, (int, float)) and not isinstance(sec, bool):
        return max(120, 3 * sec)
    return 600


def _pytest_outcomes(root, targets, gate=None):
    """实跑 targets，返回 (outcomes, rc, out_text, timed_out)；outcomes = [(nodeid, PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)]，nodeid 以 root 为 rootdir。"""
    gate = gate or {}
    prefix, _ = _g7_runner(gate)
    timeout = _g7_timeout(gate)
    with tempfile.TemporaryDirectory(prefix="flight-g7-") as tmp:
        with open(os.path.join(tmp, "flight_g7_outcomes.py"), "w", encoding="utf-8") as f:
            f.write(G7_PLUGIN)
        out = os.path.join(tmp, "outcomes.jsonl")
        # 不写字节码：__pycache__ 落进被测 worktree 会被当成改动（G5 起点测量、source 判定）
        env = dict(os.environ, FLIGHT_G7_OUT=out, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=os.pathsep.join(p for p in (tmp, os.environ.get("PYTHONPATH")) if p))
        argv = prefix + ["-p", "flight_g7_outcomes", "-p", "no:cacheprovider", "--rootdir", root, *targets]
        timed_out, rc, text = False, None, ""
        try:
            # 独立进程组：超时整组杀掉，免得包装脚本的孙进程占住输出管道
            p = subprocess.Popen(argv, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, start_new_session=True)
        except OSError as e:
            return [], None, str(e), False
        try:
            text, _ = p.communicate(timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(p.pid, 9)
            except OSError:
                pass
            p.communicate()
            rc = p.returncode
        outcomes = []
        if os.path.isfile(out):
            with open(out, "r", encoding="utf-8") as f:
                outcomes = [tuple(json.loads(line)) for line in f if line.strip()]
        return outcomes, rc, text or "", timed_out


def _g7_diag(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    hit = next((ln for ln in lines if "Error" in ln), lines[-1] if lines else "")
    return hit[:200]


def scenario_status(root, data, slice_ids=None):
    """返回 (violations, total, passed)。passed = 有映射、函数存在、无 xfail/skip 标记，且 .py 目标实跑结果全为 PASSED。"""
    tests = data.get("scenario_tests") or {}
    wanted = []
    for s in data.get("slices") or []:
        if slice_ids is None or s["id"] in slice_ids:
            wanted.extend(s.get("scenarios") or [])
    violations, passed, py_targets = [], 0, []
    for sid in wanted:
        target = tests.get(sid)
        if not target or "::" not in target:
            violations.append("G7 scenario: %s 无测试映射" % sid)
            continue
        rel, func = target.split("::", 1)
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            violations.append("G7 scenario: %s → %s 文件不存在" % (sid, rel))
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        lines = source.splitlines()
        hit = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*(?:async\s+)?def\s+%s\s*\(" % re.escape(func), line) or (
                    JS_TEST_DEF.match(line) and JS_TEST_DEF.match(line).group(1) == func):
                hit = i
                break
        if hit is None:
            violations.append("G7 scenario: %s → %s 未定义" % (sid, target))
            continue
        marked = False
        decos = _py_decorators(source, func) if rel.endswith(".py") else None
        if decos is not None:
            marked = bool(MARK_RE.search(decos))  # AST 取完整 decorator_list，跨行装饰器也能识别
        else:
            k = hit - 1
            while k >= 0 and lines[k].strip().startswith("@"):
                if MARK_RE.search(lines[k]):
                    marked = True
                k -= 1
        if marked:
            violations.append("G7 scenario: %s → %s 仍标记 xfail/skip" % (sid, target))
            continue
        if rel.endswith(".py"):
            py_targets.append((sid, target))
        else:
            passed += 1
    warnings = []
    if py_targets:
        # 文本检查认不出别名装饰器 / 测试体内 pytest.skip()：对 .py 目标实跑一次，只认 PASSED
        gate = data.get("gate") or {}
        _, warn = _g7_runner(gate)
        if warn:
            warnings.append(warn)
        outcomes, rc, text, timed_out = _pytest_outcomes(root, [t for _, t in py_targets], gate)
        for sid, target in py_targets:
            outs = [o for i, o in outcomes if i == target or i.startswith(target + "[")]
            if timed_out:
                violations.append("G7 scenario: %s → %s 运行超时（%g 秒）" % (sid, target, _g7_timeout(gate)))
            elif not outs:
                violations.append("G7 scenario: %s → %s 未被收集运行（pytest rc=%s：%s）" % (sid, target, rc, _g7_diag(text)))
            elif any(o != "PASSED" for o in outs):
                bad = next(o for o in outs if o != "PASSED")
                violations.append("G7 scenario: %s → %s 实际结果 %s（未真正通过）" % (sid, target, bad))
            else:
                passed += 1
    return violations, len(wanted), passed, warnings


def detect_test_cmd(root):
    if os.path.isfile(os.path.join(root, "package.json")):
        return "npm test"
    if any(os.path.isfile(os.path.join(root, f)) for f in ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")) or os.path.isdir(os.path.join(root, "tests")):
        return "python3 -m pytest -q"
    if os.path.isfile(os.path.join(root, "go.mod")):
        return "go test ./..."
    if os.path.isfile(os.path.join(root, "Cargo.toml")):
        return "cargo test"
    return None


# ---------------------------------------------------------------- 子命令

def cmd_lint(args, print_waves=True):
    data = load_plan(args.change_dir)
    errors, waves = lint_plan(data)
    if errors:
        die("slices.json 不合法：\n  - " + "\n  - ".join(errors))
    if print_waves:
        print(json.dumps(waves, ensure_ascii=False))
    return waves


def _is_ancestor(root, anc, desc):
    # 不能用 git()：--is-ancestor 不成立时退出 1，git() 会当成异常抛；任何非 0 都按「不成立」
    return subprocess.run(["git", "merge-base", "--is-ancestor", anc, desc],
                          cwd=root, capture_output=True, text=True).returncode == 0


def _base_check(root, branch):
    """G0：HEAD 必须是 branch 最新 commit 的后代（含相等）。通过返回 None，否则返回 failed 文案。"""
    try:
        tip = git(root, "rev-parse", "--verify", branch + "^{commit}")
    except RuntimeError:
        return "G0 base: 分支 %s 不存在" % branch
    head = git(root, "rev-parse", "HEAD")
    if not _is_ancestor(root, tip, head):
        return "G0 base: HEAD %s 不是分支 %s（%s）的后代——worktree 不是从 change 分支最新 commit 分叉" % (
            head[:10], branch, tip[:10])
    return None


def _ckpt_ref(change_dir, slice_id):
    return "refs/flight/%s/%s" % (os.path.basename(os.path.abspath(change_dir).rstrip(os.sep)), slice_id)


def _ckpt_delete(root, ref):
    # 引用不存在时 update-ref -d 也可能非 0：一律忽略
    subprocess.run(["git", "update-ref", "-d", ref], cwd=root, capture_output=True, text=True)


def _gate_ref(change_dir, slice_id):
    return "refs/flight/%s/gate-%s" % (os.path.basename(os.path.abspath(change_dir).rstrip(os.sep)), slice_id)


def _gate_save(root, change_dir, result):
    """把门禁结论写成以切片 commit 为父的提交，挂到 gate ref。成功返回 None，失败返回 stderr 首行。"""
    def g(args, stdin=None):
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, input=stdin)
        if p.returncode != 0:
            raise RuntimeError((p.stderr.strip().splitlines() or ["git %s exit %d" % (args[0], p.returncode)])[0])
        return p.stdout.strip()

    try:
        blob = g(["hash-object", "-w", "--stdin"], json.dumps(result, ensure_ascii=False))
        tree = g(["mktree"], "100644 blob %s\tgate.json\n" % blob)
        sha = g(["commit-tree", tree, "-p", result["commit"], "-m",
                 "flight: gate %s ok %s" % (result["slice"], result["commit"][:8])])
        g(["update-ref", _gate_ref(change_dir, result["slice"]), sha])
    except RuntimeError as e:
        return str(e)
    return None


def _gate_load(root, ref):
    p = subprocess.run(["git", "show", ref + ":gate.json"], cwd=root, capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        rec = json.loads(p.stdout)
    except ValueError:
        return None
    return rec if isinstance(rec, dict) else None


def _slice_owns(change_dir, slice_id):
    with open(os.path.join(change_dir, "slices.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    for s in data.get("slices") or []:
        if s.get("id") == slice_id:
            return s.get("owns") or []
    return []


def _checkpoint(root):
    marker = _read_marker(root)
    if not marker or not marker.get("slice") or not marker.get("change_dir"):
        return
    slice_id, change_dir = marker["slice"], marker["change_dir"]
    owns = _slice_owns(change_dir, slice_id)
    change_rel = os.path.relpath(change_dir, root).replace(os.sep, "/").rstrip("/") + "/"
    # 按文件粒度：-uall 展开未跟踪目录；-z 免引号转义（重命名项后随原路径，跳过）
    raw = subprocess.run(["git", "status", "--porcelain", "-z", "-uall"], cwd=root,
                         capture_output=True, text=True).stdout
    entries, files, skip = raw.split("\0"), [], False
    for e in entries:
        if skip:
            skip = False
            continue
        if len(e) < 4:
            continue
        if e[0] in "RC":
            skip = True
        path = e[3:]
        if path == MARKER or path.startswith(change_rel):
            continue
        if any(glob_match(path, o) for o in owns):
            files.append(path)
    head = git(root, "rev-parse", "HEAD")
    if not files and head == marker.get("base"):
        return
    fd, index = tempfile.mkstemp(prefix="flight-ckpt-", suffix=".index")
    os.close(fd)
    try:
        env = dict(os.environ, GIT_INDEX_FILE=index)

        def g(*a):
            p = subprocess.run(["git", *a], cwd=root, capture_output=True, text=True, env=env)
            if p.returncode != 0:
                raise RuntimeError("git %s: %s" % (" ".join(a), p.stderr.strip()))
            return p.stdout.strip()

        g("read-tree", head)
        if files:
            g("add", "-A", "--", *files)
        tree = g("write-tree")
        sha = g("commit-tree", tree, "-p", head, "-m", "flight checkpoint %s" % slice_id)
    finally:
        try:
            os.remove(index)
        except OSError:
            pass
    git(root, "update-ref", _ckpt_ref(change_dir, slice_id), sha)


def cmd_checkpoint(args):
    """PostToolUse hook：把本片 owns 内的工作区改动快照到 refs/flight/<change>/<S>。静默、永不阻断。"""
    try:
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            payload = {}
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd or os.getcwd(),
                           capture_output=True, text=True)
        if p.returncode == 0:
            _checkpoint(p.stdout.strip())
    except BaseException:
        pass
    sys.exit(0)


def _ckpt_restore(root, ref, owns):
    """把快照里相对 HEAD 有差异的 owns 文件放回工作区。返回 (restored, note)。"""
    try:
        snap = git(root, "rev-parse", "--verify", "-q", ref + "^{commit}")
    except RuntimeError:
        return [], "无快照 %s，未恢复" % ref
    if not _is_ancestor(root, "HEAD", snap):
        return [], "快照 %s 的祖先链不含当前 HEAD（基点不符），未恢复" % snap[:10]
    # -z：免 core.quotePath 把非 ASCII 路径转义成带引号的八进制串；不经 git() 的 strip，按 \0 切分
    # --no-renames：重命名的删除端以独立路径出现，走下面"快照中不存在就删除"分支
    p = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames", "HEAD", snap], cwd=root,
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("git diff: %s" % p.stderr.strip())
    names = [x for x in p.stdout.split("\0") if x]
    restored = []
    for f in names:
        if f == MARKER or not any(glob_match(f, o) for o in owns):
            continue
        exists = subprocess.run(["git", "cat-file", "-e", "%s:%s" % (snap, f)], cwd=root,
                                capture_output=True, text=True).returncode == 0
        if exists:
            git(root, "checkout", snap, "--", f)
        else:
            try:
                os.remove(os.path.join(root, f))
            except OSError:
                pass
        restored.append(f)
    return restored, ("" if restored else "快照与 HEAD 在 owns 内无差异，未恢复")


def cmd_start(args):
    root = toplevel()
    data = load_plan(args.change_dir)
    if args.slice not in [s["id"] for s in data.get("slices") or []]:
        die("切片 %s 不在 slices.json 中" % args.slice)
    if args.expect_branch:
        msg = _base_check(root, args.expect_branch)
        if msg:
            print(json.dumps({"slice": args.slice, "ok": False, "commit": "", "failed": [msg],
                              "warnings": [], "summary": "基点校验未通过"}, ensure_ascii=False))
            sys.exit(1)
    if args.resume_checkpoint:
        # 上一轮执行体门禁已绿却没返回：基点吻合就直接交出留存的结论，不再重做
        rec = _gate_load(root, _gate_ref(args.change_dir, args.slice))
        if rec and rec.get("ok") and rec.get("slice") == args.slice and \
                git(root, "rev-parse", "HEAD") in (rec.get("base"), rec.get("commit")):
            timeline_record(args.change_dir, "slice-start", "%s (recovered gate)" % args.slice)
            print(json.dumps(dict(rec, recovered=True), ensure_ascii=False))
            sys.exit(3)
    existing = _read_marker(root)
    if existing and existing.get("slice") == args.slice:
        # 重试同一切片：区间起点与 red_count 都要保住，标记原样不动
        timeline_record(args.change_dir, "slice-start", "%s (resume)" % args.slice)
        print(json.dumps(existing, ensure_ascii=False))
        return
    ref = _ckpt_ref(args.change_dir, args.slice)
    ckpt, note = None, args.slice
    if args.resume_checkpoint:
        owns = next((s.get("owns") or [] for s in data.get("slices") or [] if s["id"] == args.slice), [])
        restored, why = _ckpt_restore(root, ref, owns)
        ckpt = {"restored": restored, "note": why}
        note = "%s (checkpoint %d files)" % (args.slice, len(restored))
    else:
        # 首轮起跑：上一次飞行残留的快照不属于本轮，清掉免得被误恢复
        _ckpt_delete(root, ref)
        _ckpt_delete(root, _gate_ref(args.change_dir, args.slice))
    marker = {"slice": args.slice, "change_dir": os.path.abspath(args.change_dir),
              "base": args.base or git(root, "rev-parse", "HEAD"), "started": now_iso()}
    with open(os.path.join(root, MARKER), "w", encoding="utf-8") as f:
        json.dump(marker, f, ensure_ascii=False)
    timeline_record(args.change_dir, "slice-start", note)
    print(json.dumps(dict(marker, checkpoint=ckpt) if ckpt is not None else marker, ensure_ascii=False))


def _read_marker(root):
    path = os.path.join(root, MARKER)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def cmd_gate(args):
    root = toplevel()
    data = load_plan(args.change_dir)
    by_id = {s["id"]: s for s in data.get("slices") or []}
    if args.slice not in by_id:
        die("切片 %s 不在 slices.json 中" % args.slice)
    sl = by_id[args.slice]
    marker = _read_marker(root)
    base = args.base or (marker or {}).get("base")
    if not base:
        die("没有 base：先运行 `slice-gate.py start %s`，或传 --base" % args.slice)
    change_rel = os.path.relpath(os.path.abspath(args.change_dir), root).replace(os.sep, "/")
    failed, warnings = [], []

    committed, uncommitted = changed_files(root, base)
    stray = sorted(f for f in uncommitted if f != MARKER and not f.startswith(change_rel + "/"))
    if stray:
        warnings.append("工作树有未提交改动：%s" % ", ".join(stray[:8]))
    files = committed | uncommitted

    rc, tail = run_cmd(sl["verify"], root)
    if rc != 0:
        failed.append("G1 verify: exit %d\n%s" % (rc, tail))
    gate = data.get("gate") or {}
    baseline = load_baseline(args.change_dir)
    for key in ("lint", "typecheck"):
        cmd = gate.get(key)
        if cmd:
            f2, w2 = gate_cmd_verdict(key, cmd, root, baseline)
            if f2:
                failed.append(f2)
            if w2:
                warnings.append(w2)

    source = source_files(files, change_rel)
    tests =[f for f in files if is_test_path(f)]
    if source and not tests:
        failed.append("G3 pairing: 改了源码 %s 但区间内没有测试文件改动" % ", ".join(sorted(source)[:6]))
    failed.extend(gwt_violations(root, tests))
    ev = evidence_state(args.change_dir, args.slice)
    hooks_missing = ev == "missing_file"
    if ev == "missing_file":
        warnings.append("G5 evidence: 无 evidence.log（test-evidence hook 未安装或未触发），本切片留痕无法核对")
    elif ev == "no_rows":
        failed.append("G5 evidence: evidence.log 无本切片 %s 的测试运行记录（hook 在工作却没跑过测试）" % args.slice)
    elif ev == "no_red":
        warnings.append("G5 evidence: 未见 RED 先于 GREEN 的测试运行记录")
    failed.extend(ownership_violations(files, sl.get("owns") or [], change_rel, committed))
    v7, _, _, w7 = scenario_status(root, data, {args.slice})
    failed.extend(v7)
    warnings.extend(w7)
    v8, ceilings = ceiling_rows(root, base)
    failed.extend(v8)

    result = {"slice": args.slice, "ok": not failed, "commit": git(root, "rev-parse", "HEAD"), "base": base,
              "failed": failed, "warnings": warnings, "hooks_missing": hooks_missing,
              "ceilings": [[rel, ln, limit, up] for rel, ln, limit, up in ceilings],
              "summary": "%s：%d 项失败，%d 项警告；改动 %d 个文件" % ("通过" if not failed else "阻断", len(failed), len(warnings), len(files))}
    if result["ok"]:
        err = _gate_save(root, args.change_dir, result)
        if err:
            warnings.append("门禁结论未能留存：%s" % err)
    append_report(args.change_dir, result)
    record_ceilings(args.change_dir, args.slice, ceilings)
    timeline_record(args.change_dir, "gate", "%s %s" % (args.slice, "ok" if result["ok"] else "red"))
    if marker is not None:
        if result["ok"]:
            try:
                os.remove(os.path.join(root, MARKER))
            except OSError:
                pass
            _ckpt_delete(root, _ckpt_ref(marker.get("change_dir") or args.change_dir, args.slice))
        else:
            # 记红次数：连续 2 次红执行体按纪律停下上报，stop-gate 据此不再强制续跑
            marker["red_count"] = int(marker.get("red_count") or 0) + 1
            try:
                with open(os.path.join(root, MARKER), "w", encoding="utf-8") as f:
                    json.dump(marker, f, ensure_ascii=False)
            except OSError:
                pass
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


def cmd_record(args):
    """integrator 把（在临时 worktree 里跑出的）切片门禁 JSON 幂等写回 change 分支的 gate-report.md / timeline.md。"""
    if args.json:
        try:
            result = json.loads(args.json)
        except ValueError as e:
            die("--json 不是合法 JSON：%s" % e)
    else:
        if not (args.slice and args.commit):
            die("record 需要 --json，或 --slice 与 --commit（可选 --ok/--red --failed --warnings）")
        result = {"slice": args.slice, "ok": not args.red, "commit": args.commit,
                  "failed": [x for x in (args.failed or "").split(";") if x.strip()],
                  "warnings": [x for x in (args.warnings or "").split(";") if x.strip()]}
    result.setdefault("failed", [])
    result.setdefault("warnings", [])
    if result.get("slice"):
        # 结论已交到 integrator 手里，留存的那份完成使命（不存在时静默）
        _ckpt_delete(os.getcwd(), _gate_ref(args.change_dir, result["slice"]))
    if report_has_row(args.change_dir, result.get("slice", ""), result.get("commit", "")):
        print(json.dumps({"recorded": False, "reason": "already recorded"}, ensure_ascii=False))
        return
    append_report(args.change_dir, result)
    # 临时 worktree 里跑出的天花板行同样不会随 commit 进分支，随门禁结论一起写回（幂等由上面的 report_has_row 兜）
    record_ceilings(args.change_dir, result.get("slice", ""),
                    ceiling_rows_from_json(result.get("ceilings")))
    timeline_record(args.change_dir, "gate", "%s %s" % (result.get("slice"), "ok" if result.get("ok") else "red"))
    print(json.dumps({"recorded": True, "slice": result.get("slice"), "commit": result.get("commit")}, ensure_ascii=False))


def _dirty_paths(root, change_dir):
    """工作树里未提交 / 未跟踪的路径，排除本 change 的记账文件与 MARKER。"""
    change_rel = os.path.relpath(os.path.abspath(change_dir), root).replace(os.sep, "/")
    skip = {MARKER} | {"%s/%s" % (change_rel, b) for b in BOOKKEEPING}
    raw = subprocess.run(["git", "status", "--porcelain", "-z", "--untracked-files=all"], cwd=root,
                         capture_output=True, text=True).stdout
    paths, rename = [], False
    for e in raw.split("\0"):
        if rename:  # 重命名 / 复制项后随原路径
            rename = False
            continue
        if len(e) < 4:
            continue
        rename = e[0] in "RC"
        if e[3:] not in skip:
            paths.append(e[3:])
    return sorted(paths)


def cmd_final(args):
    root = toplevel()
    data = load_plan(args.change_dir)
    gate = data.get("gate") or {}
    failed, warnings = [], []
    # 先于任何测试运行取证：测的是工作树，合回只带已提交内容
    dirty = _dirty_paths(root, args.change_dir)
    if dirty:
        warnings.append("工作树有未提交改动，结论不对应 commit：%s" % ", ".join(dirty[:8]))
    v7, total, passed, w7 = scenario_status(root, data)
    failed.extend(v7)
    warnings.extend(w7)
    baseline = load_baseline(args.change_dir)
    for key in ("lint", "typecheck"):
        cmd = gate.get(key)
        if cmd:
            f2, w2 = gate_cmd_verdict(key, cmd, root, baseline)
            if f2:
                failed.append(f2)
            if w2:
                warnings.append(w2)
    if v7:
        warnings.append("G2 全量未跑：G7 已红，scenario 全绿后重跑 final")
    else:
        test_cmd = gate.get("test") or detect_test_cmd(root)
        if not test_cmd:
            warnings.append("未配置也未探测到全量测试命令")
        else:
            f2, w2 = full_suite_verdict(test_cmd, root, baseline)
            if f2:
                failed.append(f2)
            if w2:
                warnings.append(w2)
    result = {"slice": "final", "ok": not failed, "commit": git(root, "rev-parse", "HEAD"),
              "failed": failed, "warnings": warnings,
              "scenarios": {"total": total, "passed": passed if not failed else min(passed, total - len(v7))},
              "summary": "final %s：scenario %d/%d" % ("通过" if not failed else "阻断", passed, total)}
    if dirty:
        result["dirty"] = True
    append_report(args.change_dir, result)
    timeline_record(args.change_dir, "final", "ok" if result["ok"] else "red")
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


def cmd_baseline(args):
    root = toplevel()
    data = load_plan(args.change_dir)
    gate = data.setdefault("gate", {})
    test_cmd = gate.get("test") or detect_test_cmd(root)
    if not test_cmd:
        die("未配置也未探测到全量测试命令")
    gate["test"] = test_cmd
    sha0 = plan_sha(data)
    name = os.path.basename(os.path.realpath(args.change_dir))
    change_rel = _change_rel(root, args.change_dir)
    # 开跑前（覆盖成运行标记之前）：旧基线（运行标记不算；--full 也要读它的 byproducts）、开始快照、命令指纹
    old = load_baseline(args.change_dir)
    if not isinstance(old, dict) or old.get("running") is True:
        old = None
    try:
        s0 = _snapshot(root, change_rel)
        key = cmd_key(root, change_rel, test_cmd)
    except RuntimeError as e:  # design D12：不写运行标记，不碰现有 gate-baseline.json
        die("内容快照失败：%s" % e)
    # 运行标记：preflight 据此分辨「还在跑」与「跑到一半中断」，不把半成品当缺基线
    with open(os.path.join(args.change_dir, BASELINE), "w", encoding="utf-8") as f:
        json.dump({"running": True, "pid": os.getpid(), "started": now_iso()}, f, ensure_ascii=False)
        f.write("\n")
    cands = _baseline_candidates(root, old, key, name, args.full)
    # 本 change 旧基线候选是 dict(old, …) 的浅拷贝，与 old 共用 snapshot 对象；池候选各自读盘，不会共用
    own = cands[0] if cands and old is not None and cands[0].get("snapshot") is old.get("snapshot") else None
    hit, src, skipped, rerun_cache = None, None, [], {}
    for cand in cands:
        hit, why, abort = _try_reuse(root, args.change_dir, data, cand, s0, key, rerun_cache)
        if hit is not None:
            src = cand
            break
        skipped.append({"change": cand.get("change"), "commit": str(cand.get("commit") or "")[:12], "reason": why})
        if abort:  # 补跑红 / 超时 / 异常退出码与候选无关，直接走全量（design D3）
            break
    reasons, warnings, out = [], [], ""
    bl = {"commit": git(root, "rev-parse", "HEAD"), "at": now_iso(), "plan_sha": None,
          "ok": None, "reasons": reasons}
    if hit is not None:
        ct = src.get("test") or {}
        bl["test"] = {k: ct[k] for k in ("exit", "sec", "failed") if k in ct}
        if isinstance(ct.get("failed"), list) and ct["failed"]:
            warnings.append("预存红 %d 条（沿用 %s 的全量），final 按基线差分" % (len(ct["failed"]), src.get("change")))
    else:
        t0 = time.time()
        tg = run_test_gate(test_cmd, root)
        rc, out = tg["rc"], tg["out"]
        gate["full_suite_sec"] = round(time.time() - t0, 1)
        bl["test"] = {"exit": rc, "sec": gate["full_suite_sec"]}
        if rc != 0 and tg["failed"] is not None:
            bl["test"]["failed"] = tg["failed"]
            warnings.append("预存红 %d 条已记录，final 按基线差分" % len(tg["failed"]))
        elif rc != 0:
            reasons.append("全量测试在基线上红（exit %d；按退出码判：%s）" % (rc, tg["why"]))
    # lint / typecheck 沿用（design D10）：只看本 change 旧基线；严格差异（含其他 change 目录）为空且命令与指纹不变
    strict_delta = None
    if hit is not None and src is own:
        strict_delta = _delta(root, own, s0, bl["commit"], change_rel, True, strict=True)
    for kind in ("lint", "typecheck"):
        cmd = gate.get(kind)
        if cmd:
            kkey = cmd_key(root, change_rel, cmd)
            ok_ = old.get(kind) if isinstance(old, dict) else None
            if (strict_delta == [] and kkey and isinstance(ok_, dict) and "exit" in ok_
                    and ok_.get("cmd") == cmd and ok_.get("key") == kkey):
                bl[kind] = {"exit": ok_["exit"], "lines": ok_.get("lines") or [], "cmd": cmd, "key": kkey,
                            "reused": True}
                continue
            krc, kout = run_cmd_full(cmd, root)
            bl[kind] = {"exit": krc, "lines": normalize_lines(kout) if krc != 0 else [], "cmd": cmd, "key": kkey}
        else:
            bl[kind] = None
    bl["verify"] = {}
    # 增量时只有候选是本 change 的旧基线才有上一次的 verify 可沿用（design D7）；跨 change 候选全部重跑
    prev = (old.get("verify") or {}) if hit is not None and src is own else {}
    # 本次跑了全量且 gate.test 是可推导的直接 pytest 调用 → 可推导的 verify 按全量 junit 判（design D11）
    full_head = None
    if hit is None:
        fh = _pytest_head(test_cmd)
        if fh is not None and _derive_paths(fh[1]) is not None:
            full_head = fh[0]
    derived = 0
    for s in data.get("slices") or []:
        vcmd = s.get("verify")
        pv = prev.get(s["id"])
        if hit is not None and not _verify_rerun(root, vcmd, pv, hit["files"]):
            bl["verify"][s["id"]] = {"exit": pv.get("exit"), "cmd": vcmd, "reused": True}
            continue
        if hit is None and _derive_verify(root, full_head, vcmd, tg.get("cases"), tg["failed"]):
            bl["verify"][s["id"]] = {"exit": 0, "cmd": vcmd, "derived": "full"}
            derived += 1
            continue
        vrc, _ = run_cmd_full(vcmd or "false", root)
        bl["verify"][s["id"]] = {"exit": vrc, "cmd": vcmd}
        if vrc != 0:
            reasons.append("%s verify 在基线上红（exit %d）：命令不可运行或含既有错误" % (s["id"], vrc))
    # 运行期间的改动（design D6）
    s1, byproducts = None, []
    try:
        s1 = _snapshot(root, change_rel)
        reasons_d6, warnings_d6, byproducts = _run_changes(root, change_rel, s0, s1, (old or {}).get("byproducts"))
        reasons.extend(reasons_d6)
        warnings.extend(warnings_d6)
    except RuntimeError as e:  # design D12：运行标记一定被结果覆盖
        reasons.append("基线结束时内容快照失败：%s；重跑 baseline" % e)
    # 后台跑期间人可能改了 slices.json：重读当前文件，只写回耗时，不拿开跑时的旧数据整份覆盖
    cur = load_plan(args.change_dir)
    cg = cur.setdefault("gate", {})
    if not cg.get("test"):
        cg["test"] = test_cmd
    if hit is None:
        cg["full_suite_sec"] = gate["full_suite_sec"]
    elif cg.get("full_suite_sec") is None:  # 增量不改已有耗时；本 change 还没有时写候选的（design D9）
        cg["full_suite_sec"] = (src.get("test") or {}).get("sec")
    save_plan(args.change_dir, cur)
    bl["plan_sha"] = sha0
    if plan_sha(cur) != sha0:
        reasons.append("基线运行期间 gate / verify 被修改，重跑 baseline")
    if warnings:
        bl["warnings"] = warnings
    bl.update({"change": name, "mode": "incremental" if hit is not None else "full", "snapshot": s1,
               "cmd_key": key, "byproducts": byproducts})
    if hit is not None:
        bl["incremental"] = hit
    elif skipped:
        bl["reuse_skipped"] = skipped[:5]
    bl["ok"] = not reasons
    # 入池（design D5）：只收全绿的全量；带预存红的跨 change 用不上，指纹为空的匹配不到
    if hit is None and bl["ok"] and bl["test"].get("exit") == 0 and key:
        w = _pool_write(root, {k: bl.get(k) for k in
                               ("change", "commit", "at", "ok", "cmd_key", "snapshot", "byproducts", "test")})
        if w:
            warnings.append(w)
            bl["warnings"] = warnings
    with open(os.path.join(args.change_dir, BASELINE), "w", encoding="utf-8") as f:
        json.dump(bl, f, ensure_ascii=False, indent=2)
        f.write("\n")
    t, verdict = bl["test"], "ok" if bl["ok"] else "red"
    if hit is not None:
        note = "增量（复用 %s 的全量 exit %s, %ss；补跑 %d 个测试文件 %ss） %s" % (
            hit["from"].get("change"), t.get("exit"), t.get("sec"), len(hit["files"]), hit["sec"], verdict)
    else:
        note = "exit %s, %ss %s" % (t.get("exit"), t.get("sec"), verdict)
        if derived:
            note += "；verify 推导 %d 片" % derived
    timeline_record(args.change_dir, "baseline", note)
    print(json.dumps(dict(bl, test_cmd=test_cmd, tail=_tail(out)), ensure_ascii=False))
    sys.exit(0 if bl["ok"] else 1)


def _die_running_baseline(change_dir, bl, data):
    """gate-baseline.json 仍是运行标记：进程活着 → 等；进程已不在 / pid 不合法 → 中断，重跑。"""
    pid = bl.get("pid")
    alive = False
    if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
        try:
            os.kill(pid, 0)
            alive = True
        except PermissionError:
            alive = True
        except OSError:  # ProcessLookupError 等：进程已不在
            alive = False
    if not alive:
        die("基线中断（进程 %s 已不在）：重跑 slice-gate.py baseline --change-dir %s" % (pid, change_dir))
    try:
        started = datetime.strptime(bl.get("started") or "", "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        mins = "%d" % ((datetime.now(timezone.utc) - started).total_seconds() // 60)
    except ValueError:
        mins = "?"
    sec = (data.get("gate") or {}).get("full_suite_sec")
    est = "%s 秒" % sec if isinstance(sec, (int, float)) and not isinstance(sec, bool) else "未知"
    die("基线仍在跑（已 %s 分钟，上次全量约 %s）：等它结束再起飞" % (mins, est))


def cmd_preflight(args):
    """起飞前四项校验：计划合法、基线存在且绿、基线未过期、基线 commit 在当前分支历史。通过打印 waves。"""
    root = toplevel()
    data = load_plan(args.change_dir)
    errors, waves = lint_plan(data)
    if errors:
        die("slices.json 不合法：\n  - " + "\n  - ".join(errors))
    bl = load_baseline(args.change_dir)
    if isinstance(bl, dict) and bl.get("running") is True:
        _die_running_baseline(args.change_dir, bl, data)
    if bl is None:
        die("缺基线：先运行 slice-gate.py baseline --change-dir %s" % args.change_dir)
    if not bl.get("ok"):
        die("基线红，不能起飞：\n  - " + "\n  - ".join(bl.get("reasons") or ["ok 为 false 但无 reasons"]))
    if bl.get("plan_sha") != plan_sha(data):
        die("基线过期：gate / verify 改动后需重跑 baseline")
    # 不能用 git()：--is-ancestor 不成立时退出 1，git() 会当成异常抛
    p = subprocess.run(["git", "merge-base", "--is-ancestor", str(bl.get("commit") or ""), "HEAD"],
                       cwd=root, capture_output=True, text=True)
    if p.returncode != 0:
        die("基线 commit 不在当前分支历史：%s（重跑 baseline）" % (bl.get("commit") or "?")[:10])
    # 按内容判过期（design D8）：只在首次起飞前；旧格式基线（无 snapshot）与已 approve 的 change 只做四项校验
    if isinstance(bl.get("snapshot"), dict) and not _has_approve(args.change_dir):
        change_rel = _change_rel(root, args.change_dir)
        try:
            delta = _delta(root, bl, _snapshot(root, change_rel), git(root, "rev-parse", "HEAD"), change_rel, True)
        except RuntimeError as e:
            die("基线内容比对失败：%s；重跑 baseline" % e)
        if delta is None:  # 上面已校验基线 commit 是 HEAD 的祖先，此处 None 只能是 git 调用失败（fail-closed）
            die("基线内容比对失败：git 调用出错；重跑 baseline")
        if delta:
            die("基线过期：自基线以来有改动：%s；重跑 baseline（只改了测试文件时走增量）" % ", ".join(delta[:8]))
    print(json.dumps(waves, ensure_ascii=False))


def _has_approve(change_dir):
    """本 change 的 timeline.md 里有没有事件列为 approve 的行；文件不存在或读不出 → 没有（更严，design D8）。"""
    try:
        with open(os.path.join(change_dir, TIMELINE), "r", encoding="utf-8") as f:
            return any(len(cols) > 1 and cols[1] == "approve" for cols in (line.rstrip("\n").split("\t") for line in f))
    except (OSError, ValueError):
        return False


def report_latest(change_dir):
    """gate-report.md 按切片取最后一行：{slice: {"ok": bool, "commit": 10位, "failed": str}}。"""
    path = os.path.join(change_dir, REPORT)
    latest = {}
    if not os.path.isfile(path):
        return latest
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cols) >= 5 and cols[2] in ("ok", "red"):
                latest[cols[1]] = {"ok": cols[2] == "ok", "commit": cols[3], "failed": cols[4]}
    return latest


BOOKKEEPING = ("timeline.md", "gate-report.md", "evidence.log", "review-findings.json", "tasks.md",
               "slices/_interfaces.md")


# ---------------------------------------------------------------- 基线内容指纹与增量复用（design D1–D4、D6–D9、D12）

# 本 change 的计划工件：不进 snapshot、不计入 Δ（design D2）
PLAN_FILES = ("proposal.md", "design.md", "tasks.md", "slices.json", "spec.html", BASELINE, ".openspec.yaml") + BOOKKEEPING
PLAN_DIRS = ("specs/", "slices/")
LS_TREE_BATCH = 500


def _change_rel(root, change_dir):
    return os.path.relpath(os.path.realpath(change_dir), os.path.realpath(root)).replace(os.sep, "/")


def _plan_file(rel, change_rel):
    if not rel.startswith(change_rel + "/"):
        return False
    rest = rel[len(change_rel) + 1:]
    return rest in PLAN_FILES or rest.startswith(PLAN_DIRS)


def _other_change(rel, change_rel, keep_own=True):
    """路径在 <changes 根>（change 目录的上一级）下；keep_own 时本 change 目录里的不算。"""
    if "/" not in change_rel:
        return False
    changes_root = change_rel.rsplit("/", 1)[0]
    return rel.startswith(changes_root + "/") and not (keep_own and rel.startswith(change_rel + "/"))


def _ignored(rel):
    """测试副产物：字节码与 .pytest_cache，不影响结果。"""
    return is_bytecode(rel) or ".pytest_cache" in rel.split("/")


def _git_raw(root, args, stdin=None):
    """不 strip 的 git 调用（-z 输出要原样保留）；非 0 抛 RuntimeError。"""
    p = subprocess.run(["git", *args], cwd=root, input=stdin, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("git %s: %s" % (" ".join(args[:3]), p.stderr.strip()))
    return p.stdout


def _hash_paths(root, rels):
    """一次 git hash-object --stdin-paths 批量取 blob id，与 rels 同序。"""
    if not rels:
        return []
    return _git_raw(root, ["hash-object", "--stdin-paths"], "\n".join(rels) + "\n").split()


def _snapshot(root, change_rel):
    """工作区相对 HEAD 的未提交改动 {路径: blob id | None（删除）}；不含字节码、.pytest_cache 与本 change 的计划工件。
    软链按链接文本取 blob（与 git 树里的表示一致，断链也不抛错，design D1）。git 失败抛 RuntimeError。"""
    entries, paths, i = _git_raw(root, ["status", "--porcelain", "-z", "--untracked-files=all"]).split("\0"), set(), 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        paths.add(e[3:])
        if "R" in e[:2] or "C" in e[:2]:  # 改名 / 复制项后随原路径：两边都记，原路径按是否存在取值
            if i < len(entries) and entries[i]:
                paths.add(entries[i])
            i += 1
    snap, present = {}, []
    for p in sorted(paths):
        if _ignored(p) or _plan_file(p, change_rel):
            continue
        full = os.path.join(root, p)
        if os.path.islink(full):
            snap[p] = _git_raw(root, ["hash-object", "--stdin"], os.readlink(full)).strip()
        elif os.path.isfile(full):
            present.append(p)
        elif not os.path.exists(full):
            snap[p] = None
        # 目录（嵌套仓库 / 子模块）不记
    for p, b in zip(present, _hash_paths(root, present)):
        snap[p] = b
    return snap


def _blobs_at(root, commit, paths):
    """{路径: commit 里的 blob id | None}；ls-tree 每批至多 LS_TREE_BATCH 个路径。"""
    paths = list(paths)
    out = {p: None for p in paths}
    for i in range(0, len(paths), LS_TREE_BATCH):
        raw = _git_raw(root, ["ls-tree", "-r", "-z", commit, "--", *paths[i:i + LS_TREE_BATCH]])
        for e in raw.split("\0"):
            if "\t" not in e:
                continue
            meta, path = e.split("\t", 1)
            if path in out:
                out[path] = meta.split()[2]
    return out


def _repo_rel(root, tok):
    """词指向仓库内（相对 root，或 root 之下的绝对路径）时返回仓库相对路径，否则 None；不检查存在。"""
    if not tok or tok.startswith("-"):
        return None
    if os.path.isabs(tok):
        base, r = os.path.realpath(root), os.path.realpath(tok)
        if r != base and not r.startswith(base + os.sep):
            return None
        rel = os.path.relpath(r, base)
    else:
        rel = os.path.normpath(tok)
    rel = rel.replace(os.sep, "/")
    if rel == ".." or rel.startswith("../"):
        return None
    return rel


def cmd_key(root, change_rel, cmd):
    """全量命令指纹（design D4）：归一命令文本 + 命令里直接写出的仓库内文件的 blob id；切词失败返回 None。"""
    try:
        toks = shlex.split(cmd or "")
    except ValueError:
        return None

    def norm(s):
        return s.replace(change_rel, "<change>") if change_rel else s

    files = []
    for tok in toks:
        rel = _repo_rel(root, tok)
        if rel and os.path.isfile(os.path.join(root, rel)):
            files.append((norm(tok), rel))
    pairs = [[t, b] for (t, _), b in zip(files, _hash_paths(root, [r for _, r in files]))]
    return hashlib.sha1(json.dumps([norm(cmd or ""), pairs], ensure_ascii=False, sort_keys=True)
                        .encode("utf-8")).hexdigest()


def _delta(root, cand, cur_snap, head, change_rel, same_change, strict=False):
    """候选所测代码树 vs 当前代码树按 blob 比较（design D1、D2）；候选 commit 不是 HEAD 的祖先或 git 失败 → None。
    候选 byproducts 里在候选 commit 与 HEAD 都未跟踪的路径不计；strict=True 时 <changes 根> 下其他 change 的路径也计入（design D10）。"""
    commit = cand.get("commit")
    if not isinstance(commit, str) or not commit or not _is_ancestor(root, commit, head):
        return None
    old_snap = cand.get("snapshot") or {}
    byp = set(cand.get("byproducts") or [])
    try:
        names = [n for n in _git_raw(root, ["diff", "--name-only", "--no-renames", "-z", commit, head]).split("\0") if n]
    except RuntimeError:
        return None
    keep = [p for p in set(names) | set(old_snap) | set(cur_snap)
            if not (_ignored(p) or _plan_file(p, change_rel) or (not strict and _other_change(p, change_rel, same_change)))]
    try:
        old_b = _blobs_at(root, commit, [p for p in keep if p not in old_snap or p in byp])
        new_b = _blobs_at(root, head, [p for p in keep if p not in cur_snap or p in byp])
    except RuntimeError:
        return None
    return sorted(p for p in keep
                  if not (p in byp and old_b.get(p) is None and new_b.get(p) is None)
                  and (old_snap[p] if p in old_snap else old_b.get(p)) != (cur_snap[p] if p in cur_snap else new_b.get(p)))


def _baseline_candidates(root, old, key, name, full):
    """可复用候选，按优先级排：本 change 旧基线（有 snapshot、非运行标记）在前，池候选在后（design D5）；--full 时没有候选。"""
    if full:
        return []
    cands = []
    if isinstance(old, dict) and old.get("running") is not True and isinstance(old.get("snapshot"), dict):
        cands.append(dict(old, change=old.get("change") or name))
    return cands + _pool_candidates(root, key)


# ---------------------------------------------------------------- 基线池（design D5）

POOL_DIR = "flight-baseline-pool"
POOL_KEEP = 30
POOL_TMP_TTL = 3600  # .tmp- 残留超过这么久（秒）视为崩溃遗留，清掉


def _pool_dir(root):
    """git common dir 下的基线池目录（同仓各 worktree 共享）；相对路径按 root 解析成绝对路径。"""
    common = git(root, "rev-parse", "--git-common-dir")
    return os.path.join(common if os.path.isabs(common) else os.path.join(root, common), POOL_DIR)


def _pool_order(name, entry):
    """排序键：at 去掉符号（读不出时用文件名，文件名以它开头），由旧到新可比。"""
    at = entry.get("at") if isinstance(entry, dict) else None
    return re.sub(r"[^0-9A-Za-z]", "", at) if isinstance(at, str) and at else name


def _pool_read(pdir, name):
    try:
        with open(os.path.join(pdir, name), encoding="utf-8") as f:
            e = json.load(f)
    except (OSError, ValueError):
        return None
    return e if isinstance(e, dict) else None


def _pool_write(root, entry):
    """原子写一条池记录（临时文件 + os.replace），再按 at 只留最新 POOL_KEEP 条、清掉过期 .tmp- 残留；
    失败返回警告文本，成功返回 None。"""
    try:
        pdir = _pool_dir(root)
        os.makedirs(pdir, exist_ok=True)
        stamp = re.sub(r"[^0-9A-Za-z]", "", str(entry.get("at") or ""))
        name = "%s-%s-%s.json" % (stamp, entry.get("change"), str(entry.get("commit") or "")[:12])
        fd, tmp = tempfile.mkstemp(dir=pdir, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp, os.path.join(pdir, name))
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        all_names = os.listdir(pdir)
        names = [n for n in all_names if n.endswith(".json") and not n.startswith(".tmp-")]
        names.sort(key=lambda n: _pool_order(n, _pool_read(pdir, n)), reverse=True)
        drop = names[POOL_KEEP:]
        cutoff = time.time() - POOL_TMP_TTL
        for n in all_names:
            if n.startswith(".tmp-"):
                try:
                    if os.path.getmtime(os.path.join(pdir, n)) < cutoff:
                        drop.append(n)
                except FileNotFoundError:
                    pass
        for n in drop:
            try:
                os.unlink(os.path.join(pdir, n))
            except FileNotFoundError:  # 别的 worktree 同时在清理
                pass
    except (OSError, RuntimeError) as e:
        return "基线池写入失败（不影响本次基线）：%s" % e
    return None


def _pool_candidates(root, key, limit=10):
    """池里 cmd_key == key 的条目，按 at 由新到旧取前 limit 个；坏 JSON 跳过，池不可读返回 []。"""
    if not key:
        return []
    try:
        pdir = _pool_dir(root)
        names = [n for n in os.listdir(pdir) if n.endswith(".json") and not n.startswith(".tmp-")]
    except (OSError, RuntimeError):
        return []
    hits = []
    for n in names:
        e = _pool_read(pdir, n)
        if e is not None and e.get("cmd_key") == key:
            hits.append((_pool_order(n, e), e))
    hits.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in hits[:limit]]


def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache):
    """复用判定（design D3）：返回 (hit | None, 不复用的理由, abort)；hit = {"from", "files", "sec"}。
    补跑结果按 Δ 现存测试文件的 (路径, 当前 blob) 记进 rerun_cache；补跑红 / 超时 / 异常退出码 → abort=True。"""
    if not isinstance(cand, dict) or cand.get("ok") is not True:
        return None, "候选基线不是绿", False
    test = cand.get("test") or {}
    if not (test.get("exit") == 0 or isinstance(test.get("failed"), list)):
        return None, "候选测试结果不可度量", False
    if not key or cand.get("cmd_key") != key:
        return None, "cmd_key 不同", False
    same = cand.get("change") == os.path.basename(os.path.realpath(change_dir))
    if not same and test.get("exit") != 0:
        return None, "跨 change 候选有预存红（只复用全绿的全量）", False
    change_rel = _change_rel(root, change_dir)
    try:
        head = git(root, "rev-parse", "HEAD")
    except RuntimeError as e:
        return None, "内容比对失败：%s" % e, False
    delta = _delta(root, cand, cur_snap, head, change_rel, same)
    if delta is None:
        return None, "候选 commit 不是 HEAD 的祖先，或内容比对失败", False
    other = [p for p in delta if not fnmatch.fnmatchcase(p.rsplit("/", 1)[-1], "test_*.py")]
    if other:
        return None, "有非测试文件改动：%s" % ", ".join(other[:8]), False
    stems = {p.rsplit("/", 1)[-1][:-3] for p in delta}
    for f in test.get("failed") or []:
        if stems & set(str(f).split("::", 1)[0].split(".")):
            return None, "改动的测试文件有预存红：%s" % f, False
    files = [p for p in delta if os.path.isfile(os.path.join(root, p))]
    sec = 0
    if files:
        try:
            ck = tuple(sorted(zip(files, _hash_paths(root, files))))
        except RuntimeError as e:
            return None, "补跑前取内容失败：%s" % e, False
        if ck not in rerun_cache:
            t0 = time.time()
            outcomes, rc, _, timed_out = _pytest_outcomes(root, files, data.get("gate") or {})
            bad = [n for n, o in outcomes if o in ("FAILED", "ERROR")]
            why = ("补跑超时" if timed_out else "补跑红：%s" % ", ".join(bad[:8]) if bad
                   else "补跑 exit %s" % rc if rc not in (0, 5) else None)
            rerun_cache[ck] = (why is None, why, round(time.time() - t0, 1))
        ok, why, sec = rerun_cache[ck]
        if not ok:
            return None, why, True
    return {"from": {"change": cand.get("change"), "commit": cand.get("commit"), "at": cand.get("at")},
            "files": delta, "sec": sec}, None, False


def _run_changes(root, change_rel, s0, s1, prev_byproducts):
    """运行期间的改动（design D6）→ (reasons, warnings, byproducts)。
    先去掉 <changes 根> 下非本 change 的路径；上一次 byproducts 里未跟踪的非测试路径被改写、或新出现的非测试文件 → 只警告并登记；
    其余（开始就存在、已跟踪、测试文件）→ 判红。git 失败抛 RuntimeError。"""
    prev = set(prev_byproducts or []) if isinstance(prev_byproducts, list) else set()
    moved = sorted(p for p in set(s0) | set(s1)
                   if s0.get(p, "-") != s1.get(p, "-") and not _other_change(p, change_rel))
    at_head = _blobs_at(root, "HEAD", [p for p in moved if p not in s0 or p in prev])
    reasons, warnings, byp = [], [], {p for p in prev if p in s1}
    for p in moved:
        tracked = at_head.get(p) is not None
        if p in prev and not is_test_path(p) and not tracked:
            warnings.append("基线运行期间副产物 %s 被改写" % p)
            byp.add(p)
        elif p in s0 or tracked or is_test_path(p):
            reasons.append("基线运行期间 %s 被修改，重跑 baseline" % p)
        else:
            warnings.append("基线运行期间新出现 %s（视为运行副产物）" % p)
            byp.add(p)
    return reasons, warnings, sorted(byp)


def _verify_paths(root, cmd, delta):
    """verify 命令里认得出的路径（design D7）：切词、去掉 :: 之后的部分，仓库内已存在或等于 Δ 路径。"""
    try:
        toks = shlex.split(cmd or "")
    except ValueError:
        return []
    out = []
    for tok in toks:
        rel = _repo_rel(root, tok.split("::", 1)[0])
        if rel and (rel in delta or os.path.exists(os.path.join(root, rel))):
            out.append(rel)
    return out


def _verify_rerun(root, cmd, prev, delta):
    """增量时这一片要不要重跑 verify：没有上一次记录 / cmd 变了 / 认不出路径 / 路径覆盖到 Δ。"""
    if not isinstance(prev, dict) or prev.get("cmd") != cmd:
        return True
    paths = _verify_paths(root, cmd, delta)
    if not paths:
        return True
    return any(p == "." or f == p or f.startswith(p + "/") for p in paths for f in delta)


def _final_fresh(root, change_dir, final_commit):
    """final 之后的 commit 只改了 changes 根下任一 change 的记账文件 → 仍算新鲜；任一 git 调用失败 → 不新鲜。"""
    if not _is_ancestor(root, final_commit, "HEAD"):
        return False
    try:
        names = git(root, "diff", "--name-only", final_commit, "HEAD").splitlines()
    except RuntimeError:
        return False
    changes_rel = os.path.relpath(os.path.dirname(os.path.abspath(change_dir)), root).replace(os.sep, "/")
    prefix = changes_rel + "/"

    def bookkeeping(n):
        if not n.startswith(prefix):
            return False
        parts = n[len(prefix):].split("/", 1)
        return len(parts) == 2 and parts[1] in BOOKKEEPING

    return all(bookkeeping(n) for n in names if n)


def cmd_ship(args):
    """draft / ready 裁决：只读 gate-report.md、HEAD、review-findings.json；工作流的 blocked 只作说明。"""
    root = toplevel()
    head = git(root, "rev-parse", "HEAD")
    reasons = []
    findings = {}
    fpath = os.path.join(args.change_dir, "review-findings.json")
    if os.path.isfile(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            findings = json.load(f) or {}
    plan_path = os.path.join(args.change_dir, "slices.json")
    if os.path.isfile(plan_path):
        data = load_plan(args.change_dir)
        latest = report_latest(args.change_dir)
        for s in data.get("slices") or []:
            row = latest.get(s["id"])
            if row is None:
                reasons.append("切片 %s 无门禁记录" % s["id"])
            elif not row["ok"]:
                reasons.append("切片 %s 门禁红：%s" % (s["id"], row["failed"]))
        final = latest.get("final")
        if final is None:
            reasons.append("final 未运行")
        elif not final["ok"]:
            reasons.append("final 红：%s" % final["failed"])
        elif final["commit"] != head[:10] and not _final_fresh(root, args.change_dir, final["commit"]):
            reasons.append("final 过期：记录 %s，HEAD %s" % (final["commit"], head[:10]))
    # 铁律 4：CRITICAL/HIGH 未闭环不得非 draft —— 与是否飞行模式无关，无条件检查
    blocking = findings.get("blocking") or []
    if blocking:
        reasons.append("%d 条 CRITICAL/HIGH 评审未闭环" % len(blocking))
    blocked = findings.get("blocked") or []
    result = {"ready": not reasons, "commit": head, "reasons": reasons, "blocked": blocked}
    timeline_record(args.change_dir, "ship", "ready" if result["ready"] else "draft: " + "; ".join(reasons))
    if args.markdown:
        parts = []
        if reasons:
            parts.append("## 飞行门禁未全绿\n\n" + "\n".join("- %s" % r for r in reasons))
        if blocked:
            parts.append("### 飞行中记 blocked 的切片\n\n" + "\n".join(
                "- %s（%s）：%s" % (b.get("slice", "?"), b.get("kind", "infra"), b.get("reason", "")) for b in blocked))
        print("\n\n".join(parts))
    else:
        print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ready"] else 1)


def main():
    ap = argparse.ArgumentParser(description="slice-gate：切片规划 lint 与切片门禁")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("lint", "waves", "final", "baseline", "preflight"):
        p = sub.add_parser(name)
        p.add_argument("--change-dir", required=True)
        if name == "baseline":
            p.add_argument("--full", action="store_true", help="不复用旧基线，强制跑全量 gate.test")
    p = sub.add_parser("start")
    p.add_argument("slice")
    p.add_argument("--change-dir", required=True)
    p.add_argument("--base", help="区间起点；默认 HEAD（临时 worktree 里从分支 commit 分叉时由派发方传入）")
    p.add_argument("--expect-branch", help="基点校验：HEAD 须是该分支最新 commit 的后代，否则 G0 拒绝起跑")
    p.add_argument("--resume-checkpoint", action="store_true",
                   help="重派：无同片标记时把 refs/flight/<change>/<S> 快照恢复为未提交改动（基点须在快照祖先链上）")
    sub.add_parser("checkpoint", help="PostToolUse hook：stdin 载荷取 cwd，把本片 owns 内改动快照到 refs/flight/<change>/<S>；永远静默 exit 0")
    p = sub.add_parser("gate")
    p.add_argument("slice")
    p.add_argument("--change-dir", required=True)
    p.add_argument("--base")
    p = sub.add_parser("record", help="把切片门禁 JSON 幂等写回 gate-report.md / timeline.md（integrator 合回并行切片时用）")
    p.add_argument("--change-dir", required=True)
    p.add_argument("--json")
    p.add_argument("--slice")
    p.add_argument("--commit")
    p.add_argument("--red", action="store_true")
    p.add_argument("--failed")
    p.add_argument("--warnings")
    p = sub.add_parser("ship", help="draft / ready 裁决：读 gate-report.md + HEAD + review-findings.json；退出码 0 ready / 1 draft")
    p.add_argument("--change-dir", required=True)
    p.add_argument("--markdown", action="store_true", help="打印可贴入 PR 正文的段落而不是 JSON")
    args = ap.parse_args()
    {"lint": cmd_lint, "waves": cmd_lint, "start": cmd_start, "gate": cmd_gate, "record": cmd_record,
     "final": cmd_final, "baseline": cmd_baseline, "preflight": cmd_preflight, "ship": cmd_ship,
     "checkpoint": cmd_checkpoint}[args.cmd](args)


if __name__ == "__main__":
    main()
