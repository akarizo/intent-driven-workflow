#!/usr/bin/env python3
# plan-scaffold · 规划期 scenario 测试骨架生成与 GWT / 占位自查
#
# 用法：
#   plan-scaffold.py scaffold --change-dir D
#     按 slices.json 的 scenario_tests 为缺失的 path::func 追加 strict-xfail 骨架函数
#     （GWT 注释取 specs 里的 Gherkin 原文，末行是带 PLACEHOLDER 的占位断言）。
#     stdout 打印 {"created": [...], "existing": [...], "skipped": [...]}。
#     退出码：0 成功；2 映射的 scenario 在 specs 里找不到 / slices.json 不可读（stderr 点名）。
#   plan-scaffold.py gwt --change-dir D
#     只针对映射到的函数：复用 slice-gate.py 的 gwt_violations 查 G4 GWT 注释，再查函数体残留的 PLACEHOLDER。
#     逐条打印问题；有问题 exit 1，全部通过 exit 0；slice-gate.py 加载失败 / slices.json 不可读 exit 2。
# 只用标准库，兼容 Python 3.8+。
import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys

PLACEHOLDER = "PLAN-SCAFFOLD-PLACEHOLDER"
STEP = re.compile(r"^\s*-\s*\*\*(GIVEN|WHEN|THEN|AND|BUT)\*\*\s*(.*?)\s*$", re.IGNORECASE)


