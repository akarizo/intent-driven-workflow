"""文档描述分层文件按条目判定与选测范围契约（scenario: tier-file-incremental#docs-describe-tier-file-narrowing、
gate-scope-report#docs-describe-scope-contract）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""

from conftest import ROOT


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def _line_with(text, word):
    """第一行含 word 的行；没有 → 空串。"""
    return next((l for l in text.splitlines() if word in l), "")


def test_docs_describe_tier_file_narrowing():
    # Given: 本 change 的文档改动已完成
    tiers = read("template/.claude/commands/test-tiers.md")
    verify = {rel: read(rel) for rel in ("template/.claude/commands/opsx-verify.md",
                                         "template/.claude/skills/openspec-verify-change/SKILL.md")}
    readme = read("README.md")

    # When: 取「放行慢单测」一节、各「自动全量」/「何时全量」行
    section = tiers.split("## 放行慢单测", 1)[1].split("\n## ", 1)[0]

    # Then: 放行一节含「不退回全量」；verify 命令与同名 skill 含「单元层指纹」且自动全量一行不列 test-tiers.json；
    #       README 的何时全量一行不列 test-tiers.json
    assert "不退回全量" in section, section
    for rel, text in verify.items():
        assert "单元层指纹" in text, rel
        line = _line_with(text, "**自动全量**")
        assert line and "test-tiers.json" not in line, (rel, line)
    line = _line_with(readme, "**何时全量**")
    assert line and "test-tiers.json" not in line, line


def test_docs_describe_scope_contract():
    # Given: 本 change 的文档改动已完成
    texts = {rel: read(rel) for rel in ("template/openspec/schemas/intent-driven/schema.yaml",
                                        "template/.claude/commands/opsx-propose.md",
                                        "template/.claude/skills/openspec-propose/SKILL.md")}

    # When: 检查 schema、/opsx-propose 命令与同名 skill、README

    # Then: 三份都含 gate.scope、gate-scope.json、GATE_SCOPE_OUT、gate.scope_full_reason；README 含 gate.scope
    for rel, text in texts.items():
        for word in ("gate.scope", "gate-scope.json", "GATE_SCOPE_OUT", "gate.scope_full_reason"):
            assert word in text, (rel, word)
    assert "gate.scope" in read("README.md")
