"""文档描述增量 final；/pr-ship 评审自动修复不询问
（scenario: incremental-final#docs-describe-incremental-final、pr-ship-review-autofix#pr-ship-autofixes-without-asking）。"""
import pathlib

import pytest

XF = pytest.mark.xfail(strict=True, reason="S4 尚未实现")
ROOT = pathlib.Path(__file__).resolve().parents[1]
T = ROOT / "template"


def read(path):
    return path.read_text(encoding="utf-8")


@XF
def test_docs_describe_incremental_final():
    # Given: 本 change 合入后的模板文档
    verify = [read(T / ".claude/commands/opsx-verify.md"), read(T / ".claude/skills/openspec-verify-change/SKILL.md")]
    apply_ = [read(T / ".claude/commands/opsx-apply.md"), read(T / ".claude/skills/openspec-apply-change/SKILL.md")]
    schema = read(T / "openspec/schemas/intent-driven/schema.yaml")
    readme = read(ROOT / "README.md")

    # When: 取 schema 的 tasks instruction 段
    tasks = schema[schema.index("- id: tasks"):schema.index("apply:")]

    # Then: verify 命令与 skill 都写明增量、--full 与同树沿用；apply 命令与 skill 都写明同树；
    #       tasks instruction 含 gate.impacted；README 含「增量 final」与「锚点」
    for text in verify:
        assert "增量" in text and "--full" in text and "同树沿用" in text
    for text in apply_:
        assert "同树" in text
    assert "gate.impacted" in tasks
    assert "增量 final" in readme and "锚点" in readme


@XF
def test_pr_ship_autofixes_without_asking():
    # Given: 本 change 合入后的 template/.claude/commands/pr-ship.md
    text = read(T / ".claude/commands/pr-ship.md")

    # When: 取自动修复一步与 Guardrails 段
    step = text[text.index("10. "):text.index("11. ")]
    guard = text[text.index("**Guardrails**"):]

    # Then: 全文无 AskUserQuestion 与「只贴评论交人」；自动修复一步写明直接修复并 push、不询问，保留至多 2 轮与停下交人；
    #       Guardrails 写明全程不问询
    assert "AskUserQuestion" not in text
    assert "只贴评论交人" not in text
    assert "不询问" in step and "push" in step
    assert "至多 2 轮" in step and "停下交人" in step
    assert "全程不问询" in guard
