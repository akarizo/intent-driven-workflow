"""文档：运行器契约的「测试套件合规标准」一节，/test-tiers 命令文档指向体检
（scenario: test-audit#contract-states-compliance-standard、#test-tiers-doc-points-to-audit）。
骨架：strict xfail，断言是真实的；切片 S6 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT
from test_budget_docs import CONTRACT, OLD_HEADS, TIERS_DOC

PENDING = pytest.mark.xfail(strict=True, reason="change test-audit S6 未实现")

TITLE = "测试套件合规标准"
VIOLATIONS = ("no-tiers", "layering", "unit-impure", "unit-slow", "no-case-limit", "region-slow", "total-over",
              "allow-stale", "allow-expired", "allow-unbounded")
ADVICE = ("allow-soon", "allow-unneeded", "pure-in-region", "purity-unchecked", "gwt-missing")
ACTION_NAMES = ("move", "split", "retier", "budget", "drop-allow", "allow", "speedup", "purify", "delete", "keep")


def standard_section(text=None):
    """契约文档里标题含「测试套件合规标准」的二级标题之下、到下一个二级标题之前的正文；没有 → 空串。"""
    lines = (text if text is not None else CONTRACT.read_text(encoding="utf-8")).splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## ") and TITLE in l), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1:end])


@PENDING
def test_contract_states_compliance_standard():
    # Given: 模板仓库的运行器契约文档
    text = CONTRACT.read_text(encoding="utf-8")

    # When: 取标题含「测试套件合规标准」的那一节
    body = standard_section(text)
    heads = [l for l in text.splitlines() if l.startswith("## ")]

    # Then: 八条规则、全部类别与级别、去向与轨道、退出码、与门禁的区别都有明文；原有各节标题都在
    assert body, heads
    for word in ["R%d" % i for i in range(1, 9)]:
        assert word in body, word
    for name in VIOLATIONS + ADVICE + ACTION_NAMES + ("unjudged",):
        assert "`%s`" % name in body, name
    for word in ("不合规", "提示", "未判", "命令内执行", "交人放行", "转 change", "退出码", "老债", "不跑测试"):
        assert word in body, word
    for code in ("`0`", "`1`", "`2`", "`3`"):
        assert code in body, code
    for h in OLD_HEADS:
        assert h in heads, h
    assert any(h.startswith("## 10.") and "时间预算" in h for h in heads), heads


@PENDING
def test_test_tiers_doc_points_to_audit():
    # Given: /test-tiers 的命令文档
    lines = TIERS_DOC.read_text(encoding="utf-8").splitlines()

    # When: 逐行查找同时提到体检子命令与体检命令的那一行
    hit = [l for l in lines if "test-tiers.py audit" in l and "/test-audit" in l]

    # Then: 有这样一行
    assert hit, "test-tiers.md 缺少同时含 test-tiers.py audit 与 /test-audit 的一行"
    assert ROOT.joinpath("template", ".claude", "commands", "test-tiers.md").samefile(TIERS_DOC)
