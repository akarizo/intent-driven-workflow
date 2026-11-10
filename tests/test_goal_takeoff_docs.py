"""propose 收尾 / apply 自检 / 铁律文本写明会话 /goal（scenario: goal-takeoff-authorization#propose-continues-under-goal、
#apply-and-iron-rule-name-goal，共 2 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
from conftest import ROOT

CLAUDE = ROOT / "template" / ".claude"


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, start, end):
    return text[text.index(start):text.index(end)]


def rule7(text):
    return next(line for line in text.splitlines() if line.startswith("7. "))


def test_propose_continues_under_goal():
    # Given: /opsx-propose 命令与同名 skill
    docs = [read(CLAUDE / "commands" / "opsx-propose.md"), read(CLAUDE / "skills" / "openspec-propose" / "SKILL.md")]

    # When: 切出 step 6「收尾」（到 **Output** 为止）
    steps = [section(t, "6. **收尾**", "**Output**") for t in docs]

    # Then: 都先跑 takeoff-gate.py --change-dir，证据为 /goal 时不硬交接、等 baseline 后单独 commit 工件再按 /opsx-apply 起飞；
    #       原硬交接措辞仍在
    for t, step in zip(docs, steps):
        assert "takeoff-gate.py --change-dir" in step and "/goal" in step
        assert "不硬交接" in step and "单独 commit" in step and "baseline" in step and "/opsx-apply" in step
        assert ("本命令到此结束" in step or "本 skill 到此结束" in step) and "绝对路径" in step
        assert "即视为批准" not in t


def test_apply_and_iron_rule_name_goal():
    # Given: apply 命令与同名 skill、根 CLAUDE.md 与模板 snippet、README 与 WORKFLOW_zh
    applies = [read(CLAUDE / "commands" / "opsx-apply.md"), read(CLAUDE / "skills" / "openspec-apply-change" / "SKILL.md")]
    root_rule = rule7(read(ROOT / "CLAUDE.md"))
    snippet_rule = rule7(read(ROOT / "template" / "CLAUDE.md.snippet"))
    guides = [read(ROOT / "README.md"), read(ROOT / "docs" / "WORKFLOW_zh.md")]

    # When: 切出两处 step 0「批准自检」
    step0s = [section(t, "0. **批准自检", "1. **选 change**") for t in applies]

    # Then: step 0 写明证据可来自会话 /goal；两处铁律 7 都写 /goal，根铁律保留新鲜度并写明 goal 豁免；说明文档提到 /goal
    for step in step0s:
        assert "/goal" in step and "takeoff-gate.py --change-dir" in step
        assert "AskUserQuestion" not in step
    assert "/goal" in root_rule and "新鲜度" in root_rule and "豁免" in root_rule
    assert "/goal" in snippet_rule
    for doc in guides:
        assert "/goal" in doc
