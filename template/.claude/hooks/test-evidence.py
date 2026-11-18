#!/usr/bin/env python3
# test-evidence · PostToolUse / PostToolUseFailure(Bash)：测试运行留痕，代替模型自述 RED / GREEN
#
# 认作测试运行的 Bash 命令追加一行留痕：
#   ISO时间\t<切片id 或 ->\t<PASS|FAIL>\t<命令前 120 字符>
# change 目录来源（三级，不猜）：① git toplevel 下 .openspec-slice 标记的 change_dir；
#   ② 分支名 worktree-<name> 对应 openspec/changes/<name>；③ tasks.md 仍有未勾选项的 change 恰好 1 个；否则不写。
# 留痕去处：来自 ① 标记 → <git common dir>/flight-evidence/<change 目录名>/<切片>.log（同仓任何 worktree 可读，
#   不写工作树）；来自 ②③ 或取不到共用目录 → <change>/evidence.log。
# 心跳：有标记时任何 Bash 事件都先确保 <切片>.log 存在（无行即空文件 = hook 在工作）；无标记不在共用目录建任何东西。
# 认定测试运行：命中 TEST_RE 运行器名字，或命令含本片 verify / 顶层 gate.test 里的脚本路径记号
#   （按空白与 ; & | ( ) 引号切开，含 / 且以 .sh .py .js .mjs .ts 结尾）；slices.json 读不到 → 只按运行器名字认。
# 结果判定：事件为 PostToolUseFailure → FAIL；否则 stdout/stderr 命中 failed|error|FAIL → FAIL；其余 PASS。
# fail-open：任何异常静默退出。兼容 Python 3.8+。
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

TEST_RE = re.compile(r"\b(pytest|npm (run )?test|pnpm (run )?test|yarn test|vitest|jest|go test|cargo test|make test|tox|unittest|mocha)\b")
FAIL_RE = re.compile(r"\b(failed|failures?|errors?|FAIL|FAILED)\b")
UNCHECKED = re.compile(r"^\s*[-*+]\s+\[ \]", re.M)
MARKER = ".openspec-slice"
BRANCH_PREFIX = "worktree-"
EVIDENCE = "evidence.log"
SHARED = "flight-evidence"
TOKEN_SPLIT = re.compile(r"[\s;&|()'\"]+")
SCRIPT_EXT = (".sh", ".py", ".js", ".mjs", ".ts")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def toplevel(cwd):
    try:
        p = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except OSError:
        pass
    return cwd


def current_branch(root):
    """git branch --show-current；失败或 detached HEAD（空串）返回 None。"""
    try:
        p = subprocess.run(["git", "branch", "--show-current"], cwd=root, capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
    except OSError:
        pass
    return None


def common_dir(root):
    """git common dir 的绝对路径（相对路径按 root 解析）；取不到返回 None。"""
    try:
        p = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=root, capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            return os.path.normpath(os.path.join(root, p.stdout.strip()))
    except OSError:
        pass
    return None


def read_marker(root):
    """切片标记指向的 (change_dir, slice_id)；无标记或无效返回 (None, None)。"""
    marker = os.path.join(root, MARKER)
    if os.path.isfile(marker):
        try:
            with open(marker, "r", encoding="utf-8") as f:
                data = json.load(f)
            cd = data.get("change_dir") or ""
            if not os.path.isabs(cd):
                cd = os.path.join(root, cd)
            if os.path.isdir(cd):
                return cd, data.get("slice") or "-"
        except (OSError, ValueError):
            pass
    return None, None


def find_change(root):
    """无标记时的两级回退：返回 (change_dir, "-")；找不到或多候选返回 (None, None)。"""
    changes = os.path.join(root, "openspec", "changes")
    if not os.path.isdir(changes):
        return None, None
    # 2 分支名 worktree-<name>
    branch = current_branch(root)
    if branch and branch.startswith(BRANCH_PREFIX):
        cd = os.path.join(changes, branch[len(BRANCH_PREFIX):])
        if os.path.isdir(cd):
            return cd, "-"
    # 3 唯一候选
    candidates = []
    for name in sorted(os.listdir(changes)):
        if name == "archive":
            continue
        tasks = os.path.join(changes, name, "tasks.md")
        try:
            with open(tasks, "r", encoding="utf-8") as f:
                if UNCHECKED.search(f.read()):
                    candidates.append(os.path.join(changes, name))
        except OSError:
            continue
    if len(candidates) == 1:
        return candidates[0], "-"
    return None, None


def text_of(resp):
    if isinstance(resp, dict):
        return "%s\n%s" % (resp.get("stdout") or "", resp.get("stderr") or "")
    if isinstance(resp, list):
        return "\n".join(str(c.get("text", "")) if isinstance(c, dict) else str(c) for c in resp)
    return str(resp or "")


def script_tokens(change_dir, slice_id):
    """本片 verify 与顶层 gate.test 里的脚本路径记号；读不到或解析失败返回空列表。"""
    try:
        with open(os.path.join(change_dir, "slices.json"), "r", encoding="utf-8") as f:
            plan = json.load(f)
        texts = [str((plan.get("gate") or {}).get("test") or "")]
        texts += [str(s.get("verify") or "") for s in plan.get("slices") or [] if s.get("id") == slice_id]
    except (OSError, ValueError, AttributeError, TypeError):
        return []
    return [t for text in texts for t in TOKEN_SPLIT.split(text) if "/" in t and t.endswith(SCRIPT_EXT)]


def main():
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    if data.get("tool_name") != "Bash":
        return
    cmd = (data.get("tool_input") or {}).get("command") or ""
    root = toplevel(data.get("cwd") or os.getcwd())
    change_dir, slice_id = read_marker(root)
    common = common_dir(root) if change_dir else None
    if common:
        # 有标记：先留心跳（判断是不是测试命令之前），再按运行器名字或脚本路径记号认定
        shared = os.path.join(common, SHARED, os.path.basename(os.path.normpath(change_dir)))
        os.makedirs(shared, exist_ok=True)
        log = os.path.join(shared, slice_id + ".log")
        open(log, "a", encoding="utf-8").close()
        if not (TEST_RE.search(cmd) or any(t in cmd for t in script_tokens(change_dir, slice_id))):
            return
    else:
        if not TEST_RE.search(cmd):
            return
        if not change_dir:
            change_dir, slice_id = find_change(root)
            if not change_dir:
                return
        log = os.path.join(change_dir, EVIDENCE)
    if data.get("hook_event_name") == "PostToolUseFailure":
        result = "FAIL"
    else:
        result = "FAIL" if FAIL_RE.search(text_of(data.get("tool_response"))) else "PASS"
    with open(log, "a", encoding="utf-8") as f:
        f.write("%s\t%s\t%s\t%s\n" % (now_iso(), slice_id, result, cmd.replace("\n", " ")[:120]))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
