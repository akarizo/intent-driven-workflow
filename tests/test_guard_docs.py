"""运行器契约与 propose 文档说明全局守护、wave 集成检查与 owns 分档（scenario: slice-guards#contract-describes-guards-and-wave-check、
#propose-docs-describe-guards-and-owns-tiers，共 2 条）。
骨架：strict xfail，断言是真实的；切片 S6 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="change wave-integration-guard S6 未实现")

CONTRACT = ROOT / "template" / ".claude" / "flight-runner-contract.md"
PROPOSE_DOCS = (ROOT / "template" / ".claude" / "commands" / "opsx-propose.md",
                ROOT / "template" / ".claude" / "skills" / "openspec-propose" / "SKILL.md",
                ROOT / "template" / "openspec" / "schemas" / "intent-driven" / "schema.yaml")
OLD_HEADINGS = ("## 1. 包装脚本要转发的两个变量", "## 2. `GATE_PHASE` / `GATE_CHANGE`", "## 3. 检查可读的 `GATE_TEST_RESULT`",
                "## 4. 易变变量与项目缓存键", "## 5. 依赖图未测的四类原因与修法", "## 6. `gate-scope.json` 的可选字段",
                "## 7. 接入步骤", "## 8. 全机测试锁", "## 9. 测试账本")


@PENDING
def test_contract_describes_guards_and_wave_check():
    # Given: template/.claude/flight-runner-contract.md
    text = CONTRACT.read_text(encoding="utf-8")
    heads = [l for l in text.splitlines() if l.startswith("## ")]

    # When: 取出标题含「全局守护」的那一节

    # Then: 该节写明 slice 字段、GATE_PHASE 的两个新取值、并行与只读、日志名、G15 / G16 与预算字段；原有九节的标题都还在
    title = next(h for h in heads if "全局守护" in h)
    section = text.split(title, 1)[1].split("\n## ", 1)[0]
    for word in ("`slice`", "GATE_PHASE", "`wave`", "并行", "只读", ".gate-slice-", "G15", "G16", "wave_test_budget_sec"):
        assert word in section, word
    for h in OLD_HEADINGS:
        assert h in heads, h


@PENDING
def test_propose_docs_describe_guards_and_owns_tiers():
    # Given: opsx-propose.md、同名 skill 与 schema.yaml
    texts = {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8") for p in PROPOSE_DOCS}

    # When: 阅读这三份文档

    # Then: 每一份都提到全局守护、owns_wide、预算字段，并写明 owns 条数上限按轮次档（标准档 12、大片档 30）
    for name, text in texts.items():
        for word in ("全局守护", "owns_wide", "wave_test_budget_sec", "大片档 30"):
            assert word in text, (name, word)
        assert "每片 owns ≤ 12 条" not in text, name
