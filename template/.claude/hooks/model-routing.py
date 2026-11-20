#!/usr/bin/env python3
# model-routing · 执行层路由配置：校验 · 内建默认 · 钉进 slices.json · 起飞解析 · 单键查询
#
# 用法：
#   model-routing.py show    [--change-dir D | --openspec DIR] [--json]
#   model-routing.py pin     --change-dir D
#   model-routing.py resolve --change-dir D
#   model-routing.py get     <组.键> [--change-dir D | --openspec DIR]
#   model-routing.py frontmatter [--check] [--openspec DIR] [--commands DIR]   把路由值渲染进 fork 命令的 frontmatter
#
# 配置：<openspec 根>/model-routing.json，两级「组.键」→ {"model","effort"}；文件缺失视为 {}，缺的键走内建默认。
#   openspec 根：--openspec 优先 > <change-dir>/../.. > ./openspec。
# 退出码：
#   exit 0  成功
#   exit 1  frontmatter --check 发现漂移（逐条点名「文件：字段 期望 x 实际 y」）
#   exit 2  配置非法（逐条点名「组.键」）/ 未登记的键 / pin 时 slices.json 缺失
#   exit 3  resolve 停飞：routing 未钉或不合法，或覆盖环境变量非空（点名变量）
# 规划期组（propose / explore / new / continue / mini）不进路由配置；model 只写模型名。
# 兼容 Python 3.8+，只用标准库。
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_INVALID = 2
EXIT_GROUNDED = 3
CONFIG_NAME = "model-routing.json"

MODELS = ("opus", "sonnet", "haiku", "fable")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PLANNING_GROUPS = ("propose", "explore", "new", "continue", "mini")
REGISTRY = {
    "flight": ("executor", "executor-large", "fixer", "reviewer", "integrator"),
    "ship": ("reviewer", "followup"),
    "archive": ("sync",),
    "claudemd": ("evidence",),
    "bulk": ("apply",),
    "cleanup": ("runner",),
}
_OPUS_HIGH = {"model": "opus", "effort": "high"}
_SONNET_LOW = {"model": "sonnet", "effort": "low"}
BUILTIN = {
    "flight.executor": _OPUS_HIGH,
    "flight.executor-large": _OPUS_HIGH,
    "flight.fixer": _OPUS_HIGH,
    "flight.reviewer": _OPUS_HIGH,
    "flight.integrator": _SONNET_LOW,
    "ship.reviewer": _OPUS_HIGH,
    "ship.followup": _OPUS_HIGH,
    "archive.sync": _SONNET_LOW,
    "claudemd.evidence": _SONNET_LOW,
    "bulk.apply": {"model": "opus", "effort": "medium"},
    "cleanup.runner": _SONNET_LOW,
}
PINNED_GROUPS = ("flight", "ship")
# fork 命令的唯一登记处：路由键 → 命令文件名（frontmatter 的 model / effort 由 frontmatter 子命令渲染）
FORK_COMMANDS = {"cleanup.runner": "clean-after-merged.md"}
FRONTMATTER_RE = re.compile(r"^---(\r?\n)(.*?)\r?\n---(\r?\n|\Z)", re.S)
ENV_OVERRIDES = ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE")


def die(code, lines):
    for line in lines:
        sys.stderr.write("model-routing: %s\n" % line)
    sys.exit(code)


def openspec_root(args):
    if getattr(args, "openspec", None):
        return Path(args.openspec)
    if getattr(args, "change_dir", None):
        return Path(args.change_dir).parent.parent
    return Path("openspec")


def config_path(root):
    return root / CONFIG_NAME


def load_config(root):
    """返回 (cfg, errors)。文件不存在视为 {}。"""
    path = config_path(root)
    if not path.is_file():
        return {}, []
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {}, ["%s 不是合法 JSON：%s" % (path, e)]
    return cfg, []


def check_value(name, value):
    """单个键的值校验：必须同时有合法 model 与 effort。"""
    if not isinstance(value, dict):
        return ["%s：值必须是 {\"model\", \"effort\"}" % name]
    errs = []
    if "model" not in value:
        errs.append("%s：缺 model" % name)
    elif value["model"] not in MODELS:
        errs.append("%s：model=%r 不是模型名，只写模型名（%s）" % (name, value["model"], " | ".join(MODELS)))
    if "effort" not in value:
        errs.append("%s：缺 effort" % name)
    elif value["effort"] not in EFFORTS:
        errs.append("%s：effort=%r 不在允许集合（%s）" % (name, value["effort"], " | ".join(EFFORTS)))
    return errs


