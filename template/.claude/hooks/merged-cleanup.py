#!/usr/bin/env python3
# merged-cleanup · 合并后清理（零 token 判定）
#   plan  [--target T] [--remote R] [--fetch] [--markdown]   列出 worktree / 分支 / 远端分支 / 快照 ref 的清理档位
#   apply [--target T] [--remote R] [--no-fetch]             fetch → ff 同步 → 只执行 safe 档；manual 交人
# 档位：safe 自动执行 · manual 打印命令交人 · keep 保留并写原因。必须在主 worktree 运行，否则 exit 2。
# 退出码：0 正常 · 1 apply 有失败项 · 2 拒绝运行。纯标准库，兼容 Python 3.9。
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

FLIGHT_RE = re.compile(r"(^|.*/)openspec/changes/[^/]+/(timeline\.md|gate-report\.md|evidence\.log)$")
CHANGE_RE = re.compile(r"(?:^|/)openspec/changes/([^/]+)/")
HOME_DIRS = (".worktrees", os.path.join(".claude", "worktrees"))


class Refuse(Exception):
    pass


def run(cwd, *args):
    """git 调用（参数列表，不经 shell）；返回 (rc, stdout, stderr)。"""
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def out(cwd, *args):
    rc, so, _ = run(cwd, *args)
    return so.strip() if rc == 0 else None


def ok(cwd, *args):
    return run(cwd, *args)[0] == 0


def cmd_str(args):
    return " ".join(shlex.quote(a) for a in args)


def real(p):
    return os.path.realpath(p)


def under(path, base):
    return path.startswith(base.rstrip(os.sep) + os.sep)


# ---------- 定位 ----------

