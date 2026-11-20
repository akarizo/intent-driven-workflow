#!/usr/bin/env python3
# flight-doctor · 测试成本的预告 / 归因 / 体检（unified-test-result-reuse design D12；只读，恒 exit 0）
#
# CLI:
#   flight-doctor.py forecast --change-dir DIR [--json]   起飞前预告 baseline / final 走全量还是增量
#   flight-doctor.py cost --change-dir DIR [--json]       从 timeline.md 归因每一次全量（必要 / 可避免 / 未分类）
#                                                         另读备注里的「测试 Xs」（全量 final 秒数）与「排队 Xs」（按事件累加到 wait_sec）
#                                                         wave-check 事件另汇总到 wave（次数 / 守护秒 / 测试秒 / 跳过测试次数）
#   flight-doctor.py doctor [--openspec-root DIR]         项目级体检：[runner] [anchors] [gate.test] [declare] [checks] [lock] [tests] [routing]
#                                                         [declare] 声明了 inert 时另与锚点池的依赖图对账，列出矛盾
#                                                         [tests] 分层文件写了预算 / 放行时另列各范围预算对实际、区域超线条数与放行到期
#                                                         [routing] 调用 model-routing.py frontmatter --check（只读），报 fork 命令 frontmatter 漂移
#
# 判定逻辑不复制：经 importlib 按路径加载同目录的 slice-gate.py，只调用它的 load_plan / load_baseline /
# final_forecast / suite_sec / git（final 预告与 ship 的补跑预告共用 final_forecast）；inert 对账另调
# _git_top / _git_raw / _inert_ctx / _inert_paths / _pool_order。
# [lock] 同法加载 flight-lock.py，只调用 holders() / lock_dir()（machine-test-lock design D7、D10）。
# [tests] 同法加载 test-ledger.py，只调用 load / summary / parse_segment / segment / _sort_key / budget（test-ledger design D11）；
# 预算与放行另调 slice-gate.py 的 _load_tiers_file / tier_parts / tier_budgets / budget_scope_of / allow_view（tier-budgets）。
# 纯标准库，兼容 Python 3.9。
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))

# cost 的全量原因归类表（design D12）：按序取第一个命中的关键词；认不出 → 未分类
COST_CLASSES = (
    ("依赖图未测", "可避免"),
    ("plugins-dropped", "可避免"),
    ("plugin-import-failed", "可避免"),
    ("not-pytest", "可避免"),
    ("incomplete", "可避免"),
    ("候选基线不是绿", "可避免"),
    ("预存红", "可避免"),
    ("cmd_key 不同", "可避免"),
    ("有非测试文件改动", "可避免"),
    ("--full", "必要"),
    ("全局文件", "必要"),
    ("全局路径", "必要"),
    ("锚点链已达上限", "必要"),
    ("恒全量", "必要"),
    ("多部件分层", "必要"),
    ("锚点池为空", "必要"),
    ("没有可用锚点", "必要"),
)
UNCLASSIFIED = "未分类"
TIMELINE = "timeline.md"
BASELINE = "gate-baseline.json"
SCOPE_FILE = "gate-scope.json"
ANCHOR_DIR = "flight-anchors"
DECLARE_KEYS = ("global", "blind", "inert", "anchor_max_hops")
SEC_RE = re.compile(r"exit -?\d+, ([\d.]+)s")
TEST_RE = re.compile(r"测试 ([\d.]+)s")
WAIT_RE = re.compile(r"排队 ([\d.]+)s")
CHECKS_RE = re.compile(r"检查 (.+?)(?= · | ok$| red$|$)")
CHECK_ITEM_RE = re.compile(r"^(.+) ([\d.]+)s$")
GUARD_RE = re.compile(r"守护 (.+?)(?= · | ok$| red$|$)")
GUARD_SEC_RE = re.compile(r"(?:^| )([\d.]+)s(?= / |$)")
INC_MARKS = ("增量", "同树沿用")
FULL_MARKS = ("全量：", "全量（")
# [checks] 的「检查耗时接近测试」阈值（design D10，草案）：秒数 ≥ SLOW_CHECK_MIN_SEC 且 ≥ 测试秒数 × SLOW_CHECK_RATIO
SLOW_CHECK_MIN_SEC = 10.0
SLOW_CHECK_RATIO = 0.5


