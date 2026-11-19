"""收口回收的文档与铁律（scenario: flight-close-reap#apply-close-runs-reap、#iron-rule-names-close-reap、
merged-cleanup-agent-worktrees#cleanup-doc-explains-new-reasons，共 3 条）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT
from test_clean_after_merged_docs import iron6

CMD = ROOT / "template" / ".claude" / "commands"
SKILL = ROOT / "template" / ".claude" / "skills" / "openspec-apply-change" / "SKILL.md"


def read(p):
    return p.read_text(encoding="utf-8")


@pytest.mark.xfail(strict=True, reason="scenario: flight-close-reap#apply-close-runs-reap")
def test_apply_close_runs_reap():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    docs = [read(CMD / "opsx-apply.md"), read(SKILL)]

    for text in docs:
        # When: 定位收口步骤里的 flight-doctor.py cost、slice-gate.py reap 与其后第一次出现的 review-findings.json
        i_cost = text.index("flight-doctor.py cost")
        i_reap = text.index("slice-gate.py reap --change-dir")
        i_rf = text.index("review-findings.json", i_cost)

        # Then: reap 在 cost 之后、写 review-findings.json 之前；这一段写明打印回收一行与 invalid choice 时跳过
        assert i_cost < i_reap < i_rf, (i_cost, i_reap, i_rf)
        seg = text[i_reap:i_rf]
        assert "invalid choice" in seg and "回收" in seg, seg


@pytest.mark.xfail(strict=True, reason="scenario: flight-close-reap#iron-rule-names-close-reap")
def test_iron_rule_names_close_reap():
    # Given: 根 CLAUDE.md 与 template/CLAUDE.md.snippet
    root = read(ROOT / "CLAUDE.md")
    snippet = read(ROOT / "template" / "CLAUDE.md.snippet")

    # When: 找出两者的铁律 6 那一行
    r6, s6 = iron6(root), iron6(snippet)

    # Then: 两行都写明 slice-gate.py reap 收口回收与作废尝试先归档；原有 merge 回收与 /clean-after-merged 仍在；
    #       根 CLAUDE.md 仍写明不删 worktree、不带强制参数、branch -D 交人；snippet 不超过 8KB
    assert len(r6) == 1 and len(s6) == 1, (r6, s6)
    for line in (r6[0], s6[0]):
        assert "slice-gate.py reap" in line and "归档" in line, line
        assert "slice-gate.py merge" in line and "/clean-after-merged" in line, line
    assert "不删 worktree" in r6[0] and "不带强制参数" in r6[0] and "branch -D" in r6[0], r6[0]
    assert len(snippet.encode("utf-8")) <= 8 * 1024


@pytest.mark.xfail(strict=True, reason="scenario: merged-cleanup-agent-worktrees#cleanup-doc-explains-new-reasons")
def test_cleanup_doc_explains_new_reasons():
    # Given: template/.claude/commands/clean-after-merged.md
    text = read(CMD / "clean-after-merged.md")

    # When: 取原因标记表里以 `landed` 与 `dead-attempt` 开头的行
    rows = {tag: [line for line in text.splitlines() if line.startswith("| `%s`" % tag)] for tag in ("landed", "dead-attempt")}

    # Then: 两行都在，且说明列非空
    for tag, hit in rows.items():
        assert len(hit) == 1, (tag, hit)
        cells = [c.strip() for c in hit[0].strip("|").split("|")]
        assert len(cells) >= 2 and cells[1], (tag, hit)
