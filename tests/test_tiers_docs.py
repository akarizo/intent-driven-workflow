"""文档写明测试分层规则与 /test-tiers 命令（scenario: test-tiers#docs-describe-test-tiers）。
骨架：strict xfail，断言是真实的；切片 S4 完成文档后去掉标记即解锁。"""
import pytest

from conftest import ROOT

XF = pytest.mark.xfail(strict=True, reason="S4 尚未实现")


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


@XF
def test_docs_describe_test_tiers():
    # Given: 本 change 的文档改动已完成
    cmd = read("template/.claude/commands/test-tiers.md")
    schema = read("template/openspec/schemas/intent-driven/schema.yaml")
    propose = [read("template/.claude/commands/opsx-propose.md"), read("template/.claude/skills/openspec-propose/SKILL.md")]
    verify = [read("template/.claude/commands/opsx-verify.md"), read("template/.claude/skills/openspec-verify-change/SKILL.md")]

    # When: 检查各文件

    # Then: 命令文档含四个子命令、/opsx-mini 与门禁分层耗时 tier_sec；schema 含 gate.integration、gate.integration_skip、unit.cmd；
    #       propose 命令与同名 skill 都含「先定层」；verify 命令与同名 skill 都含 G10 与 G11；
    #       TDD skill 含「先定层」与「3 秒」；slice-executor 含 G12；README 含 /test-tiers 与「16 个 slash 命令」；
    #       install.sh 含「16 个 slash command」；CLAUDE.md.snippet 含 test-tiers.json
    for word in ("test-tiers.py probe", "render", "check", "allow-slow", "/opsx-mini", "tier_sec"):
        assert word in cmd, word
    for word in ("gate.integration", "gate.integration_skip", "unit.cmd"):
        assert word in schema, word
    for text in propose:
        assert "先定层" in text
    for text in verify:
        assert "G10" in text and "G11" in text
    tdd = read("template/.claude/skills/test-driven-development/SKILL.md")
    assert "先定层" in tdd and "3 秒" in tdd
    assert "G12" in read("template/.claude/agents/slice-executor.md")
    readme = read("README.md")
    assert "/test-tiers" in readme and "16 个 slash 命令" in readme
    assert "16 个 slash command" in read("install.sh")
    assert "test-tiers.json" in read("template/CLAUDE.md.snippet")
