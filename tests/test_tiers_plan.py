"""分层文件与计划的 lint 规则、plan_sha 追加区域、切片门禁 G12
（scenario: test-tiers#lint-rejects-unreadable-tiers-file … #no-tiers-file-lint-unchanged、#gate-flags-test-file-outside-tiers）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。
护栏（lint-accepts-valid-tiers-plan、no-tiers-file-lint-unchanged）在 base 上已成立，不带 xfail。"""
import hashlib
import json

import pytest

from conftest import commit_all, load_hook, run_hook, write

XF = pytest.mark.xfail(strict=True, reason="S1 尚未实现")
UNIT_CMD = "python3 -m pytest -q tests/unit"


def tiers():
    """合法的分层文件：单元层 tests/unit；区域 hooks（守护 src/hooks）与 docs（守护 docs）。"""
    return {
        "unit": {"paths": ["tests/unit/**"], "cmd": UNIT_CMD},
        "regions": {
            "hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"],
                      "cmd": "python3 -m pytest -q tests/integration/hooks"},
            "docs": {"paths": ["tests/integration/docs/**"], "covers": ["docs/**"],
                     "cmd": "python3 -m pytest -q tests/integration/docs"},
        },
        "slow_allow": {},
    }


def plan(owns=("src/app.py",), scenario_tests=None, **gate):
    """单片计划；gate 缺省 test = UNIT_CMD，其余字段由关键字参数覆盖或追加。"""
    g = {"test": UNIT_CMD, "lint": None, "typecheck": None}
    g.update(gate)
    st = scenario_tests or {}
    return {
        "version": 1, "change": "c", "gate": g,
        "slices": [{"id": "S1", "title": "t", "owns": list(owns), "deps": [],
                    "verify": "python3 -m pytest -q tests/unit", "scenarios": list(st), "packet": "slices/S1.md"}],
        "scenario_tests": st,
    }


def make(root, data, tiers_obj=None):
    """写 openspec/changes/c/slices.json 与可选的 openspec/test-tiers.json（tiers_obj 为 str 时原样写入）。返回 change 目录。"""
    d = root / "openspec" / "changes" / "c"
    write(d / "slices.json", json.dumps(data, ensure_ascii=False))
    if tiers_obj is not None:
        text = tiers_obj if isinstance(tiers_obj, str) else json.dumps(tiers_obj, ensure_ascii=False)
        (root / "openspec" / "test-tiers.json").write_text(text, encoding="utf-8")
    return d


def lint(root, d):
    return run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=root)


def tier_lines(p):
    """stderr 里以 tiers: 开头的违规行（lint 输出形如 `  - tiers: …`）。"""
    return [l.strip().lstrip("- ") for l in p.stderr.splitlines() if l.strip().lstrip("- ").startswith("tiers:")]


# ---------------------------------------------------------------- lint：分层文件


@XF
def test_lint_rejects_unreadable_tiers_file(tmp_path):
    # Given: openspec/test-tiers.json 的内容不是合法 JSON；本 change 的计划其余部分合法
    d = make(tmp_path, plan(), "{not json")

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；stderr 有一行以 tiers: 开头并含 test-tiers.json
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("test-tiers.json" in l for l in tier_lines(p)), p.stderr


@XF
def test_lint_rejects_malformed_tiers_file(tmp_path):
    # Given: unit 缺 cmd；区域 Bad 名字不合法；区域 typo 带未知字段 cover（且缺 covers）；
    #        slow_allow 里 tests/unit/test_a.py::test_x 的 reason 是空白
    t = tiers()
    del t["unit"]["cmd"]
    t["regions"]["Bad"] = {"paths": ["tests/x/**"], "covers": [], "cmd": "true"}
    t["regions"]["typo"] = {"paths": ["tests/y/**"], "cover": ["src/**"], "cmd": "true"}
    t["slow_allow"] = {"tests/unit/test_a.py::test_x": {"reason": "  ", "approved": "2026-10-28T08:00:00Z · 放行 test_x"}}
    d = make(tmp_path, plan(), t)

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；tiers: 行分别点名 unit（缺 cmd）、Bad、typo、tests/unit/test_a.py::test_x
    assert p.returncode != 0, p.stdout + p.stderr
    lines = tier_lines(p)
    assert any("unit" in l and "cmd" in l and "test_a.py" not in l for l in lines), lines
    assert any("Bad" in l for l in lines), lines
    assert any("typo" in l for l in lines), lines
    assert any("tests/unit/test_a.py::test_x" in l for l in lines), lines


@XF
def test_lint_requires_gate_test_to_be_unit_cmd(tmp_path):
    # Given: unit.cmd 是 python3 -m pytest -q tests/unit；计划的 gate.test 是 python3 -m pytest -q tests
    d = make(tmp_path, plan(test="python3 -m pytest -q tests"), tiers())

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；stderr 有一行以 tiers: 开头并含 gate.test
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("gate.test" in l for l in tier_lines(p)), p.stderr


# ---------------------------------------------------------------- lint：区域选择


@XF
def test_lint_rejects_bad_region_selection(tmp_path):
    # Given: 分层文件只有区域 hooks 与 docs；gate.integration = [hooks, ghost, hooks]；
    #        gate.integration_skip = {docs: 空白理由, hooks: 不碰}
    data = plan(integration=["hooks", "ghost", "hooks"], integration_skip={"docs": "  ", "hooks": "不碰"})
    d = make(tmp_path, data, tiers())

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；tiers: 行点名 ghost、理由空白的 docs，且至少两行点名 hooks（重复 + 两处同时出现）
    assert p.returncode != 0, p.stdout + p.stderr
    lines = tier_lines(p)
    assert any("ghost" in l for l in lines), lines
    assert any("docs" in l for l in lines), lines
    assert len([l for l in lines if "hooks" in l]) >= 2, lines


