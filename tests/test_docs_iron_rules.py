"""文档与铁律（scenario: executable-specs#claudemd-iron-rules / docs-updated, flight-apply#legacy-mode-optional）。"""
import re

from conftest import ROOT

IRON = ["先意图后代码", "规格即验收", "TDD", "独立评审", "门禁", "Git 边界", "两处", "度量", "零 token", "回退", "显式路由"]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def before_legacy(text):
    """返回第一个含 legacy 的标题之前的正文（水位线只允许出现在 legacy 段）。"""
    m = re.search(r"^#{1,6} .*legacy.*$", text, re.I | re.M)
    return text[: m.start()] if m else text


def test_claudemd_iron_rules():
    # Given: 本仓库根 CLAUDE.md 与 template/CLAUDE.md.snippet
    root = read("CLAUDE.md")
    snippet = read("template/CLAUDE.md.snippet")

    # When: 找出两者的铁律段
    sections = [root, snippet]

    # Then: 两者都含「铁律」并覆盖 10 条关键短语；根 CLAUDE.md 另含仓库开发纪律（schema validate / pytest / 假名谚文）；snippet 不超过 8KB
    assert all("铁律" in s for s in sections)
    assert all(all(k in s for k in IRON) for s in sections)
    assert "openspec schema validate" in root and "pytest" in root and "假名" in root
    assert len(snippet.encode("utf-8")) <= 8 * 1024


def test_docs_updated():
    # Given: README.md、docs/WORKFLOW_zh.md、template/CLAUDE.md.snippet
    readme, workflow, snippet = read("README.md"), read("docs/WORKFLOW_zh.md"), read("template/CLAUDE.md.snippet")

    # When: 取 legacy 段之前的正文
    main_readme, main_workflow = before_legacy(readme), before_legacy(workflow)

    # Then: 主体不再把水位线 / 逐 task 守门描述为默认，而描述 slices.json 与飞行流程；snippet 含 v2.1.251 顺序且不再声称 env 压过一切
    assert "水位线" not in main_readme and "水位线" not in main_workflow
    assert "slices.json" in readme and "飞行" in readme
    assert "slices.json" in workflow and "飞行" in workflow
    assert "2.1.251" in snippet and "压过一切" not in snippet


def test_legacy_mode_optional():
    # Given: 安装后的 skills 目录
    legacy = ROOT / "template" / ".claude" / "skills" / "legacy" / "openspec-subagent-apply-change" / "SKILL.md"
    old = ROOT / "template" / ".claude" / "skills" / "openspec-subagent-apply-change"

    # When: 检查 legacy 位置与旧位置
    head = legacy.read_text(encoding="utf-8")[:1200] if legacy.exists() else ""

    # Then: legacy 路径存在且开头说明仅 --gate=per-task 时读取；旧路径不再存在
    assert legacy.exists()
    assert "legacy" in head and "--gate=per-task" in head
    assert not old.exists()


# ---------------------------------------------------------------- 判据机械化（scenario: model-routing#docs-state-mechanical-resolution）
def test_docs_state_mechanical_resolution():
    # Given: README.md、docs/WORKFLOW_zh.md、template/CLAUDE.md.snippet、仓库根 CLAUDE.md、install.sh
    docs = {rel: read(rel) for rel in
            ("README.md", "docs/WORKFLOW_zh.md", "template/CLAUDE.md.snippet", "CLAUDE.md", "install.sh")}

    # When: 检索模型路由与起飞批准相关段落
    routed = [docs["README.md"], docs["docs/WORKFLOW_zh.md"], docs["template/CLAUDE.md.snippet"], docs["CLAUDE.md"]]

    # Then: 都声明路由由 model-routing 机械解析；铁律含"禁自述"与起飞批准的机械校验；无"看 /model"式措辞；install.sh 说明同步
    assert all("model-routing" in t for t in routed)
    assert all("看 `/model`" not in t for t in docs.values())
    assert "禁自述" in docs["CLAUDE.md"] and "禁自述" in docs["template/CLAUDE.md.snippet"]
    assert "takeoff-gate" in docs["CLAUDE.md"] and "takeoff-gate" in docs["install.sh"]
    assert "model-routing" in docs["install.sh"]


# ---------------------------------------------------------------- 配置驱动路由（scenario: iron-rule-routing#iron-rule-names-routing-config、
# #readme-and-installer-describe-routing，共 2 条）。骨架：strict xfail，切片 S6 实现后去掉标记即解锁。
import pytest  # noqa: E402


def rule_11(text):
    return next(line for line in text.splitlines() if re.match(r"^11\.\s", line))


def test_iron_rule_names_routing_config():
    # Given: 仓库根 CLAUDE.md 与 template/CLAUDE.md.snippet
    lines = [rule_11(read("CLAUDE.md")), rule_11(read("template/CLAUDE.md.snippet"))]

    # When: 取两者的铁律 11 一行
    # Then: 都含 model-routing.json / slices.json / --expect-efforts / main / 「主会话或 fork」，都不含「会话主模型」
    for line in lines:
        for k in ("model-routing.json", "slices.json", "--expect-efforts", "main", "主会话或 fork"):
            assert k in line, (k, line)
        assert "会话主模型" not in line, line


def test_readme_and_installer_describe_routing():
    # Given: README.md、docs/WORKFLOW_zh.md 与 install.sh
    docs = {rel: read(rel) for rel in ("README.md", "docs/WORKFLOW_zh.md", "install.sh")}

    # When: 读三者全文
    # Then: 都含 model-routing；不再把执行体与评审员写成「会话主模型（session-model.py 判定）」
    for rel, t in docs.items():
        assert "model-routing" in t, rel
        assert "会话主模型（`session-model.py` 判定）" not in t and "会话主模型（session-model.py 判定）" not in t, rel
    assert "会话主模型 `<main>`" not in docs["docs/WORKFLOW_zh.md"]
