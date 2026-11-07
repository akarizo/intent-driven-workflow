"""选测范围报告契约与全选表态（scenario: gate-scope-report#scope-lint-rejects-malformed-declarations …
#reason-without-scope-command-is-red，共 14 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。护栏（waves-does-not-run-scope、
scope-fields-not-in-plan-sha）在 base 上已成立，不带 xfail。"""
import copy
import json

import pytest

from conftest import load_hook, run_hook, write
from test_slice_gate import plan, slice_, write_plan

# 选测命令替身：把仓库相对路径 tools/report.json 原样写进 GATE_SCOPE_OUT；带参数 N 时不写、以退出码 N 退出
SCOPE = """
    import os
    import sys

    code = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if code == 0:
        with open(os.path.join("tools", "report.json"), encoding="utf-8") as src:
            body = src.read()
        with open(os.environ["GATE_SCOPE_OUT"], "w", encoding="utf-8") as out:
            out.write(body)
    sys.exit(code)
"""
CMD = "python3 tools/scope.py"


def _repo(repo, report=None, gate_scope=None, reasons=None, default=None, undeclared=False):
    """被测仓库：tools/scope.py 替身 + 可选 tools/report.json；change c 单片计划，可带 gate.scope / gate.scope_full_reason；
    default 为对象时写成 openspec 根的 gate-scope.json（覆盖基座声明）；undeclared 为真时删掉基座声明（契约 v2「未声明」）。
    返回 change 目录。"""
    write(repo / "tools" / "scope.py", SCOPE)
    if report is not None:
        write(repo / "tools" / "report.json", json.dumps(report, ensure_ascii=False))
    if default is not None:
        write(repo / "openspec" / "gate-scope.json", json.dumps(default, ensure_ascii=False))
    data = plan([slice_("S1", ["a/**"])])
    if gate_scope is not None:
        data["gate"]["scope"] = gate_scope
    if reasons is not None:
        data["gate"]["scope_full_reason"] = reasons
    change = write_plan(repo / "openspec" / "changes" / "c", data)
    if undeclared:
        (repo / "openspec" / "gate-scope.json").unlink()
    return change


def _run(sub, change, cwd):
    return run_hook("slice-gate", sub, "--change-dir", str(change), cwd=cwd)


def _scope_lines(stderr):
    """stderr 里以 scope: 开头的行（违规行格式 `  - scope: …`，摘要行 `scope: …`）。"""
    out = []
    for l in stderr.splitlines():
        s = l.strip()
        s = s[2:] if s.startswith("- ") else s
        if s.startswith("scope:"):
            out.append(s)
    return out


def test_scope_lint_rejects_malformed_declarations(git_repo):
    # Given: gate.scope 是空白串；gate.scope_full_reason 里 a.json 的理由是空白；openspec 根 gate-scope.json 带未知字段 args
    change = _repo(git_repo, gate_scope="  ", reasons={"a.json": " "}, default={"cmd": CMD, "args": "-x"})

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；以 scope: 开头的行分别点名 gate.scope、a.json、args
    assert p.returncode != 0, p.stdout
    lines = _scope_lines(p.stderr)
    for word in ("gate.scope", "a.json", "args"):
        assert any(word in l for l in lines), (word, p.stderr)


def test_scope_command_failure_is_red(git_repo):
    # Given: 计划的 gate.scope 命令以退出码 3 退出
    change = _repo(git_repo, gate_scope=CMD + " 3")

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、含 exit 3
    assert p.returncode != 0, p.stdout
    assert any("exit 3" in l for l in _scope_lines(p.stderr)), p.stderr


def test_scope_bad_report_is_red(git_repo):
    # Given: gate.scope 退出 0，但写进 GATE_SCOPE_OUT 的是 {"full": "yes", "triggers": "a"}
    change = _repo(git_repo, report={"full": "yes", "triggers": "a"}, gate_scope=CMD)

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、点名 full
    assert p.returncode != 0, p.stdout
    assert any("full" in l for l in _scope_lines(p.stderr)), p.stderr


def test_scope_not_full_passes(git_repo):
    # Given: gate.scope 从仓库相对路径读报告、写进 GATE_SCOPE_OUT：{"full": false, "triggers": [], "count": 12}
    change = _repo(git_repo, report={"full": False, "triggers": [], "count": 12}, gate_scope=CMD)

    # When: 在仓库子目录 openspec 里运行 slice-gate.py lint（选测命令须在 git 顶层运行才找得到报告）
    p = _run("lint", change, git_repo / "openspec")

    # Then: 退出 0，stdout 是 waves JSON；stderr 有一行以 scope: 开头、含「未全选」与 12
    assert p.returncode == 0, p.stderr
    assert isinstance(json.loads(p.stdout.strip().splitlines()[-1]), list), p.stdout
    assert any("未全选" in l and "12" in l for l in _scope_lines(p.stderr)), p.stderr


def test_repo_default_used_when_plan_silent(git_repo):
    # Given: gate-scope.json 是 {"cmd": "python3 tools/scope.py"}，它报告全选、触发项 tools/infra.txt；计划没写 gate.scope 与理由
    change = _repo(git_repo, report={"full": True, "triggers": ["tools/infra.txt"]}, default={"cmd": CMD})

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、同时含 tools/infra.txt 与 gate.scope_full_reason
    assert p.returncode != 0, p.stdout
    assert any("tools/infra.txt" in l and "gate.scope_full_reason" in l for l in _scope_lines(p.stderr)), p.stderr


