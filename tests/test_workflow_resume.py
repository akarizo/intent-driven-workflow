"""工作流的接续与轮次档（scenario: slice-continue#workflow-retry-continues-via-start、#executor-contract-describes-continue；
turn-tiers#workflow-picks-definition-by-tier、#large-definition-is-thin、#noreturn-blocked-reason-names-tier-and-snapshot、
#large-executor-is-gated-and-audited，共 6 条）。
S4 已解锁（骨架标记已去）。"""
import json
import re

from conftest import load_hook, run_hook
from test_agents_workflow import (AGENTS, TAIL_REPLIES, exec_prompts, flight_args, frontmatter, gate_json, run_workflow,
                                  start_cmds)
from test_approval_gate import change_dir, human, transcript

LARGE = AGENTS / "slice-executor-large.md"


def exec_calls(out):
    return {c["opts"]["label"]: c for c in out["calls"] if re.fullmatch(r"S\d+(:retry)?", c["opts"]["label"])}


def test_workflow_retry_continues_via_start(tmp_path):
    # Given: S1 首轮门禁红（带 commit 与 base），重派后绿；S2、S3 一次绿
    replies = [
        ["^S1$", gate_json("S1", ok=False, commit="e" * 40, failed=["G1 verify: exit 1"])],
        ["^S1:retry$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
    ] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流，取 S1 重派的 prompt
    out = run_workflow(tmp_path, flight_args(), replies)
    prompt = exec_prompts(out)["S1:retry"]
    cmds = start_cmds(prompt)

    # Then: 重派的 start 带 --continue <上一轮 commit> 与 --expect-branch，不带 --base；prompt 没有「第零步」，
    #       只在 hooks 未升级的回退句里提到 cherry-pick；仍要求只修门禁项
    assert cmds and all("--continue " + "e" * 40 in c and "--expect-branch worktree-c" in c for c in cmds), cmds
    assert not any("--base" in c for c in cmds), cmds
    assert "第零步" not in prompt
    assert "unrecognized arguments" in prompt and "cherry-pick" in prompt
    assert "只修这些门禁项" in prompt


def test_workflow_picks_definition_by_tier(tmp_path):
    # Given: args.turns 把 S2 标为大片档；S2 首轮门禁红、重派后绿；分别在 agent 类型已注册与未注册两种配置下起飞
    replies = [
        ["^S1$", gate_json("S1")], ["^S2$", gate_json("S2", ok=False, commit="e" * 40, failed=["G1 verify: exit 1"])],
        ["^S2:retry$", gate_json("S2")], ["^S3$", gate_json("S3")],
    ] + TAIL_REPLIES
    turns = {"S1": "standard", "S2": "large", "S3": "standard"}

    # When: 用 mock agent 各跑一遍工作流
    typed = exec_calls(run_workflow(tmp_path, flight_args(turns=turns), replies))
    untyped = exec_calls(run_workflow(tmp_path, flight_args(turns=turns, useAgentTypes=False), replies))

    # Then: 已注册时 S2 的首轮与重派都派给 slice-executor-large，其余派给 slice-executor；
    #       未注册时 S2 的 prompt 让执行体先读 slice-executor-large.md，其余读 slice-executor.md；没传 turns 时全部是标准档
    assert {k: v["opts"].get("agentType") for k, v in typed.items()} == {
        "S1": "slice-executor", "S2": "slice-executor-large", "S2:retry": "slice-executor-large", "S3": "slice-executor"}
    for label in ("S2", "S2:retry"):
        assert ".claude/agents/slice-executor-large.md" in untyped[label]["prompt"], untyped[label]["prompt"][:200]
        assert "agentType" not in untyped[label]["opts"]
    assert ".claude/agents/slice-executor.md" in untyped["S1"]["prompt"]
    assert "slice-executor-large" not in untyped["S1"]["prompt"]
    plain = exec_calls(run_workflow(tmp_path, flight_args(), replies))
    assert all(v["opts"].get("agentType") == "slice-executor" for v in plain.values()), plain


def test_large_definition_is_thin():
    # Given: template/.claude/agents/ 下的两份执行体定义
    std_fm, _ = frontmatter(AGENTS / "slice-executor.md")
    assert LARGE.is_file(), "缺少 slice-executor-large.md"

    # When: 解析大片档定义的 frontmatter 与正文
    fm, body = frontmatter(LARGE)

    # Then: 大片档只换名字与轮次上限（80），其余 frontmatter 与标准档一致；正文只指向标准档定义，不复制纪律
    assert fm.get("name") == "slice-executor-large" and fm.get("maxTurns") == "80"
    assert std_fm.get("maxTurns") == "40"
    for key in ("tools", "model", "effort", "permissionMode"):
        assert fm.get(key) == std_fm.get(key), key
    assert "test-driven-development" in LARGE.read_text(encoding="utf-8")
    assert "slice-executor.md" in body
    assert len([line for line in body.splitlines() if line.strip()]) <= 6, body
    assert "只写 owns 内文件" not in body


def test_noreturn_blocked_reason_names_tier_and_snapshot(tmp_path):
    # Given: S1 是大片档、S2 是标准档；两片的首轮与重派都没有交回结果
    replies = [["^S3$", gate_json("S3")]] + TAIL_REPLIES
    args = flight_args(turns={"S1": "large", "S2": "standard"}, deps={"S3": ["S1"]})

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, args, replies)
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: 两片都记 blocked（infra）；理由写明档位与该档上限、本次飞行内已重派一次、半成品快照所在的 ref
    for sid, tier, cap in (("S1", "大片档", "80"), ("S2", "标准档", "40")):
        reason = blocked[sid]["reason"]
        assert blocked[sid]["kind"] == "infra"
        assert "未返回" in reason and "已重派一次" in reason, reason
        assert tier in reason and cap in reason, reason
        assert "refs/flight/c/" + sid in reason, reason


