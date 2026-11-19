"""propose 改用工具链、补断言用 fork 并配串行回退、规划期派发只允许 fork、未补完的骨架过不了 lint
（scenario: propose-fork-assertions#propose-docs-use-plan-kit-in-order、#propose-docs-fork-with-serial-fallback、
#planning-dispatch-allows-only-fork、#lint-rejects-unfilled-scaffold，共 4 条）。
骨架：strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import json
import re

import pytest

from conftest import ROOT, load_hook, run_hook, write

CMD = ROOT / "template" / ".claude" / "commands"
SKILLS = ROOT / "template" / ".claude" / "skills"
DOCS = [CMD / "opsx-propose.md", SKILLS / "openspec-propose" / "SKILL.md"]
ORDER = ["slice-gate.py warm", "plan-kit.py instructions", "plan-kit.py packets", "plan-scaffold.py scaffold",
         "plan-scaffold.py gwt", "plan-kit.py tasks", "slice-gate.py lint --change-dir", "model-routing.py pin"]
PLANNING_SKILLS = ("openspec-explore", "openspec-new-change", "openspec-continue-change", "openspec-propose")


def read(p):
    return p.read_text(encoding="utf-8")


@pytest.mark.xfail(strict=True, reason="S4 未实现")
def test_propose_docs_use_plan_kit_in_order():
    # Given: 两份 propose 文档
    for doc in DOCS:
        t = read(doc)

        # When: 依次找 8 处工具调用的首次出现位置
        pos = [t.find(k) for k in ORDER]

        # Then: 都存在且按顺序出现
        assert all(p >= 0 for p in pos), (doc.name, dict(zip(ORDER, pos)))
        assert pos == sorted(pos), (doc.name, dict(zip(ORDER, pos)))


@pytest.mark.xfail(strict=True, reason="S4 未实现")
def test_propose_docs_fork_with_serial_fallback():
    # Given: 两份 propose 文档
    for doc in DOCS:
        t = read(doc)

        # When: 取 scaffold 与 gwt 之间的补断言段
        seg = t[t.index("plan-scaffold.py scaffold"):t.index("plan-scaffold.py gwt")]

        # Then: 写明按测试文件分组、fork 派发、串行回退，并点名占位标记
        assert "测试文件" in seg and 'subagent_type: "fork"' in seg, (doc.name, seg)
        assert "串行" in seg and "PLAN-SCAFFOLD-PLACEHOLDER" in seg, (doc.name, seg)


@pytest.mark.xfail(strict=True, reason="S4 未实现")
def test_planning_dispatch_allows_only_fork():
    # Given: 由 model-routing.py 规划期组名得出的规划类命令与 skill
    groups = sorted(load_hook("model-routing").PLANNING_GROUPS)
    files = [CMD / ("opsx-%s.md" % g) for g in groups] + [SKILLS / s / "SKILL.md" for s in PLANNING_SKILLS]

    # When: 找出每个 subagent_type 的取值
    values = {f.name if f.parent == CMD else f.parent.name: re.findall(r'subagent_type:\s*"?([\w-]+)', read(f)) for f in files}

    # Then: 全是 fork，propose 里至少一次；没有 model: "
    assert all(v == "fork" for vs in values.values() for v in vs), values
    assert values["opsx-propose.md"] and values["openspec-propose"], values
    assert all('model: "' not in read(f) for f in files)


@pytest.mark.xfail(strict=True, reason="S4 未实现")
def test_lint_rejects_unfilled_scaffold(git_repo):
    # Given: 计划的 scenario 由 plan-scaffold.py 生成骨架，尚未补断言
    d = git_repo / "openspec" / "changes" / "c"
    write(d / "specs" / "cap" / "spec.md", "## ADDED Requirements\n\n### Requirement: r\n系统 SHALL 工作。\n\n"
          "#### Scenario: works\n- **GIVEN** a\n- **WHEN** b\n- **THEN** c\n")
    write(d / "slices.json", json.dumps({
        "gate": {"test": "python3 -m pytest -q tests"},
        "slices": [{"id": "S1", "title": "t", "owns": ["src/a.py", "tests/test_cap.py"], "deps": [],
                    "verify": "python3 -m pytest -q tests/test_cap.py", "scenarios": ["cap#works"], "packet": "slices/S1.md"}],
        "scenario_tests": {"cap#works": "tests/test_cap.py::test_works"}}, ensure_ascii=False))
    assert run_hook("plan-scaffold", "scaffold", "--change-dir", str(d), cwd=git_repo).returncode == 0

    # When: 运行 lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: 非 0，有以 skeleton: 开头、点名该函数的一条；补上真实断言后这一条消失
    assert p.returncode != 0, p.stdout
    assert any(ln.lstrip("- ").startswith("skeleton:") and "tests/test_cap.py::test_works" in ln
               for ln in p.stderr.splitlines()), p.stderr
    f = git_repo / "tests" / "test_cap.py"
    write(f, re.sub(r'assert False, "PLAN-SCAFFOLD-PLACEHOLDER[^"]*"', "assert 1 + 1 == 2", read(f)))
    p2 = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)
    assert "skeleton:" not in p2.stderr, p2.stderr
    assert load_hook("plan-scaffold").PLACEHOLDER == load_hook("slice-gate").SCAFFOLD_PLACEHOLDER == "PLAN-SCAFFOLD-PLACEHOLDER"
