"""命令文档镜像 wave 集成检查与跨片修复（scenario: wave-fix#apply-docs-mirror-wave-check-and-fix、
#pr-ship-doc-lists-cross-slice-fixes、#readme-describes-wave-guard，共 3 条）。
骨架：strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="change wave-integration-guard S5 未实现")

CMD = ROOT / "template" / ".claude" / "commands"
APPLY_DOCS = (CMD / "opsx-apply.md", ROOT / "template" / ".claude" / "skills" / "openspec-apply-change" / "SKILL.md")


def read(path):
    return path.read_text(encoding="utf-8")


@PENDING
def test_apply_docs_mirror_wave_check_and_fix():
    # Given: opsx-apply.md 与同名 skill
    texts = {p.name + ":" + p.parent.name: read(p) for p in APPLY_DOCS}

    # When: 阅读这两份文档

    # Then: 两份都写了已落地切片、每个 wave 的集成检查、跨片修复及其收尾与合回、守护红的停飞范围，以及 waves 的落点
    for name, text in texts.items():
        for word in ("slice-gate.py landed", "slice-gate.py wave-check", "跨片修复", "--fix-base", "wavefix", "G15"):
            assert word in text, (name, word)
        assert any("waves" in line and "review-findings.json" in line for line in text.splitlines()), name


@PENDING
def test_pr_ship_doc_lists_cross_slice_fixes():
    # Given: pr-ship.md
    text = read(CMD / "pr-ship.md")

    # When: 阅读全文

    # Then: 写明正文列出 waves 里的跨片修复；理由出现「wave 集成检查红」时重跑 wave-check
    assert any("waves" in line and "跨片修复" in line for line in text.splitlines()), "缺 waves / 跨片修复"
    assert "wave 集成检查红" in text and "slice-gate.py wave-check" in text


@PENDING
def test_readme_describes_wave_guard():
    # Given: README.md
    text = read(ROOT / "README.md")

    # When: 阅读全文

    # Then: 提到全局守护、wave 集成检查、owns_wide 与 landed 子命令
    for word in ("全局守护", "wave 集成检查", "owns_wide", "slice-gate.py landed"):
        assert word in text, word
