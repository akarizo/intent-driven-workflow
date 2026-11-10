"""运行器契约文档与规划指引（scenario: flight-runner-contract#contract-doc-shipped-with-template / propose-guidance-forwards-contract；
test-cost-visibility#apply-and-propose-docs-print-forecast）。"""

from conftest import ROOT

CLAUDE = ROOT / "template" / ".claude"
CONTRACT = CLAUDE / "flight-runner-contract.md"
PROPOSE = (CLAUDE / "commands" / "opsx-propose.md", CLAUDE / "skills" / "openspec-propose" / "SKILL.md")
APPLY = (CLAUDE / "commands" / "opsx-apply.md", CLAUDE / "skills" / "openspec-apply-change" / "SKILL.md")


def _read(p):
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_contract_doc_shipped_with_template():
    # Given: 模板仓库
    # When: 读 template/.claude/flight-runner-contract.md
    text = _read(CONTRACT)

    # Then: 含契约变量、结果文件变量、链长字段与四个类别名；写明 FLIGHT_ / GATE_ 前缀须从项目缓存键剔除
    for token in ("FLIGHT_PLUGIN_PATH", "FLIGHT_PYTEST_ARGS", "GATE_TEST_RESULT", "GATE_CHANGE", "anchor_max_hops",
                  "not-pytest", "plugins-dropped", "plugin-import-failed", "incomplete"):
        assert token in text, token
    assert any("FLIGHT_" in l and "GATE_" in l and "缓存键" in l and "剔除" in l for l in text.splitlines()), text[:500]


def test_propose_guidance_forwards_contract():
    # Given: 模板仓库
    # When: 读 opsx-propose.md 与 openspec-propose/SKILL.md
    lines = [{l.strip() for l in _read(p).splitlines() if "FLIGHT_PYTEST_ARGS" in l} for p in PROPOSE]

    # Then: 两处有同一句要求，含两个契约变量与 $GATE_CHANGE，并写明不写死 change 名
    common = lines[0] & lines[1]
    assert any("FLIGHT_PLUGIN_PATH" in l and "$GATE_CHANGE" in l and "不写死" in l for l in common), lines


def test_apply_and_propose_docs_print_forecast():
    # Given: 模板仓库
    # When: 读 opsx-apply.md、opsx-propose.md 与两者的同名 skill
    texts = {p.name + ":" + p.parent.name: _read(p) for p in PROPOSE + APPLY}

    # Then: 四处都含 flight-doctor.py forecast，且都写明「只预告，不阻断」
    for name, text in texts.items():
        assert "flight-doctor.py forecast" in text, name
        assert "只预告，不阻断" in text, name
