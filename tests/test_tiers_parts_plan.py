"""分层文件部件形态的 lint 规则与部件归属 G12
（scenario: test-tiers-polyglot#parts-lint-rejects-mixed-shapes … #shorthand-tiers-unchanged、#gate-flags-file-outside-parts）。
切片 S1 已实现，各 scenario 的 xfail 标记已去；护栏（shorthand-tiers-unchanged）在 base 上即已成立。"""
import hashlib
import json
import shlex
import sys

from conftest import commit_all, run_hook, write

PY = shlex.quote(sys.executable)
DRIVER = "python3 .claude/hooks/test-tiers.py run unit"
LIST_GO = "%s list.py" % PY
PY_UNIT = "python3 -m pytest -q tests/unit"


def layout(root):
    """被测仓库的两个子项目：svc/go（list.py 只列出 a_test.go；另有 b_test.go 与区域文件 it/db_test.go）、
    svc/py（单元层 tests/unit/test_p.py，仓库内适配器脚本 probe.py）。"""
    write(root / "svc" / "go" / "list.py", "print('a_test.go')\n")
    write(root / "svc" / "go" / "a_test.go", "package svc\n")
    write(root / "svc" / "go" / "b_test.go", "package svc\n")
    write(root / "svc" / "go" / "it" / "db_test.go", "package it\n")
    write(root / "svc" / "py" / "tests" / "unit" / "test_p.py", "def test_p():\n    assert True\n")
    write(root / "svc" / "py" / "probe.py", "print('probe v1')\n")


def parts_tiers():
    """合法的部件形态：go 用 list、带区域 go-db；py 用 paths 与 test_files。"""
    return {
        "parts": {
            "go": {"root": "svc/go",
                   "unit": {"list": LIST_GO, "cmd": "go test ./..."},
                   "regions": {"go-db": {"paths": ["svc/go/it/**"], "covers": ["svc/go/store/**"],
                                         "cmd": "go test ./it/..."}}},
            "py": {"root": "svc/py", "test_files": ["svc/py/tests/**/test_*.py"],
                   "unit": {"paths": ["svc/py/tests/unit/**"], "cmd": PY_UNIT}},
        },
        "slow_allow": {},
    }


def plan(scenario_tests=None, owns=("svc/py/app.py",), **gate):
    """单片计划；gate 缺省 test = 驱动命令，其余字段由关键字参数覆盖或追加。"""
    g = {"test": DRIVER, "lint": None, "typecheck": None}
    g.update(gate)
    st = scenario_tests or {}
    return {
        "version": 1, "change": "c", "gate": g,
        "slices": [{"id": "S1", "title": "t", "owns": list(owns), "deps": [], "verify": "true",
                    "scenarios": list(st), "packet": "slices/S1.md"}],
        "scenario_tests": st,
    }


def make(root, data, tiers_obj):
    """写被测布局、openspec/changes/c/slices.json 与 openspec/test-tiers.json。返回 change 目录。"""
    layout(root)
    d = root / "openspec" / "changes" / "c"
    write(d / "slices.json", json.dumps(data, ensure_ascii=False))
    set_tiers(root, tiers_obj)
    return d


def set_tiers(root, tiers_obj):
    (root / "openspec" / "test-tiers.json").write_text(json.dumps(tiers_obj, ensure_ascii=False), encoding="utf-8")


def lint(root, d):
    return run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=root)


def tier_lines(p):
    """stderr 里以 tiers: 开头的违规行（lint 输出形如 `  - tiers: …`）。"""
    return [l.strip().lstrip("- ") for l in p.stderr.splitlines() if l.strip().lstrip("- ").startswith("tiers:")]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- lint：形状


def test_parts_lint_rejects_mixed_shapes(git_repo):
    # Given: 分层文件顶层同时有 parts 与 unit
    t = parts_tiers()
    t["unit"] = {"paths": ["tests/unit/**"], "cmd": PY_UNIT}
    d = make(git_repo, plan(), t)

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出非 0；有一行 tiers: 同时含 parts 与 unit
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("parts" in l and "unit" in l for l in tier_lines(p)), p.stderr


