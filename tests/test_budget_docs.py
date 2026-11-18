"""文档：运行器契约第 10 节「时间预算与放行」、test-tiers 命令文档与 README 的新字段
（scenario: tier-budgets#docs-describe-budgets-and-allow-fields）。
骨架：strict xfail，断言是真实的；切片 S6 实现后去掉标记即解锁。"""
from conftest import ROOT

CONTRACT = ROOT / "template" / ".claude" / "flight-runner-contract.md"
TIERS_DOC = ROOT / "template" / ".claude" / "commands" / "test-tiers.md"
README = ROOT / "README.md"
OLD_HEADS = ("## 1. 包装脚本要转发的两个变量", "## 2. `GATE_PHASE` / `GATE_CHANGE`", "## 3. 检查可读的 `GATE_TEST_RESULT`",
             "## 4. 易变变量与项目缓存键", "## 5. 依赖图未测的四类原因与修法", "## 6. `gate-scope.json` 的可选字段",
             "## 7. 接入步骤", "## 8. 全机测试锁", "## 9. 测试账本")


def body(text, prefix):
    """以 prefix 开头的那个二级标题之下、到下一个二级标题之前的正文。"""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(prefix)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1:end])


def test_docs_describe_budgets_and_allow_fields():
    # Given: 模板仓库的文档
    contract = CONTRACT.read_text(encoding="utf-8")
    tiers_doc = TIERS_DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")

    # When: 取契约文档的二级标题、第 10 节与第 8 节正文
    heads = [l for l in contract.splitlines() if l.startswith("## ")]
    ten, eight = body(contract, "## 10."), body(contract, "## 8.")

    # Then: 第 10 节讲时间预算与放行；原有 1–9 节标题都在；第 8 节把三种时间判定并列；另两处文档写出新字段
    assert any(h.startswith("## 10.") and "时间预算" in h for h in heads), heads
    for h in OLD_HEADS:
        assert h in heads, h
    for word in ("case_sec", "total_sec", "limit_sec", "expires", "G13", "G14", "老债", "预算变更"):
        assert word in ten, word
    assert any("G10" in l and "G13" in l and "G14" in l for l in eight.splitlines()), eight
    for word in ('"budget"', "--limit-sec", "--expires"):
        assert word in tiers_doc, word
    assert any("budget" in l and "limit_sec" in l for l in readme.splitlines()), "README 缺少同时含 budget 与 limit_sec 的一行"
