"""文档说明测试账本与「测试变更」（scenario: test-ledger#docs-describe-test-ledger、#pr-ship-doc-mentions-test-delta-section）。
骨架：strict xfail，断言是真实的；切片 S7 实现后去掉标记即解锁。"""
from conftest import ROOT

CLAUDE = ROOT / "template" / ".claude"
OLD_HEADS = ("## 1. 包装脚本要转发的两个变量", "## 2. `GATE_PHASE` / `GATE_CHANGE`", "## 3. 检查可读的 `GATE_TEST_RESULT`",
             "## 4. 易变变量与项目缓存键", "## 5. 依赖图未测的四类原因与修法", "## 6. `gate-scope.json` 的可选字段",
             "## 7. 接入步骤", "## 8. 全机测试锁")


def test_docs_describe_test_ledger():
    # Given: 本 change 落地后的模板文档
    lines = (CLAUDE / "flight-runner-contract.md").read_text(encoding="utf-8").splitlines()
    tiers = (CLAUDE / "commands" / "test-tiers.md").read_text(encoding="utf-8").splitlines()
    readme = (ROOT / "README.md").read_text(encoding="utf-8").splitlines()

    # When: 取契约文档的二级标题与第 9 节正文
    heads = [l for l in lines if l.startswith("## ")]
    nine = [h for h in heads if h.startswith("## 9.")]
    start = lines.index(nine[0]) + 1 if nine else len(lines)
    body = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    body = "\n".join(body)

    # Then: 第 9 节讲测试账本的位置、子命令、空耗时、沿用与不判红；原有 1–8 节标题都在；另两处文档各有一句
    assert len(nine) == 1 and "测试账本" in nine[0], heads
    for word in ("flight-ledger", "test-ledger.py show", "test-ledger.py delta", "null", "沿用", "不判红"):
        assert word in body, word
    for head in OLD_HEADS:
        assert head in heads, head
    assert any("测试账本" in l and "分层文件" in l for l in tiers), "test-tiers.md 缺测试账本归层的说明"
    assert any("测试账本" in l and "[tests]" in l for l in readme), "README 缺测试账本一条"


def test_pr_ship_doc_mentions_test_delta_section():
    # Given: 本 change 落地后的 pr-ship 命令文档
    lines = (CLAUDE / "commands" / "pr-ship.md").read_text(encoding="utf-8").splitlines()

    # When: 找到起草正文时贴 ship --markdown 输出的那一步（命令行及其后 6 行）
    at = next(i for i, l in enumerate(lines) if "slice-gate.py ship --change-dir" in l and "--markdown" in l)
    window = lines[at:at + 7]

    # Then: 写明输出可能含「## 测试变更」，且这一节原样贴入、不改写不删减
    hit = [l for l in window if "## 测试变更" in l]
    assert hit, window
    assert any("原样" in l for l in hit), hit
