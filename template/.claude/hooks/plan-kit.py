#!/usr/bin/env python3
# plan-kit · 规划期零 token 工具：汇总 instruction · 由 slices.json 生成 tasks.md · 渲染切片包机械区
#
# 用法：
#   plan-kit.py instructions --change <name> [--all]   # 在当前目录调用 openspec CLI
#   plan-kit.py tasks        --change-dir D
#   plan-kit.py packets      --change-dir D
#
# instructions：openspec status 取工件；对每个未 done 的工件（--all 时全部）取 openspec instructions，
#   按工件打印一节 `## <id> → <outputPath>`，依次是 instruction、template、非空的 rules。
# tasks：由 D/slices.json 生成 D/tasks.md（格式同 templates/tasks.md）；旧文件里已勾选的切片保持 [x]。
# packets：为每片渲染 D/slices/<S>.md 中 <!-- plan-kit:begin --> 与 <!-- plan-kit:end --> 之间的机械区；
#   标记之外原样保留；已存在但无标记 → 机械区插到最前面。
# 退出码：
#   exit 0  成功
#   exit 2  openspec 调用失败 / 输出不是 JSON / 命令找不到；slices.json 缺失或不合法
# 兼容 Python 3.8+，只用标准库。
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EXIT_FAIL = 2
TASKS_HEADER = "<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->"
BEGIN = "<!-- plan-kit:begin -->"
END = "<!-- plan-kit:end -->"
GWT_RE = re.compile(r"^- \*\*(GIVEN|WHEN|THEN|AND|BUT)\*\*")


class KitError(Exception):
    pass


def openspec_json(args):
    """运行 openspec <args>，返回解析后的 JSON；失败抛 KitError（消息含命令与子进程 stderr 末行）。"""
    cmd = ["openspec"] + list(args)
    shown = " ".join(cmd)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise KitError("%s 失败：命令找不到（openspec 不在 PATH）" % shown)
    if p.returncode != 0:
        tail = (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1]
        raise KitError("%s 失败：%s" % (shown, tail))
    try:
        return json.loads(p.stdout)
    except ValueError as e:
        raise KitError("%s 失败：输出不是 JSON（%s）" % (shown, e))


def cmd_instructions(args):
    status = openspec_json(["status", "--change", args.change, "--json"])
    out = []
    for a in status.get("artifacts") or []:
        if a.get("status") == "done" and not args.all:
            continue
        aid = a["id"]
        detail = openspec_json(["instructions", aid, "--change", args.change, "--json"])
        out.append("## %s → %s" % (aid, a.get("outputPath") or detail.get("outputPath") or ""))
        out.append("")
        out.append("### instruction")
        out.append("")
        out.append((detail.get("instruction") or "").rstrip("\n"))
        out.append("")
        out.append("### template")
        out.append("")
        out.append("```markdown")
        out.append((detail.get("template") or "").rstrip("\n"))
        out.append("```")
        out.append("")
        rules = detail.get("rules") or []
        if rules:
            out.append("### rules")
            out.append("")
            out.extend("- %s" % r for r in rules)
            out.append("")
    sys.stdout.write("\n".join(out) + ("\n" if out else ""))
    return 0


def load_plan(change_dir):
    path = Path(change_dir) / "slices.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise KitError("读取 %s 失败：%s" % (path, e))
    if not isinstance(data, dict) or not isinstance(data.get("slices"), list):
        raise KitError("%s 不合法：缺 slices 列表" % path)
    return data


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as f:
        f.write(text.rstrip("\n") + "\n")


def cmd_tasks(args):
    d = Path(args.change_dir)
    data = load_plan(d)
    path = d / "tasks.md"
    checked = set()
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^- \[[xX]\] (\S+) ", line)
            if m:
                checked.add(m.group(1))
    lines = [TASKS_HEADER, "", "## 切片", ""]
    for s in data["slices"]:
        sid = s["id"]
        lines.append("- [%s] %s %s （deps: %s · verify: `%s`）" % (
            "x" if sid in checked else " ", sid, s.get("title", ""),
            ", ".join(s.get("deps") or []) or "-", s.get("verify", "")))
    write_text(path, "\n".join(lines))
    return 0


def scenario_lines(change_dir, cap, name):
    """返回 specs/<cap>/spec.md 中 `#### Scenario: <name>` 下的 GIVEN/WHEN/THEN/AND/BUT 行；找不到返回 None。"""
    spec = Path(change_dir) / "specs" / cap / "spec.md"
    if not spec.is_file():
        return None
    found = None
    for line in spec.read_text(encoding="utf-8").splitlines():
        if found is None:
            if re.match(r"^####\s+Scenario:\s*%s\s*$" % re.escape(name), line):
                found = []
            continue
        if re.match(r"^#{2,4}\s", line):
            break
        if GWT_RE.match(line):
            found.append(line)
    return found


def render_region(change_dir, s, by_id, tests):
    out = [BEGIN, "# %s · %s" % (s["id"], s.get("title", "")), "", "## owns", ""]
    out.extend("- `%s`" % o for o in s.get("owns") or [])
    out += ["", "## 依赖的切片", ""]
    deps = s.get("deps") or []
    if not deps:
        out.append("无")
    for dep in deps:
        ds = by_id.get(dep, {})
        out.append("- `%s` · %s · `%s`" % (dep, ds.get("title", ""), ds.get("packet") or "slices/%s.md" % dep))
    out += ["", "## scenario", ""]
    scenarios = s.get("scenarios") or []
    if not scenarios:
        out.append("无")
    for sc in scenarios:
        cap, _, name = sc.partition("#")
        out.append("### %s → `%s`" % (sc, tests.get(sc, "")))
        out.append("")
        body = scenario_lines(change_dir, cap, name)
        out.extend(body if body is not None else ["（specs 中未找到）"])
        out.append("")
    if scenarios:
        out.pop()
    out += ["", "## verify", "", "`%s`" % s.get("verify", ""), END]
    return "\n".join(out)


def cmd_packets(args):
    d = Path(args.change_dir)
    data = load_plan(d)
    by_id = {s["id"]: s for s in data["slices"]}
    tests = data.get("scenario_tests") or {}
    for s in data["slices"]:
        path = d / (s.get("packet") or "slices/%s.md" % s["id"])
        region = render_region(d, s, by_id, tests)
        if not path.is_file():
            write_text(path, region)
            continue
        old = path.read_text(encoding="utf-8")
        b, e = old.find(BEGIN), old.find(END)
        if b != -1 and e > b:
            new = old[:b] + region + old[e + len(END):]
        else:
            new = region + "\n\n" + old
        with open(str(path), "w", encoding="utf-8", newline="\n") as f:
            f.write(new)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="plan-kit.py", description="规划期零 token 工具")
    sub = ap.add_subparsers(dest="cmd")
    sub.required = True
    p = sub.add_parser("instructions")
    p.add_argument("--change", required=True)
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_instructions)
    for name, fn in (("tasks", cmd_tasks), ("packets", cmd_packets)):
        p = sub.add_parser(name)
        p.add_argument("--change-dir", required=True)
        p.set_defaults(func=fn)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except KitError as e:
        sys.stderr.write("%s\n" % e)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