def _load(mod_name, file_name):
    spec = importlib.util.spec_from_file_location(mod_name, os.path.join(HOOKS_DIR, file_name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_gate():
    return _load("slice_gate", "slice-gate.py")


def load_lock():
    return _load("flight_lock", "flight-lock.py")


def load_ledger():
    return _load("test_ledger", "test-ledger.py")


def _err(e):
    """异常 → 人话（slice-gate 的 die 以 SystemExit 退出，原因已写在 stderr）。"""
    if isinstance(e, SystemExit):
        return "slice-gate 退出（%s）" % e.code
    return "%s: %s" % (type(e).__name__, e)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- forecast

def _baseline_part(sg, change_dir):
    bl = sg.load_baseline(change_dir)
    if bl is None:
        return {"mode": "missing", "why": "未跑 baseline" if not os.path.exists(os.path.join(change_dir, BASELINE))
                else "gate-baseline.json 读不了", "sec": None}, None
    if bl.get("running") is True:
        return {"mode": "pending", "why": "baseline 运行中（始于 %s）" % bl.get("started"), "sec": None}, None
    skipped = bl.get("reuse_skipped") or []
    why = skipped[0].get("reason") if skipped and isinstance(skipped[0], dict) else ""
    return {"mode": bl.get("mode") or "full", "why": why or "", "sec": (bl.get("test") or {}).get("sec")}, bl


def forecast(change_dir):
    out = {"baseline": {"mode": "unknown", "why": "", "sec": None},
           "final": {"mode": "unknown", "why": "", "sec": None}, "checks": []}
    try:
        sg = load_gate()
    except (Exception, SystemExit) as e:
        out["baseline"]["why"] = out["final"]["why"] = "slice-gate.py 加载失败：%s" % _err(e)
        return out
    data, baseline = {}, None
    try:
        data = sg.load_plan(change_dir)
        gate = data.get("gate") or {}
        out["final"]["sec"] = sg.suite_sec(change_dir, data)
        checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
        out["checks"] = [c.get("name") for c in checks if isinstance(c, dict) and c.get("name")]
    except (Exception, SystemExit) as e:
        out["final"]["why"] = "slices.json 读不了：%s" % _err(e)
        data = None
    try:
        out["baseline"], baseline = _baseline_part(sg, change_dir)
    except (Exception, SystemExit) as e:
        out["baseline"]["why"] = _err(e)
    if data is not None:
        try:
            out["final"]["mode"], out["final"]["why"] = sg.final_forecast(change_dir, data, baseline)
        except (Exception, SystemExit) as e:
            out["final"]["mode"], out["final"]["why"] = "unknown", _err(e)
    return out


def _paren(why):
    return "（%s）" % why if why else ""


def forecast_line(fc):
    b, f = fc["baseline"], fc["final"]
    fwhy = "，".join(x for x in (f["why"], "约 %s 秒" % f["sec"] if f.get("sec") is not None else "") if x)
    return "测试成本预告：baseline %s%s · final %s%s · 检查 %d 项" % (
        b["mode"], _paren(b["why"]), f["mode"], _paren(fwhy), len(fc["checks"]))


# ---------------------------------------------------------------- cost

def _balanced(text, start):
    """text[start] 是「（」：取到与之配对的「）」之间的文字（不配对取到末尾）。"""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "（":
            depth += 1
        elif text[i] == "）":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return text[start + 1:]


def _first(note, marks):
    hits = [note.find(m) for m in marks if m in note]
    return min(hits) if hits else -1


def classify(reason):
    for kw, cls in COST_CLASSES:
        if kw in reason:
            return cls
    return UNCLASSIFIED


def parse_note(note):
    """timeline 备注 → ("full", 原因, 秒数 | None) | ("incremental", None, None) | None（认不出）。"""
    fi, ii = _first(note, FULL_MARKS), _first(note, INC_MARKS)
    if fi < 0 and ii < 0:
        return None
    if ii >= 0 and (fi < 0 or ii < fi):
        return "incremental", None, None
    if note.startswith("全量：", fi):
        reason = note[fi + len("全量："):].split("；", 1)[0]
    else:
        reason = _balanced(note, fi + len("全量"))
    m = SEC_RE.search(note[:fi])
    return "full", reason.strip(), (float(m.group(1)) if m else None)


def note_costs(note):
    """timeline 备注 → {"test": 秒 | None, "wait": 秒 | None, "checks": {名: 秒}}（design D8 的片段）。"""
    t, w = TEST_RE.search(note), WAIT_RE.search(note)
    checks = {}
    m = CHECKS_RE.search(note)
    for part in (m.group(1).split(" / ") if m else ()):
        item = CHECK_ITEM_RE.match(part.strip())
        if item:
            checks[item.group(1)] = float(item.group(2))
    return {"test": float(t.group(1)) if t else None, "wait": float(w.group(1)) if w else None, "checks": checks}


def cost(change_dir):
    out = {ev: {"full": 0, "incremental": 0, "full_sec": 0.0} for ev in ("baseline", "final")}
    out["full_runs"] = []
    wait = {"baseline": 0.0, "final": 0.0}
    try:
        with open(os.path.join(change_dir, TIMELINE), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 3 or cols[1] not in ("baseline", "final"):
            continue
        nc = note_costs(cols[2])
        wait[cols[1]] += nc["wait"] or 0.0
        parsed = parse_note(cols[2])
        if parsed is None:
            continue
        kind, reason, sec = parsed
        if cols[1] == "final" and nc["test"] is not None:
            sec = nc["test"]
        out[cols[1]][kind] += 1
        if kind == "full":
            out[cols[1]]["full_sec"] += sec or 0.0
            out["full_runs"].append({"event": cols[1], "reason": reason, "class": classify(reason), "sec": sec})
    out["wait_sec"] = {ev: round(s, 1) for ev, s in wait.items()}
    out["wave"] = wave_cost(lines)
    return out


def wave_cost(lines):
    """时间线的 wave-check 行 → {"count", "guard_sec", "test_sec", "skipped"}（wave-integration-guard；不进 baseline / final）。"""
    count, guard, test, skipped = 0, 0.0, 0.0, 0
    for line in lines:
        cols = line.split("\t")
        if len(cols) < 3 or cols[1] != "wave-check":
            continue
        note = cols[2]
        count += 1
        g = GUARD_RE.search(note)
        guard += sum(float(s) for s in GUARD_SEC_RE.findall(g.group(1))) if g else 0.0
        if "测试跳过" in note:
            skipped += 1
        else:
            t = TEST_RE.search(note)
            test += float(t.group(1)) if t else 0.0
    return {"count": count, "guard_sec": round(guard, 1), "test_sec": round(test, 1), "skipped": skipped}


def cost_text(c):
    lines = ["测试成本归因："]
    for ev in ("baseline", "final"):
        s = c[ev]
        lines.append("  %s：全量 %d 次（%.1f 秒）· 增量 %d 次 · 排队 %.1f 秒" % (
            ev, s["full"], s["full_sec"], s["incremental"], c["wait_sec"][ev]))
    for r in c["full_runs"]:
        lines.append("  - %s 全量 [%s]：%s%s" % (r["event"], r["class"], r["reason"] or "（无原因）",
                                               "（%s 秒）" % r["sec"] if r["sec"] is not None else ""))
    w = c.get("wave") or {}
    if w.get("count"):
        lines.append("  wave 集成检查 %d 次：守护 %.1f 秒 · 测试 %.1f 秒 · 跳过测试 %d 次" % (
            w["count"], w["guard_sec"], w["test_sec"], w["skipped"]))
    return "\n".join(lines)


# ---------------------------------------------------------------- doctor

def _changes(openspec_root):
    """在途 change 目录（不含 archive/）：[(名, 目录)]，按名排序。"""
    base = os.path.join(openspec_root, "changes")
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    return [(n, os.path.join(base, n)) for n in names if n != "archive" and os.path.isdir(os.path.join(base, n))]


def _baselines(changes):
    out = []
    for name, d in changes:
        bl = _read_json(os.path.join(d, BASELINE))
        if isinstance(bl, dict) and bl.get("running") is not True:
            out.append((name, bl))
    return out


def doctor_runner(baselines):
    lines = ["[runner]"]
    kinds = {}
    for name, bl in baselines:
        un = bl.get("deps_unmeasured")
        if isinstance(un, dict) and un.get("kind"):
            kinds.setdefault(un["kind"], [un.get("why") or "", []])[1].append(name)
    if not kinds:
        lines.append("  在途 %d 份基线，依赖图均已测到（或尚无基线）" % len(baselines))
        return lines
    for kind in sorted(kinds):
        why, names = kinds[kind]
        lines.append("  %d 份基线是 %s：%s" % (len(names), kind, ", ".join(names)))
        if why:
            lines.append("    修法：%s" % why)
    if any(k in kinds for k in ("plugins-dropped", "plugin-import-failed")):
        lines.append("  包装脚本须转发 $FLIGHT_PLUGIN_PATH 与 $FLIGHT_PYTEST_ARGS（见 .claude/flight-runner-contract.md）")
    return lines


def doctor_anchors(sg, openspec_root):
    lines = ["[anchors]"]
    try:
        root = sg.git(openspec_root, "rev-parse", "--show-toplevel")
        common = sg.git(root, "rev-parse", "--git-common-dir")
    except (Exception, SystemExit):
        lines.append("  不在 git 仓库，跳过")
        return lines
    pdir = os.path.join(common if os.path.isabs(common) else os.path.join(root, common), ANCHOR_DIR)
    try:
        names = sorted(n for n in os.listdir(pdir) if n.endswith(".json") and not n.startswith(".tmp-"))
    except OSError:
        names = []
    entries = [e for e in (_read_json(os.path.join(pdir, n)) for n in names) if isinstance(e, dict)]
    if not entries:
        lines.append("  锚点池为空（首次 final 全量属正常）")
    else:
        measured = sum(1 for e in entries if e.get("measured") is True)
        hops = {}
        for e in entries:
            h = e.get("hops")
            k = "%d 代" % h if isinstance(h, int) else "未记录"
            hops[k] = hops.get(k, 0) + 1
        lines.append("  锚点 %d 条，测到依赖图 %d 条（%d%%）" % (len(entries), measured, 100 * measured // len(entries)))
        lines.append("  hops 分布：%s" % "、".join("%s %d 条" % (k, v) for k, v in sorted(hops.items())))
    lines.append("  注：cmd_key 算法变化后（design D9），旧锚点匹配不到，首次全量属正常")
    return lines


def doctor_gate_test(changes, baselines):
    lines = ["[gate.test]"]
    bmap = dict(baselines)
    hit = []
    for name, d in changes:
        plan = _read_json(os.path.join(d, "slices.json"))
        if not isinstance(plan, dict):
            continue
        gate = plan.get("gate") or {}
        if gate.get("impacted"):
            continue
        un = (bmap.get(name) or {}).get("deps_unmeasured")
        if name in bmap:
            not_pytest = isinstance(un, dict) and un.get("kind") == "not-pytest"
        else:
            not_pytest = bool(gate.get("test")) and "pytest" not in gate["test"]
        if not_pytest:
            hit.append(name)
    if hit:
        lines.append("  %d 个在途 change 的 gate.test 不是 pytest、又没配 gate.impacted（final 恒全量）：%s"
                     % (len(hit), ", ".join(hit)))
        lines.append("    修法：改用 pytest，或配 gate.impacted 自己选测")
    else:
        lines.append("  无：在途 change 都是 pytest 或已配 gate.impacted")
    return lines


def doctor_declare(openspec_root):
    lines = ["[declare]"]
    path = os.path.join(openspec_root, SCOPE_FILE)
    if not os.path.isfile(path):
        lines.append("  未找到 %s" % path)
        return lines
    decl = _read_json(path)
    if not isinstance(decl, dict):
        lines.append("  %s 无法解析为 JSON 对象" % path)
        return lines
    for k in DECLARE_KEYS:
        lines.append("  %s：%s" % (k, json.dumps(decl[k], ensure_ascii=False) if k in decl else "未声明（取缺省）"))
    if "inert" in decl:
        lines.extend(_inert_recon(openspec_root))
    return lines


def _inert_recon(openspec_root):
    """inert 与锚点池里每条测到依赖图的锚点（由新到旧）对账（ship-rerun-hardening D3）；同一路径只列一次。"""
    try:
        sg = load_gate()
    except (Exception, SystemExit) as e:
        return ["  inert：无法对账（slice-gate.py 加载失败：%s）" % _err(e)]
    top = sg._git_top(openspec_root)
    if top is None:
        return ["  inert：无法对账（不在 git 仓库）"]
    try:
        common = sg.git(top, "rev-parse", "--git-common-dir")
        tracked = [p for p in sg._git_raw(top, ["ls-files", "-z"]).split("\0") if p]
        ctx = sg._inert_ctx(top, os.path.join(openspec_root, "changes", "_"))
    except (Exception, SystemExit) as e:
        return ["  inert：无法对账（%s）" % _err(e)]
    pdir = os.path.join(common if os.path.isabs(common) else os.path.join(top, common), ANCHOR_DIR)
    try:
        names = [n for n in os.listdir(pdir) if n.endswith(".json") and not n.startswith(".tmp-")]
    except OSError:
        names = []
    anchors = [(sg._pool_order(n, e), e) for n, e in ((n, _read_json(os.path.join(pdir, n))) for n in names)
               if isinstance(e, dict) and e.get("measured") is True]
    if not anchors:
        return ["  inert：没有测到依赖图的锚点，无法对账"]
    anchors.sort(key=lambda x: x[0], reverse=True)
    lines, seen = [], set()
    for _, a in anchors:
        for p, f in sg._inert_paths(top, tracked, ctx, a)[1]:
            if p in seen:
                continue
            seen.add(p)
            lines.append("  inert 与依赖图矛盾：%s 被测试文件 %s 依赖（锚点 %s@%s）"
                         % (p, f, a.get("change"), str(a.get("commit") or "")[:10]))
    return lines or ["  inert：与 %d 条锚点的依赖图无矛盾" % len(anchors)]


def _last_final_costs(change_dir):
    """timeline 里最近一条带「测试 Xs」的 final 备注的 note_costs；没有 → None。"""
    try:
        with open(os.path.join(change_dir, TIMELINE), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        cols = line.split("\t")
        if len(cols) >= 3 and cols[1] == "final":
            nc = note_costs(cols[2])
            if nc["test"] is not None:
                return nc
    return None


def doctor_checks(changes):
    lines = ["[checks]"]
    for name, d in changes:
        nc = _last_final_costs(d)
        if nc is None:
            continue
        test = nc["test"]
        for check, sec in nc["checks"].items():
            if sec >= SLOW_CHECK_MIN_SEC and sec >= test * SLOW_CHECK_RATIO:
                lines.append("  %s：检查 %s %s 秒，接近测试 %s 秒 → 疑似检查在重跑测试，改读 $GATE_TEST_RESULT"
                             "（见 .claude/flight-runner-contract.md 第 3 节）" % (name, check, sec, test))
    if len(lines) == 1:
        lines.append("  无：最近的 final 里没有耗时接近测试的检查")
    return lines


def doctor_lock():
    lines = ["[lock]"]
    try:
        fl = load_lock()
        lines.append("  锁目录：%s" % fl.lock_dir())
    except (Exception, SystemExit) as e:
        lines.append("  flight-lock.py 加载失败：%s" % _err(e))
        return lines
    if os.environ.get("FLIGHT_LOCK", "").strip().lower() == "off":
        lines.append("  已关闭（FLIGHT_LOCK=off）")
        return lines
    hs = fl.holders()
    for h in hs:
        lines.append("  %s · %s · %s · pid %s · 已持有 %s 秒" % (
            "独占" if h.get("mode") == "exclusive" else "共享", h.get("change") or "-",
            h.get("label") or "-", h.get("pid"), h.get("held_sec")))
    if not hs:
        lines.append("  空闲")
    return lines


SLOWEST_N = 10  # [tests] 最慢清单至多列 10 条
RECENT_N = 5  # [tests] 最近的测试变更至多列 5 个 change


def _last_segment(change_dir, tl):
    """timeline 里最后一条带「用例 +A/-R（新增 Xs）」片段的 final 行 → (时间, 片段)；没有 → None。"""
    try:
        with open(os.path.join(change_dir, TIMELINE), "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        cols = line.split("\t")
        if len(cols) >= 3 and cols[1] == "final":
            seg = tl.parse_segment(cols[2])
            if seg is not None:
                return cols[0], seg
    return None


def _tests_budget(path, tl, best):
    """[tests] 的预算与放行行（tier-budgets）：各范围合计对预算、区域单条超线、放行名单到期；都没写 → []。"""
    sg = load_gate()
    tiers, _ = sg._load_tiers_file(path)
    if tiers is None:
        return ["  分层文件不合法，预算与放行未列出"]
    budgets = sg.tier_budgets(tiers)
    view = sg.allow_view(tiers.get("slow_allow") or {})
    has_budget = any("budget" in t for part in sg.tier_parts(tiers).values()
                     for t in [part["unit"]] + list((part.get("regions") or {}).values()))
    out = []
    if best is not None and has_budget:
        led, scope_of = best[2], sg.budget_scope_of(tiers)
        b = tl.budget(led, None, budgets, scope_of, view, "baseline")
        for sc, tot in sorted(b["totals"].items()):
            if tot["budget"] is None:
                continue
            mark = "（未判）" if tot["over"] is None else "（超预算）" if tot["over"] else ""
            out.append("  预算 %s：合计 %.1fs / %gs%s" % (sc, tot["sec"], tot["budget"], mark))
        for sc, spec in sorted(budgets.items()):
            if spec["kind"] != "region" or spec["case_sec"] is None:
                continue
            one = tl.budget(led, None, {sc: spec}, scope_of, view, "baseline")
            if one["debt_n"] > 0:
                cid, s = one["debt"][0][0], one["debt"][0][1]
                out.append("  区域 %s 单条上限 %gs：超线 %d 条，最慢 %s %.1fs" % (sc, spec["case_sec"], one["debt_n"], cid, s))
    if view:
        expired = sorted(k for k, v in view.items() if v["expired"])
        soon = sum(1 for v in view.values() if v["soon"])
        bare = sum(1 for v in view.values() if not v["expired"] and v["limit"] is None)
        out.append("  放行：共 %d 条 · 已过期 %d 条%s · %d 天内到期 %d 条 · 无上限 %d 条"
                   % (len(view), len(expired), "（%s）" % "、".join(expired) if expired else "",
                      sg.ALLOW_SOON_DAYS, soon, bare))
    return out


def doctor_tests(openspec_root, changes):
    lines = ["[tests]"]
    tl = load_ledger()
    p = subprocess.run(["git", "-C", openspec_root, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        return lines + ["  不在 git 仓库，跳过"]
    root = p.stdout.strip()
    best, best_key = None, None
    for name, _ in changes:
        for phase in ("final", "baseline"):
            led = tl.load(root, name, phase)
            if led is None:
                continue
            key = (str(led.get("at") or ""), phase == "final")
            if best_key is None or key > best_key:
                best, best_key = (name, phase, led), key
    if best is None:
        lines.append("  没有账本数据：本机还没有带账本的 baseline / final（升级后重跑一次 baseline 即有）")
    else:
        name, phase, led = best
        summ = tl.summary(led)
        lines.append("  账本：%s · %s · %s · %s" % (name, phase, str(led.get("commit") or "-")[:10], led.get("mode") or "-"))
        for t, slot in sorted(summ["tiers"].items(), key=lambda kv: (kv[0] == tl.NO_TIER, kv[0])):
            lines.append("  %s：%d 条 · %.1f 秒" % ("未分层" if t == tl.NO_TIER else t, slot["cases"], slot["sec"]))
        lines.append("  无耗时 %d 条" % summ["no_sec"])
        slow = [it for it in sorted((led.get("cases") or {}).items(), key=tl._sort_key) if it[1].get("s") is not None]
        if slow:
            lines.append("  最慢：")
            for cid, c in slow[:SLOWEST_N]:
                lines.append("    %.3fs  %s（%s）" % (c["s"], cid, "未分层" if (c.get("t") or tl.NO_TIER) == tl.NO_TIER
                                                       else c["t"]))
    if not os.path.isfile(os.path.join(openspec_root, "test-tiers.json")):
        lines.append("  未配置测试分层：账本不分层；跑 /test-tiers 划分后才有各层数字")
    else:
        try:
            lines += _tests_budget(os.path.join(openspec_root, "test-tiers.json"), tl, best)
        except (Exception, SystemExit) as e:
            lines.append("  预算与放行未列出：%s" % _err(e))
    recent =[(r[0], name, r[1]) for name, d in changes for r in (_last_segment(d, tl),) if r is not None]
    if recent:
        recent.sort(key=lambda x: x[0], reverse=True)
        lines.append("  最近的测试变更：")
        for _, name, seg in recent[:RECENT_N]:
            lines.append("    %s：%s" % (name, tl.segment(seg)))
    return lines


def doctor_routing(openspec_root):
    """[routing]：只读调用 model-routing.py frontmatter --check，报 fork 命令 frontmatter 与路由的漂移。"""
    try:
        p = subprocess.run([sys.executable, os.path.join(HOOKS_DIR, "model-routing.py"), "frontmatter", "--check",
                            "--openspec", openspec_root], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return ["[routing]", "  不可用：%s" % _err(e)]
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    if p.returncode == 0:
        return ["[routing]", "  " + (lines[0] if lines else "frontmatter 与路由一致")]
    if p.returncode == 1:
        return (["[routing]"] + ["  " + l for l in lines]
                + ["  修法：在仓库根运行 python3 .claude/hooks/model-routing.py frontmatter"])
    err = [l for l in p.stderr.splitlines() if l.strip()]
    return ["[routing]", "  不可用：%s" % (err[0] if err else "exit %d" % p.returncode)]


def doctor(openspec_root):
    openspec_root = os.path.abspath(openspec_root)
    changes = _changes(openspec_root)
    baselines = _baselines(changes)
    out = doctor_runner(baselines)
    try:
        out += doctor_anchors(load_gate(), openspec_root)
    except (Exception, SystemExit) as e:
        out += ["[anchors]", "  slice-gate.py 加载失败：%s" % _err(e)]
    out += doctor_gate_test(changes, baselines)
    out += doctor_declare(openspec_root)
    out += doctor_checks(changes)
    out += doctor_lock()
    try:
        out += doctor_tests(openspec_root, changes)
    except (Exception, SystemExit) as e:
        out += ["[tests]", "  test-ledger.py 不可用：%s" % _err(e)]
    out += doctor_routing(openspec_root)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="flight-doctor：测试成本的预告 / 归因 / 体检（只读，恒 exit 0）")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("forecast", "cost"):
        p = sub.add_parser(name)
        p.add_argument("--change-dir", required=True)
        p.add_argument("--json", action="store_true")
    p = sub.add_parser("doctor")
    p.add_argument("--openspec-root", default=os.path.join(os.getcwd(), "openspec"))
    try:
        args = ap.parse_args()
    except SystemExit:
        sys.exit(0)
    try:
        if args.cmd == "forecast":
            fc = forecast(args.change_dir)
            print(json.dumps(fc, ensure_ascii=False) if args.json else forecast_line(fc))
        elif args.cmd == "cost":
            c = cost(args.change_dir)
            print(json.dumps(c, ensure_ascii=False) if args.json else cost_text(c))
        elif args.cmd == "doctor":
            print(doctor(args.openspec_root))
        else:
            ap.print_help()
    except Exception as e:  # 恒 exit 0：只读报告不阻断任何流程
        print("flight-doctor %s 失败：%s" % (args.cmd, _err(e)))
    sys.exit(0)


if __name__ == "__main__":
    main()
