"""grill-me 的术语表一节、README 与 schema 引用术语表（scenario: domain-glossary#grill-me-challenges-against-glossary、
#grill-me-writes-resolved-term-except-on-main、#schema-proposal-and-specs-use-glossary，共 3 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="change grill-glossary S2 未实现")
SKILL = ROOT / "template" / ".claude" / "skills" / "grill-me" / "SKILL.md"
SCHEMA = ROOT / "template" / "openspec" / "schemas" / "intent-driven" / "schema.yaml"


def read(path):
    return path.read_text(encoding="utf-8")


def glossary_part(text):
    return text[text.index("## 术语表"):]


@PENDING
def test_grill_me_challenges_against_glossary():
    # Given: grill-me 的 SKILL.md 与 README.md
    skill = read(SKILL)
    readme = read(ROOT / "README.md")

    # When: 切出 SKILL.md 的「## 术语表」一节，找出 README 里 grill-me 那一行
    part = glossary_part(skill)
    row = next(line for line in readme.splitlines() if line.startswith("| `grill-me` |"))

    # Then: 该节写明先读 openspec/glossary.md、不存在时等第一个术语定下再建；用词冲突 / 用了避用词时当场指出，
    #       含糊时提出规范词；原有的一次一问与能查代码就不问两句仍在；README 那一行提到 openspec/glossary.md
    assert "openspec/glossary.md" in part and "不存在" in part
    assert "冲突" in part and "避用词" in part and "含糊" in part and "规范词" in part
    assert "Ask the questions one at a time." in skill
    assert "If a question can be answered by exploring the codebase, explore the codebase instead." in skill
    assert "openspec/glossary.md" in row


@PENDING
def test_grill_me_writes_resolved_term_except_on_main():
    # Given: grill-me 的 SKILL.md
    skill = read(SKILL)

    # When: 切出「## 术语表」一节
    part = glossary_part(skill)

    # Then: 写明用户回答后当场写入；默认分支（如 main）上不写文件、访谈末尾列出待写词条；
    #       词条格式 `**规范词**：定义` 与 `避用：`；只收本项目特有的概念、不写实现细节
    assert "当场写入" in part
    assert "默认分支" in part and "main" in part and "待写词条" in part
    assert "`**规范词**：定义`" in part and "`避用：`" in part
    assert "本项目特有" in part and "实现细节" in part


@PENDING
def test_schema_proposal_and_specs_use_glossary():
    # Given: intent-driven schema.yaml
    schema = read(SCHEMA)

    # When: 切出 proposal、specs 两个工件的段，以及 design 起的其余部分
    proposal = schema[schema.index("- id: proposal"):schema.index("- id: specs")]
    specs = schema[schema.index("- id: specs"):schema.index("- id: design")]
    rest = schema[schema.index("- id: design"):]

    # Then: proposal 与 specs 都提到 openspec/glossary.md 与「避用」；design / adr / tasks 不提 glossary
    for part in (proposal, specs):
        assert "openspec/glossary.md" in part and "避用" in part
    assert "glossary" not in rest
