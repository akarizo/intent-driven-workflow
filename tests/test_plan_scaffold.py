"""plan-scaffold.py：scenario 骨架生成与规划期 GWT / 占位自查
（scenario: scenario-scaffold#scaffold-creates-strict-xfail-skeletons、#scaffold-leaves-existing-functions、
#scaffold-skips-non-python、#gwt-reports-missing-steps-and-placeholders，共 4 条）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import ast
import json

import pytest

from conftest import run_hook, write

MARK = "PLAN-SCAFFOLD-PLACEHOLDER"
SPEC = ("## ADDED Requirements\n\n### Requirement: 退款\n订单 SHALL 能退款。\n\n"
        "#### Scenario: refund-paid-order\n- **GIVEN** 已有订单\n- **AND** 订单已付款\n"
        "- **WHEN** 用户申请退款\n- **THEN** 订单变为退款中\n\n"
        "#### Scenario: keep-beta\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n\n"
        "#### Scenario: add-gamma\n- **GIVEN** x\n- **WHEN** y\n- **THEN** z\n\n"
        "#### Scenario: js-render\n- **GIVEN** p\n- **WHEN** q\n- **THEN** r\n")


def repo(tmp_path, tests):
    """建 <tmp>/openspec/changes/c：单片 S1，scenario_tests = tests（{scenario 名: path::func}）。返回 (根, change 目录)。"""
    d = tmp_path / "openspec" / "changes" / "c"
    write(d / "specs" / "refund" / "spec.md", SPEC)
    write(d / "slices.json", json.dumps({
        "gate": {"test": "pytest -q"},
        "slices": [{"id": "S1", "title": "退款", "owns": ["src/r.py"], "deps": [], "verify": "pytest -q",
                    "scenarios": ["refund#%s" % k for k in tests], "packet": "slices/S1.md"}],
        "scenario_tests": {"refund#%s" % k: v for k, v in tests.items()}}, ensure_ascii=False))
    return tmp_path, d


def scaffold(root, d):
    return run_hook("plan-scaffold", "scaffold", "--change-dir", str(d), cwd=root)


def func_src(text, name):
    tree = ast.parse(text)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node), node


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_scaffold_creates_strict_xfail_skeletons(tmp_path):
    # Given: scenario refund-paid-order 映射到尚不存在的 tests/test_new.py::test_alpha
    root, d = repo(tmp_path, {"refund-paid-order": "tests/test_new.py::test_alpha"})

    # When: 运行 scaffold
    p = scaffold(root, d)

    # Then: 文件含 import pytest 与 strict xfail 的 test_alpha；GWT 取原文（AND 并入 Given 行）；含占位标记；created 正确
    assert p.returncode == 0, p.stderr
    text = (root / "tests" / "test_new.py").read_text(encoding="utf-8")
    assert "import pytest" in text
    src, node = func_src(text, "test_alpha")
    deco = ast.unparse(node.decorator_list[0]) if hasattr(ast, "unparse") else text
    assert "xfail" in deco and "strict=True" in deco, deco
    lines = {k: next(ln for ln in src.splitlines() if ln.strip().startswith("# %s:" % k)) for k in ("Given", "When", "Then")}
    assert "已有订单" in lines["Given"] and "订单已付款" in lines["Given"], lines
    assert "用户申请退款" in lines["When"] and "订单变为退款中" in lines["Then"], lines
    assert MARK in src
    assert json.loads(p.stdout)["created"] == ["tests/test_new.py::test_alpha"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_scaffold_leaves_existing_functions(tmp_path):
    # Given: tests/test_old.py 已有写好断言的 test_beta；同时映射尚不存在的 test_gamma
    root, d = repo(tmp_path, {"keep-beta": "tests/test_old.py::test_beta", "add-gamma": "tests/test_old.py::test_gamma"})
    beta = "def test_beta():\n    # Given: a\n    # When: b\n    # Then: c\n    assert 1 + 1 == 2\n"
    write(root / "tests" / "test_old.py", "import pytest\n\n\n" + beta)

    # When: 运行 scaffold
    p = scaffold(root, d)

    # Then: test_beta 逐字不变；末尾多出 test_gamma；existing / created 正确
    assert p.returncode == 0, p.stderr
    text = (root / "tests" / "test_old.py").read_text(encoding="utf-8")
    assert func_src(text, "test_beta")[0] == beta.rstrip("\n")
    assert text.rstrip().endswith(func_src(text, "test_gamma")[0].rstrip())
    out = json.loads(p.stdout)
    assert "tests/test_old.py::test_beta" in out["existing"] and "tests/test_old.py::test_gamma" in out["created"], out


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_scaffold_skips_non_python(tmp_path):
    # Given: 一个 scenario 映射到 web/a.test.js::renders
    root, d = repo(tmp_path, {"js-render": "web/a.test.js::renders"})

    # When: 运行 scaffold
    p = scaffold(root, d)

    # Then: 退出 0；skipped 含该项；文件未被创建
    assert p.returncode == 0, p.stderr
    assert "web/a.test.js::renders" in json.loads(p.stdout)["skipped"]
    assert not (root / "web" / "a.test.js").exists()


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_gwt_reports_missing_steps_and_placeholders(tmp_path):
    # Given: test_beta 缺 When 注释；test_gamma 仍含占位标记
    root, d = repo(tmp_path, {"keep-beta": "tests/test_g.py::test_beta", "add-gamma": "tests/test_g.py::test_gamma"})
    bad = ("def test_beta():\n    # Given: a\n    # Then: c\n    assert True\n\n\n"
           "def test_gamma():\n    # Given: x\n    # When: y\n    # Then: z\n    assert False, \"%s：换成真实断言\"\n" % MARK)
    write(root / "tests" / "test_g.py", bad)

    # When: 运行 gwt
    p = run_hook("plan-scaffold", "gwt", "--change-dir", str(d), cwd=root)

    # Then: exit 1，分别点名两个函数；修好后退出 0
    assert p.returncode == 1, (p.returncode, p.stdout, p.stderr)
    out = p.stdout + p.stderr
    assert "test_beta" in out and "test_gamma" in out, out
    good = ("def test_beta():\n    # Given: a\n    # When: b\n    # Then: c\n    assert True\n\n\n"
            "def test_gamma():\n    # Given: x\n    # When: y\n    # Then: z\n    assert 2 > 1\n")
    write(root / "tests" / "test_g.py", good)
    p2 = run_hook("plan-scaffold", "gwt", "--change-dir", str(d), cwd=root)
    assert p2.returncode == 0, (p2.stdout, p2.stderr)