def test_parts_lint_rejects_malformed_parts(git_repo):
    # Given: 部件名 Api 不合法；up 的 root 是 ../out；ghost 的 root 是不存在的 nope；both 的 unit 同时有 paths 与 list；
    #        区域 dup 同时出现在 both 与 odd；odd 带未知字段 extra
    t = {
        "parts": {
            "Api": {"root": "svc/py", "test_files": ["svc/py/x/**"], "unit": {"paths": ["svc/py/x/**"], "cmd": "true"}},
            "up": {"root": "../out", "unit": {"paths": ["out/**"], "cmd": "true"}},
            "ghost": {"root": "nope", "unit": {"paths": ["nope/**"], "cmd": "true"}},
            "both": {"root": "svc/go", "unit": {"paths": ["svc/go/**"], "list": LIST_GO, "cmd": "true"},
                     "regions": {"dup": {"paths": ["svc/go/it/**"], "covers": [], "cmd": "true"}}},
            "odd": {"root": "svc/py", "extra": [], "test_files": ["svc/py/tests/**"],
                    "unit": {"paths": ["svc/py/tests/unit/**"], "cmd": "true"},
                    "regions": {"dup": {"paths": ["svc/py/it/**"], "covers": [], "cmd": "true"}}},
        },
        "slow_allow": {},
    }
    d = make(git_repo, plan(), t)

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出非 0；tiers: 行分别点名 Api、../out、nope、both、dup、extra
    assert p.returncode != 0, p.stdout + p.stderr
    lines = tier_lines(p)
    for word in ("Api", "../out", "nope", "both", "dup", "extra"):
        assert any(word in l for l in lines), (word, lines)


def test_parts_lint_requires_driver_gate_test(git_repo):
    # Given: 合法的部件形态；gate.test 是部件 py 的 unit.cmd
    d = make(git_repo, plan(test=PY_UNIT), parts_tiers())

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出非 0；有一行 tiers: 含 gate.test 与 test-tiers.py run unit
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("gate.test" in l and "test-tiers.py run unit" in l for l in tier_lines(p)), p.stderr


def test_parts_lint_rejects_impacted(git_repo):
    # Given: 合法的部件形态；gate.test 是驱动命令，另有 gate.impacted
    d = make(git_repo, plan(impacted="%s select.py" % PY), parts_tiers())

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出非 0；有一行 tiers: 含 gate.impacted
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("gate.impacted" in l for l in tier_lines(p)), p.stderr


# ---------------------------------------------------------------- lint：选择器与适配器


def test_parts_lint_resolves_list_selector(git_repo):
    # Given: 部件 go（root svc/go）的单元层 list 只输出 a_test.go；scenario_tests 分别映射到 a_test.go 与 b_test.go
    st = {"c#a": "svc/go/a_test.go::TestA", "c#b": "svc/go/b_test.go::TestB"}
    d = make(git_repo, plan(scenario_tests=st), parts_tiers())

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出非 0；tiers: 行恰有一行点名 svc/go/b_test.go，没有一行点名 svc/go/a_test.go
    assert p.returncode != 0, p.stdout + p.stderr
    lines = tier_lines(p)
    assert len([l for l in lines if "svc/go/b_test.go" in l]) == 1, lines
    assert not [l for l in lines if "svc/go/a_test.go" in l], lines

    # When: list 命令改成退出 1 后再运行 lint
    write(git_repo / "svc" / "go" / "list.py", "import sys\nsys.exit(1)\n")
    p = lint(git_repo, d)

    # Then: 有一行 tiers: 含 go 与 list
    assert any("go" in l and "list" in l for l in tier_lines(p)), p.stderr