def test_large_executor_is_gated_and_audited(tmp_path):
    # Given: 回退路径用 Agent 工具派 slice-executor-large，prompt 指向某个 change；转录里没有人类批准
    d = change_dir(tmp_path)
    none = transcript(tmp_path / "none.jsonl", [human("继续", "2026-09-10T08:30:00Z")])
    payload = {"tool_name": "Agent", "cwd": str(tmp_path), "transcript_path": str(none),
               "tool_input": {"subagent_type": "slice-executor-large",
                              "prompt": "切片包：`openspec/changes/demo/slices/S1.md`，按 TDD 执行"}}

    # When: 以 hook 模式运行起飞门禁；另读收口对账脚本的 agent 类型到角色的映射
    p = run_hook("takeoff-gate", stdin=json.dumps(payload))
    roles = load_hook("session-decompose").AGENT_ROLE

    # Then: 起飞门禁照样拦下未批准的派发并点名 change 目录；对账把大片档执行体记为 executor 角色
    assert p.stdout.strip(), "起飞门禁没有判定 slice-executor-large 的派发"
    out = json.loads(p.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny" and str(d) in out["permissionDecisionReason"]
    assert roles.get("slice-executor-large") == "executor" and roles.get("slice-executor") == "executor"


def test_executor_contract_describes_continue():
    # Given: template/.claude/agents/slice-executor.md
    fm, body = frontmatter(AGENTS / "slice-executor.md")

    # When: 读它的开工段与预算条
    text = body

    # Then: 写明重派时 start 带 --continue、由脚本接上一轮的全部提交、非 0 退出原样返回；不再有手工第零步；
    #       预算条指向 frontmatter 的上限并点名大片档定义；既有的快照接续、基点校验、分层说明都还在
    assert "--continue" in text and "continued" in text
    assert "第零步" not in text
    assert "slice-executor-large" in text
    for kept in ("--resume-checkpoint", "--expect-branch", "checkpoint.restored", "G12", "recovered"):
        assert kept in text, kept
    assert fm.get("maxTurns") == "40"
