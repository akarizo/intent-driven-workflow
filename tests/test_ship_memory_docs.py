"""/pr-ship 记忆层沉淀与 /claudemd-commit 自动录入（scenario: ship-memory-sedimentation#claudemd-commit-auto-records、
#claudemd-commit-bounded-recurring-errors、#pr-ship-sediments-before-commit、#pr-ship-reruns-final-after-sediment、
#pr-ship-lists-alignment-items-in-pr，共 5 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="change post-ship-hygiene S3 未实现")
CLAUDE = ROOT / "template" / ".claude"
CMD = CLAUDE / "commands"


def read(path):
    return path.read_text(encoding="utf-8")


def ship_and_2b():
    text = read(CMD / "pr-ship.md")
    return text, text[text.index("2b. **"):text.index("3. **")]


@PENDING
def test_claudemd_commit_auto_records():
    # Given: claudemd-commit.md 与 claudemd-standard.md
    text = read(CMD / "claudemd-commit.md")
    std = read(CLAUDE / "claudemd-standard.md")

    # When: 切出 claudemd-commit 的 step 6 与 standard §13 合约表的 /claudemd-commit 行
    step6 = text[text.index("### 6."):text.index("### 7.")]
    row = [line for line in std.splitlines() if line.startswith("| `/claudemd-commit`")]

    # Then: step 6 写自动录入、不再有「与用户逐类确认」；列出四种较大差异，较大差异才用 AskUserQuestion；
    #       被 /pr-ship 调用时较大差异不落盘；§13 行含「自动录入」
    assert "自动录入" in step6 and "与用户逐类确认" not in text
    for k in ("删除或反转", "矛盾", "铁律", "~/.claude/CLAUDE.md"):
        assert k in step6, k
    assert "较大差异" in step6 and "AskUserQuestion" in step6
    assert "/pr-ship" in step6 and "不落盘" in step6
    assert len(row) == 1 and "自动录入" in row[0], row


@PENDING
def test_claudemd_commit_bounded_recurring_errors():
    # Given: claudemd-commit.md
    text = read(CMD / "claudemd-commit.md")

    # When: 切出 step 3 及其中的 E 类条目（到 step 3 末尾）
    step3 = text[text.index("### 3."):text.index("### 4.")]
    e = step3[step3.index("**E. 反复错误**"):]

    # Then: E 类写明至少 2 次与证据（含 review-findings.json、fix commit）；1 次进 backlog；Q4 ✓ 进 backlog 立项、留一行过渡条目；
    #       仍写明 C 类废除
    for k in ("至少 2 次", "证据", "review-findings.json", "fix commit", "1 次", "backlog", "过渡"):
        assert k in e, k
    assert "C 类" in step3 and "废除" in step3


@PENDING
def test_pr_ship_sediments_before_commit():
    # Given: pr-ship.md
    text, s2b = ship_and_2b()

    # When: 定位 step 2、step 2b、step 3 与 Guardrails
    order = [text.index("2. **"), text.index("2b. **"), text.index("3. **")]
    guard = text[text.index("**Guardrails**"):]

    # Then: 2b 位于 2 与 3 之间，含 /claudemd-commit、对话、飞行记录、独立 commit 与两个 lint；全文无 AskUserQuestion；Guardrails 全程不问询
    assert order == sorted(order), order
    for k in ("/claudemd-commit", "对话", "timeline.md", "review-findings.json", "docs(memory)", "claudemd-lint", "memory-lint"):
        assert k in s2b, k
    assert "AskUserQuestion" not in text
    assert "全程不问询" in guard


@PENDING
def test_pr_ship_reruns_final_after_sediment():
    # Given: pr-ship.md 的 step 2b
    text, s2b = ship_and_2b()

    # When: 取 2b 里的 slice-gate.py final 与 step 6 里的 slice-gate.py ship 位置
    i_final = text.index("slice-gate.py final", text.index("2b. **"))
    i_ship = text.index("slice-gate.py ship", text.index("6. **"))

    # Then: 2b 写明重跑 final，且在 step 6 的 ship 裁决之前
    assert "slice-gate.py final" in s2b
    assert i_final < i_ship


@PENDING
def test_pr_ship_lists_alignment_items_in_pr():
    # Given: pr-ship.md
    text = read(CMD / "pr-ship.md")

    # When: 切出 step 6、step 11 与 Output Summary
    step6 = text[text.index("6. **"):text.index("7. **")]
    step11 = text[text.index("11. **"):text.index("**Output Summary")]
    summary = text[text.index("**Output Summary"):text.index("**Guardrails**")]

    # Then: step 6 有两段记忆层标题；Output Summary 含「记忆层」；step 11 提示 /clean-after-merged
    assert "## 记忆层沉淀" in step6 and "## 记忆层：需与你对齐" in step6
    assert "记忆层" in summary
    assert "/clean-after-merged" in step11
