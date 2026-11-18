"""随模板下发的全机测试锁说明
（scenario: machine-test-lock#contract-documents-machine-test-lock、#commands-and-skills-mention-queueing）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S6 实现后去掉标记即解锁。"""
from conftest import ROOT

CLAUDE = ROOT / "template" / ".claude"
CONTRACT = CLAUDE / "flight-runner-contract.md"
DOCS = {
    "opsx-apply.md": CLAUDE / "commands" / "opsx-apply.md",
    "opsx-propose.md": CLAUDE / "commands" / "opsx-propose.md",
    "openspec-apply-change/SKILL.md": CLAUDE / "skills" / "openspec-apply-change" / "SKILL.md",
    "openspec-propose/SKILL.md": CLAUDE / "skills" / "openspec-propose" / "SKILL.md",
    "test-tiers.md": CLAUDE / "commands" / "test-tiers.md",
    "README.md": ROOT / "README.md",
}


def read(path):
    return path.read_text(encoding="utf-8")


def test_contract_documents_machine_test_lock():
    # Given: 运行器契约文档
    text = read(CONTRACT)
    heads = [l for l in text.splitlines() if l.startswith("## ")]

    # When: 切出标题含「全机测试锁」的一节
    head = next(h for h in heads if "全机测试锁" in h)
    sec = text[text.index(head):]
    nxt = sec.find("\n## ", 1)
    sec = sec if nxt < 0 else sec[:nxt]

    # Then: 该节提到四个环境变量与 flight-lock.py run，写明独占与共享、CI、降为警告；原有第 1–7 节标题都还在
    for token in ("FLIGHT_LOCK=off", "FLIGHT_LOCK_DIR", "FLIGHT_LOCK_MAX_HOLD_SEC", "FLIGHT_LOCK_HELD",
                  "flight-lock.py run", "独占", "共享", "CI", "降为警告"):
        assert token in sec, token
    for n in range(1, 8):
        assert any(h.startswith("## %d. " % n) for h in heads), n


def test_commands_and_skills_mention_queueing():
    # Given: opsx-apply / opsx-propose 的命令与同名 skill、test-tiers.md、README.md
    texts = {name: read(path) for name, path in DOCS.items()}

    # When: 逐个找含「全机测试锁」的行
    hits = {name: [l for l in text.splitlines() if "全机测试锁" in l] for name, text in texts.items()}

    # Then: 六个文件都有这样的行且其中有一行含「排队」；都提到 flight-lock.py 或 flight-runner-contract.md
    for name, text in texts.items():
        assert hits[name], name
        assert any("排队" in l for l in hits[name]), name
        assert "flight-lock.py" in text or "flight-runner-contract.md" in text, name
