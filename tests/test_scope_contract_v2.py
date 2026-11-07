"""选测提供方契约 v2（scenario: scope-provider-contract#undeclared-provider-is-red、#establishing-change-passes-only-with-reason、
#builtin-declaration-reports-builtin、#builtin-with-unrecognized-gate-test-is-red、#malformed-v2-declaration-is-red、
#cmd-provider-receives-planned-files-and-change、#scope-seed-decides-by-history，共 7 条；#spec-html-shows-provider-state 在
tests/test_spec_html_scope.py）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。
各用例显式写或删 openspec/gate-scope.json，不依赖测试基座 git_repo 的默认声明。"""
import json

import pytest

from conftest import run_hook, write
from test_slice_gate import plan, slice_, write_plan

PENDING = pytest.mark.xfail(strict=True, reason="change scope-guard-enforced S1 未实现")

PY = "python3 -m pytest -q tests"

# 替身提供方：把 GATE_SCOPE_PLANNED 每行加前缀 planned:、GATE_SCOPE_CHANGE 加前缀 change:，作为触发项报全选；变量缺失则不全选
PLANNED_TOOL = """
    import json
    import os

    trig = []
    planned = os.environ.get("GATE_SCOPE_PLANNED")
    if planned:
        with open(planned, encoding="utf-8") as f:
            trig += ["planned:" + l.strip() for l in f if l.strip()]
    change = os.environ.get("GATE_SCOPE_CHANGE")
    if change:
        trig.append("change:" + change)
    with open(os.environ["GATE_SCOPE_OUT"], "w", encoding="utf-8") as out:
        json.dump({"full": bool(trig), "triggers": trig}, out)
"""


def _decl(repo, obj):
    """写 openspec 根的选测声明；obj 为 None → 删除（测「未声明」）。"""
    path = repo / "openspec" / "gate-scope.json"
    if obj is None:
        if path.exists():
            path.unlink()
        return
    write(path, json.dumps(obj, ensure_ascii=False))


def _change(repo, owns=("a/**",), **gate):
    """change c 的单片计划；gate 的键值并入 gate 段。返回 change 目录。"""
    data = plan([slice_("S1", list(owns))])
    data["gate"].update(gate)
    return write_plan(repo / "openspec" / "changes" / "c", data)


def _lint(repo, change):
    return run_hook("slice-gate", "lint", "--change-dir", str(change), cwd=repo)


def _scope_lines(stderr):
    """stderr 里以 scope: 开头的行（违规行格式 `  - scope: …`，摘要行 `scope: …`）。"""
    out = []
    for line in stderr.splitlines():
        s = line.strip()
        s = s[2:] if s.startswith("- ") else s
        if s.startswith("scope:"):
            out.append(s)
    return out


@PENDING
def test_undeclared_provider_is_red(git_repo):
    # Given: openspec 根没有 gate-scope.json，计划没写 gate.scope，唯一切片的 owns 是 a/**
    d = _change(git_repo)
    _decl(git_repo, None)

    # When: 运行 slice-gate.py lint
    p = _lint(git_repo, d)

    # Then: 退出非 0；有一行 scope: 含「未声明选测范围」，并同时提到 builtin 与 cmd
    assert p.returncode != 0, p.stderr
    hits = [l for l in _scope_lines(p.stderr) if "未声明选测范围" in l]
    assert hits and "builtin" in hits[0] and "cmd" in hits[0], p.stderr


@PENDING
def test_establishing_change_passes_only_with_reason(git_repo):
    # Given: 没有任何选测声明；切片 owns 含 openspec/gate-scope.json（本 change 建立声明）
    d = _change(git_repo, owns=("a/**", "openspec/gate-scope.json"))
    _decl(git_repo, None)

    # When: 先不写理由运行 lint；再补上 scope:undeclared 的理由运行一次
    first = _lint(git_repo, d)
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["gate"]["scope_full_reason"] = {"scope:undeclared": "本 change 建立仓库选测声明"}
    write_plan(d, data)
    second = _lint(git_repo, d)

    # Then: 第一次退出非 0 且点名 scope:undeclared；第二次退出 0，摘要含「本 change 建立仓库选测声明」
    assert first.returncode != 0, first.stderr
    assert any("scope:undeclared" in l for l in _scope_lines(first.stderr)), first.stderr
    assert second.returncode == 0, second.stderr
    assert any("本 change 建立仓库选测声明" in l for l in _scope_lines(second.stderr)), second.stderr


@PENDING
def test_builtin_declaration_reports_builtin(git_repo):
    # Given: 仓库声明 {"builtin": true}，gate.test 是 pytest 命令，切片 owns 只有 a/**
    d = _change(git_repo, test=PY)
    _decl(git_repo, {"builtin": True})

    # When: 运行 lint
    p = _lint(git_repo, d)

    # Then: 退出 0；stderr 有一行 scope: 摘要含「模板内建」
    assert p.returncode == 0, p.stderr
    assert any("模板内建" in l for l in _scope_lines(p.stderr)), p.stderr


