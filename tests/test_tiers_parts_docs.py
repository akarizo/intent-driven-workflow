"""文档写明分层文件的部件形态与两种契约（scenario: test-tiers-polyglot#docs-describe-parts）。
切片 S5 已解锁。"""
from conftest import ROOT


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_docs_describe_parts():
    # Given: 本 change 的文档改动已完成
    cmd = read("template/.claude/commands/test-tiers.md")
    driver_docs = [read("template/openspec/schemas/intent-driven/schema.yaml"),
                   read("template/.claude/commands/opsx-propose.md"),
                   read("template/.claude/skills/openspec-propose/SKILL.md")]

    # When: 检查各文档

    # Then: /test-tiers 命令写明部件形态、两种契约、金丝雀与未覆盖清单；schema 与 propose 命令 / skill 写驱动命令；
    #       README 提到部件与 canary；CLAUDE.md.snippet 提到 parts
    for word in ("parts", "root", "test_files", "list", "FLIGHT_JUNIT", "FLIGHT_UNIT_CMD", "FLIGHT_CANARY_TOKEN",
                 "canary", "run unit", "金丝雀", "未覆盖"):
        assert word in cmd, word
    for text in driver_docs:
        assert "test-tiers.py run unit" in text
    readme = read("README.md")
    assert "部件" in readme and "canary" in readme
    assert "parts" in read("template/CLAUDE.md.snippet")