@XF
def test_lint_rejects_integration_without_tiers_file(tmp_path):
    # Given: openspec 根目录下没有 test-tiers.json；计划的 gate.integration 是 [hooks]
    d = make(tmp_path, plan(integration=["hooks"]))

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；stderr 有一行以 tiers: 开头并含 test-tiers.json
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("test-tiers.json" in l for l in tier_lines(p)), p.stderr


@XF
def test_lint_requires_decision_for_covered_region(tmp_path):
    # Given: 区域 hooks 的 covers 是 src/hooks/**；切片 S1 的 owns 含 src/hooks/gate.py；
    #        gate.integration 与 gate.integration_skip 都没有 hooks
    d = make(tmp_path, plan(owns=("src/hooks/gate.py",)), tiers())

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；stderr 有一行以 tiers: 开头并点名 hooks
    assert p.returncode != 0, p.stdout + p.stderr
    assert any("hooks" in l for l in tier_lines(p)), p.stderr


@XF
def test_lint_requires_scenario_test_in_tier(tmp_path):
    # Given: 区域 hooks 没被选上；一条 scenario 映射到 tests/integration/hooks/test_g.py，另一条映射到 tests/test_loose.py
    st = {"cap#a": "tests/integration/hooks/test_g.py::test_g", "cap#b": "tests/test_loose.py::test_loose"}
    d = make(tmp_path, plan(scenario_tests=st), tiers())

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出非 0；tiers: 行分别点名两个测试文件
    assert p.returncode != 0, p.stdout + p.stderr
    lines = tier_lines(p)
    assert any("tests/integration/hooks/test_g.py" in l for l in lines), lines
    assert any("tests/test_loose.py" in l for l in lines), lines


def test_lint_accepts_valid_tiers_plan(tmp_path):
    # Given: 分层文件合法、unit.cmd 与 gate.test 相同；hooks 的 covers 与 S1 owns 相交且已选；
    #        docs 的 covers 也相交、在 integration_skip 写了理由；scenario 测试分别在 tests/unit 与 tests/integration/hooks 下
    st = {"cap#a": "tests/unit/test_a.py::test_a", "cap#b": "tests/integration/hooks/test_b.py::test_b"}
    data = plan(owns=("src/hooks/gate.py", "docs/guide.md"), scenario_tests=st,
                integration=["hooks"], integration_skip={"docs": "只改错别字，不碰文档生成"})
    d = make(tmp_path, data, tiers())

    # When: 运行 slice-gate.py lint
    p = lint(tmp_path, d)

    # Then: 退出 0，stdout 打印 waves
    assert p.returncode == 0, p.stdout + p.stderr
    assert json.loads(p.stdout) == [["S1"]]


def test_no_tiers_file_lint_unchanged(tmp_path):
    # Given: openspec 根目录下没有 test-tiers.json；计划没有 gate.integration 与 gate.integration_skip
    data = plan(lint="python3 -m compileall -q src")
    d = make(tmp_path, data)

    # When: 运行 slice-gate.py lint，并对同一份计划计算 plan_sha
    p = lint(tmp_path, d)
    got = load_hook("slice-gate").plan_sha(data)

    # Then: lint 退出 0、没有 tiers: 行；plan_sha 等于按旧算法 [test, lint, typecheck, [[id, verify]]] 算出的值
    assert p.returncode == 0, p.stdout + p.stderr
    assert not tier_lines(p), p.stderr
    g = data["gate"]
    key = [g.get("test"), g.get("lint"), g.get("typecheck"), [[s.get("id"), s.get("verify")] for s in data["slices"]]]
    assert got == hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 切片门禁 G12


@XF
def test_gate_flags_test_file_outside_tiers(git_repo):
    # Given: unit.paths 是 tests/unit/**，已选区域 hooks 的 paths 是 tests/integration/hooks/**；
    #        切片 S1 起跑后，区间里新增 tests/integration/hooks/test_ok.py 与 tests/test_stray.py
    data = plan(owns=("tests/**",), integration=["hooks"])
    data["slices"][0]["verify"] = "true"
    d = make(git_repo, data, tiers())
    commit_all(git_repo, "plan")
    s = run_hook("slice-gate", "start", "S1", "--change-dir", str(d), cwd=git_repo)
    assert s.returncode == 0, s.stdout + s.stderr
    write(git_repo / "tests" / "integration" / "hooks" / "test_ok.py", "def test_ok():\n    assert True\n")
    write(git_repo / "tests" / "test_stray.py", "def test_stray():\n    assert True\n")
    commit_all(git_repo, "S1")

    # When: 运行 slice-gate.py gate S1
    p = run_hook("slice-gate", "gate", "S1", "--change-dir", str(d), cwd=git_repo)

    # Then: failed 里有一条以 G12 开头并点名 tests/test_stray.py；没有任何 G12 项点名 tests/integration/hooks/test_ok.py
    out = json.loads(p.stdout)
    g12 = [f for f in out["failed"] if f.startswith("G12")]
    assert any("tests/test_stray.py" in f for f in g12), out
    assert not any("tests/integration/hooks/test_ok.py" in f for f in g12), out