def repo_root(change_dir):
    """git 顶层优先；否则 D/../../..（与 spec_html.project_root 同口径）。"""
    try:
        p = subprocess.run(["git", "-C", change_dir, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except OSError:
        pass
    d = os.path.abspath(change_dir)
    return os.path.dirname(os.path.dirname(os.path.dirname(d)))


def load_plan(change_dir):
    with open(os.path.join(change_dir, "slices.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def split_target(target):
    path, _, func = target.partition("::")
    return path, func


def func_exists(text, func):
    """与 G7 同判据：^\\s*(?:async\\s+)?def\\s+<func>\\s*\\(。"""
    return re.search(r"(?m)^\s*(?:async\s+)?def\s+%s\s*\(" % re.escape(func), text) is not None


def scenario_steps(change_dir, cap, name):
    """取 specs/<cap>/spec.md 中 #### Scenario: <name> 块的 Given/When/Then 行（AND / BUT 并入前一关键字）；找不到返回 None。"""
    path = os.path.join(change_dir, "specs", cap, "spec.md")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    head = re.compile(r"^####\s+Scenario:\s*%s\s*$" % re.escape(name))
    start = next((i for i, ln in enumerate(lines) if head.match(ln)), None)
    if start is None:
        return None
    steps = {"Given": [], "When": [], "Then": []}
    cur = None
    for ln in lines[start + 1:]:
        if ln.startswith("#"):
            break
        m = STEP.match(ln)
        if not m:
            continue
        kw, text = m.group(1).upper(), m.group(2)
        if kw in ("AND", "BUT"):
            if cur is None:
                continue
        else:
            cur = kw.capitalize()
        steps[cur].append(text)
    return steps


def render_func(func, slice_id, steps):
    return ("@pytest.mark.xfail(strict=True, reason=\"%s 未实现\")\n"
            "def %s():\n"
            "    # Given: %s\n"
            "    # When: %s\n"
            "    # Then: %s\n"
            "    assert False, \"%s：换成真实断言\"\n") % (
        slice_id, func, "；".join(steps["Given"]), "；".join(steps["When"]),
        "；".join(steps["Then"]), PLACEHOLDER)


def has_pytest_import(tree):
    for node in tree.body:
        if isinstance(node, ast.Import) and any(a.name == "pytest" and a.asname is None for a in node.names):
            return True
    return False


def ensure_pytest_import(text):
    """缺 import pytest 时插入：最后一条顶层 import 之后 → docstring 之后 → 文件开头。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    if tree is not None and has_pytest_import(tree):
        return text
    lines = text.splitlines()
    imports = [n for n in (tree.body if tree else []) if isinstance(n, (ast.Import, ast.ImportFrom))]
    if imports:
        end = getattr(imports[-1], "end_lineno", None) or imports[-1].lineno
        lines[end:end] = ["import pytest"]
    elif tree and tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(
            getattr(tree.body[0], "value", None), ast.Constant) and isinstance(tree.body[0].value.value, str):
        end = getattr(tree.body[0], "end_lineno", None) or tree.body[0].lineno
        lines[end:end] = ["", "import pytest"]
    else:
        lines[0:0] = ["import pytest", ""]
    return "\n".join(lines) + "\n"


def cmd_scaffold(change_dir):
    try:
        plan = load_plan(change_dir)
    except (OSError, ValueError) as e:
        print("slices.json 不可读：%s" % e, file=sys.stderr)
        return 2
    root = repo_root(change_dir)
    owner = {}
    for s in plan.get("slices", []):
        for key in s.get("scenarios", []):
            owner.setdefault(key, s.get("id", "?"))
    out = {"created": [], "existing": [], "skipped": []}
    todo, missing = [], []
    for key, target in (plan.get("scenario_tests") or {}).items():
        path, func = split_target(target)
        if not path.endswith(".py"):
            out["skipped"].append(target)
            continue
        cap, _, name = key.partition("#")
        steps = scenario_steps(change_dir, cap, name)
        if steps is None:
            missing.append(key)
            continue
        todo.append((key, target, path, func, cap, steps))
    if missing:
        for key in missing:
            print("scenario 在 specs 里找不到：%s" % key, file=sys.stderr)
        return 2
    files = {}  # path -> (text, is_new)
    for key, target, path, func, cap, steps in todo:
        sid = owner.get(key, "?")
        if path not in files:
            full = os.path.join(root, path)
            if os.path.isfile(full):
                with open(full, "r", encoding="utf-8") as f:
                    files[path] = f.read()
            else:
                files[path] = ('"""%s 的 scenario 骨架（strict xfail；切片 %s 实现后去掉标记即解锁）。"""\n'
                               "import pytest\n") % (cap, sid)
        text = files[path]
        if func_exists(text, func):
            out["existing"].append(target)
            continue
        text = ensure_pytest_import(text)
        files[path] = text.rstrip("\n") + "\n\n\n" + render_func(func, sid, steps)
        out["created"].append(target)
    for path, text in files.items():
        full = os.path.join(root, path)
        old = None
        if os.path.isfile(full):
            with open(full, "r", encoding="utf-8") as f:
                old = f.read()
        if text == old:
            continue
        os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
    print(json.dumps(out, ensure_ascii=False))
    return 0


def load_gwt_violations():
    """按路径加载同目录 slice-gate.py 的 gwt_violations（文件名含连字符不能 import）；失败返回 None。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slice-gate.py")
    try:
        spec = importlib.util.spec_from_file_location("slice_gate", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.gwt_violations
    except Exception:  # noqa: BLE001 — 加载失败由调用方报 exit 2
        return None


def placeholder_funcs(full, funcs):
    """返回 funcs 中函数体（AST 源码段）仍含 PLACEHOLDER 的函数名。"""
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        tree = ast.parse(text)
    except (OSError, SyntaxError):
        return []
    lines = text.splitlines()
    hit = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in funcs:
            end = getattr(node, "end_lineno", None) or node.lineno
            if PLACEHOLDER in "\n".join(lines[node.lineno - 1:end]) and node.name not in hit:
                hit.append(node.name)
    return hit


def cmd_gwt(change_dir):
    try:
        plan = load_plan(change_dir)
    except (OSError, ValueError) as e:
        print("slices.json 不可读：%s" % e, file=sys.stderr)
        return 2
    gwt_violations = load_gwt_violations()
    if gwt_violations is None:
        print("无法加载 slice-gate.py 的 gwt_violations", file=sys.stderr)
        return 2
    root = repo_root(change_dir)
    by_file = {}
    for target in (plan.get("scenario_tests") or {}).values():
        path, func = split_target(target)
        if path and func:
            by_file.setdefault(path, set()).add(func)
    problems = []
    wanted = {"%s::%s " % (p, f) for p, fs in by_file.items() for f in fs}
    for msg in gwt_violations(root, list(by_file)):
        if any(w in msg for w in wanted):
            problems.append(msg)
    for path in sorted(by_file):
        if not path.endswith(".py"):
            continue
        full = os.path.join(root, path)
        for func in placeholder_funcs(full, by_file[path]):
            problems.append("占位: %s::%s 仍是 scaffold 占位断言" % (path, func))
    for msg in problems:
        print(msg)
    return 1 if problems else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="规划期 scenario 骨架生成（scaffold）与 GWT / 占位自查（gwt）")
    ap.add_argument("cmd", choices=["scaffold", "gwt"])
    ap.add_argument("--change-dir", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "scaffold":
        return cmd_scaffold(args.change_dir)
    return cmd_gwt(args.change_dir)


if __name__ == "__main__":
    sys.exit(main())