def main_root(cwd):
    rc, gd, _ = run(cwd, "rev-parse", "--path-format=absolute", "--git-dir")
    rc2, cd, _ = run(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if rc or rc2:
        raise Refuse("not-main-worktree: 当前目录不在 git 仓库内")
    gd, cd = real(gd.strip()), real(cd.strip())
    if gd != cd:
        raise Refuse("not-main-worktree: 当前在 linked worktree（git-dir %s），请到主 worktree %s 运行"
                     % (gd, os.path.dirname(cd)))
    return os.path.dirname(cd)


def resolve_target(root, remote, target):
    if not target:
        sym = out(root, "symbolic-ref", "-q", "refs/remotes/%s/HEAD" % remote)
        prefix = "refs/remotes/%s/" % remote
        target = sym[len(prefix):] if sym and sym.startswith(prefix) else "main"
    for ref in ("refs/remotes/%s/%s" % (remote, target), "refs/heads/" + target):
        if ok(root, "rev-parse", "--verify", "-q", ref):
            return target, ref
    raise Refuse("no-target: 找不到 refs/remotes/%s/%s 或 refs/heads/%s" % (remote, target, target))


# ---------- 判定 ----------

class Ctx:
    def __init__(self, root, remote, target, target_ref):
        self.root, self.remote, self.target, self.target_ref = root, remote, target, target_ref
        self.is_remote = target_ref.startswith("refs/remotes/")
        self.tgt_sha = out(root, "rev-parse", target_ref)
        self.tgt_tree = out(root, "rev-parse", target_ref + "^{tree}")
        self.fp = set((out(root, "rev-list", "--first-parent", target_ref) or "").split())

    def merged(self, tip):
        if tip in self.fp:
            return "fresh"
        if ok(self.root, "merge-base", "--is-ancestor", tip, self.target_ref):
            return "ancestor"
        rc, so, _ = run(self.root, "merge-tree", "--write-tree", self.target_ref, tip)
        if rc == 0 and so.splitlines()[:1] == [self.tgt_tree]:
            return "content"
        return "unmerged"


def keep_reason(state, target):
    if state == "fresh":
        return "fresh: tip 在 %s 的 first-parent 链上，没有独有提交" % target
    return "unmerged: 未合入 %s" % target


def list_worktrees(root):
    rc, so, _ = run(root, "worktree", "list", "--porcelain")
    wts, cur = [], None
    for line in so.splitlines():
        if not line:
            cur = None
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur = {"path": val, "head": None, "branch": None, "locked": None, "prunable": None}
            wts.append(cur)
        elif cur is None:
            continue
        elif key == "HEAD":
            cur["head"] = val
        elif key == "branch":
            cur["branch"] = val
        elif key == "locked":
            cur["locked"] = val or "（未写原因）"
        elif key == "prunable":
            cur["prunable"] = val or "gitdir 已失效"
    return wts


def status_paths(wt):
    rc, so, _ = run(wt, "status", "--porcelain=v1", "-z", "--ignore-submodules=none", "--untracked-files=all")
    segs, paths, i = so.split("\0"), [], 0
    while i < len(segs):
        s = segs[i]
        i += 1
        if len(s) < 4:
            continue
        paths.append(s[3:])
        if s[0] in "RC":  # 重命名 / 复制：下一段是原路径
            if i < len(segs) and segs[i]:
                paths.append(segs[i])
            i += 1
    return paths


def is_flight(p):
    return p == ".openspec-slice" or bool(FLIGHT_RE.match(p))


def check_subs(ctx, wt, item):
    """D5：已填充子仓 → force；子仓库随 W 删除且有未推送提交 → manual。返回是否命中 manual。"""
    populated = []
    for line in (out(wt, "ls-files", "-s") or "").splitlines():
        meta, _, path = line.partition("\t")
        if meta.startswith("160000 ") and os.path.exists(os.path.join(wt, path, ".git")):
            populated.append(path)
    if not populated:
        return False
    item["force"] = True
    item["reasons"].append("submodule: " + ",".join(populated))
    own = real(out(wt, "rev-parse", "--path-format=absolute", "--git-dir") or wt)
    rwt = real(wt)
    manual = False
    for p in populated:
        sub = os.path.join(wt, p)
        common = real(out(sub, "rev-parse", "--path-format=absolute", "--git-common-dir") or sub)
        if not (under(common, own) or under(common, rwt)):
            item["_prune_subs"].append(common)
            continue
        tips = [out(sub, "rev-parse", "HEAD")]
        tips += (out(sub, "for-each-ref", "--format=%(objectname)", "refs/heads", "refs/flight-sub") or "").split()
        main_sub = os.path.join(ctx.root, p)
        for tip in dict.fromkeys(t for t in tips if t):
            if os.path.exists(os.path.join(main_sub, ".git")) and ok(main_sub, "cat-file", "-e", tip + "^{commit}"):
                continue
            if out(sub, "for-each-ref", "--contains", tip, "--format=%(refname)", "refs/remotes"):
                continue
            item["reasons"].append("unpushed-submodule: %s %s 只存在于该 worktree 的子仓库，删除会丢失；"
                                   "先推送子仓（或在主 checkout 里 fetch 它）" % (p, tip[:10]))
            manual = True
            break
    return manual


def worktree_item(ctx, wt):
    path = real(wt["path"])
    root = real(ctx.root)
    name = os.path.relpath(path, root).replace(os.sep, "/") if under(path, root) else path
    item = {"kind": "worktree", "name": name, "merged": "-", "tier": "safe", "force": False,
            "reasons": [], "dirty": [], "command": "", "_path": path, "_prune_subs": [], "_branch": wt["branch"]}
    if wt["prunable"]:
        item["reasons"].append("prunable: " + wt["prunable"])
        item["command"] = "git worktree prune"
        item["_prunable"] = True
        return item
    state = ctx.merged(wt["head"])
    item["merged"] = state
    manual = False
    missing = not os.path.isdir(path)  # locked 的 worktree 目录被删，git 不报 prunable
    changes = [] if missing else status_paths(path)
    if missing:
        item["reasons"].append("missing: worktree 目录已不存在，只剩 git 登记")
        manual = True
    if changes:
        item["force"] = True
        if all(is_flight(p) for p in changes):
            item["reasons"].append("flight-records: " + ",".join(changes))
        else:
            item["dirty"] = changes
            item["reasons"].append("dirty: %d 处未提交改动，需人工确认后再删" % len(changes))
            manual = True
    if not missing:
        manual = check_subs(ctx, path, item) or manual
    if wt["locked"]:
        item["reasons"].append("locked: " + wt["locked"])
        manual = True
    if not any(under(path, os.path.join(root, d)) for d in HOME_DIRS):
        item["reasons"].append("outside: 不在 .worktrees/ 或 .claude/worktrees/ 下")
        manual = True
    rm = ["git", "worktree", "remove"] + (["--force"] if item["force"] else []) + [name]
    item["command"] = cmd_str(rm)
    item["_args"] = rm[1:]
    if wt["locked"]:
        item["command"] = cmd_str(["git", "worktree", "unlock", name]) + " && " + item["command"]
    if state in ("fresh", "unmerged"):
        item["tier"] = "keep"
        item["reasons"].append(keep_reason(state, ctx.target))
    elif manual:
        item["tier"] = "manual"
    return item


def branch_item(ctx, b, eff_head, wt_item):
    tip = out(ctx.root, "rev-parse", "refs/heads/" + b)
    state = ctx.merged(tip)
    item = {"kind": "branch", "name": b, "merged": state, "tier": "keep", "force": False,
            "reasons": [], "dirty": [], "command": ""}
    if state in ("fresh", "unmerged"):
        item["reasons"].append(keep_reason(state, ctx.target))
        return item
    if wt_item is not None and wt_item["tier"] == "keep":
        item["reasons"] = [r for r in wt_item["reasons"] if r.startswith(("fresh", "unmerged"))]
        return item
    flag = "-d"
    tier = "safe"
    if state == "content":
        flag, tier = "-D", "manual"
        item["reasons"].append("content: merge-tree 结果与 %s 树相同（squash 等方式合入）" % ctx.target)
    else:
        up = out(ctx.root, "for-each-ref", "--format=%(upstream)", "refs/heads/" + b)
        ref = up if up and ok(ctx.root, "rev-parse", "--verify", "-q", up) else eff_head
        if not ok(ctx.root, "merge-base", "--is-ancestor", tip, ref):
            flag, tier = "-D", "manual"
            item["reasons"].append("reference: tip 不是 %s 的祖先，git branch -d 会拒绝" % ref)
    if wt_item is not None and wt_item["tier"] == "manual":
        tier = "manual"
    item["tier"] = tier
    item["command"] = cmd_str(["git", "branch", flag, b])
    return item


def plan_sync(ctx, warnings):
    root = ctx.root
    head = out(root, "rev-parse", "HEAD")
    if head == ctx.tgt_sha:
        return None, head
    cur = out(root, "symbolic-ref", "-q", "HEAD")
    src = "%s/%s" % (ctx.remote, ctx.target) if ctx.is_remote else ctx.target
    if cur != "refs/heads/" + ctx.target:
        warnings.append("not-on-target: 主 worktree 当前不在 %s，跳过同步" % ctx.target)
        return None, head
    if not ok(root, "merge-base", "--is-ancestor", head, ctx.target_ref):
        if not ok(root, "merge-base", "--is-ancestor", ctx.target_ref, head):
            warnings.append("diverged: 本地 %s 与 %s 已分叉，跳过同步" % (ctx.target, src))
        return None, head
    if out(root, "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all"):
        warnings.append("dirty: 主 worktree 有未提交改动，跳过同步")
        return None, head
    sync = {"from": head, "to": ctx.tgt_sha, "command": cmd_str(["git", "merge", "--ff-only", src])}
    return sync, ctx.tgt_sha


def landed_changes(ctx):
    names = out(ctx.root, "ls-tree", "-r", "--name-only", ctx.target_ref) or ""
    return set(m.group(1) for m in (CHANGE_RE.search(p) for p in names.splitlines()) if m)


def compute(ctx):
    warnings = []
    sync, eff_head = plan_sync(ctx, warnings)
    wts = list_worktrees(ctx.root)
    main_branch = wts[0]["branch"] if wts else None
    wt_items = [worktree_item(ctx, wt) for wt in wts[1:]]
    by_branch = dict((i["_branch"], i) for i in wt_items if i["_branch"])
    br_items = []
    heads = (out(ctx.root, "for-each-ref", "--format=%(refname)", "refs/heads/") or "").split()
    for ref in heads:
        b = ref[len("refs/heads/"):]
        if not b.startswith("worktree-") or ref == main_branch:
            continue
        br_items.append(branch_item(ctx, b, eff_head, by_branch.get(ref)))
    rm_items = []
    if ctx.is_remote:
        prefix = "refs/remotes/%s/" % ctx.remote
        for ref in (out(ctx.root, "for-each-ref", "--format=%(refname)", prefix) or "").split():
            b = ref[len(prefix):]
            if not b.startswith("worktree-"):
                continue
            state = ctx.merged(out(ctx.root, "rev-parse", ref))
            if state in ("ancestor", "content"):
                rm_items.append({"kind": "remote", "name": "%s/%s" % (ctx.remote, b), "merged": state,
                                 "tier": "manual", "force": False, "reasons": [], "dirty": [],
                                 "command": cmd_str(["git", "push", ctx.remote, "--delete", b])})
    ref_items = []
    flight = (out(ctx.root, "for-each-ref", "--format=%(refname)", "refs/flight/") or "").split()
    if flight:
        landed = landed_changes(ctx)
        for ref in flight:
            parts = ref.split("/")
            if len(parts) > 3 and parts[2] in landed:
                ref_items.append({"kind": "ref", "name": ref, "merged": "landed", "tier": "safe", "force": False,
                                  "reasons": [], "dirty": [], "command": cmd_str(["git", "update-ref", "-d", ref])})
    items = wt_items + br_items + rm_items + ref_items
    manual = [i["command"] for i in wt_items + br_items + rm_items if i["tier"] == "manual"]
    return {"ok": True, "target": ctx.target, "target_ref": ctx.target_ref, "sync": sync,
            "items": items, "manual": manual, "warnings": warnings}


def public(plan):
    res = dict(plan)
    res["items"] = [dict((k, v) for k, v in i.items() if not k.startswith("_")) for i in plan["items"]]
    return res


def markdown(plan):
    safe = [i for i in plan["items"] if i["tier"] == "safe"]
    keep = [i for i in plan["items"] if i["tier"] == "keep"]
    lines = ["## 将自动执行（safe）", ""]
    if plan["sync"]:
        lines.append("- `%s`（同步 %s）" % (plan["sync"]["command"], plan["target"]))
    lines += ["- `%s`（%s %s）" % (i["command"], i["kind"], i["name"]) for i in safe]
    if not plan["sync"] and not safe:
        lines.append("- 无")
    lines += ["", "## 交你执行（manual）", ""]
    for i in plan["items"]:
        if i["tier"] == "manual" and i["reasons"]:
            lines.append("- %s %s：%s" % (i["kind"], i["name"], "；".join(i["reasons"])))
    lines += ["", "```bash"] + plan["manual"] + ["```", "", "## 保留（keep）", ""]
    if keep:
        lines += ["| 类型 | 名称 | 原因 |", "|---|---|---|"]
        lines += ["| %s | %s | %s |" % (i["kind"], i["name"], "；".join(i["reasons"]).replace("|", "\\|"))
                  for i in keep]
    else:
        lines.append("- 无")
    if plan["warnings"]:
        lines += ["", "## 提示", ""] + ["- " + w for w in plan["warnings"]]
    return "\n".join(lines) + "\n"


# ---------- 执行 ----------

def apply(root, args):
    done, failed = [], []

    def do(argv, cwd=root, label=None):
        rc, _, se = run(cwd, *argv)
        cmd = label or cmd_str(["git", *argv])
        if rc == 0:
            done.append(cmd)
        else:
            failed.append({"command": cmd, "error": se.strip() or "exit %d" % rc})
        return rc == 0

    if not args.no_fetch:
        do(["fetch", "--prune", args.remote])
    target, target_ref = resolve_target(root, args.remote, args.target)
    ctx = Ctx(root, args.remote, target, target_ref)
    plan = compute(ctx)
    if plan["sync"]:
        src = plan["sync"]["command"].split()[-1]
        if do(["merge", "--ff-only", src], label=plan["sync"]["command"]):
            plan = compute(ctx)
    wts = [i for i in plan["items"] if i["kind"] == "worktree" and i["tier"] == "safe" and not i.get("_prunable")]
    claude = os.path.join(real(root), ".claude", "worktrees")
    wts.sort(key=lambda i: 0 if under(i["_path"], claude) else 1)
    for i in wts:
        if do(i["_args"], label=i["command"]):
            for c in i["_prune_subs"]:
                do(["--git-dir=" + c, "worktree", "prune"])
    do(["worktree", "prune"])
    for kind in ("ref", "branch"):
        for i in plan["items"]:
            if i["kind"] == kind and i["tier"] == "safe":
                do(shlex.split(i["command"])[1:], label=i["command"])
    kept = [i["name"] for i in plan["items"] if i["tier"] == "keep"]
    return {"ok": not failed, "done": done, "failed": failed, "manual": plan["manual"], "kept": kept}


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="merged-cleanup")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--target")
        p.add_argument("--remote", default="origin")
        if name == "plan":
            p.add_argument("--fetch", action="store_true")
            p.add_argument("--markdown", action="store_true")
        else:
            p.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args(argv)
    try:
        root = main_root(os.getcwd())
        if args.cmd == "apply":
            res = apply(root, args)
            emit(res)
            return 0 if res["ok"] else 1
        if args.fetch:
            run(root, "fetch", "--prune", args.remote)
        target, target_ref = resolve_target(root, args.remote, args.target)
        plan = compute(Ctx(root, args.remote, target, target_ref))
    except Refuse as e:
        emit({"ok": False, "reasons": [str(e)]})
        return 2
    if args.markdown:
        sys.stdout.write(markdown(plan))
    else:
        emit(public(plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
