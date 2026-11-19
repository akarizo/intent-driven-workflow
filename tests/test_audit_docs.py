"""文档：/test-audit 命令、README 与 install.sh 的命令计数、标准文档与脚本常量一致
（scenario: test-audit#test-audit-command-doc-covers-flow、#readme-and-install-count-test-audit、
#standard-doc-matches-script-constants）。
骨架：strict xfail，断言是真实的；切片 S7 实现后去掉标记即解锁。"""
from conftest import ROOT, load_hook
from test_audit_standard_docs import standard_section

CMD = ROOT / "template" / ".claude" / "commands" / "test-audit.md"
README = ROOT / "README.md"
INSTALL = ROOT / "install.sh"


def test_test_audit_command_doc_covers_flow():
    # Given: 模板仓库的 /test-audit 命令文档
    text = CMD.read_text(encoding="utf-8")

    # When: 取 frontmatter 与正文
    head = text.split("---", 2)

    # Then: 有 description；五步用到的脚本与两条轨道的出口都写明；三条不做的事与「无同名 skill」都在
    assert text.startswith("---\n") and len(head) == 3 and "description:" in head[1], text[:200]
    for word in ("test-tiers.py audit", "--out", "test-audit.py render", "test-audit.py verify", "--compare", "--plan",
                 "test-tiers.py probe", "allow-slow", "/opsx-mini", "/opsx-propose"):
        assert word in head[2], word
    for word in ("等人类批准", "不改断言", "不代 commit", "无同名 skill"):
        assert word in head[2], word


def test_readme_and_install_count_test_audit():
    # Given: README.md 与 install.sh
    readme, install = README.read_text(encoding="utf-8"), INSTALL.read_text(encoding="utf-8")

    # When: 查命令计数与命令清单
    row = [l for l in readme.splitlines() if l.startswith("| `/test-audit")]

    # Then: 计数是 18，两处都列出 /test-audit，不再出现 17
    assert "18 个 slash 命令" in readme and row, "README 缺 18 个 slash 命令或 /test-audit 的表格行"
    assert "18 个 slash command" in install and "/test-audit" in install
    assert "17 个 slash" not in readme and "17 个 slash" not in install


def test_standard_doc_matches_script_constants():
    # Given: test-tiers.py 的 AUDIT_RULES 与 test-audit.py 的 ACTIONS
    rules, actions = load_hook("test-tiers").AUDIT_RULES, load_hook("test-audit").ACTIONS

    # When: 与契约文档「测试套件合规标准」一节对照
    body = standard_section()

    # Then: 每个类别名、规则号、去向名都在文档里；每个可选去向都是已定义的去向
    assert body and rules and actions
    for cat, spec in rules.items():
        assert "`%s`" % cat in body, cat
        assert not spec.get("rule") or spec["rule"] in body, (cat, spec)
        assert set(spec.get("fix") or []) <= set(actions), (cat, spec)
    for name in actions:
        assert "`%s`" % name in body, name
