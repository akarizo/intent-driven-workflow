"""/clean-after-merged 命令、铁律 6 例外与文档同步（scenario: clean-after-merged-command#command-runs-plan-then-apply、
#iron-rule-grants-cleanup-exception、#git-discipline-points-to-command、#docs-list-new-command、
#readme-describes-auto-sedimentation，共 5 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import re

import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="change post-ship-hygiene S2 未实现")
CLAUDE = ROOT / "template" / ".claude"


def read(path):
    return path.read_text(encoding="utf-8")


def section(text, start, end=None):
    """返回匹配 start（行首正则）之后、匹配 end 之前的正文；end 缺省或未命中 → 到文末。"""
    m = re.search(start, text, re.M)
    assert m, start
    rest = text[m.end():]
    if end:
        e = re.search(end, rest, re.M)
        rest = rest[: e.start()] if e else rest
    return rest


def iron6(text):
    return [line for line in text.splitlines() if line.startswith("6. Git 边界")]


@PENDING
def test_command_runs_plan_then_apply():
    # Given: template/.claude/commands/clean-after-merged.md
    text = read(CLAUDE / "commands" / "clean-after-merged.md")

    # When: 定位 plan / apply 调用、回退段与 Guardrails
    i_plan = text.index("merged-cleanup.py plan --markdown")
    i_apply = text.index("merged-cleanup.py apply")
    fallback = section(text, r"^\*\*回退", r"^\*\*Guardrails\*\*")
    guard = section(text, r"^\*\*Guardrails\*\*")

    # Then: plan 在 apply 之前；在主 worktree 根运行并以 git worktree list 验证；回退含 --ff-only 且不自动删除；
    #       Guardrails 写明不执行 branch -D / push --delete / manual 档、不 cd 进待删 worktree
    assert i_plan < i_apply
    assert "--git-common-dir" in text and "git worktree list" in text
    assert "--ff-only" in fallback and "不自动删除" in fallback
    for k in ("git branch -D", "push --delete", "manual", "cd"):
        assert k in guard, k


@PENDING
def test_iron_rule_grants_cleanup_exception():
    # Given: 根 CLAUDE.md 与 template/CLAUDE.md.snippet
    root = read(ROOT / "CLAUDE.md")
    snippet = read(ROOT / "template" / "CLAUDE.md.snippet")

    # When: 找出两者的铁律 6 那一行
    r6, s6 = iron6(root), iron6(snippet)

    # Then: 两行都含 /clean-after-merged；根那一行仍含「不删 worktree」与 branch -D；snippet 不超过 8KB
    assert len(r6) == 1 and len(s6) == 1, (r6, s6)
    assert "/clean-after-merged" in r6[0] and "/clean-after-merged" in s6[0]
    assert "不删 worktree" in r6[0] and "branch -D" in r6[0], r6[0]
    assert len(snippet.encode("utf-8")) <= 8 * 1024


@PENDING
def test_git_discipline_points_to_command():
    # Given: openspec-git-discipline/SKILL.md
    text = read(CLAUDE / "skills" / "openspec-git-discipline" / "SKILL.md")

    # When: 切出 Worktree Isolation 节、其中的清理条款与飞行临时 worktree 的 carve-out 段
    iso = section(text, r"^## Worktree Isolation", r"^## ")
    clean = [line for line in iso.splitlines() if line.startswith("- **清理只在主仓库根**")]
    carve = section(iso, r"^\*\*Carve-out — 每个执行体的临时 worktree")

    # Then: 清理条款含 /clean-after-merged、merged-cleanup.py 与「主仓库根」；carve-out 段含 /clean-after-merged
    assert len(clean) == 1, clean
    for k in ("/clean-after-merged", "merged-cleanup.py", "主仓库根"):
        assert k in clean[0], k
    assert "/clean-after-merged" in carve


@PENDING
def test_docs_list_new_command():
    # Given: README.md、install.sh、docs/WORKFLOW_zh.md
    readme = read(ROOT / "README.md")
    install = read(ROOT / "install.sh")
    workflow = read(ROOT / "docs" / "WORKFLOW_zh.md")

    # When: 查找新命令的登记
    row = re.search(r"^\| `/clean-after-merged", readme, re.M)

    # Then: README 命令表有它一行；install.sh 写 17 个 slash command 并列出它；WORKFLOW_zh 提到它
    assert row, "README 命令表缺 /clean-after-merged"
    assert "17 个 slash command" in install and "/clean-after-merged" in install
    assert "/clean-after-merged" in workflow


@PENDING
def test_readme_describes_auto_sedimentation():
    # Given: README.md
    readme = read(ROOT / "README.md")

    # When: 取 /claudemd-commit 的命令表行与「阶段 4」的 /pr-ship 流程说明
    row = [line for line in readme.splitlines() if line.startswith("| `/claudemd-commit`")]
    ship = section(readme, r"^### 阶段 4", r"^### ")

    # Then: 该行含「自动」与「对齐」，全文不再含「逐条与用户讨论」；阶段 4 含「记忆层沉淀」
    assert len(row) == 1 and "自动" in row[0] and "对齐" in row[0], row
    assert "逐条与用户讨论" not in readme
    assert "记忆层沉淀" in ship
