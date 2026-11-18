"""propose 文档写明 baseline 不改计划文件；契约 / README / schema / propose 写明未测须表态
（scenario: plan-hygiene#propose-docs-say-baseline-leaves-plan-alone、runner-statement#docs-describe-runner-statement，共 2 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S4 改完文档后去掉标记即解锁。"""
import re

from conftest import ROOT

CLAUDE = ROOT / "template" / ".claude"
PROPOSE = (CLAUDE / "commands" / "opsx-propose.md", CLAUDE / "skills" / "openspec-propose" / "SKILL.md")
CONTRACT = CLAUDE / "flight-runner-contract.md"
README = ROOT / "README.md"
SCHEMA = ROOT / "template" / "openspec" / "schemas" / "intent-driven" / "schema.yaml"
TRIGGER = "runner:deps-unmeasured"


def _read(p):
    return p.read_text(encoding="utf-8")


def _common_lines(*words):
    """两份 propose 文档里逐字相同、且同时含全部 words 的行。"""
    sets = [{l.strip() for l in _read(p).splitlines() if all(w in l for w in words)} for p in PROPOSE]
    return sets[0] & sets[1]


def _tasks_instruction(text):
    """schema.yaml 里 tasks 工件的 instruction 段（到下一个工件或文件末尾）。"""
    at = text.index("- id: tasks")
    nxt = re.search(r"\n  - id: ", text[at + 1:])
    return text[at:at + 1 + nxt.start()] if nxt else text[at:]


def test_propose_docs_say_baseline_leaves_plan_alone():
    # Given: template/.claude/commands/opsx-propose.md 与 template/.claude/skills/openspec-propose/SKILL.md
    texts = [_read(p) for p in PROPOSE]

    # When: 读两份文档全文，并取两处逐字相同的行
    kept = _common_lines("gate-baseline.json", "耗时", "不改", "计划文件")
    gitlink = _common_lines("gitlink", "同一次提交")

    # Then: 两处都不再说耗时写回 slices.json；有同一行写明耗时记在 gate-baseline.json、不改计划文件；
    #       有同一行写明子仓 gitlink 与工件同一次提交
    for text in texts:
        assert "full_suite_sec" not in text
        assert "`slices.json` 的耗时" not in text
    assert kept, [p.name for p in PROPOSE]
    assert gitlink, [p.name for p in PROPOSE]


def test_docs_describe_runner_statement():
    # Given: 运行器契约文档、README.md、schema.yaml 与 propose 的两份文档
    contract, readme, schema = _read(CONTRACT), _read(README), _read(SCHEMA)

    # When: 读其中关于依赖图未测的段落
    tasks = _tasks_instruction(schema)
    relint = _common_lines("slice-gate.py lint", TRIGGER)

    # Then: 契约文档含触发项、gate.scope_full_reason 与 gate.impacted；README 有一行同时含触发项与「理由」；
    #       schema 的 tasks instruction 含触发项；propose 两处有同一行要求 baseline 报告后重跑 lint 并提到触发项
    for token in (TRIGGER, "gate.scope_full_reason", "gate.impacted"):
        assert token in contract, token
    assert any(TRIGGER in l and "理由" in l for l in readme.splitlines()), "README"
    assert TRIGGER in tasks
    assert relint, [p.name for p in PROPOSE]
