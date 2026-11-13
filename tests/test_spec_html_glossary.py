"""spec.html 列出工件里的避用词（scenario: domain-glossary#spec-html-lists-avoided-term-hits、
#spec-html-omits-glossary-section-without-hits、#spec-html-skips-canonical-and-code-hits，共 3 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import re

import pytest

from conftest import run_hook, write

PENDING = pytest.mark.xfail(strict=True, reason="change grill-glossary S1 未实现")
NOW = "2026-11-13T00:00:00Z"

GLOSSARY = """
    # 术语表

    **切片**：一次飞行里可独立门禁的最小改动单元。
    避用：任务、子任务

    **起飞**：人类批准飞行计划后开始执行。
    避用：上线
"""


def render(change, out):
    return run_hook("spec_html", "--change-dir", str(change), "--out", str(out), "--now", NOW)


def glossary_section(html):
    m = re.search(r'<section id="glossary">(.*?)</section>', html, re.S)
    return m.group(1) if m else None


def rows(section):
    """表体每行 → (位置, 避用词, 规范词)，单元格内标签去掉。"""
    found = re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", section, re.S)
    return {tuple(re.sub(r"<[^>]+>", "", c).strip() for c in r) for r in found}


@PENDING
def test_spec_html_lists_avoided_term_hits(tmp_path):
    # Given: 术语表有「切片」（避用：任务、子任务）与「起飞」（避用：上线）；
    #        proposal.md 第 3 行「本次上线拆成三个任务」，specs/x/spec.md 第 5 行「每个子任务独立门禁」
    write(tmp_path / "openspec" / "glossary.md", GLOSSARY)
    change = tmp_path / "openspec" / "changes" / "c"
    write(change / "proposal.md", "## Why\n\n本次上线拆成三个任务。\n")
    write(change / "specs" / "x" / "spec.md", "## ADDED Requirements\n\n### Requirement: r\n\n每个子任务独立门禁。\n")
    out = tmp_path / "spec.html"

    # When: 运行 spec_html.py --change-dir
    p = render(change, out)

    # Then: 退出 0；有「术语对照」一节，恰好三条：proposal.md:3 的 上线→起飞 与 任务→切片、specs/x/spec.md:5 的 子任务→切片
    #       （「子任务」里面的「任务」不另报）
    assert p.returncode == 0, p.stderr
    section = glossary_section(out.read_text(encoding="utf-8"))
    assert section is not None and "术语对照" in section
    assert rows(section) == {
        ("proposal.md:3", "上线", "起飞"),
        ("proposal.md:3", "任务", "切片"),
        ("specs/x/spec.md:5", "子任务", "切片"),
    }


@PENDING
def test_spec_html_omits_glossary_section_without_hits(tmp_path):
    # Given: 项目 a 没有 openspec/glossary.md（工件里有「上线」）；项目 b 有术语表，但工件里一个避用词都没用
    a = tmp_path / "a" / "openspec" / "changes" / "c"
    write(a / "proposal.md", "## Why\n\n本次上线拆成三个任务。\n")
    write(tmp_path / "b" / "openspec" / "glossary.md", GLOSSARY)
    b = tmp_path / "b" / "openspec" / "changes" / "c"
    write(b / "proposal.md", "## Why\n\n本次起飞拆成三个切片。\n")

    # When: 分别渲染
    results = [(render(c, tmp_path / ("%s.html" % name)), tmp_path / ("%s.html" % name)) for name, c in (("a", a), ("b", b))]

    # Then: 两次都退出 0，两份面板都没有「术语对照」一节，只留下模板里空的 glossary 占位
    for p, out in results:
        assert p.returncode == 0, p.stderr
        html = out.read_text(encoding="utf-8")
        assert glossary_section(html) is None and "术语对照" not in html
        assert re.search(r"<!-- block:glossary -->\s*<!-- /block:glossary -->", html)


@PENDING
def test_spec_html_skips_canonical_and_code_hits(tmp_path):
    # Given: 术语表有「飞行计划」（避用：计划）与「切片」（避用：task）；proposal.md 里「飞行计划」在正文，
    #        「计划」只在行内代码与代码块里，tasks.md 只作为文件名出现在正文
    write(tmp_path / "openspec" / "glossary.md", """
        # 术语表

        **飞行计划**：人类批准后交给执行体的切片计划。
        避用：计划

        **切片**：一次飞行里可独立门禁的最小改动单元。
        避用：task
    """)
    change = tmp_path / "openspec" / "changes" / "c"
    body = "## Why\n\n飞行计划由人批准。\n别写 `计划` 这个词。\n看 tasks.md 的勾选。\n\n```text\n计划\n```\n"
    write(change / "proposal.md", body)
    out = tmp_path / "spec.html"

    # When: 渲染；再在 proposal.md 末尾追加一行正文「这个 Task 很急。」后重新渲染
    first = render(change, out)
    first_html = out.read_text(encoding="utf-8")
    (change / "proposal.md").write_text(body + "这个 Task 很急。\n", encoding="utf-8")
    second = render(change, out)
    second_html = out.read_text(encoding="utf-8")

    # Then: 第一次没有「术语对照」一节；第二次只列出追加那一行的 task→切片（避用词按术语表原文显示）
    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    assert glossary_section(first_html) is None
    line = len(body.splitlines()) + 1
    assert rows(glossary_section(second_html) or "") == {("proposal.md:%d" % line, "task", "切片")}
