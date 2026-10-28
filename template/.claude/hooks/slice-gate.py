#!/usr/bin/env python3
# slice-gate · 切片规划 lint 与切片门禁（零 token）
#
# 子命令：
#   lint     --change-dir DIR                 校验 slices.json；stdout 打印 waves JSON；违规 exit 2 并在 stderr 点名规则
#                                              含 gate.checks（name/baseline/final/timeout_sec）与 checks_skip 形状，并对账 <openspec 根>/gate-checks.json 默认检查
#                                              tiers:：<openspec 根>/test-tiers.json 存在时校验其形状、gate.test == unit.cmd、
#                                              gate.integration / integration_skip、covers × owns 表态、scenario 测试归层；不存在而计划写了区域选择 → 报缺文件
#   waves    --change-dir DIR                 只打印 waves JSON
#   start    S --change-dir DIR [--base REF] [--expect-branch BRANCH]
#                                              在 git toplevel 写 .openspec-slice 标记（slice / change_dir / base / started）；
#                                              标记已是同一切片时不改（resume），保住区间与 red_count；
#                                              给了 --expect-branch 先校验 HEAD 是该分支最新 commit 的后代，否则打印 G0 JSON、exit 1、不写标记
#                                              无同片标记时：带 --resume-checkpoint 恢复 refs/flight/<change>/<S> 快照（stdout 追加 checkpoint），
#                                              不带则清掉本片旧快照
#   checkpoint                                 PostToolUse hook：有标记时把本片 owns 内改动快照到 refs/flight/<change>/<S>；静默、恒 exit 0
#   gate     S --change-dir DIR [--base REF]  跑 G1–G8、G12（分层文件合法时：区间内改动的测试文件须落在单元层或已选区域）；stdout 打印 JSON（含 base）；追加 gate-report.md；ok 时删标记，红时标记 red_count+1
#   record   --change-dir DIR --json '<gate JSON>' | --slice S --commit SHA [--red] [--failed ...] [--warnings ...]
#                                              把（临时 worktree 里跑出的）门禁结论幂等写回分支的 gate-report.md / timeline.md
#   final    --change-dir DIR                 先 G7（全部 scenario 状态），再 lint / typecheck，最后全量 test（均按基线差分）；
#                                              G7 红不跑全量；最后运行 gate.checks 的 final（G9，先核对基线记录，G7 红不跑）
#                                              分层文件合法时：单元层带探针判 G10 / G11，已选区域按基线 regions 差分（缺记录 / cmd 变 → G2 region 红）
#   baseline --change-dir DIR [--full]        起飞前预检：先把 gate-baseline.json 写成运行标记 {running, pid, started}，
#                                              再跑 gate.test / lint / typecheck 与每片 verify，结束时整体覆盖为结果；
#                                              耗时写回 slices.json.gate.full_suite_sec；退出码按 ok；
#                                              结果带 change / mode / snapshot / cmd_key / byproducts；旧基线可复用（cmd_key 相同、
#                                              Δ 只有 test_*.py 且补跑不红）→ mode incremental：不跑 gate.test，verify 只重跑受影响的片；
#                                              --full 不复用；运行期间已有文件或测试文件被改 → 红，新出现的非测试文件 → 副产物只警告；
#                                              走全量且判过候选时记 reuse_skipped（≤5 条）；开跑前内容快照失败 → 停下、不写运行标记；
#                                              配了 gate.checks 时在每片 verify 之后跑每个 baseline 非空的检查（共用目录
#                                              <git common dir>/flight-gate-checks/<change>/<name>，记 checks.<name>；沿用条件同 lint / typecheck
#                                              且目录仍在），检查红 / 超时 → 基线红
#                                              分层文件存在时：恒走全量，单元层带探针判 G10 / G11（红 → 基线红），verify 之后逐个跑已选区域记 regions；
#                                              分层文件不合法或 gate.integration 有未知区域 → 停下、不写运行标记
#   preflight --change-dir DIR                lint_plan + 运行标记识别（仍在跑 / 已中断）+ 基线四项校验（存在 / ok / plan_sha /
#                                              commit 在分支历史）；基线带 snapshot 且 timeline.md 无 approve 事件时再按内容判过期
#                                              （Δ 非空 → 基线过期）；通过打印 waves；plan_sha 含各检查的 [name, baseline]，只改 final 不算过期
#                                              分层文件存在时已选区域的基线 regions.<name>.cmd 须等于分层文件当前 cmd，否则基线过期
#
# G2 差分：gate / final 的 lint / typecheck 非 0 时，与 gate-baseline.json 里规范化后的输出行比对，只为新增行判红；
#          无基线或该项基线为 null 时行为不变（直接判红）。
#          gate.test 经 PYTEST_ADDOPTS 注入 --junitxml，可度量的 exit 1 按失败用例标识（classname::name）逐条差分：
#          baseline 记 test.failed，final 只为基线外的失败判红；不可度量（非 pytest / 多次 pytest / 计数不一致 / exit≠1）按退出码判。
#
# JSON 契约：{"slice", "ok", "commit", "failed": [...], "warnings": [...],
#             "ceilings": [[路径, 行号, 限制, 升级路径], ...], "summary"}；failed 每项以 G<n> 开头并点名对象。
#             ceilings 由执行体转写后经 record --json 回流，形状不可信：解析见 ceiling_rows_from_json，绝不抛异常。
#             探针：run_test_gate(cmd, root, probe=True) 另返回 probe = {nodeid: {"sec", "hits": {"文件"|"子进程"|"网络": 样例}}}
#             或 None（不可度量，probe_why 写原因）；probe=False 时二者恒为 None。
#             防护插件：run_test_gate 恒加载 flight_guard，嵌套 pytest 会话不写 junit、不写探针 / 依赖图记录；
#             任一 flight 插件加载失败 → 去掉插件只带 junit 重跑一次，探针 / 依赖图判没测到（*_why 写原因）。
#             依赖图：run_test_gate(..., deps=True) / _pytest_outcomes(..., deps_out={}) 另返回
#             deps = {"deps": {测试文件: [仓库文件...]}, "blind", "files", "nodes": {仓库相对 nodeid: outcome}} 或 None（deps_why）。
#             锚点池：baseline 跑全量后向 <git common dir>/flight-anchors/ 写一条锚点（只留最新 20 条），
#             gate-baseline.json 的 test 段在有失败且依赖图测到时另记 failed_nodes（仓库相对 nodeid）。
#             gate-baseline.json 配了 gate.checks 时另有 "checks": {name: {exit, sec, cmd, key[, reused][, timed_out]}}；未配置时无此键。
#             gate-baseline.json 有分层文件时另有 "tiers": {"measured": bool[, "why"]} 与 "regions": {name: {exit, sec, cmd[, failed]}}；
#             无分层文件时无这两个键。
#             分层文件合法时 gate / final 的 JSON 与 gate-baseline.json（及 baseline 的 stdout）另有
#             "tier_sec": {"unit", "integration", "regions": {name: 秒}[, "unclassified"]}，summary / timeline 备注带「单元 Xs · 集成 Ys」；
#             无分层文件时无此键，summary 与备注不变。
# 兼容 Python 3.8+，只用标准库。
import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
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
# 逐用例结论口径（G7 插件与依赖图插件共用）：report → PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS，不记的返回 None
OUTCOME_SRC = '''

def _outcome(report):
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            return "XPASS" if report.passed else "XFAIL"
        if report.failed and isinstance(report.longrepr, str) and report.longrepr.startswith("[XPASS(strict)]"):
            return "XPASS"  # 严格 xfail 意外通过：pytest 记 failed、longrepr 带此前缀、不设 wasxfail
        return report.outcome.upper()
    if report.failed:
        return "ERROR"
    if report.skipped:
        return "XFAIL" if hasattr(report, "wasxfail") else "SKIPPED"
    return None
'''
G7_PLUGIN = '''import json, os
''' + OUTCOME_SRC + '''

_sec = {}


def pytest_runtest_logreport(report):
    if "FLIGHT_G7_SEC" in os.environ:
        _sec[report.nodeid] = _sec.get(report.nodeid, 0.0) + report.duration
        if report.when == "teardown":
            with open(os.environ["FLIGHT_G7_SEC"], "a", encoding="utf-8") as f:
                f.write(json.dumps([report.nodeid, _sec.pop(report.nodeid)]) + "\\n")
    out = _outcome(report)
    if out is None:
        return
    with open(os.environ["FLIGHT_G7_OUT"], "a", encoding="utf-8") as f:
        f.write(json.dumps([report.nodeid, out]) + "\\n")
'''
# 嵌套会话防护插件（design D1）：写进临时目录为 flight_guard.py，与 --junitxml 一起经 -p 恒加载；
# 环境里没有 FLIGHT_GUARD_OWNER 且不是 worker → 外层（设 OWNER，给自己的 xdist worker 写 flight_outer）；
# 带 flight_outer 的 worker 算外层；其余是嵌套：抢在 junitxml 之前清掉 xmlpath，并设 FLIGHT_GUARD_NESTED=1（探针 / 依赖图据此不写）
GUARD_PLUGIN = '''import os

import pytest

_outer = [False]


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    wi = getattr(config, "workerinput", None)
    if wi is None and not os.environ.get("FLIGHT_GUARD_OWNER"):
        os.environ["FLIGHT_GUARD_OWNER"] = str(os.getpid())
        os.environ.pop("FLIGHT_GUARD_NESTED", None)
        _outer[0] = True
        return
    if wi is not None and wi.get("flight_outer"):
        return
    config.option.xmlpath = None
    os.environ["FLIGHT_GUARD_NESTED"] = "1"


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node):
    if _outer[0]:
        node.workerinput["flight_outer"] = 1
'''
# 依赖图公共部分（flight_deps.py 与 sitecustomize.py 共用，design D2）：仓库文件判定、审计事件 → 依赖 / 盲
DEPS_CORE = '''import json, os, sys

_ROOT = os.path.realpath(os.environ.get("FLIGHT_ROOT") or os.getcwd())
_TMP = os.path.dirname(os.path.realpath(__file__))
_EXCLUDE = (os.path.join(_ROOT, ".git") + os.sep, _TMP + os.sep)
_busy = [False]


def _nested():
    return os.environ.get("FLIGHT_GUARD_NESTED") == "1"


def _abs_rel(p):
    """绝对路径 → 仓库相对路径（/ 分隔）；不在仓库内、在 .git/ 或门禁临时目录内 → None。"""
    if not p.startswith(_ROOT + os.sep) or p.startswith(_EXCLUDE):
        return None
    return os.path.relpath(p, _ROOT).replace(os.sep, "/")


def _repo_rel(path, cwd=None):
    """被打开 / 被执行的路径 → 仓库内现存文件的相对路径；__pycache__/<stem>.<tag>.pyc 映射回 <dir>/<stem>.py。"""
    if isinstance(path, int):
        return None
    try:
        p = os.fsdecode(path)
        if not os.path.isabs(p):
            p = os.path.join(os.fsdecode(cwd) if cwd else os.getcwd(), p)
        p = os.path.realpath(p)
    except (TypeError, ValueError, OSError):
        return None
    d, base = os.path.split(p)
    if base.endswith(".pyc"):
        if os.path.basename(d) != "__pycache__":
            return None
        p = os.path.join(os.path.dirname(d), base.split(".", 1)[0] + ".py")
    if not os.path.isfile(p):
        return None
    return _abs_rel(p)


def _argv(args):
    if isinstance(args, (str, bytes)):
        return [os.fsdecode(args)]
    try:
        return [os.fsdecode(a) for a in args]
    except TypeError:
        return []


def _is_blind(executable, argv, env):
    """Python 子进程看不见：env 显式给出且 PYTHONPATH 不含门禁临时目录，或带 -I / -S / -E。"""
    names = [os.path.basename(a) for a in ([os.fsdecode(executable)] if executable else []) + argv[:1]]
    if not any(n.startswith("python") for n in names):
        return False
    for a in argv[1:]:
        if not a.startswith("-"):
            break
        if a in ("-I", "-S", "-E"):
            return True
    if env is None:
        return False
    try:
        pp = env.get("PYTHONPATH") or env.get(b"PYTHONPATH") or ""
        return _TMP not in [os.path.realpath(x) for x in os.fsdecode(pp).split(os.pathsep) if x]
    except (AttributeError, TypeError):
        return False


def _observe(event, args, deps):
    """审计事件 → 仓库文件加进 deps（set）；返回该事件是否让当前测试文件变盲。"""
    if event == "open":
        r = _repo_rel(args[0]) if args else None
        if r:
            deps.add(r)
        return False
    if event == "subprocess.Popen":
        executable, argv, cwd, env = args[0], _argv(args[1]), args[2], args[3]
    elif event in ("os.exec", "os.posix_spawn"):
        executable, argv, cwd, env = args[0], _argv(args[1]), None, args[2]
    else:
        return False
    for a in ([os.fsdecode(executable)] if executable else []) + argv:
        r = _repo_rel(a, cwd)
        if r:
            deps.add(r)
    return _is_blind(executable, argv, env)


def _emit(recs):
    out = os.environ.get("FLIGHT_DEPS_OUT")
    if not out or not recs:
        return
    saved, _busy[0] = _busy[0], True
    try:
        with open(out, "a", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    except OSError:
        pass
    finally:
        _busy[0] = saved
'''
# 依赖图插件：写进临时目录为 flight_deps.py，经 -p 加载；收集窗口与用例窗口里记 open / 子进程 argv，
# 会话结束并入测试文件的静态 import 闭包；逐用例结论口径同 G7；记录以 JSON 行追加进 FLIGHT_DEPS_OUT
DEPS_PLUGIN = DEPS_CORE + OUTCOME_SRC + '''
import ast

import pytest

_cur = [None]
_cfg = [None]
_deps = {}
_blind = set()
_files = set()
_keys = {}
_nodes = []
_edges = {}


def _hook(event, args):
    key = _cur[0]
    if key is None or _busy[0] or _nested():
        return
    _busy[0] = True
    try:
        if _observe(event, args, _deps.setdefault(key, set())):
            _blind.add(key)
    except Exception:
        pass
    finally:
        _busy[0] = False


sys.addaudithook(_hook)


def _key(node):
    p = getattr(node, "path", None) or getattr(node, "fspath", None)
    return _abs_rel(os.path.realpath(str(p))) if p is not None else None


def _enter(key):
    _cur[0] = key
    if key is not None:
        _files.add(key)
        os.environ["FLIGHT_DEPS_FILE"] = key


def _leave():
    _cur[0] = None
    os.environ.pop("FLIGHT_DEPS_FILE", None)


def pytest_configure(config):
    _cfg[0] = config


def pytest_sessionstart(session):
    if not _nested():
        _emit([{"flight_deps": "start"}])


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    on = not _nested() and isinstance(collector, pytest.Module)
    if on:
        _enter(_key(collector))
    yield
    if on:
        _leave()


def _window(item):
    if _nested():
        return None
    key = _key(item)
    if key is not None:
        _keys[item.nodeid] = key
    return key


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _enter(_window(item))
    yield
    _leave()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _enter(_window(item))
    yield
    _leave()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    _enter(_window(item))
    yield
    _leave()


def _rootdir():
    c = _cfg[0]
    return os.path.realpath(str(getattr(c, "rootpath", None) or getattr(c, "rootdir", None) or os.getcwd()))


def pytest_runtest_logreport(report):
    if _nested():
        return
    out = _outcome(report)
    if out is None:
        return
    head, sep, rest = report.nodeid.partition("::")
    key = _keys.get(report.nodeid) or _abs_rel(os.path.normpath(os.path.join(_rootdir(), head)))
    if key is not None:
        _nodes.append([key + sep + rest, out])


def _chain(path):
    """path 所在目录到仓库根的目录链。"""
    out, d = [], os.path.dirname(path)
    while d.startswith(_ROOT + os.sep) or d == _ROOT:
        out.append(d)
        if d == _ROOT:
            break
        d = os.path.dirname(d)
    return out


def _resolve(mod, level, path, roots):
    """模块名 → 仓库内 .py（含沿途包的 __init__.py）；完整解析不到 → []。"""
    if level:
        base = os.path.dirname(path)
        for _ in range(level - 1):
            base = os.path.dirname(base)
        bases = [base]
    else:
        bases = roots
    parts = [p for p in mod.split(".") if p]
    for b in bases:
        found, cur, ok = [], b, True
        for i, part in enumerate(parts):
            cur = os.path.join(cur, part)
            if i == len(parts) - 1 and os.path.isfile(cur + ".py"):
                found.append(cur + ".py")
            elif os.path.isfile(os.path.join(cur, "__init__.py")):
                found.append(os.path.join(cur, "__init__.py"))
            elif not os.path.isdir(cur):
                ok = False
                break
        if not parts and os.path.isfile(os.path.join(b, "__init__.py")):
            found.append(os.path.join(b, "__init__.py"))
        if ok and (found or parts):
            return found
    return []


def _imports(path, roots):
    """文件的全部 import（含函数体内）解析到的仓库内 .py 绝对路径；按文件缓存。"""
    if path in _edges:
        return _edges[path]
    _edges[path] = out = set()
    try:
        with open(path, "rb") as f:
            tree = ast.parse(f.read(), path)
    except (OSError, SyntaxError, ValueError):
        return out
    roots = roots + _chain(path)
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods = [(a.name, 0) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            mods = [(base, n.level)] + [((base + "." if base else "") + a.name, n.level)
                                         for a in n.names if a.name != "*"]
        else:
            continue
        for mod, level in mods:
            for q in _resolve(mod, level, path, roots):
                q = os.path.realpath(q)
                if _abs_rel(q):
                    out.add(q)
    return out


def _closure(key, roots):
    # ceiling: 逐测试文件 BFS 求闭包，O(测试文件 × 模块) -> 大仓收口变慢时改为 SCC 缩点后自底向上合并
    start = os.path.join(_ROOT, key)
    roots = roots + _chain(start)
    seen, todo = set(), [start]
    while todo:
        for q in _imports(todo.pop(), roots):
            if q not in seen:
                seen.add(q)
                todo.append(q)
    return {_abs_rel(q) for q in seen} - {None, key}


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session):
    if _nested():
        return
    roots = [_rootdir()]
    for p in sys.path:
        rp = os.path.realpath(p or os.getcwd())
        if _abs_rel(rp) is not None or rp == _ROOT:
            roots.append(rp)
    recs = []
    for key in sorted(_files):
        d = _deps.setdefault(key, set())
        d |= _closure(key, roots)
        d.discard(key)
        recs.append({"file": key, "deps": sorted(d), "test": True})
    recs += [{"file": k, "blind": True} for k in sorted(_blind)]
    recs += [{"node": n, "outcome": o} for n, o in _nodes]
    _emit(recs)
'''
# 依赖图的 Python 子进程端：写进临时目录为 sitecustomize.py，经 PYTHONPATH 生效；
# FLIGHT_DEPS_OUT 与 FLIGHT_DEPS_FILE 都在且不是嵌套会话时装同样的审计钩子，atexit 把仓库内已加载模块与 open 过的文件
# 按 FLIGHT_DEPS_FILE 追加；最后暂时去掉自身目录链到仓库自己的 sitecustomize（失败忽略），不遮蔽它
SITECUSTOMIZE = DEPS_CORE + '''
import atexit
import importlib


def _flight_site():
    if getattr(sys, "_flight_deps_site", False):  # 同一进程里另一份门禁临时目录的 sitecustomize 已装过
        return
    sys._flight_deps_site = True
    key = os.environ.get("FLIGHT_DEPS_FILE")
    if not os.environ.get("FLIGHT_DEPS_OUT") or not key or _nested():
        return
    deps, blind = set(), [False]

    def hook(event, args):
        if _busy[0]:
            return
        _busy[0] = True
        try:
            if _observe(event, args, deps):
                blind[0] = True
        except Exception:
            pass
        finally:
            _busy[0] = False

    def dump():
        _busy[0] = True
        for m in list(sys.modules.values()):
            f = getattr(m, "__file__", None)
            r = _repo_rel(f) if isinstance(f, str) else None
            if r:
                deps.add(r)
        _busy[0] = False
        rec = {"file": key, "deps": sorted(deps)}
        if blind[0]:
            rec["blind"] = True
        _emit([rec])

    sys.addaudithook(hook)
    atexit.register(dump)


_flight_site()
_saved_path = list(sys.path)
sys.path[:] = [p for p in sys.path if os.path.realpath(p or os.getcwd()) != _TMP]
_self = sys.modules.pop("sitecustomize", None)
try:
    importlib.import_module("sitecustomize")
except Exception:
    if _self is not None:
        sys.modules["sitecustomize"] = _self
finally:
    sys.path[:] = _saved_path
'''
FLIGHT_ENV = ("FLIGHT_GUARD_OWNER", "FLIGHT_GUARD_NESTED", "FLIGHT_DEPS_OUT", "FLIGHT_DEPS_FILE", "FLIGHT_ROOT")
# 三个 flight 插件任一导入失败（包装命令覆写了 PYTHONPATH 等）的 pytest 输出特征
FLIGHT_PLUGIN_FAIL = re.compile(r'Error importing plugin "flight_(?:guard|deps|tier_probe)"')
# 测试分层（design D1、D4、D13）：仓库级分层文件在 <openspec 根>/test-tiers.json；单元层用例耗时上限（秒，不可配置）
TIER_FILE = "test-tiers.json"
UNIT_MAX_SEC = 3.0
TIER_NAME_RE = re.compile(r"[a-z0-9-]+")
# 单元层探针插件：写进临时目录为 flight_tier_probe.py，经 PYTEST_ADDOPTS -p 加载；
# 只在 setup / call / teardown 窗口内用审计钩子记文件 / 子进程 / 网络触碰（import 机制与断言重写读源文件不计），
# 每个用例 teardown 后向 FLIGHT_TIER_OUT 追加一行 {nodeid, sec, hits}；会话开始先写一行 {"probe": "start"}
TIER_PROBE_PLUGIN = '''import json, os, sys

import pytest

FS = {"open", "os.mkdir", "os.remove", "os.rename", "os.rmdir", "os.chmod", "os.truncate", "os.utime",
      "os.symlink", "os.link", "os.listdir", "os.scandir", "os.walk", "glob.glob", "shutil.copyfile",
      "shutil.copytree", "shutil.move", "shutil.rmtree", "shutil.copymode", "shutil.copystat"}
PROC = {"subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.fork"}
NET = {"socket.connect", "socket.bind", "urllib.Request"}
KIND = dict([(e, "文件") for e in FS] + [(e, "子进程") for e in PROC] + [(e, "网络") for e in NET])
SKIP = ("importlib._bootstrap", "zipimport", "_pytest.assertion.rewrite", "linecache")  # linecache：回溯 / inspect 读源码
_cur = [None]
_hits = {}
_sec = {}


def _hook(event, args):
    nid = _cur[0]
    if nid is None:
        return
    kind = KIND.get(event)
    if kind is None:
        return
    f = sys._getframe(1)
    while f is not None:
        if str(f.f_globals.get("__name__") or "").startswith(SKIP):
            return
        f = f.f_back
    hits = _hits.setdefault(nid, {})
    if kind not in hits:
        hits[kind] = "%s %s" % (event, str(args[0] if args else "")[:120])


sys.addaudithook(_hook)


def _write(rec):
    path = os.environ.get("FLIGHT_TIER_OUT")
    if not path or os.environ.get("FLIGHT_GUARD_NESTED") == "1":  # 嵌套会话不写（design D1）
        return
    saved, _cur[0] = _cur[0], None
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\\n")
    finally:
        _cur[0] = saved


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _cur[0] = item.nodeid
    yield
    _cur[0] = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _cur[0] = item.nodeid
    yield
    _cur[0] = None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):
    _cur[0] = item.nodeid
    yield
    _cur[0] = None


def pytest_sessionstart(session):
    _write({"probe": "start"})


def pytest_runtest_logreport(report):
    nid = report.nodeid
    _sec[nid] = _sec.get(nid, 0.0) + (report.duration or 0.0)
    if report.when == "teardown":
        _write({"nodeid": nid, "sec": _sec.pop(nid, 0.0), "hits": _hits.pop(nid, {})})
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


def _read_probe(path):
    """读探针 jsonl → (probe | None, probe_why | None)。没有开跑记录 → 不可度量；
    同一 nodeid 多行（xdist 主进程与 worker）合并：sec 取最大、hits 按类别保留先出现的样例。"""
    started, probe = False, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("probe") == "start":
            started = True
            continue
        nid = rec.get("nodeid")
        if not isinstance(nid, str):
            continue
        cur = probe.setdefault(nid, {"sec": 0.0, "hits": {}})
        cur["sec"] = max(cur["sec"], float(rec.get("sec") or 0.0))
        for kind, sample in (rec.get("hits") or {}).items():
            cur["hits"].setdefault(kind, sample)
    if not started:
        return None, "没有探针输出（不是 pytest？）"
    return probe, None


def _flight_plugins(tmp, env, root, deps):
    """把防护插件（deps=True 时另加依赖图插件与 sitecustomize）写进 tmp，tmp 放到 env 的 PYTHONPATH 最前；
    先清掉外层门禁漏下来的 flight 环境变量（本次运行是新的外层）。返回依赖图输出路径（deps=False 时 None）。"""
    for k in FLIGHT_ENV:
        env.pop(k, None)
    files = {"flight_guard.py": GUARD_PLUGIN}
    if deps:
        files.update({"flight_deps.py": DEPS_PLUGIN, "sitecustomize.py": SITECUSTOMIZE})
    for name, text in files.items():
        with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
            f.write(text)
    parts = [p for p in (env.get("PYTHONPATH") or "").split(os.pathsep) if p]
    env["PYTHONPATH"] = os.pathsep.join([tmp] + [p for p in parts if p != tmp])
    if not deps:
        return None
    out = os.path.join(tmp, "deps.jsonl")
    env["FLIGHT_ROOT"] = os.path.realpath(root)
    env["FLIGHT_DEPS_OUT"] = out
    return out


def _read_deps(path):
    """读依赖图 jsonl → ({"deps": {文件: [路径...]}, "blind", "files", "nodes": {nodeid: outcome}} | None, why | None)。
    没有开跑记录 → 不可度量；同一 nodeid 多条（xdist 主进程与 worker、call 与 teardown）以 FAILED / ERROR 优先。"""
    started, deps, blind, files, nodes = False, {}, set(), set(), {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        if rec.get("flight_deps") == "start":
            started = True
            continue
        if isinstance(rec.get("node"), str):
            if nodes.get(rec["node"]) not in ("FAILED", "ERROR"):
                nodes[rec["node"]] = rec.get("outcome")
            continue
        f = rec.get("file")
        if not isinstance(f, str):
            continue
        if rec.get("test"):
            files.add(f)
        if isinstance(rec.get("deps"), list):
            deps.setdefault(f, set()).update(x for x in rec["deps"] if isinstance(x, str))
        if rec.get("blind"):
            blind.add(f)
    if not started:
        return None, "没有依赖图输出（不是 pytest？）"
    return {"deps": {f: sorted(v) for f, v in sorted(deps.items())}, "blind": sorted(blind),
            "files": sorted(files), "nodes": nodes}, None


def _deps_merge(a, b):
    """两份依赖图并起来（同一测试文件的依赖取并集；nodes 以 FAILED / ERROR 优先）。"""
    deps = {f: set(v) for f, v in a["deps"].items()}
    for f, v in b["deps"].items():
        deps.setdefault(f, set()).update(v)
    nodes = dict(a["nodes"])
    for n, o in b["nodes"].items():
        if nodes.get(n) not in ("FAILED", "ERROR"):
            nodes[n] = o
    return {"deps": {f: sorted(v) for f, v in sorted(deps.items())}, "blind": sorted(set(a["blind"]) | set(b["blind"])),
            "files": sorted(set(a["files"]) | set(b["files"])), "nodes": nodes}


def run_test_gate(cmd, root, probe=False, deps=False, _plain=False, extra_env=None):
    """跑 gate.test，经 PYTEST_ADDOPTS 注入 --junitxml 并恒加载防护插件 flight_guard（design D1）。
    返回 {"rc", "out", "failed": [classname::name, ...] | None, "why": str | None, "cases": set | None,
          "probe": {nodeid: {"sec", "hits"}} | None, "probe_why": str | None,
          "deps": {"deps", "blind", "files", "nodes"} | None, "deps_why": str | None}；
    deps=True 时另加载依赖图插件（design D2）；deps=False 时 deps / deps_why 恒为 None。
    任一 flight 插件加载失败 → 去掉全部插件、只带 junit 重跑一次（_plain）并返回其结果，探针 / 依赖图判没测到；
    failed 非 None ⇔ 可度量（rc 1、junit 可解析、汇总行恰一行、汇总与 junit 计数一致且非 0，
    且输出不含 pytest-cov 覆盖率失败标记），why 是不可度量的理由。
    cases = junit 全部 testcase 的 classname 集合：只在 rc 0（junit 可解析）与可度量的 rc 1 时给出，否则 None（design D11）。
    probe=True 时另加载探针插件（design D4）：插件加载失败 → 不带探针重跑一次并返回其结果，probe 判不可度量；
    probe=False 时 probe / probe_why 恒为 None。extra_env（dict）在 os.environ 之上追加给命令的环境变量。"""
    with tempfile.TemporaryDirectory() as tmp:
        junit = os.path.join(tmp, "junit.xml")
        env = dict(os.environ, **(extra_env or {}))
        env["PYTEST_ADDOPTS"] = (env.get("PYTEST_ADDOPTS", "") + " --junitxml=" + shlex.quote(junit)).strip()
        tier_out = os.path.join(tmp, "tier-probe.jsonl")
        deps_out = None
        if not _plain:
            deps_out = _flight_plugins(tmp, env, root, deps)
            env["PYTEST_ADDOPTS"] += " -p flight_guard" + (" -p flight_deps" if deps else "")
        if probe and not _plain:
            with open(os.path.join(tmp, "flight_tier_probe.py"), "w", encoding="utf-8") as f:
                f.write(TIER_PROBE_PLUGIN)
            env["PYTEST_ADDOPTS"] += " -p flight_tier_probe"
            env["FLIGHT_TIER_OUT"] = tier_out
        p = subprocess.run(cmd, cwd=root, shell=True, capture_output=True, text=True, env=env)
        rc, out = p.returncode, (p.stdout or "") + (p.stderr or "")
        if not _plain and FLIGHT_PLUGIN_FAIL.search(out):
            res = run_test_gate(cmd, root, _plain=True, extra_env=extra_env)
            why = "防护插件加载失败（包装命令覆写了 PYTHONPATH？），%s"
            if probe:
                res["probe_why"] = why % "探针未测；G10/G11 未判"
            if deps:
                res["deps_why"] = why % "依赖图未测"
            return res
        res = {"rc": rc, "out": out, "failed": None, "why": None, "cases": None, "probe": None, "probe_why": None,
               "deps": None, "deps_why": None}
        if probe and not _plain:
            res["probe"], res["probe_why"] = _read_probe(tier_out)
        if deps_out:
            res["deps"], res["deps_why"] = _read_deps(deps_out)
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
    checks = gate.get("checks")
    if isinstance(checks, list) and checks:  # 检查的 baseline 命令也归基线负责（design D7）；final 不在此列
        key.append([[c.get("name"), c.get("baseline")] for c in checks if isinstance(c, dict)])
    if gate.get("impacted") is not None:  # gate 命令之一（incremental-final design D8）；未配置时与旧算法相同
        key.append(["impacted", gate.get("impacted")])
    integration = gate.get("integration")
    if isinstance(integration, list) and integration:  # 已选区域归基线负责（design D9）；未选时与旧算法相同
        key.append(["integration", list(integration)])
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


def _diff_verdict(label, tg, known_failed):
    """run_test_gate 结果对基线已知失败差分，返回 (failed_item, warning_item)；label 为 test 或 region <NAME>。"""
    rc = tg["rc"]
    if rc == 0:
        return None, None
    if tg["failed"] is None:
        return "G2 %s: exit %d（按退出码判：%s）\n%s" % (label, rc, tg["why"], _tail(tg["out"])), None
    old = set(known_failed or [])
    new = [t for t in tg["failed"] if t not in old]
    if not new:
        return None, "G2 %s: exit 1，失败均为基线预存红（%d 条已按基线排除）" % (label, len(tg["failed"]))
    return "G2 %s: exit 1（新增 %d 条失败）\n%s" % (label, len(new), "\n".join(new[:6])), None


def _selected_regions(gate):
    """gate.integration 里的区域名（形状不合法时视为未选）。"""
    integration = gate.get("integration")
    return [n for n in integration if isinstance(n, str)] if isinstance(integration, list) else []


def slow_candidates(probe):
    """首跑耗时 >= UNIT_MAX_SEC 的 nodeid（排序）；probe 为 None → []。"""
    if not probe:
        return []
    return sorted(n for n, r in probe.items() if float(r.get("sec") or 0.0) >= UNIT_MAX_SEC)


def tier_verdicts(probe, probe_why, rerun, allow):
    """单元层 G10 / G11 判定（纯函数）→ (failed, warnings)。慢候选须单独重跑仍超线（或重跑无记录）才确认。"""
    if probe is None:
        return [], ["G10/G11 不可度量：%s" % probe_why]
    failed, warnings = [], []
    for nid in slow_candidates(probe):
        again = rerun.get(nid)
        if again is not None and again < UNIT_MAX_SEC:
            continue
        sec = float(probe[nid].get("sec") or 0.0)
        if nid in allow:
            warnings.append("G10 slow unit test 已人工放行：%s %.1fs（%s）" % (nid, sec, allow[nid]["approved"]))
        else:
            failed.append("G10 slow unit test: %s 首跑 %.1fs，重跑 %s（≥3s）：提速、移入集成区域，或由人类放行（test-tiers.py allow-slow）"
                          % (nid, sec, "未取得" if again is None else "%.1fs" % again))
    for nid in sorted(probe):
        hits = probe[nid].get("hits") or {}
        if hits:
            failed.append("G11 impure unit test: %s 碰了%s（%s）：改成纯函数或移入集成区域"
                          % (nid, "、".join(hits), "；".join(str(v) for v in hits.values())))
    return failed, warnings


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


CHECK_FIELDS = ("name", "baseline", "final", "timeout_sec")
CHECK_NAME_RE = re.compile(r"[a-z0-9-]+")
DEFAULT_CHECKS = "gate-checks.json"


def _nonblank(v):
    return isinstance(v, str) and bool(v.strip())


def _lint_checks(gate):
    """gate.checks / gate.checks_skip 的形状校验；返回 (errors, checks 里出现的 name 集合, checks_skip 的键集合)。"""
    errors, names, skip_keys = [], set(), set()
    checks = gate.get("checks")
    if checks is not None and not isinstance(checks, list):
        errors.append("checks: gate.checks 须是列表")
        checks = []
    dup = set()
    for i, c in enumerate(checks or []):
        if not isinstance(c, dict):
            errors.append("checks: gate.checks 第 %d 项须是对象" % (i + 1))
            continue
        name = c.get("name")
        label = name if isinstance(name, str) else "第 %d 项" % (i + 1)
        if not (isinstance(name, str) and CHECK_NAME_RE.fullmatch(name)):
            errors.append("checks: 检查名 %r 不合法（须匹配 [a-z0-9-]+）" % (name,))
        elif name in names and name not in dup:
            dup.add(name)
            errors.append("checks: 检查名 %s 重复" % name)
        if isinstance(name, str):
            names.add(name)
        extra = sorted(k for k in c if k not in CHECK_FIELDS)
        if extra:
            errors.append("checks: %s 有未知字段 %s" % (label, ", ".join(map(str, extra))))
        if not _nonblank(c.get("final")):
            errors.append("checks: %s 缺少 final 命令（须是非空字符串）" % label)
        if c.get("baseline") is not None and not _nonblank(c.get("baseline")):
            errors.append("checks: %s 的 baseline 须缺省、null 或非空字符串" % label)
        t = c.get("timeout_sec")
        if "timeout_sec" in c and not (isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0):
            errors.append("checks: %s 的 timeout_sec 须是正数" % label)
    skip = gate.get("checks_skip")
    if skip is not None and not isinstance(skip, dict):
        errors.append("checks: gate.checks_skip 须是对象（检查名 → 理由）")
        skip = {}
    for k, reason in (skip or {}).items():
        skip_keys.add(k)
        if not _nonblank(reason):
            errors.append("checks: checks_skip 的 %s 理由须是非空字符串" % k)
        if k in names:
            errors.append("checks: %s 同时出现在 gate.checks 与 gate.checks_skip" % k)
    return errors, names, skip_keys


def _repo_default_checks(change_dir):
    """读 <openspec 根>/gate-checks.json；返回 (默认检查 name 列表 | None, 错误文本 | None)。文件不存在 → (None, None)。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(change_dir))), DEFAULT_CHECKS)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            items = json.load(f)
    except (OSError, ValueError) as e:
        return None, "checks: 仓库默认检查文件 %s 无法解析：%s" % (path, e)
    if not isinstance(items, list):
        return None, "checks: 仓库默认检查文件 %s 无法解析：顶层须是列表" % path
    names = []
    for i, c in enumerate(items):
        name = c.get("name") if isinstance(c, dict) else None
        if not isinstance(c, dict):
            why = "第 %d 项不是对象" % (i + 1)
        elif not (isinstance(name, str) and CHECK_NAME_RE.fullmatch(name)):
            why = "检查名 %r 不合法" % (name,)
        elif name in names:
            why = "检查名 %s 重复" % name
        else:
            names.append(name)
            continue
        return None, "checks: 仓库默认检查文件 %s 无法解析：%s" % (path, why)
    return names, None


def _tiers_path(change_dir):
    """<openspec 根>/test-tiers.json；openspec 根 = change 目录上两级（与 _repo_default_checks 同一解析）。"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(change_dir))), TIER_FILE)


def _tier_shape(label, obj, fields):
    """unit / 区域对象的字段校验：只含 fields；paths 非空数组；covers（若在 fields）是数组；cmd 非空。"""
    errors = []
    extra = sorted(str(k) for k in obj if k not in fields)
    if extra:
        errors.append("tiers: %s 有未知字段 %s" % (label, ", ".join(extra)))
    paths = obj.get("paths")
    if not (isinstance(paths, list) and paths and all(_nonblank(x) for x in paths)):
        errors.append("tiers: %s 的 paths 须是非空数组、每项非空" % label)
    if "covers" in fields:
        covers = obj.get("covers")
        if not (isinstance(covers, list) and all(_nonblank(x) for x in covers)):
            errors.append("tiers: %s 的 covers 须是数组（可为空）、每项非空" % label)
    if not _nonblank(obj.get("cmd")):
        errors.append("tiers: %s 缺少 cmd（须是非空字符串）" % label)
    return errors


def _load_tiers_file(path):
    """读分层文件 → (tiers | None, errors)。文件不存在 → (None, [])；有任何形状错误时 tiers 为 None。"""
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, "r", encoding="utf-8") as f:
            tiers = json.load(f)
    except (OSError, ValueError) as e:
        return None, ["tiers: 测试分层文件 %s 无法解析：%s" % (path, e)]
    if not isinstance(tiers, dict):
        return None, ["tiers: 测试分层文件 %s 无法解析：顶层须是对象" % path]
    errors = []
    extra = sorted(k for k in tiers if k not in ("unit", "regions", "slow_allow"))
    if extra:
        errors.append("tiers: 分层文件顶层有未知字段 %s" % ", ".join(extra))
    unit = tiers.get("unit")
    if isinstance(unit, dict):
        errors.extend(_tier_shape("unit", unit, ("paths", "cmd")))
    else:
        errors.append("tiers: 分层文件缺少 unit（须是含 paths 与 cmd 的对象）")
    regions = tiers.get("regions", {})
    if not isinstance(regions, dict):
        errors.append("tiers: regions 须是对象（区域名 → {paths, covers, cmd}）")
        regions = {}
    for name in sorted(regions):
        if not TIER_NAME_RE.fullmatch(name):
            errors.append("tiers: 区域名 %s 不合法（须匹配 [a-z0-9-]+）" % name)
        if isinstance(regions[name], dict):
            errors.extend(_tier_shape("区域 %s" % name, regions[name], ("paths", "covers", "cmd")))
        else:
            errors.append("tiers: 区域 %s 须是对象（paths / covers / cmd）" % name)
    slow = tiers.get("slow_allow", {})
    if not isinstance(slow, dict):
        errors.append("tiers: slow_allow 须是对象（nodeid → {reason, approved}）")
        slow = {}
    for nid in sorted(slow):
        item = slow[nid]
        if not isinstance(item, dict):
            errors.append("tiers: slow_allow 的 %s 须是对象（reason / approved）" % nid)
            continue
        extra = sorted(str(k) for k in item if k not in ("reason", "approved"))
        if extra:
            errors.append("tiers: slow_allow 的 %s 有未知字段 %s" % (nid, ", ".join(extra)))
        for k in ("reason", "approved"):
            if not _nonblank(item.get(k)):
                errors.append("tiers: slow_allow 的 %s 缺少 %s（须是非空字符串）" % (nid, k))
    return (None if errors else tiers), errors


def _load_tiers(change_dir):
    return _load_tiers_file(_tiers_path(change_dir))


def tiers_matching(path, tiers):
    """path 落在哪些层：unit 在前，区域按名字排序；用 glob_match（与 owns 同一语义）。"""
    out = ["unit"] if any(glob_match(path, g) for g in tiers["unit"]["paths"]) else []
    regions = tiers.get("regions") or {}
    out.extend(n for n in sorted(regions) if any(glob_match(path, g) for g in regions[n]["paths"]))
    return out


def tier_seconds(durations, tiers):
    """逐用例耗时 {nodeid: 秒} 按分层文件归层（design D14）：文件部分取 nodeid 的第一段，tiers_matching 取第一个；
    不在任何层 → unclassified（为 0 时不出现）；integration = 各区域之和；各项保留 1 位小数。"""
    unit, loose, regions = 0.0, 0.0, {}
    for nodeid, sec in durations.items():
        hit = tiers_matching(nodeid.split("::", 1)[0], tiers)
        if not hit:
            loose += sec
        elif hit[0] == "unit":
            unit += sec
        else:
            regions[hit[0]] = regions.get(hit[0], 0.0) + sec
    ts = {"unit": round(unit, 1), "integration": round(sum(regions.values()), 1),
          "regions": {n: round(regions[n], 1) for n in sorted(regions)}}
    if round(loose, 1):
        ts["unclassified"] = round(loose, 1)
    return ts


def _tier_add(ts, unit=0.0, regions=None):
    """把墙钟秒数并入已有 tier_sec（返回新 dict）：重算 integration，各项保留 1 位小数。"""
    regs = dict(ts.get("regions") or {})
    for n, sec in (regions or {}).items():
        regs[n] = regs.get(n, 0.0) + sec
    out = dict(ts, unit=round(ts.get("unit", 0.0) + unit, 1), regions={n: round(regs[n], 1) for n in sorted(regs)})
    out["integration"] = round(sum(regs.values()), 1)
    return out


def _tier_note(ts):
    return "单元 %.1fs · 集成 %.1fs" % (ts["unit"], ts["integration"])


def _lint_tiers(data, change_dir):
    """计划 × 分层文件的校验（design D1–D3）；违规文本都以 tiers: 开头。"""
    gate = data.get("gate") or {}
    path = _tiers_path(change_dir)
    tiers, errors = _load_tiers_file(path)
    if tiers is None:
        if not errors and ("integration" in gate or "integration_skip" in gate):
            errors.append("tiers: 计划写了 gate.integration / integration_skip，但缺少测试分层文件 %s" % path)
        return errors
    regions = tiers.get("regions") or {}
    if (gate.get("test") or "").strip() != tiers["unit"]["cmd"].strip():
        errors.append("tiers: gate.test（%s）须与单元层 unit.cmd（%s）相同" % (gate.get("test"), tiers["unit"]["cmd"]))
    integration = gate.get("integration")
    if integration is not None and not isinstance(integration, list):
        errors.append("tiers: gate.integration 须是区域名数组")
        integration = []
    chosen = set()
    for name in integration or []:
        if not (isinstance(name, str) and name in regions):
            errors.append("tiers: gate.integration 的 %s 不是分层文件 regions 里的区域" % (name,))
        elif name in chosen:
            errors.append("tiers: gate.integration 里区域 %s 重复" % name)
        else:
            chosen.add(name)
    skip = gate.get("integration_skip")
    if skip is not None and not isinstance(skip, dict):
        errors.append("tiers: gate.integration_skip 须是对象（区域名 → 理由）")
        skip = {}
    for name, reason in (skip or {}).items():
        if name not in regions:
            errors.append("tiers: gate.integration_skip 的 %s 不是分层文件 regions 里的区域" % name)
        if not _nonblank(reason):
            errors.append("tiers: gate.integration_skip 的区域 %s 理由须是非空字符串" % name)
        if name in chosen:
            errors.append("tiers: 区域 %s 同时出现在 gate.integration 与 gate.integration_skip" % name)
    decided = chosen | set(skip or {})
    for name in sorted(regions):
        if name in decided:
            continue
        hit = next(((c, s.get("id"), o) for c in regions[name]["covers"] for s in data.get("slices") or []
                    for o in s.get("owns") or [] if globs_intersect(c, o)), None)
        if hit:
            errors.append("tiers: 区域 %s 的 covers %s 与切片 %s 的 owns %s 相交，须写进 gate.integration 或在 gate.integration_skip 写理由"
                          % (name, hit[0], hit[1], hit[2]))
    allowed = {"unit"} | chosen
    for sid, target in sorted((data.get("scenario_tests") or {}).items()):
        if not isinstance(target, str):
            continue
        rel = target.split("::", 1)[0]
        if not set(tiers_matching(rel, tiers)) & allowed:
            errors.append("tiers: scenario %s 的测试文件 %s 不在单元层或已选区域的 paths 内" % (sid, rel))
    return errors


def lint_plan(data, change_dir=None):
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
    imp = (data.get("gate") or {}).get("impacted")
    if imp is not None and not _nonblank(imp):
        errors.append("gate: gate.impacted 必须是非空字符串")
    check_errors, check_names, skip_keys = _lint_checks(data.get("gate") or {})
    errors.extend(check_errors)
    if change_dir is not None:
        defaults, err = _repo_default_checks(change_dir)
        if err:
            errors.append(err)
        for name in defaults or []:
            if name not in check_names and name not in skip_keys:
                errors.append("checks: 仓库默认检查 %s 未出现在 gate.checks，也没有在 gate.checks_skip 写理由" % name)
        errors.extend(_lint_tiers(data, change_dir))
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
    """rest 只含白名单与路径 → 路径列表；含其他词 → None。带 `::` 的节点选择不是路径：
    全量只跑了某个节点时，它的 junit 不能替整个文件判绿（gate.test 与 verify 同走此函数）。"""
    paths, i = [], 0
    while i < len(rest):
        t = rest[i]
        if t == "-p" and i + 1 < len(rest) and rest[i + 1] == "no:cacheprovider":
            i += 1
        elif t in DERIVE_WHITELIST or t.startswith("--tb="):
            pass
        elif t and not t.startswith("-") and "::" not in t and not DERIVE_UNSAFE.search(t):
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
        if not os.path.isfile(os.path.join(root, p)) or not (
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


def _pytest_outcomes(root, targets, gate=None, durations=None, deps_out=None, probe_out=None):
    """实跑 targets，返回 (outcomes, rc, out_text, timed_out)；outcomes = [(nodeid, PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)]，nodeid 以 root 为 rootdir。
    durations 是 dict 时把逐用例耗时（setup + call + teardown）按 nodeid 累加进去。
    deps_out 是 dict 时另加载防护与依赖图插件，结束后把依赖图（形状同 run_test_gate 的 deps）写进去；没测到则不写。
    probe_out 是 dict 时另加载单元层探针，结束后写入 {"probe", "probe_why"}（形状同 run_test_gate）。"""
    gate = gate or {}
    prefix, _ = _g7_runner(gate)
    timeout = _g7_timeout(gate)
    with tempfile.TemporaryDirectory(prefix="flight-g7-") as tmp:
        with open(os.path.join(tmp, "flight_g7_outcomes.py"), "w", encoding="utf-8") as f:
            f.write(G7_PLUGIN)
        out = os.path.join(tmp, "outcomes.jsonl")
        # 不写字节码：__pycache__ 落进被测 worktree 会被当成改动（G5 起点测量、source 判定）；
        # 字节码前缀指向临时目录：不读树内旧 .pyc（源文件同秒同长度改动时 mtime+size 校验认不出，会测到旧代码）
        env = dict(os.environ, FLIGHT_G7_OUT=out, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"),
                   PYTHONPATH=os.pathsep.join(p for p in (tmp, os.environ.get("PYTHONPATH")) if p))
        sec_out = os.path.join(tmp, "seconds.jsonl")
        env.pop("FLIGHT_G7_SEC", None)  # 外层门禁的耗时文件不得漏给本次运行
        if isinstance(durations, dict):
            env["FLIGHT_G7_SEC"] = sec_out
        dout = _flight_plugins(tmp, env, root, True) if isinstance(deps_out, dict) else None
        flight = ["-p", "flight_guard", "-p", "flight_deps"] if dout else []
        tier_out = os.path.join(tmp, "tier-probe.jsonl")
        env.pop("FLIGHT_TIER_OUT", None)
        if isinstance(probe_out, dict):
            with open(os.path.join(tmp, "flight_tier_probe.py"), "w", encoding="utf-8") as f:
                f.write(TIER_PROBE_PLUGIN)
            env["FLIGHT_TIER_OUT"] = tier_out
            flight += ["-p", "flight_tier_probe"]
        argv = prefix + ["-p", "flight_g7_outcomes", *flight, "-p", "no:cacheprovider", "--rootdir", root, *targets]
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
        if isinstance(durations, dict) and os.path.isfile(sec_out):
            with open(sec_out, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        nid, sec = json.loads(line)
                        durations[nid] = durations.get(nid, 0.0) + sec
        if dout:
            parsed, _ = _read_deps(dout)
            if parsed is not None:
                deps_out.update(parsed)
        if isinstance(probe_out, dict):
            probe_out["probe"], probe_out["probe_why"] = _read_probe(tier_out)
        return outcomes, rc, text or "", timed_out


def _tier_rerun(root, gate, nodeids):
    """单独重跑慢候选（带探针）→ {nodeid: sec}；拿不到探针输出 / 超时 / 起不来 → None（调用方按「未取得」处理）。"""
    prefix, _ = _g7_runner(gate)
    with tempfile.TemporaryDirectory(prefix="flight-tier-") as tmp:
        with open(os.path.join(tmp, "flight_tier_probe.py"), "w", encoding="utf-8") as f:
            f.write(TIER_PROBE_PLUGIN)
        out = os.path.join(tmp, "tier-probe.jsonl")
        env = dict(os.environ, FLIGHT_TIER_OUT=out, PYTHONDONTWRITEBYTECODE="1",
                   PYTHONPATH=os.pathsep.join(p for p in (tmp, os.environ.get("PYTHONPATH")) if p))
        argv = prefix + ["-p", "flight_tier_probe", "-p", "no:cacheprovider", "--rootdir", root, *nodeids]
        try:
            subprocess.run(argv, cwd=root, env=env, capture_output=True, text=True, timeout=_g7_timeout(gate))
        except (OSError, subprocess.TimeoutExpired):
            return None
        probe, _ = _read_probe(out)
    if probe is None:
        return None
    return {n: r["sec"] for n, r in probe.items()}


def _unit_tier_verdict(root, gate, tg, allow):
    """单元层 G10 / G11：有慢候选才重跑，再交给 tier_verdicts。"""
    cands = slow_candidates(tg["probe"])
    rerun = (_tier_rerun(root, gate, cands) or {}) if cands else {}
    return tier_verdicts(tg["probe"], tg["probe_why"], rerun, allow)


def _g7_diag(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    hit = next((ln for ln in lines if "Error" in ln), lines[-1] if lines else "")
    return hit[:200]


def scenario_status(root, data, slice_ids=None, durations=None):
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
        outcomes, rc, text, timed_out = _pytest_outcomes(root, [t for _, t in py_targets], gate, durations)
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
    errors, waves = lint_plan(data, args.change_dir)
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
    tiers, _ = _load_tiers(args.change_dir)  # 不合法由 lint 管，这里只在合法时判 G12
    if tiers is not None:
        integration = gate.get("integration")
        chosen = {"unit"} | set(n for n in (integration if isinstance(integration, list) else []) if isinstance(n, str))
        for f in sorted(tests):
            if TEST_FILE_RE.search(f) and os.path.isfile(os.path.join(root, f)) and not set(tiers_matching(f, tiers)) & chosen:
                failed.append("G12 tiers: %s 不在单元层或本 change 已选区域的 paths 内（挪到对应目录，或在 gate.integration 选上该区域）" % f)
    ev = evidence_state(args.change_dir, args.slice)
    hooks_missing = ev == "missing_file"
    if ev == "missing_file":
        warnings.append("G5 evidence: 无 evidence.log（test-evidence hook 未安装或未触发），本切片留痕无法核对")
    elif ev == "no_rows":
        failed.append("G5 evidence: evidence.log 无本切片 %s 的测试运行记录（hook 在工作却没跑过测试）" % args.slice)
    elif ev == "no_red":
        warnings.append("G5 evidence: 未见 RED 先于 GREEN 的测试运行记录")
    failed.extend(ownership_violations(files, sl.get("owns") or [], change_rel, committed))
    durations = {} if tiers is not None else None
    v7, _, _, w7 = scenario_status(root, data, {args.slice}, durations=durations)
    failed.extend(v7)
    warnings.extend(w7)
    v8, ceilings = ceiling_rows(root, base)
    failed.extend(v8)

    result = {"slice": args.slice, "ok": not failed, "commit": git(root, "rev-parse", "HEAD"), "base": base,
              "failed": failed, "warnings": warnings, "hooks_missing": hooks_missing,
              "ceilings": [[rel, ln, limit, up] for rel, ln, limit, up in ceilings],
              "summary": "%s：%d 项失败，%d 项警告；改动 %d 个文件" % ("通过" if not failed else "阻断", len(failed), len(warnings), len(files))}
    gate_note = args.slice
    if durations is not None:
        ts = tier_seconds(durations, tiers)
        result["tier_sec"] = ts
        result["summary"] += "；" + _tier_note(ts)
        gate_note = "%s %s" % (args.slice, _tier_note(ts))
    if result["ok"]:
        err = _gate_save(root, args.change_dir, result)
        if err:
            warnings.append("门禁结论未能留存：%s" % err)
    append_report(args.change_dir, result)
    record_ceilings(args.change_dir, args.slice, ceilings)
    timeline_record(args.change_dir, "gate", "%s %s" % (gate_note, "ok" if result["ok"] else "red"))
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
    tiers, terrs = _load_tiers(args.change_dir)
    name = os.path.basename(os.path.realpath(args.change_dir))
    change_rel = _change_rel(root, args.change_dir)
    head = git(root, "rev-parse", "HEAD")
    snap_why = None
    try:
        cur_snap = _snapshot(root, change_rel)
    except RuntimeError as e:
        cur_snap, snap_why = None, "内容快照失败：%s" % e
    fps = _final_fps(root, change_rel, data, tiers)
    # 同树沿用（design D6）：不运行 G7 及其后的任何东西
    rec = _final_rec_read(root, name)
    if not args.full and _final_reusable(root, rec, cur_snap, head, change_rel, fps):
        prev, short = rec["result"], str(rec["commit"])[:10]
        result = {"slice": "final", "ok": True, "commit": head, "failed": [], "warnings": warnings,
                  "scenarios": prev.get("scenarios"), "summary": "%s；同树沿用 %s" % (prev.get("summary"), short),
                  "incremental": {"mode": "reused", "from": rec["commit"]}}
        if dirty:
            result["dirty"] = True
        append_report(args.change_dir, result)
        timeline_record(args.change_dir, "final", "同树沿用 %s ok" % short)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    durations = {} if tiers is not None else None
    unit_wall, region_wall = 0.0, {}
    v7, total, passed, w7 = scenario_status(root, data, durations=durations)
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
    inc = None
    final_ctx = {"mode": "full", "delta": None, "anchor": ""}  # 检查与 gate.impacted 的注入（design D7）
    if v7:
        warnings.append("G2 全量未跑：G7 已红，scenario 全绿后重跑 final")
    else:
        test_cmd = gate.get("test") or detect_test_cmd(root)
        if terrs:  # 分层文件不合法：单元层照旧差分，不跑探针与区域
            failed.append("G2 tiers：测试分层文件不合法，先跑 lint 修好")
            tiers = None
        if not test_cmd:
            warnings.append("未配置也未探测到全量测试命令")
        else:
            bt = (baseline or {}).get("test") or {}
            key = cmd_key(root, change_rel, test_cmd)
            tkey = _tiers_key(root, args.change_dir, tiers)
            imp = gate.get("impacted")
            pick = None
            if not args.full and cur_snap is not None:
                pick = (_impacted_anchor(root, rec, baseline, cur_snap, head, change_rel, name) if imp
                        else _pick_anchor(root, key, tkey, cur_snap, head, change_rel, name))
            why, wpy = _full_why(root, args.full, pick, baseline, snap_why, impacted=bool(imp))
            warnings.extend(wpy)
            if pick is not None:
                final_ctx = {"mode": "full" if why else "incremental", "delta": pick[1],
                             "anchor": pick[0].get("commit") or ""}
            anchor_part, byproducts = None, []
            run_regions = None  # 本次运行的已选区域；None = 全部
            t0 = time.time()
            if why is None and imp:  # gate.impacted 代替内建选测（design D8）
                anchor, delta = pick
                with tempfile.TemporaryDirectory(prefix="flight-impacted-") as tmp:
                    tg = run_test_gate(imp, root, extra_env=_final_env(final_ctx, tmp))
                unit_wall = time.time() - t0
                f2, w2 = _diff_verdict("test", tg, bt.get("failed"))
                failed.extend([f2] if f2 else [])
                warnings.extend([w2] if w2 else [])
                if tiers is not None:
                    warnings.append("G10/G11 未判：gate.impacted 增量不挂单元层探针")
                inc = {"mode": "incremental", "source": "impacted",
                       "anchor": {"change": anchor.get("change"), "commit": anchor.get("commit")}, "delta": len(delta)}
            elif why is None:  # 增量（design D5；有分层时 D9：单元层挂探针、区域按需）
                anchor, delta = pick
                sel = _final_select(root, anchor, delta)
                run_sel, unit_files, hit = sel, set(), {}
                if tiers is not None:
                    regs = tiers.get("regions") or {}
                    hit = {r: [f for f in sel if any(glob_match(f, g) for g in regs[r]["paths"])] for r in regs}
                    run_regions = [r for r in _selected_regions(gate) if hit.get(r)]
                    run_sel = [f for f in sel if not any(f in v for v in hit.values())]
                    unit_files = {f for f in run_sel if any(glob_match(f, g) for g in tiers["unit"]["paths"])}
                d, pr, outcomes, rc, text, timed_out = {}, {}, [], 0, "", False
                if run_sel:
                    outcomes, rc, text, timed_out = _pytest_outcomes(root, run_sel, gate, deps_out=d,
                                                                     probe_out=pr if unit_files else None)
                unit_wall = time.time() - t0
                known = set(bt.get("failed_nodes") or [])
                fails = sorted({n for n, o in outcomes if o in ("FAILED", "ERROR")})
                new = [n for n in fails if n not in known]
                if timed_out:
                    failed.append("G2 test：增量重跑超时")
                elif new:
                    failed.append("G2 test：新增失败 %d 条：%s" % (len(new), ", ".join(new)))
                elif sel and (rc not in (0, 1, 5) or (rc == 1 and not fails)):
                    failed.append("G2 test：增量重跑 exit %s\n%s" % (rc, _tail(text)))
                elif fails:
                    warnings.append("G2 test：增量重跑的失败均为基线预存红（%d 条已按基线排除）" % len(fails))
                if unit_files:  # 只对选中的单元层用例判 G10 / G11（与全量同一套判定）
                    probe = pr.get("probe")
                    if probe is not None:
                        probe = {n: r for n, r in probe.items() if n.split("::", 1)[0] in unit_files}
                    f10, w10 = _unit_tier_verdict(root, gate, {"probe": probe, "probe_why": pr.get("probe_why")},
                                                  tiers.get("slow_allow") or {})
                    failed.extend(f10)
                    warnings.extend(w10)
                rerun = sorted(set(run_sel).union(*[hit[r] for r in run_regions or []]))
                inherited = sum(n for f, n in (anchor.get("tests") or {}).items()
                                if f not in rerun and os.path.isfile(os.path.join(root, f)))
                inc = {"mode": "incremental", "source": "builtin",
                       "anchor": {"change": anchor.get("change"), "commit": anchor.get("commit")},
                       "delta": len(delta), "rerun": rerun, "rerun_tests": len({n for n, _ in outcomes}),
                       "inherited_tests": inherited}
                if tiers is not None:
                    inc["regions_skipped"] = [r for r in _selected_regions(gate) if r not in run_regions]
                anchor_part = _anchor_forward(root, anchor, rerun, d, fails, outcomes)
                anchor_part["measured"] = bool(d) or not run_sel
                anchor_part["source"] = "final-incremental"
                byproducts = anchor.get("byproducts") or []
            else:  # 全量：按基线差分，并记录依赖图（design D4）
                tg = run_test_gate(test_cmd, root, probe=tiers is not None, deps=True)
                f2, w2 = _diff_verdict("test", tg, bt.get("failed"))
                failed.extend([f2] if f2 else [])
                warnings.extend([w2] if w2 else [])
                if tiers is not None:
                    f10, w10 = _unit_tier_verdict(root, gate, tg, tiers.get("slow_allow") or {})
                    unit_wall = time.time() - t0
                    failed.extend(f10)
                    warnings.extend(w10)
                ad = tg["deps"]
                anchor_part = {"files": ad["files"] if ad else [], "deps": ad["deps"] if ad else {},
                               "blind": ad["blind"] if ad else [],
                               "failed": sorted(n for n, o in (ad or {}).get("nodes", {}).items()
                                                if o in ("FAILED", "ERROR")),
                               "tests": _node_counts((ad or {}).get("nodes") or {}),
                               "measured": ad is not None, "source": "final-full"}
                if ad is None:
                    warnings.append("依赖图未测：%s" % tg["deps_why"])
                inc = {"mode": "full", "full_why": why}
            if tiers is not None:  # 区域：内建增量只跑选中的（design D9），其余全跑；运行都记依赖图并入锚点
                bregions = (baseline or {}).get("regions")
                for rname in (_selected_regions(gate) if run_regions is None else run_regions):
                    rcmd = ((tiers.get("regions") or {}).get(rname) or {}).get("cmd")
                    rrec = bregions.get(rname) if isinstance(bregions, dict) else None
                    if not isinstance(rrec, dict) or not rcmd or rrec.get("cmd") != rcmd:
                        failed.append("G2 region %s：基线缺记录或命令已变，重跑 baseline" % rname)
                        continue
                    full_run = inc["mode"] == "full"
                    t0 = time.time()
                    rg = run_test_gate(rcmd, root, deps=anchor_part is not None)
                    region_wall[rname] = time.time() - t0
                    f2, w2 = _diff_verdict("region " + rname, rg, rrec.get("failed"))
                    failed.extend([f2] if f2 else [])
                    warnings.extend([w2] if w2 else [])
                    if anchor_part is not None and anchor_part["measured"]:
                        if rg["deps"] is None:
                            anchor_part["measured"] = False
                            warnings.append("依赖图未测：区域 %s：%s" % (rname, rg["deps_why"]))
                        else:
                            m = _deps_merge(dict(anchor_part, nodes={}), rg["deps"])
                            anchor_part.update({k: m[k] for k in ("deps", "blind", "files")})
                            rfail = [n for n, o in rg["deps"]["nodes"].items() if o in ("FAILED", "ERROR")]
                            anchor_part["failed"] = sorted(set(anchor_part["failed"]) | set(rfail))
                            for f, n in _node_counts(rg["deps"]["nodes"]).items():  # 增量：区域文件换成本次计数
                                anchor_part["tests"][f] = (anchor_part["tests"].get(f, 0) if full_run else 0) + n
            if cur_snap is not None and anchor_part is not None:
                w = _anchor_write(root, dict(anchor_part, change=name, commit=head, at=now_iso(), snapshot=cur_snap,
                                             byproducts=byproducts, cmd_key=key, tiers_key=tkey))
                if w:
                    warnings.append(w)
    checks = gate.get("checks") or []
    cerrs = _lint_checks(gate)[0]
    if cerrs:  # /opsx-verify 可不经 preflight 直接跑 final（design D8）：形状非法时不运行任何检查
        failed.append("G9 gate.checks 形状非法，先跑 lint 修好：%s" % "；".join(cerrs))
    elif checks and v7:
        warnings.append("G9 检查未跑：G7 已红，scenario 全绿后重跑 final")
    elif checks:
        failed.extend(_final_checks(root, args.change_dir, checks, baseline, final_ctx))
    result = {"slice": "final", "ok": not failed, "commit": head,
              "failed": failed, "warnings": warnings,
              "scenarios": {"total": total, "passed": passed if not failed else min(passed, total - len(v7))},
              "summary": "final %s：scenario %d/%d" % ("通过" if not failed else "阻断", passed, total)}
    if dirty:
        result["dirty"] = True
    inc_note = None
    if inc is not None:
        result["incremental"] = inc
        if inc.get("source") == "impacted":
            a10 = str(inc["anchor"]["commit"])[:10]
            result["summary"] += "；增量：gate.impacted，Δ %d 个文件，锚点 %s" % (inc["delta"], a10)
            inc_note = "增量（gate.impacted，锚点 %s，Δ %d 个文件）" % (a10, inc["delta"])
        elif inc["mode"] == "incremental":
            a10 = str(inc["anchor"]["commit"])[:10]
            result["summary"] += "；增量：重跑 %d 个文件（%d 个用例）/ 沿用 %d 个，锚点 %s" % (
                len(inc["rerun"]), inc["rerun_tests"], inc["inherited_tests"], a10)
            inc_note = "增量（锚点 %s，重跑 %d 个文件 / 沿用 %d 个用例）" % (a10, len(inc["rerun"]), inc["inherited_tests"])
        else:
            result["summary"] += "；全量（%s）" % inc["full_why"]
            inc_note = "全量（%s）" % inc["full_why"]
    final_note = "ok" if result["ok"] else "red"
    if durations is not None:
        ts = tier_seconds(durations, tiers)
        if not v7:  # G7 红时全量与区域未跑，只报 G7 部分
            ts = _tier_add(ts, unit_wall, region_wall)
        result["tier_sec"] = ts
        result["summary"] += "；" + _tier_note(ts)
        final_note = "%s %s" % (_tier_note(ts), final_note)
    if inc_note:  # 结论词恒在末尾（timeline.py 按末尾取结论）
        final_note = "%s %s" % (inc_note, final_note)
    append_report(args.change_dir, result)
    timeline_record(args.change_dir, "final", final_note)
    if cur_snap is not None:  # 每次实跑结束（绿或红）都写记录，供下次同树沿用（design D6）
        entry = {"commit": head, "snapshot": cur_snap, "fps": fps, "result": result}
        green = None if result["ok"] else _last_green(rec)
        if green:  # 红记录带上最近一次绿的树，供 gate.impacted 取锚点（design D8）
            entry["green"] = green
        w = _final_rec_write(root, name, entry)
        if w:
            result["warnings"].append(w)
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
    # 检查名会拼进 rmtree 的路径：形状先于任何动作校验，非法时不写运行标记，不碰现有 gate-baseline.json
    cerrs = _lint_checks(gate)[0]
    if cerrs:
        die("gate.checks 形状非法，先跑 lint 修好：%s" % "；".join(cerrs))
    tiers, terrs = _load_tiers(args.change_dir)
    if terrs:
        die("测试分层文件不合法，先跑 lint 修好：%s" % "；".join(terrs))
    regions = _selected_regions(gate)
    unknown = [n for n in regions if n not in ((tiers or {}).get("regions") or {})]
    if unknown:
        die("gate.integration 的区域 %s 不在测试分层文件 regions 里，先跑 lint 修好" % ", ".join(unknown))
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
    # 有分层文件时恒走全量：G10 / G11 要单元层探针，复用的旧结果没有（design D5）
    cands = _baseline_candidates(root, old, key, name, args.full or tiers is not None)
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
    unit_wall = 0.0
    adeps, deps_whys = None, []  # 锚点的依赖图（全量与区域运行并起来）与没测到的原因（design D3）
    bl = {"commit": git(root, "rev-parse", "HEAD"), "at": now_iso(), "plan_sha": None,
          "ok": None, "reasons": reasons}
    if hit is not None:
        ct = src.get("test") or {}
        bl["test"] = {k: ct[k] for k in ("exit", "sec", "failed") if k in ct}
        if isinstance(ct.get("failed"), list) and ct["failed"]:
            warnings.append("预存红 %d 条（沿用 %s 的全量），final 按基线差分" % (len(ct["failed"]), src.get("change")))
    else:
        t0 = time.time()
        tg = run_test_gate(test_cmd, root, probe=tiers is not None, deps=True)
        rc, out = tg["rc"], tg["out"]
        gate["full_suite_sec"] = round(time.time() - t0, 1)
        bl["test"] = {"exit": rc, "sec": gate["full_suite_sec"]}
        adeps = tg["deps"]
        if adeps is None:
            deps_whys.append(tg["deps_why"])
        elif rc != 0:
            bl["test"]["failed_nodes"] = sorted(n for n, o in adeps["nodes"].items() if o in ("FAILED", "ERROR"))
        if rc != 0 and tg["failed"] is not None:
            bl["test"]["failed"] = tg["failed"]
            warnings.append("预存红 %d 条已记录，final 按基线差分" % len(tg["failed"]))
        elif rc != 0:
            reasons.append("全量测试在基线上红（exit %d；按退出码判：%s）" % (rc, tg["why"]))
        if tiers is not None:
            f10, w10 = _unit_tier_verdict(root, gate, tg, tiers.get("slow_allow") or {})
            reasons.extend(f10)
            warnings.extend(w10)
            unit_wall = time.time() - t0
            bl["tiers"] = {"measured": True} if tg["probe"] is not None else {"measured": False, "why": tg["probe_why"]}
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
    # 已选区域（design D9）：可度量的红记 failed 供 final 差分；不可度量的红 → 基线红
    if tiers is not None:
        bl["regions"] = {}
    for rname in regions:
        rcmd = tiers["regions"][rname]["cmd"]
        t0 = time.time()
        rg = run_test_gate(rcmd, root, deps=True)
        rec = {"exit": rg["rc"], "sec": round(time.time() - t0, 1), "cmd": rcmd}
        if rg["deps"] is None:
            deps_whys.append("区域 %s：%s" % (rname, rg["deps_why"]))
        elif adeps is not None:
            adeps = _deps_merge(adeps, rg["deps"])
        if rg["rc"] != 0 and rg["failed"] is not None:
            rec["failed"] = rg["failed"]
            warnings.append("区域 %s 预存红 %d 条已记录，final 按基线差分" % (rname, len(rg["failed"])))
        elif rg["rc"] != 0:
            reasons.append("区域 %s 在基线上红（exit %d；按退出码判：%s）" % (rname, rg["rc"], rg["why"]))
        bl["regions"][rname] = rec
    if tiers is not None:
        bl["tier_sec"] = _tier_add({"unit": 0.0, "regions": {}}, unit_wall,
                                   {n: r["sec"] for n, r in bl["regions"].items()})
    # 成对检查的 baseline 半（design D5）：沿用条件同 lint / typecheck（D10）外加共用目录仍在；否则清空目录后实跑
    checks = gate.get("checks") or []
    if checks:
        bl["checks"] = {}
        old_checks = (old.get("checks") if isinstance(old, dict) else None) or {}
    for c in checks:
        bcmd = c.get("baseline") if isinstance(c, dict) else None
        if not bcmd:
            continue
        cname = c["name"]
        kkey = cmd_key(root, change_rel, bcmd)
        try:
            cdir = _check_dir(root, name, cname)
        except RuntimeError as e:  # design D12：运行标记一定被结果覆盖
            bl["checks"][cname] = {"exit": None, "cmd": bcmd, "key": kkey}
            reasons.append("check %s 共用目录不可用：%s" % (cname, e))
            continue
        oc = old_checks.get(cname) if isinstance(old_checks, dict) else None
        if (strict_delta == [] and kkey and isinstance(oc, dict) and "exit" in oc
                and oc.get("cmd") == bcmd and oc.get("key") == kkey and os.path.isdir(cdir)):
            bl["checks"][cname] = {"exit": oc["exit"], "sec": oc.get("sec"), "cmd": bcmd, "key": kkey, "reused": True}
            continue
        try:  # 清空失败显式判红，不让旧数据残留
            if os.path.lexists(cdir):
                shutil.rmtree(cdir)
            os.makedirs(cdir)
        except OSError as e:
            bl["checks"][cname] = {"exit": None, "cmd": bcmd, "key": kkey}
            reasons.append("check %s 共用目录无法清空或创建：%s" % (cname, e))
            continue
        crc, cout, csec, ctimeout = _run_check(bcmd, root, _check_env("baseline", name, bl["commit"], cdir),
                                               c.get("timeout_sec"))
        bl["checks"][cname] = {"exit": crc, "sec": csec, "cmd": bcmd, "key": kkey}
        log = _check_log(cdir, "baseline", cout)
        if ctimeout:
            bl["checks"][cname]["timed_out"] = True
            reasons.append(_check_msg("check %s 在基线上超时（%s 秒）" % (cname, c.get("timeout_sec")), log, cout))
        elif crc != 0:
            reasons.append(_check_msg("check %s 在基线上红（exit %d）" % (cname, crc), log, cout))
    # 运行期间的改动（design D6）
    s1, byproducts = None, []
    try:
        s1 = _snapshot(root, change_rel)
        reasons_d6, warnings_d6, byproducts = _run_changes(root, change_rel, s0, s1, (old or {}).get("byproducts"))
        reasons.extend(reasons_d6)
        warnings.extend(warnings_d6)
    except RuntimeError as e:  # design D12：运行标记一定被结果覆盖
        reasons.append("基线结束时内容快照失败：%s；重跑 baseline" % e)
    # 锚点（design D3）：跑了全量才写；任一运行的依赖图没测到 → measured false（照样写，供 final 判「没有可用锚点」）
    if hit is None:
        measured = adeps is not None and not deps_whys
        if not measured:
            warnings.append("依赖图未测：%s" % "；".join(w for w in deps_whys if w) if deps_whys else "依赖图未测")
        tkey = _tiers_key(root, args.change_dir, tiers)
        ad = adeps if measured else {"deps": {}, "blind": [], "files": []}
        w = _anchor_write(root, {
            "change": name, "commit": bl["commit"], "at": now_iso(), "snapshot": s1, "byproducts": byproducts,
            "cmd_key": key, "tiers_key": tkey, "files": ad["files"], "failed": bl["test"].get("failed_nodes") or [],
            "deps": ad["deps"], "blind": ad["blind"], "tests": _node_counts(ad.get("nodes") or {}),
            "measured": measured, "source": "baseline"})
        if w:
            warnings.append(w)
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
        note = "exit %s, %ss%s" % (t.get("exit"), t.get("sec"),
                                    "；%s %s" % (_tier_note(bl["tier_sec"]), verdict) if "tier_sec" in bl else " " + verdict)
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
    errors, waves = lint_plan(data, args.change_dir)
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
    tiers, _ = _load_tiers(args.change_dir)
    if tiers is not None:
        bregions = bl.get("regions")
        for rname in _selected_regions(data.get("gate") or {}):
            rec = bregions.get(rname) if isinstance(bregions, dict) else None
            if not isinstance(rec, dict) or rec.get("cmd") != ((tiers.get("regions") or {}).get(rname) or {}).get("cmd"):
                die("基线过期：区域 %s 的命令已变或没有基线记录；重跑 baseline" % rname)
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


def _pool_dir(root, sub=POOL_DIR):
    """git common dir 下的池目录（默认基线池；同仓各 worktree 共享）；相对路径按 root 解析成绝对路径。"""
    common = git(root, "rev-parse", "--git-common-dir")
    return os.path.join(common if os.path.isabs(common) else os.path.join(root, common), sub)


# 锚点池（design D3）：<git common dir>/flight-anchors/，条目带依赖图，只留最新 ANCHOR_KEEP 条
ANCHOR_DIR = "flight-anchors"
ANCHOR_KEEP = 20


CHECKS_DIR = "flight-gate-checks"


def _check_dir(root, change, name):
    """检查的共用目录（design D3）：<git common dir>/flight-gate-checks/<change>/<name>，绝对路径；baseline 与 final 共用。"""
    common = git(root, "rev-parse", "--git-common-dir")
    base = common if os.path.isabs(common) else os.path.join(root, common)
    parent = os.path.join(os.path.abspath(base), CHECKS_DIR, change)
    path = os.path.join(parent, name)
    # 纵深防御：检查名已由 lint 校验；仍确认解析后（含符号链接）恰好落在本 change 的检查目录之下
    if os.path.dirname(os.path.realpath(path)) != os.path.realpath(parent):
        raise RuntimeError("%s 不在 %s 之下" % (path, parent))
    return path


def _final_env(final_ctx, ddir):
    """final 注入的三个变量（incremental-final design D7）：Δ 每行一个写进 <ddir>/.gate-delta.txt；
    final_ctx = {"mode", "delta": [...] | None, "anchor": commit | ""}；没有 Δ 时 GATE_DELTA_FILE 为空串。写失败抛 OSError。"""
    path = ""
    if final_ctx.get("delta") is not None:
        path = os.path.join(ddir, ".gate-delta.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(p + "\n" for p in final_ctx["delta"]))
    return {"GATE_FINAL_MODE": final_ctx.get("mode") or "", "GATE_DELTA_FILE": path,
            "GATE_ANCHOR_COMMIT": final_ctx.get("anchor") or ""}


def _check_env(phase, change, base_commit, cdir, final_ctx=None):
    """检查命令的环境（运行契约）：os.environ 副本 + GATE_PHASE / GATE_CHANGE / GATE_BASE_COMMIT / GATE_CHECK_DIR；
    final_ctx 非 None（只在 final）时另加 _final_env 的三个变量。"""
    env = dict(os.environ, GATE_PHASE=phase, GATE_CHANGE=change, GATE_BASE_COMMIT=base_commit or "",
               GATE_CHECK_DIR=cdir)
    if final_ctx is not None:
        env.update(_final_env(final_ctx, cdir))
    return env


def _run_check(cmd, root, env, timeout):
    """运行一条检查命令（design D2），返回 (rc, out, sec, timed_out)；timeout 为 None 不设上限，超时整个进程组结束。"""
    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, shell=True, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, start_new_session=True)
    except OSError as e:
        return 127, str(e), round(time.time() - t0, 1), False
    timed_out = False
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(p.pid, 9)
        except OSError:
            pass
        out, _ = p.communicate()
    return p.returncode, out or "", round(time.time() - t0, 1), timed_out


def _check_log(cdir, phase, out):
    """覆盖写 cdir/.gate-<phase>.log；返回 (日志路径, None)，写失败返回 (None, 错误文本)。"""
    path = os.path.join(cdir, ".gate-%s.log" % phase)
    try:
        os.makedirs(cdir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(out or "")
    except OSError as e:
        return None, str(e)
    return path, None


def _check_msg(head, log, out):
    """红的提示（design D4）：首行结论 + 日志位置（log 为 _check_log 的返回值），再接输出末尾 20 行。"""
    path, err = log
    msg = head + ("；日志 %s" % path if path else "；日志未能写入：%s" % err)
    tail = _tail(out or "", 20)
    return msg + ("\n" + tail if tail else "")


def _final_checks(root, change_dir, checks, baseline, final_ctx=None):
    """成对检查的 final 半（G9，design D8）：按 gate.checks 顺序运行，先核对基线记录；返回 failed 项列表。"""
    change = os.path.basename(os.path.realpath(change_dir))
    base = (baseline or {}).get("commit")
    recs = (baseline or {}).get("checks") or {}
    failed = []
    for c in checks:
        cname = c["name"]
        bcmd = c.get("baseline")
        rec = recs.get(cname) if isinstance(recs, dict) else None
        if not base or (bcmd and not (isinstance(rec, dict) and rec.get("exit") == 0 and rec.get("cmd") == bcmd)):
            failed.append("G9 check %s：基线缺记录或与计划不符，重跑 baseline" % cname)
            continue
        try:
            cdir = _check_dir(root, change, cname)
            os.makedirs(cdir, exist_ok=True)
            env = _check_env("final", change, base, cdir, final_ctx)
        except (RuntimeError, OSError) as e:
            failed.append("G9 check %s：共用目录不可用：%s" % (cname, e))
            continue
        rc, out, _, timed_out = _run_check(c["final"], root, env, c.get("timeout_sec"))
        log = _check_log(cdir, "final", out)
        if timed_out:
            failed.append(_check_msg("G9 check %s：超时 %s 秒" % (cname, c.get("timeout_sec")), log, out))
        elif rc != 0:
            failed.append(_check_msg("G9 check %s：exit %d" % (cname, rc), log, out))
    return failed


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


def _pool_write(root, entry, sub=POOL_DIR, keep=POOL_KEEP, label="基线池"):
    """原子写一条池记录（临时文件 + os.replace），再按 at 只留最新 keep 条、清掉过期 .tmp- 残留；
    失败返回警告文本，成功返回 None。"""
    try:
        pdir = _pool_dir(root, sub)
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
        drop = names[keep:]
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
        return "%s写入失败（不影响本次基线）：%s" % (label, e)
    return None


def _anchor_write(root, entry):
    """写一条锚点（design D3）；失败返回警告文本。"""
    return _pool_write(root, entry, ANCHOR_DIR, ANCHOR_KEEP, "锚点池")


def _anchor_candidates(root, cmd_key, tiers_key, limit=10):
    """锚点池里 cmd_key 与 tiers_key 都匹配、measured 为真的条目，按 at 由新到旧取前 limit 个。"""
    return _pool_candidates(root, cmd_key, limit, ANCHOR_DIR,
                            lambda e: e.get("tiers_key") == tiers_key and e.get("measured") is True)


# ---------------------------------------------------------------- 增量 final 与同树沿用（incremental-final design D3–D6、D10）

FINAL_DIR = "flight-final"
# Δ 含这些文件名（任何目录下）→ final 自动全量（spec「命中触发条件时 final 自动跑全量」）
GLOBAL_FILES = {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "setup.py", "Pipfile",
                "Pipfile.lock", "poetry.lock", "uv.lock", ".python-version", TIER_FILE}
GLOBAL_GLOBS = ("requirements*.txt",)


def _tiers_key(root, change_dir, tiers):
    """分层文件的 blob（锚点与 final 指纹用）；无分层或取不到 → None。"""
    if tiers is None:
        return None
    try:
        return _hash_paths(root, [_tiers_path(change_dir)])[0]
    except (RuntimeError, IndexError):
        return None


def _node_counts(nodeids):
    """{测试文件: 用例数}（nodeid 的 :: 之前部分）。"""
    out = {}
    for n in set(nodeids):
        f = str(n).split("::", 1)[0]
        out[f] = out.get(f, 0) + 1
    return dict(sorted(out.items()))


def _py_test_file(rel):
    return rel.endswith(".py") and bool(TEST_FILE_RE.search(rel))


def _global_file(rel):
    base = rel.rsplit("/", 1)[-1]
    return base in GLOBAL_FILES or any(fnmatch.fnmatchcase(base, g) for g in GLOBAL_GLOBS)


def _final_fps(root, change_rel, data, tiers):
    """同树沿用的指纹集合（design D6）。"""
    gate = data.get("gate") or {}
    checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
    return {
        "plan_sha": plan_sha(data),
        "scenario_tests": hashlib.sha1(json.dumps(data.get("scenario_tests") or {}, ensure_ascii=False, sort_keys=True)
                                       .encode("utf-8")).hexdigest(),
        "cmd": {k: cmd_key(root, change_rel, gate[k]) if gate.get(k) else None
                for k in ("test", "pytest", "lint", "typecheck", "impacted")},
        "checks": [[c.get("name"), cmd_key(root, change_rel, c.get("final"))] for c in checks if isinstance(c, dict)],
        "tiers": _tiers_key(root, os.path.join(root, change_rel), tiers),
    }


def _final_rec_read(root, name):
    try:
        return _pool_read(_pool_dir(root, FINAL_DIR), name + ".json")
    except RuntimeError:
        return None


def _final_rec_write(root, name, rec):
    """原子写 <git common dir>/flight-final/<change>.json；失败返回警告文本。"""
    try:
        pdir = _pool_dir(root, FINAL_DIR)
        os.makedirs(pdir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=pdir, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp, os.path.join(pdir, name + ".json"))
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    except (OSError, RuntimeError) as e:
        return "final 记录写入失败（下次 final 不能同树沿用）：%s" % e
    return None


def _final_reusable(root, rec, cur_snap, head, change_rel, fps):
    """记录绿、指纹全等、记录树与当前树（strict Δ 去掉记账文件）相同 → True。"""
    if cur_snap is None or not isinstance(rec, dict) or (rec.get("result") or {}).get("ok") is not True:
        return False
    if rec.get("fps") != fps:
        return False
    d = _delta(root, rec, cur_snap, head, change_rel, True, strict=True)
    changes_rel = change_rel.rsplit("/", 1)[0] if "/" in change_rel else ""
    return d is not None and not [p for p in d if not _is_bookkeeping(p, changes_rel)]


def _last_green(rec):
    """final 记录里最近一次绿的 {commit, snapshot}：记录本身绿取它，红取它带的 green；没有 → None。"""
    if not isinstance(rec, dict):
        return None
    if (rec.get("result") or {}).get("ok") is True:
        return {"commit": rec.get("commit"), "snapshot": rec.get("snapshot")}
    g = rec.get("green")
    return g if isinstance(g, dict) else None


def _impacted_anchor(root, rec, baseline, cur_snap, head, change_rel, name):
    """gate.impacted 的锚点（design D8）：本 change 最近一次绿的 final；它不是 HEAD 的祖先（或没有）时取基线 commit 与快照
    → (anchor, Δ) | None。不要求依赖图。"""
    for cand in (_last_green(rec), baseline):
        if isinstance(cand, dict) and isinstance(cand.get("snapshot"), dict):
            d = _delta(root, cand, cur_snap, head, change_rel, True)
            if d is not None:
                return dict(cand, change=name), d
    return None


def _pick_anchor(root, key, tkey, cur_snap, head, change_rel, name):
    """可用锚点里 |Δ| 最小者（同样小取最新）→ (anchor, Δ) | None。"""
    best = None
    for cand in _anchor_candidates(root, key, tkey):  # 由新到旧：严格更小才替换
        d = _delta(root, cand, cur_snap, head, change_rel, cand.get("change") == name)
        if d is not None and (best is None or len(d) < len(best[1])):
            best = (cand, d)
    return best


def _full_why(root, full, pick, baseline, snap_why, impacted=False):
    """自动全量的原因（按 spec 顺序取第一条命中）→ (why | None, warnings)。
    impacted=True（gate.impacted，design D8）：只看 --full、锚点与全局文件，不要求依赖图与 failed_nodes。"""
    if full:
        return "手动要求 --full", []
    if pick is None:
        return "没有可用锚点" + ("（%s）" % snap_why if snap_why else ""), []
    bt = (baseline or {}).get("test") or {}
    if not impacted and bt.get("failed") and not isinstance(bt.get("failed_nodes"), list):
        return "基线缺 failed_nodes（有预存红），重跑 baseline", []
    anchor, delta = pick
    glob = [p for p in delta if _global_file(p)]
    if glob:
        return "Δ 含全局文件：%s" % ", ".join(glob[:8]), []
    if impacted:
        return None, []
    seen = set()
    for v in (anchor.get("deps") or {}).values():
        seen.update(v)
    cand = [p for p in delta if p not in seen and not _py_test_file(p)]
    snap = anchor.get("snapshot") or {}
    try:
        blobs = _blobs_at(root, anchor["commit"], [p for p in cand if p not in snap])
    except RuntimeError as e:
        return "锚点内容比对失败：%s" % e, []
    existed = [p for p in cand if (snap[p] if p in snap else blobs.get(p)) is not None]
    other = [p for p in existed if not p.endswith(".py") and os.path.splitext(p)[1].lower() not in DOC_EXT]
    if other:
        return "Δ 含未被任何用例触及的非 Python 文件：%s" % ", ".join(other[:8]), []
    py = [p for p in existed if p.endswith(".py")]
    return None, (["Δ 中 %d 个 .py 文件未被任何用例加载：%s" % (len(py), ", ".join(py[:8]))] if py else [])


def _final_select(root, anchor, delta):
    """选中集合（design D5）：依赖与 Δ 相交 ∪ Δ 里的测试文件 ∪ 锚点失败所在 ∪ 盲；只留现存文件，排序。"""
    ds = set(delta)
    sel = {f for f, v in (anchor.get("deps") or {}).items() if ds.intersection(v)}
    sel.update(p for p in delta if _py_test_file(p))
    sel.update(str(n).split("::", 1)[0] for n in anchor.get("failed") or [])
    sel.update(anchor.get("blind") or [])
    return sorted(f for f in sel if os.path.isfile(os.path.join(root, f)))


def _anchor_forward(root, old, sel, d, fails, outcomes):
    """增量后的新锚点依赖部分：重跑文件（与已删除的文件）换成本次结果，其余照抄旧锚点。"""
    known = set(old.get("files") or []) | set(old.get("deps") or {}) | set(old.get("tests") or {})
    drop = set(sel) | {f for f in known if not os.path.isfile(os.path.join(root, f))}
    deps = {f: v for f, v in (old.get("deps") or {}).items() if f not in drop}
    deps.update(d.get("deps") or {})
    tests = {f: n for f, n in (old.get("tests") or {}).items() if f not in drop}
    tests.update(_node_counts(n for n, _ in outcomes))
    return {
        "files": sorted({f for f in old.get("files") or [] if f not in drop} | set(d.get("files") or [])),
        "failed": sorted({n for n in old.get("failed") or [] if str(n).split("::", 1)[0] not in drop} | set(fails)),
        "deps": dict(sorted(deps.items())),
        "blind": sorted({f for f in old.get("blind") or [] if f not in drop} | set(d.get("blind") or [])),
        "tests": tests,
        "measured": bool(d) or not sel,
    }


def _pool_candidates(root, key, limit=10, sub=POOL_DIR, pred=None):
    """池里 cmd_key == key（且满足 pred）的条目，按 at 由新到旧取前 limit 个；坏 JSON 跳过，池不可读返回 []。"""
    if not key:
        return []
    try:
        pdir = _pool_dir(root, sub)
        names = [n for n in os.listdir(pdir) if n.endswith(".json") and not n.startswith(".tmp-")]
    except (OSError, RuntimeError):
        return []
    hits = []
    for n in names:
        e = _pool_read(pdir, n)
        if e is not None and e.get("cmd_key") == key and (pred is None or pred(e)):
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


def _is_bookkeeping(rel, changes_rel):
    """路径是 changes 根下任一 change 的记账文件。"""
    prefix = changes_rel + "/"
    if not rel.startswith(prefix):
        return False
    parts = rel[len(prefix):].split("/", 1)
    return len(parts) == 2 and parts[1] in BOOKKEEPING


def _final_fresh(root, change_dir, final_commit):
    """final 行的 commit 与 HEAD 的树之差只含 changes 根下任一 change 的记账文件（或为空）→ 新鲜（design D6）；
    不要求祖先关系；任一 git 调用失败（commit 不存在等）→ 不新鲜。"""
    try:
        names = git(root, "diff", "--name-only", final_commit, "HEAD").splitlines()
    except RuntimeError:
        return False
    changes_rel = os.path.relpath(os.path.dirname(os.path.abspath(change_dir)), root).replace(os.sep, "/")
    return all(_is_bookkeeping(n, changes_rel) for n in names if n)


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
        if name == "final":
            p.add_argument("--full", action="store_true", help="不走增量与同树沿用，强制跑全量 gate.test")
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
