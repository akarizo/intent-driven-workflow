#!/usr/bin/env python3
# session-decompose · 会话转录 wall-clock 归因（apply 收口时打印「飞行记录」）
#
# 用法：session-decompose.py --session <主转录 .jsonl> [--subagents DIR]
# 归因规则：把主会话时间线切成相邻事件之间的空隙，按「终结该空隙的事件」归类：
#   assistant 条目            → 模型生成（含 thinking）
#   tool_result（非 Agent）    → 工具执行（AskUserQuestion 的结果 = 等人）
#   <task-notification>       → 等子 agent
#   人类消息                  → 等人 / 会话空闲
# 子 agent：默认读 <session 同名目录>/subagents/agent-*.jsonl，按 description 关键词分 impl / review / fix / other。
# 只读，不改任何文件。兼容 Python 3.8+，只用标准库。
import argparse
import glob
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

# 角色判定三级顺序：agentType → label 前缀 → 阶段（前一级判不出才看后一级）
# agentType → 路由角色（主键：wave integrator 在 Implement 阶段派发，只看阶段会误判成 executor）
AGENT_ROLE = {"slice-executor": "executor", "code-reviewer": "reviewer", "integrator": "integrator"}
# label 前缀 → 路由角色（次键：meta 无 agentType 时，按 opsx-apply.js 派发 label 的显式格式判；含 :retry 后缀）
LABEL_ROLE = (("integrate:", "integrator"), ("final-gate", "integrator"), ("review:", "reviewer"))
# 阶段 → 路由角色（兜底：agentType 缺失且 label 不匹配显式格式）
PHASE_ROLE = {"Implement": "executor", "Fix": "executor", "Review": "reviewer", "Finalize": "integrator"}
ROLE_ORDER = ("executor", "reviewer", "integrator")
EXIT_ROUTE_MISMATCH = 3

STRIP_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>|<task-notification>.*?</task-notification>|"
    r"<local-command-[a-z]+>.*?</local-command-[a-z]+>|<command-name>.*?</command-name>|"
    r"<command-message>.*?</command-message>|<command-args>.*?</command-args>", re.S)


def ts(s):
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load(path):
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("timestamp"):
                rows.append(d)
    return rows


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
    return ""


def classify_user(d):
    msg = d.get("message") or {}
    content = msg.get("content")
    if "toolUseResult" in d or (isinstance(content, list) and any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content)):
        return "tool_result"
    raw = text_of(content)
    if "<task-notification>" in raw:
        return "notification"
    if d.get("isMeta"):
        return "other"
    return "human" if STRIP_RE.sub("", raw).strip() else "other"


def role_of(desc):
    d = (desc or "").lower()
    if re.search(r"守门|review|复审|复核|verify|审", d) and not re.search(r"修|fix", d):
        return "review"
    if re.search(r"修复|fix", d) or d.startswith("修"):
        return "fix"
    if re.search(r"实现|implement|task|切片|slice", d):
        return "impl"
    return "other"