@PENDING
def test_builtin_with_unrecognized_gate_test_is_red(git_repo):
    # Given: 仓库声明 {"builtin": true}，gate.test 是包装脚本 bash scripts/test.sh
    d = _change(git_repo, test="bash scripts/test.sh")
    _decl(git_repo, {"builtin": True})

    # When: 运行 lint
    p = _lint(git_repo, d)

    # Then: 退出非 0；有一行 scope: 含「认不出」与 cmd
    assert p.returncode != 0, p.stderr
    assert any("认不出" in l and "cmd" in l for l in _scope_lines(p.stderr)), p.stderr


@PENDING
def test_malformed_v2_declaration_is_red(git_repo):
    # Given: 三种不合法的 v2 声明，各自应点名的问题；以及合法的 {"builtin": true}
    cases = [({"builtin": True, "cmd": "x"}, "只能取其一"),
             ({"builtin": False}, "须为 true"),
             ({"builtin": True, "args": 1}, "args")]
    d = _change(git_repo, test=PY)

    # When: 逐个写入声明并运行 lint，最后写入合法声明再运行一次
    runs = []
    for obj, word in cases:
        _decl(git_repo, obj)
        runs.append((_lint(git_repo, d), word))
    _decl(git_repo, {"builtin": True})
    ok = _lint(git_repo, d)

    # Then: 三个不合法的都退出非 0 且点名对应问题；{"builtin": true} 退出 0
    for p, word in runs:
        assert p.returncode != 0 and any(word in l for l in _scope_lines(p.stderr)), (word, p.stderr)
    assert ok.returncode == 0, ok.stderr


@PENDING
def test_cmd_provider_receives_planned_files_and_change(git_repo):
    # Given: 计划 gate.scope 是替身提供方；切片 owns 是 bin/x.sh 与 src/**；change 目录是 openspec/changes/c
    write(git_repo / "tools" / "planned.py", PLANNED_TOOL)
    d = _change(git_repo, owns=("bin/x.sh", "src/**"), scope="python3 tools/planned.py")

    # When: 运行 lint
    p = _lint(git_repo, d)

    # Then: 退出非 0；缺理由的触发项恰为 planned:bin/x.sh、planned:src/**、change:openspec/changes/c
    assert p.returncode != 0, p.stderr
    line = next((l for l in _scope_lines(p.stderr) if "缺理由" in l), "")
    got = set(line.split("触发项 ", 1)[-1].split(" 缺理由", 1)[0].split("、")) if line else set()
    assert got == {"planned:bin/x.sh", "planned:src/**", "change:openspec/changes/c"}, p.stderr


@PENDING
def test_scope_seed_decides_by_history(tmp_path):
    # Given: 三个 openspec 根：A 的历史 gate.test 只有 pytest；B 另有一条包装脚本（在 archive 下）；C 已有 {"cmd": "mine"}
    def root(name, tests, existing=None):
        r = tmp_path / name / "openspec"
        for i, t in enumerate(tests):
            sub = r / "changes" / "archive" / ("x%d" % i) if i else r / "changes" / ("x%d" % i)
            write(sub / "slices.json", json.dumps({"gate": {"test": t}}))
        if existing is not None:
            write(r / "gate-scope.json", json.dumps(existing))
        return r

    a = root("a", [PY])
    b = root("b", [PY, "bash openspec/changes/x/verify/full_suite.sh"])
    c = root("c", ["bash x.sh"], existing={"cmd": "mine"})
    before_c = (c / "gate-scope.json").read_text(encoding="utf-8")

    # When: 对每个根运行 slice-gate.py scope-seed --openspec-root <根>
    runs = {k: run_hook("slice-gate", "scope-seed", "--openspec-root", str(r)) for k, r in (("a", a), ("b", b), ("c", c))}

    # Then: 都退出 0；A 写出 {"builtin": true} 且 stdout 含「已种」；B 没有声明、stdout 含「未种」与 full_suite.sh；
    #       C 的文件不变、stdout 含「保留」与 mine
    assert all(p.returncode == 0 for p in runs.values()), {k: p.stderr for k, p in runs.items()}
    assert json.loads((a / "gate-scope.json").read_text(encoding="utf-8")) == {"builtin": True}
    assert "已种" in runs["a"].stdout, runs["a"].stdout
    assert not (b / "gate-scope.json").exists()
    assert "未种" in runs["b"].stdout and "full_suite.sh" in runs["b"].stdout, runs["b"].stdout
    assert (c / "gate-scope.json").read_text(encoding="utf-8") == before_c
    assert "保留" in runs["c"].stdout and "mine" in runs["c"].stdout, runs["c"].stdout
