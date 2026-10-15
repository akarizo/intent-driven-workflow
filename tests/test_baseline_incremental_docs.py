"""propose 命令与同名 skill、README 写明增量基线（scenario: baseline-incremental-reuse#propose-docs-describe-incremental）。
骨架：strict xfail，断言是真实的；切片 S4 改完文档后去掉标记即解锁。"""
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CMD = ROOT / "template" / ".claude" / "commands" / "opsx-propose.md"
SKILL = ROOT / "template" / ".claude" / "skills" / "openspec-propose" / "SKILL.md"
README = ROOT / "README.md"


def _baseline_step(text):
    """从 slice-gate.py baseline 首次出现处到下一个步骤标题之间的正文。"""
    at = text.index("slice-gate.py baseline")
    nxt = re.search(r"\n\d+(?:\.\d+)?\.? \*\*", text[at:])
    return text[at:at + nxt.start()] if nxt else text[at:]


def _has_line(text, *words):
    return any(all(w in line for w in words) for line in text.splitlines())


def test_propose_docs_describe_incremental():
    # Given: template/.claude/commands/opsx-propose.md、template/.claude/skills/openspec-propose/SKILL.md 与 README.md
    cmd = CMD.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    # When: 取两份命令文档的基线步骤段，并读取 README 全文
    steps = {"opsx-propose.md": _baseline_step(cmd), "openspec-propose/SKILL.md": _baseline_step(skill)}

    # Then: 两段都含 --full 与「增量：复用」；各有一行同时含「改完计划」与 baseline、test_*.py 与「预存红」、「跨 change」与「全绿」、
    #       「推导」与 verify、「沿用」与 lint；README 有一行同时含「基线」与「增量」
    for name, s in steps.items():
        assert "--full" in s and "增量：复用" in s, name
        assert _has_line(s, "改完计划", "baseline"), name
        assert _has_line(s, "test_*.py", "预存红"), name
        assert _has_line(s, "跨 change", "全绿"), name
        assert _has_line(s, "推导", "verify"), name
        assert _has_line(s, "沿用", "lint"), name
    assert _has_line(readme, "基线", "增量")