def test_parts_lint_requires_self_checked_adapter(git_repo):
    # Given: 部件 py 的 unit.probe 运行仓库内脚本 svc/py/probe.py，没有 sha 与 checked
    t = parts_tiers()
    probe = {"cmd": "python3 probe.py", "canary": "python3 -m pytest -q canary", "canary_files": ["svc/py/canary/**"]}
    t["parts"]["py"]["unit"]["probe"] = probe
    d = make(git_repo, plan(), t)

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 有一行 tiers: 含 py 与「未自检」
    assert any("py" in l and "未自检" in l for l in tier_lines(p)), p.stderr

    # When: 补上 checked 与正确的 sha 后运行 lint
    probe["sha"] = {"svc/py/probe.py": sha256(git_repo / "svc" / "py" / "probe.py")}
    probe["checked"] = "2026-10-29T00:00:00+00:00"
    set_tiers(git_repo, t)
    p = lint(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stdout + p.stderr

    # When: 改动适配器内容后运行 lint
    write(git_repo / "svc" / "py" / "probe.py", "print('probe v2')\n")
    p = lint(git_repo, d)

    # Then: 有一行 tiers: 含 svc/py/probe.py 与 canary
    assert any("svc/py/probe.py" in l and "canary" in l for l in tier_lines(p)), p.stderr


def test_parts_lint_accepts_valid_parts_plan(git_repo):
    # Given: 合法的部件形态；gate.test 是驱动命令；选了区域 go-db；scenario_tests 指向两个部件的单元层与区域 go-db
    st = {"c#a": "svc/go/a_test.go::TestA", "c#p": "svc/py/tests/unit/test_p.py::test_p",
          "c#d": "svc/go/it/db_test.go::TestDb"}
    d = make(git_repo, plan(scenario_tests=st, integration=["go-db"]), parts_tiers())

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stdout + p.stderr


def test_shorthand_tiers_unchanged(git_repo):
    # Given: 简写形态的合法分层文件，gate.test 等于 unit.cmd
    short = {"unit": {"paths": ["tests/unit/**"], "cmd": PY_UNIT}, "regions": {}, "slow_allow": {}}
    d = make(git_repo, plan(test=PY_UNIT), short)

    # When: 运行 slice-gate.py lint
    p = lint(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stdout + p.stderr

    # When: 在简写形态的 unit 里加上 list
    short["unit"]["list"] = LIST_GO
    set_tiers(git_repo, short)
    p = lint(git_repo, d)

    # Then: 退出非 0；有一行 tiers: 含「未知字段」
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("未知字段" in l for l in tier_lines(p)), p.stderr


# ---------------------------------------------------------------- 切片门禁 G12


def test_gate_flags_file_outside_parts(git_repo):
    # Given: 部件 py（test_files svc/py/tests/**/test_*.py，单元层 svc/py/tests/unit/**）；计划没选区域；
    #        切片 S1 起跑后，区间里新增 svc/py/tests/unit/test_ok.py、svc/py/tests/integration/test_i.py、tools/x_test.go
    d = make(git_repo, plan(owns=("svc/**", "tools/**")), parts_tiers())
    commit_all(git_repo, "plan")
    s = run_hook("slice-gate", "start", "S1", "--change-dir", str(d), cwd=git_repo)
    assert s.returncode == 0, s.stdout + s.stderr
    write(git_repo / "svc" / "py" / "tests" / "unit" / "test_ok.py", "def test_ok():\n    assert True\n")
    write(git_repo / "svc" / "py" / "tests" / "integration" / "test_i.py", "def test_i():\n    assert True\n")
    write(git_repo / "tools" / "x_test.go", "package tools\n")
    commit_all(git_repo, "S1")

    # When: 运行 slice-gate.py gate S1
    p = run_hook("slice-gate", "gate", "S1", "--change-dir", str(d), cwd=git_repo)

    # Then: G12 点名 test_i.py 与 tools/x_test.go，不点名 test_ok.py
    out = json.loads(p.stdout)
    g12 = [f for f in out["failed"] if f.startswith("G12")]
    assert any("svc/py/tests/integration/test_i.py" in f for f in g12), out
    assert any("tools/x_test.go" in f for f in g12), out
    assert not any("svc/py/tests/unit/test_ok.py" in f for f in g12), out