def validate(cfg):
    """配置校验，返回错误列表（每条点名「组.键」）。"""
    if not isinstance(cfg, dict):
        return ["%s 顶层必须是对象" % CONFIG_NAME]
    errs = []
    for group, keys in cfg.items():
        names = ["%s.%s" % (group, k) for k in keys] if isinstance(keys, dict) and keys else [group]
        if group in PLANNING_GROUPS:
            errs.extend("%s：规划期不进路由配置" % n for n in names)
            continue
        if group not in REGISTRY:
            errs.extend("%s：未登记的键" % n for n in names)
            continue
        if not isinstance(keys, dict):
            errs.append("%s：组的值必须是对象" % group)
            continue
        for key, value in keys.items():
            name = "%s.%s" % (group, key)
            if key not in REGISTRY[group]:
                errs.append("%s：未登记的键" % name)
                continue
            errs.extend(check_value(name, value))
    return errs


def effective(root):
    """返回 (11 键表 {组.键: {model, effort, source}}, errors)。"""
    cfg, errs = load_config(root)
    errs = errs or validate(cfg)
    if errs:
        return {}, errs
    table = {}
    for name, default in BUILTIN.items():
        group, key = name.split(".", 1)
        value = cfg.get(group, {}).get(key)
        if value is None:
            table[name] = dict(default, source="builtin")
        else:
            table[name] = {"model": value["model"], "effort": value["effort"], "source": "repo"}
    return table, []


def load_slices(change_dir):
    path = Path(change_dir) / "slices.json"
    if not path.is_file():
        return path, None
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        die(EXIT_INVALID, ["%s 不是合法 JSON：%s" % (path, e)])


def pinned_errors(routing):
    """钉住的 routing 校验：flight 5 键 + ship 2 键必须齐全合法。"""
    if not isinstance(routing, dict):
        return ["routing 缺失"]
    errs = []
    for group in PINNED_GROUPS:
        block = routing.get(group)
        if not isinstance(block, dict):
            errs.append("routing.%s 缺失" % group)
            continue
        for key in REGISTRY[group]:
            name = "%s.%s" % (group, key)
            if key not in block:
                errs.append("%s：未钉住" % name)
            else:
                errs.extend(check_value(name, block[key]))
    return errs