def test_plan_scope_overrides_repo_default(git_repo):
    # Given: gate-scope.json 的命令以退出码 1 退出；计划的 gate.scope 报告未全选、count 为 7
    change = _repo(git_repo, report={"full": False, "triggers": [], "count": 7}, gate_scope=CMD,
                   default={"cmd": CMD + " 1"})

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出 0；有一行以 scope: 开头、含「未全选」与 7
    assert p.returncode == 0, p.stderr
    assert any("未全选" in l and "7" in l for l in _scope_lines(p.stderr)), p.stderr


def test_waves_does_not_run_scope(git_repo):
    # Given: 计划的 gate.scope 命令以退出码 1 退出
    change = _repo(git_repo, gate_scope=CMD + " 1")

    # When: 运行 slice-gate.py waves
    p = _run("waves", change, git_repo)

    # Then: 退出 0，stdout 是 waves JSON
    assert p.returncode == 0, p.stderr
    assert isinstance(json.loads(p.stdout.strip().splitlines()[-1]), list), p.stdout


def test_preflight_runs_scope(git_repo):
    # Given: 计划的 gate.scope 报告全选、触发项 tools/infra.txt，计划没写 gate.scope_full_reason
    change = _repo(git_repo, report={"full": True, "triggers": ["tools/infra.txt"]}, gate_scope=CMD)

    # When: 运行 slice-gate.py preflight
    p = _run("preflight", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、含 tools/infra.txt
    assert p.returncode != 0, p.stdout
    assert any("tools/infra.txt" in l for l in _scope_lines(p.stderr)), p.stderr


def test_scope_fields_not_in_plan_sha():
    # Given: 两份计划只差在 gate.scope 与 gate.scope_full_reason
    sg = load_hook("slice-gate")
    a = plan([slice_("S1", ["a/**"])])
    b = copy.deepcopy(a)
    b["gate"]["scope"] = CMD
    b["gate"]["scope_full_reason"] = {"a.json": "理由"}

    # When: 分别计算 plan_sha
    sa, sb = sg.plan_sha(a), sg.plan_sha(b)

    # Then: 两者相等
    assert sa == sb


def test_full_without_reason_is_red(git_repo):
    # Given: gate.scope 报告全选、触发项 a.json 与 b.py，计划没写 gate.scope_full_reason
    change = _repo(git_repo, report={"full": True, "triggers": ["a.json", "b.py"]}, gate_scope=CMD)

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；以 scope: 开头的行点名 a.json 与 b.py，并含 gate.scope_full_reason
    assert p.returncode != 0, p.stdout
    lines = _scope_lines(p.stderr)
    for word in ("a.json", "b.py", "gate.scope_full_reason"):
        assert any(word in l for l in lines), (word, p.stderr)


def test_full_with_matching_reasons_passes(git_repo):
    # Given: gate.scope 报告全选、触发项 a.json 与 b.py；gate.scope_full_reason 为两项各写了非空理由
    change = _repo(git_repo, report={"full": True, "triggers": ["a.json", "b.py"]}, gate_scope=CMD,
                   reasons={"a.json": "登记表只含本 change 新文件", "b.py": "选测修复合入前接受一次全量"})

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出 0；有一行以 scope: 开头、含「全选」（不是「未全选」）与 a.json、b.py
    assert p.returncode == 0, p.stderr
    assert any("全选" in l and "未全选" not in l and "a.json" in l and "b.py" in l
               for l in _scope_lines(p.stderr)), p.stderr


def test_reason_keys_must_match_triggers(git_repo):
    # Given: gate.scope 报告全选、触发项只有 a.json；gate.scope_full_reason 写了 a.json 与 old.txt
    change = _repo(git_repo, report={"full": True, "triggers": ["a.json"]}, gate_scope=CMD,
                   reasons={"a.json": "理由", "old.txt": "过期理由"})

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、点名 old.txt
    assert p.returncode != 0, p.stdout
    assert any("old.txt" in l for l in _scope_lines(p.stderr)), p.stderr


def test_reason_when_not_full_is_red(git_repo):
    # Given: gate.scope 报告未全选；gate.scope_full_reason 写了 a.json
    change = _repo(git_repo, report={"full": False, "triggers": []}, gate_scope=CMD, reasons={"a.json": "理由"})

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、点名 a.json
    assert p.returncode != 0, p.stdout
    assert any("a.json" in l for l in _scope_lines(p.stderr)), p.stderr


def test_reason_without_scope_command_is_red(git_repo):
    # Given: 计划没写 gate.scope，openspec 根也没有 gate-scope.json；gate.scope_full_reason 写了 a.json
    change = _repo(git_repo, reasons={"a.json": "理由"}, undeclared=True)

    # When: 运行 slice-gate.py lint
    p = _run("lint", change, git_repo)

    # Then: 退出非 0；有一行以 scope: 开头、含「未声明选测范围」
    assert p.returncode != 0, p.stdout
    assert any("未声明选测范围" in l for l in _scope_lines(p.stderr)), p.stderr
