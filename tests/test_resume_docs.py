"""起飞命令、同名 skill、README 与安装脚本同步接续与轮次档（scenario: slice-continue#apply-docs-mirror-continue-and-tiers；
turn-tiers#readme-and-installer-list-four-agents，共 2 条）。
骨架：strict xfail，断言是真实的；切片 S6 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="change slice-resume-deterministic S6 未实现")
TEMPLATE = ROOT / "template" / ".claude"


def read(path):
    return path.read_text(encoding="utf-8")


def fallback_line(text):
    """回退路径那一条（以「Workflow 不可用」起头的列表项）。"""
    hits = [line for line in text.splitlines() if "Workflow 不可用" in line and "回退" in line]
    assert len(hits) == 1, hits
    return hits[0]


@PENDING
def test_apply_docs_mirror_continue_and_tiers():
    # Given: 命令文档 opsx-apply.md 与同名 skill openspec-apply-change/SKILL.md
    docs = [read(TEMPLATE / "commands" / "opsx-apply.md"), read(TEMPLATE / "skills" / "openspec-apply-change" / "SKILL.md")]

    # When: 取两份文档的全文与各自的回退路径那一条
    falls = [fallback_line(t) for t in docs]

    # Then: 两份都写明起飞前运行 slice-gate.py turns 并把结果作为 turns 传给工作流；
    #       回退路径的重派改用 start --continue、大片档派 slice-executor-large，不再有手工第零步；
    #       未返回的 blocked 理由要写档位与快照位置；既有的快照接续说明保留
    for text, fall in zip(docs, falls):
        assert "slice-gate.py turns --change-dir" in text and "turns: " in text, text[:80]
        assert "--continue" in fall and "slice-executor-large" in fall, fall[:200]
        assert "第零步" not in text
        assert "refs/flight/" in fall and "档" in fall
        assert "--resume-checkpoint" in fall and "未返回" in fall


@PENDING
def test_readme_and_installer_list_four_agents():
    # Given: README.md 与 install.sh
    readme, installer = read(ROOT / "README.md"), read(ROOT / "install.sh")

    # When: 找 agent 清单与留痕说明
    texts = (readme, installer)

    # Then: 两处都说 4 个 agent 并点名 slice-executor-large；README 另写明两档的轮次上限、档位怎么定、
    #       切片留痕先写共用目录再并回分支、合回后回收临时 worktree
    for t in texts:
        assert "4 个 agent" in t and "3 个 agent" not in t
        assert "slice-executor-large" in t
    for word in ("flight-evidence", "slice-gate.py turns", "大片档", "80", "回收"):
        assert word in readme, word
