"""飞行编排与文档接上 submodule 支持（scenario: submodule-flight-orchestration#integrator-merges-via-script、
#fix-prompt-syncs-submodules、#reviewer-reads-submodule-diff、#agent-docs-describe-submodule-discipline、
#apply-docs-mirror-submodule，共 5 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import re

from conftest import ROOT
from test_agents_workflow import REVIEW_HIGH, TAIL_REPLIES, fallback_section, flight_args, gate_json, run_workflow

CLAUDE = ROOT / "template" / ".claude"


def read(rel):
    return (CLAUDE / rel).read_text(encoding="utf-8")


def _calls(tmp_path, replies):
    out = run_workflow(tmp_path, flight_args(), replies + TAIL_REPLIES)
    return out, {c["opts"]["label"]: c for c in out["calls"]}


def test_integrator_merges_via_script(tmp_path):
    # Given: waves [[S1, S2], [S3]] 门禁全绿（commit 为 a…a / b…b / c…c）；S1 评审给出 1 条 HIGH，fix 返回 commit 9…9
    replies = [["^S1$", gate_json("S1", commit="a" * 40)], ["^S2$", gate_json("S2", commit="b" * 40)],
               ["^S3$", gate_json("S3")], ["^review:S1$", REVIEW_HIGH], ["^fix$", gate_json("final", commit="9" * 40)]]

    # When: 用 mock agent 跑完整个工作流
    out, calls = _calls(tmp_path, replies)

    # Then: wave 1 合回 prompt 含 slice-gate.py merge S1=a…a S2=b…b；finalize prompt 含 slice-gate.py merge fix=9…9 且在 slice-gate.py final 之前
    assert ("slice-gate.py merge S1=%s S2=%s" % ("a" * 40, "b" * 40)) in calls["integrate:w1"]["prompt"]
    fin = calls["final-gate"]["prompt"]
    assert ("slice-gate.py merge fix=" + "9" * 40) in fin and fin.index("merge fix=") < fin.index("slice-gate.py final"), fin


def test_fix_prompt_syncs_submodules(tmp_path):
    # Given: 同上，S1 评审给出 1 条 HIGH，触发 fix
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
               ["^review:S1$", REVIEW_HIGH], ["^fix$", gate_json("final", commit="9" * 40)]]

    # When: 跑完工作流，取 fix 派发的 prompt
    out, calls = _calls(tmp_path, replies)
    fix = calls["fix"]["prompt"]

    # Then: fix prompt 在基点校验之后、start fix 之前运行 slice-gate.py sub-sync，并带 --expect-branch worktree-c 与 --change-dir
    m = re.search(r"slice-gate\.py sub-sync [^`\n]*", fix)
    assert m and "--expect-branch worktree-c" in m.group(0) and "--change-dir openspec/changes/c" in m.group(0), fix
    assert fix.index("merge-base --is-ancestor") < m.start() < fix.index("slice-gate.py start fix")


def test_reviewer_reads_submodule_diff(tmp_path):
    # Given: waves [[S1, S2], [S3]] 门禁全绿，S1 的 commit 为 a…a
    replies = [["^S1$", gate_json("S1", commit="a" * 40)], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]]

    # When: 跑完工作流，取 review:S1 的 prompt
    out, calls = _calls(tmp_path, replies)

    # Then: 评审用 git show --submodule=diff 读切片 commit（submodule 内的改动随 diff 展开）
    assert ("git show --submodule=diff " + "a" * 40) in calls["review:S1"]["prompt"]


def test_agent_docs_describe_submodule_discipline():
    # Given: slice-executor.md 与 integrator.md
    executor, integrator = read("agents/slice-executor.md"), read("agents/integrator.md")

    # When: 取 integrator 的第 1 项与执行体的纪律段
    item1 = integrator[integrator.index("## 1."):integrator.index("## 2.")]
    rules = executor[executor.index("## 纪律"):executor.index("## 收尾")]

    # Then: integrator 第 1 项让脚本 slice-gate.py merge 合回（仍写明它逐片 git merge --no-ff）；执行体纪律写明子仓先 git -C <path> 提交、再把 gitlink 并入同一个切片 commit
    assert "slice-gate.py merge" in item1 and "git merge --no-ff" in item1, item1
    assert "git -C" in rules and "gitlink" in rules and "submodule" in rules, rules


def test_apply_docs_mirror_submodule():
    # Given: opsx-apply.md、openspec-apply-change/SKILL.md 与 openspec-git-discipline/SKILL.md
    cmd, skill = read("commands/opsx-apply.md"), read("skills/openspec-apply-change/SKILL.md")
    disc = read("skills/openspec-git-discipline/SKILL.md")

    # When: 取命令与 skill 的回退段
    sections = [fallback_section(cmd), fallback_section(skill)]

    # Then: 两处回退段都写明 integrator 用 slice-gate.py merge 合回、fix 先跑 slice-gate.py sub-sync；git-discipline 有 Submodule 小节，写明隔离 worktree 借用家子仓的 linked worktree
    for sec in sections:
        assert "slice-gate.py merge" in sec and "slice-gate.py sub-sync" in sec, sec[:200]
    assert "## Submodule" in disc and "linked worktree" in disc