def source_label(root):
    path = config_path(root)
    if not path.is_file():
        return "builtin"
    full = path.resolve()
    try:
        top = subprocess.run(["git", "-C", str(full.parent), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return full.relative_to(Path(top).resolve()).as_posix()
    except (OSError, subprocess.CalledProcessError, ValueError):
        return str(full)


def env_overrides():
    return [v for v in ENV_OVERRIDES if os.environ.get(v)]


def cmd_show(args):
    table, errs = effective(openspec_root(args))
    if errs:
        die(EXIT_INVALID, errs)
    if args.json:
        print(json.dumps(table, ensure_ascii=False, indent=2))
        return
    width = max(len(n) for n in table)
    for name, v in table.items():
        print("%s  %-6s  %-6s  %s" % (name.ljust(width), v["model"], v["effort"], v["source"]))


def cmd_pin(args):
    root = openspec_root(args)
    table, errs = effective(root)
    if errs:
        die(EXIT_INVALID, errs)
    path, plan = load_slices(args.change_dir)
    if plan is None:
        die(EXIT_INVALID, ["%s 不存在" % path])
    routing = {"source": source_label(root)}
    for group in PINNED_GROUPS:
        routing[group] = {k: {"model": table["%s.%s" % (group, k)]["model"],
                              "effort": table["%s.%s" % (group, k)]["effort"]} for k in REGISTRY[group]}
    old = plan.get("routing")
    if old is not None and old != routing:
        sys.stderr.write("model-routing: routing 已改，批准将过期，需重新批准\n")
    plan["routing"] = routing
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for group in PINNED_GROUPS:
        for key, v in routing[group].items():
            print("%s.%s  %s · %s" % (group, key, v["model"], v["effort"]))


def cmd_resolve(args):
    hits = env_overrides()
    if hits:
        die(EXIT_GROUNDED, ["环境变量 %s 非空，它会覆盖派发时传入的 model / effort；清空后再起飞" % v for v in hits])
    _, plan = load_slices(args.change_dir)
    errs = pinned_errors((plan or {}).get("routing"))
    if errs:
        die(EXIT_GROUNDED, errs + [
            "先运行 python3 .claude/hooks/model-routing.py pin --change-dir %s ；pin 后计划工件已改，需重新批准" % args.change_dir])
    flight = plan["routing"]["flight"]
    out = {"models": {r: flight[r]["model"] for r in REGISTRY["flight"]},
           "efforts": {r: flight[r]["effort"] for r in REGISTRY["flight"]}}
    print(json.dumps(out, ensure_ascii=False))


def cmd_get(args):
    name = args.key
    if name not in BUILTIN:
        die(EXIT_INVALID, ["%s：未登记的键" % name])
    table, errs = effective(openspec_root(args))
    if errs:
        die(EXIT_INVALID, errs)
    for v in env_overrides():
        sys.stderr.write("model-routing: 警告：环境变量 %s 非空，会覆盖派发时传入的值\n" % v)
    group, key = name.split(".", 1)
    if args.change_dir and group in PINNED_GROUPS:
        _, plan = load_slices(args.change_dir)
        routing = (plan or {}).get("routing")
        if isinstance(routing, dict) and isinstance(routing.get(group), dict):
            value = routing[group].get(key)
            if value is not None and not check_value(name, value):
                print(json.dumps({"model": value["model"], "effort": value["effort"], "source": "pinned"}))
                return
    print(json.dumps(table[name]))


def render_frontmatter(text, model, effort):
    """返回 (新文本, 实际值 {model, effort})；非 fork 形态返回 (None, None)。块外与块内其他行逐字保留。"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, None
    eol = m.group(1)
    lines = m.group(2).split(eol)
    if not any(l.strip() == "context: fork" for l in lines):
        return None, None
    want = {"model": model, "effort": effort}
    actual = {}
    out = []
    for line in lines:
        field = next((f for f in ("model", "effort") if line.startswith(f + ":")), None)
        if field is None:
            out.append(line)
            continue
        actual[field] = line.split(":", 1)[1].strip()
        out.append("%s: %s" % (field, want[field]))
    out.extend("%s: %s" % (f, want[f]) for f in ("model", "effort") if f not in actual)
    return "---" + eol + eol.join(out) + eol + "---" + m.group(3) + text[m.end():], actual


def cmd_frontmatter(args):
    table, errs = effective(openspec_root(args))
    if errs:
        die(EXIT_INVALID, errs)
    commands = Path(args.commands) if args.commands else Path(__file__).resolve().parent.parent / "commands"
    plans = []
    for name, filename in FORK_COMMANDS.items():
        path = commands / filename
        if not path.is_file():
            die(EXIT_INVALID, ["%s：命令文件 %s 不存在" % (name, path)])
        text = path.read_bytes().decode("utf-8")
        v = table[name]
        new, actual = render_frontmatter(text, v["model"], v["effort"])
        if new is None:
            die(EXIT_INVALID, ["%s：%s 不是 fork 形态（首个 --- 块里没有 context: fork）" % (name, path)])
        plans.append((path, text, new, actual, v))
    if args.check:
        drift = ["%s：%s 期望 %s 实际 %s" % (path.name, f, v[f], actual.get(f, "（缺）"))
                 for path, _, _, actual, v in plans for f in ("model", "effort") if actual.get(f) != v[f]]
        if drift:
            print("\n".join(drift))
            sys.exit(1)
        print("frontmatter 与路由一致")
        return
    for path, text, new, _, v in plans:
        if new != text:
            path.write_bytes(new.encode("utf-8"))
        print("%s  %s · %s" % (path.name, v["model"], v["effort"]))


def main(argv=None):
    p = argparse.ArgumentParser(prog="model-routing.py", description="执行层路由配置")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    s = sub.add_parser("show")
    loc = s.add_mutually_exclusive_group()
    loc.add_argument("--change-dir")
    loc.add_argument("--openspec")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("pin")
    s.add_argument("--change-dir", required=True)
    s.set_defaults(func=cmd_pin)

    s = sub.add_parser("resolve")
    s.add_argument("--change-dir", required=True)
    s.set_defaults(func=cmd_resolve)

    s = sub.add_parser("get")
    s.add_argument("key")
    loc = s.add_mutually_exclusive_group()
    loc.add_argument("--change-dir")
    loc.add_argument("--openspec")
    s.set_defaults(func=cmd_get)

    s = sub.add_parser("frontmatter")
    s.add_argument("--check", action="store_true")
    s.add_argument("--openspec")
    s.add_argument("--commands")
    s.set_defaults(func=cmd_frontmatter)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