def decompose(rows):
    tool_use = {}
    events = []
    dispatch = 0
    launches = {}
    ctx_series = []
    seen = set()
    for d in rows:
        t, typ = d["timestamp"], d.get("type")
        if typ == "system":
            if d.get("subtype") == "compact_boundary":
                events.append((t, "compact", {}))
            continue
        if typ == "assistant":
            msg = d.get("message") or {}
            rid = d.get("requestId") or msg.get("id")
            first = rid not in seen
            seen.add(rid)
            u = msg.get("usage") or {}
            if first and u:
                ctx_series.append((u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0))
            for c in msg.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use":
                    tool_use[c.get("id")] = c.get("name")
                    if c.get("name") == "Agent":
                        dispatch += 1
            events.append((t, "assistant", {"first": first}))
        elif typ == "user":
            kind = classify_user(d)
            if kind == "tool_result":
                name = None
                for c in (d.get("message") or {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        name = tool_use.get(c.get("tool_use_id"))
                tr = d.get("toolUseResult")
                if isinstance(tr, dict) and tr.get("agentId"):
                    launches[tr["agentId"]] = tr.get("description")
                events.append((t, "tool_result", {"name": name}))
            elif kind == "notification":
                events.append((t, "notification", {}))
            elif kind == "human":
                events.append((t, "human", {}))
    events.sort(key=lambda e: e[0])
    buckets = Counter()
    prev = ts(events[0][0]) if events else None
    for t, kind, det in events[1:]:
        cur = ts(t)
        gap = max(0.0, (cur - prev).total_seconds())
        if kind == "assistant":
            buckets["模型生成"] += gap
        elif kind == "tool_result":
            if det.get("name") == "AskUserQuestion":
                buckets["等人(问询)"] += gap
            elif det.get("name") == "Agent":
                buckets["工具执行"] += gap
            else:
                buckets["工具执行"] += gap
        elif kind == "notification":
            buckets["等子 agent"] += gap
        elif kind == "human":
            buckets["等人(下一条指令)"] += gap
        prev = cur
    span = (ts(events[-1][0]) - ts(events[0][0])).total_seconds() if len(events) > 1 else 0.0
    return {"span": span, "buckets": buckets, "dispatch": dispatch, "launches": launches,
            "api_calls": len(ctx_series), "peak_ctx": max(ctx_series) if ctx_series else 0,
            "human": sum(1 for e in events if e[1] == "human"), "compact": sum(1 for e in events if e[1] == "compact")}


def subagent_stats(sub_dir, launches):
    per_role = defaultdict(list)
    for sp in glob.glob(os.path.join(sub_dir, "agent-*.jsonl")):
        rows = load(sp)
        if len(rows) < 2:
            continue
        aid = os.path.basename(sp)[6:-6]
        wall = (ts(rows[-1]["timestamp"]) - ts(rows[0]["timestamp"])).total_seconds()
        turns = len({(r.get("requestId") or (r.get("message") or {}).get("id")) for r in rows if r.get("type") == "assistant"})
        per_role[role_of(launches.get(aid))].append((wall, turns))
    return per_role


def fmt_h(sec):
    return "%.2fh" % (sec / 3600) if sec >= 3600 else "%.1fmin" % (sec / 60)


def workflow_agents(wf_dir):
    """读 Workflow journal 目录里每个 agent 的标签 / 实际模型 / 轮次 / wall，供收口对账路由表。"""
    out = []
    for sp in sorted(glob.glob(os.path.join(wf_dir, "agent-*.jsonl"))):
        rows = load(sp)
        if not rows:
            continue
        model, reqs = None, set()
        for r in rows:
            if r.get("type") != "assistant":
                continue
            m = r.get("message") or {}
            model = model or m.get("model")
            reqs.add(r.get("requestId") or m.get("id"))
        meta = {}
        try:
            with open(sp[:-6] + ".meta.json", "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            pass
        wall = (ts(rows[-1]["timestamp"]) - ts(rows[0]["timestamp"])).total_seconds()
        out.append((meta.get("description") or os.path.basename(sp)[6:14], meta.get("workflowPhase") or "-",
                    model or "?", len(reqs), wall, meta.get("agentType")))
    return out


def load_alias_of():
    """按路径加载同目录 session-model.py 的 alias_of（文件名含连字符不能 import）；加载失败返回 None。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session-model.py")
    try:
        spec = importlib.util.spec_from_file_location("session_model", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.alias_of
    except Exception:  # noqa: BLE001 — 判定脚本缺失/损坏都只退化，不阻断收口
        return None


def label_role(label):
    """label 按 LABEL_ROLE 前缀判路由角色；为空或不匹配返回 None。"""
    if not label:
        return None
    for prefix, role in LABEL_ROLE:
        if label.startswith(prefix):
            return role
    return None


def audit_routes(agents, expect, alias_of):
    """角色按 agentType → label 前缀 → 阶段 三级判定（前一级判不出才看后一级），比对别名（比别名不比原始 id）。
    返回 (不符项, 已对账角色→期望别名, 未采样到的角色, 空 attempt)——零覆盖必须红，不能当一致。
    没有 assistant 轮次的转录（被重试掉的空 attempt，模型为 "?"）不算跑错模型，只作未采样告警。"""
    bad, seen, empty = [], {}, []
    for label, phase, model, _turns, _wall, atype in agents:
        role = AGENT_ROLE.get(atype) or label_role(label) or PHASE_ROLE.get(phase)
        if role is None or role not in expect:
            continue
        if not model or model == "?":
            empty.append((label, phase))
            continue
        want, got = expect[role], alias_of(model)
        seen[role] = want
        if got != want:
            bad.append((label, phase, want, model))
    ordered = [r for r in ROLE_ORDER if r in expect] + [r for r in expect if r not in ROLE_ORDER]
    missing = [r for r in ordered if r not in seen]
    return bad, seen, missing, empty


def main():
    ap = argparse.ArgumentParser(description="session-decompose：会话 wall-clock 归因")
    ap.add_argument("--session", required=True, help="主转录 .jsonl 路径")
    ap.add_argument("--subagents", help="子 agent 转录目录（缺省：<session 同名目录>/subagents）")
    ap.add_argument("--workflow", help="Workflow 运行的 Transcript dir（含 agent-*.jsonl 与 .meta.json），打印各 agent 实际模型")
    ap.add_argument("--expect-models", help='路由表 JSON，如 \'{"executor":"opus","reviewer":"opus","integrator":"sonnet"}\'；不符 exit 3')
    args = ap.parse_args()
    expect = None
    if args.expect_models:
        if not args.workflow:
            ap.error("--expect-models 需要同时给 --workflow（否则无实际模型可对账）")
        try:
            expect = json.loads(args.expect_models)
        except ValueError as exc:
            ap.error("--expect-models 不是合法 JSON：%s" % exc)
    rows = load(args.session)
    if not rows:
        print("转录为空")
        return
    r = decompose(rows)
    tot = sum(r["buckets"].values()) or 1
    print("飞行记录 · %s" % os.path.basename(args.session)[:8])
    print("跨度 %s · API 调用 %d · 派发 %d · 人类消息 %d · compact %d · 主会话峰值上下文 %dk" % (
        fmt_h(r["span"]), r["api_calls"], r["dispatch"], r["human"], r["compact"], r["peak_ctx"] // 1000))
    for k in ("等子 agent", "模型生成", "工具执行", "等人(问询)", "等人(下一条指令)"):
        v = r["buckets"].get(k, 0.0)
        print("  %-14s %10s  %5.1f%%" % (k, fmt_h(v), v / tot * 100))
    sub_dir = args.subagents or os.path.join(os.path.dirname(args.session), os.path.basename(args.session)[:-6], "subagents")
    if os.path.isdir(sub_dir):
        per_role = subagent_stats(sub_dir, r["launches"])
        total = sum(len(v) for v in per_role.values())
        print("子 agent %d 个：" % total)
        for role in ("impl", "review", "fix", "other"):
            xs = per_role.get(role)
            if xs:
                print("  %-6s n=%2d  均 wall %6.1fmin  均轮 %5.1f" % (role, len(xs), sum(w for w, _ in xs) / len(xs) / 60, sum(t for _, t in xs) / len(xs)))
    else:
        print("子 agent 转录目录不存在：%s" % sub_dir)
    if args.workflow:
        agents = workflow_agents(args.workflow)
        print("Workflow agent %d 个（标签 · 阶段 · 实际模型 · 轮次 · wall）：" % len(agents))
        for label, phase, model, turns, wall, _atype in agents:
            print("  %-16s %-10s %-20s %4d  %s" % (label, phase, model, turns, fmt_h(wall)))
        models = Counter(a[2] for a in agents)
        print("  模型分布：%s" % dict(models))
        if expect is not None:
            alias_of = load_alias_of()
            if alias_of is None:
                print("  ⚠ 无法加载 session-model.py 的 alias_of，路由对账跳过（只打印）")
            else:
                bad, seen, missing, empty = audit_routes(agents, expect, alias_of)
                for label, phase in empty:
                    print("  ⚠ 未采样 %s · %s（无 assistant 轮次，多半是被重试掉的空 attempt，不参与对账）" % (label, phase))
                if bad or missing:
                    for label, phase, want, model in bad:
                        print("  ❌ %s · %s · 期望 %s · 实际 %s" % (label, phase, want, model))
                    for role in missing:
                        print("  ❌ 未采样到角色 %s（期望 %s）——零覆盖不算一致" % (role, expect[role]))
                    return EXIT_ROUTE_MISMATCH
                print("  路由对账：✅ 一致（%s）" % " · ".join(
                    "%s=%s" % (role, seen[role]) for role in ROLE_ORDER if role in seen))


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except BrokenPipeError:
        sys.exit(0)
