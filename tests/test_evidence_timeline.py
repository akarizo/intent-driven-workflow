"""test-evidence / timeline / stop-gate / session-decompose（scenario: slice-gate#evidence-*, stop-hook-*, flight-apply#timeline-*, session-decompose-*）。"""
import json

from conftest import run_hook, write


def marker_repo(git_repo):
    change = git_repo / "openspec" / "changes" / "c"
    write(change / "tasks.md", "- [ ] S1 x\n")
    write(change / "slices.json", json.dumps({"version": 1, "change": "c", "gate": {"test": "true"}, "slices": [
        {"id": "S1", "title": "S1", "scenarios": [], "owns": ["src/**"], "deps": [], "verify": "true"}], "scenario_tests": {}}))
    write(git_repo / ".openspec-slice", json.dumps({"slice": "S1", "change_dir": str(change), "base": "HEAD"}))
    return change


def bash_event(cmd, stdout="", stderr="", event="PostToolUse", cwd="."):
    return json.dumps({"hook_event_name": event, "tool_name": "Bash", "cwd": str(cwd),
                       "tool_input": {"command": cmd}, "tool_response": {"stdout": stdout, "stderr": stderr, "interrupted": False}})


# ---------------------------------------------------------------- test-evidence

def test_evidence_log_records_test_runs(git_repo):
    # Given: 根目录有指向切片 S1 的 .openspec-slice 标记；一条 PostToolUse Bash 事件，命令是 pytest 且输出 "3 passed"
    change = marker_repo(git_repo)
    event = bash_event("python3 -m pytest -q tests", stdout="3 passed in 0.1s", cwd=git_repo)

    # When: 运行 test-evidence.py
    p = run_hook("test-evidence", stdin=event, cwd=git_repo)

    # Then: evidence.log 追加一行，含切片 S1、PASS 与命令
    line = (change / "evidence.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "\tS1\t" in line
    assert "\tPASS\t" in line
    assert "pytest" in line


def test_evidence_log_records_failed_run(git_repo):
    # Given: 同上标记；一条 PostToolUseFailure Bash 事件，命令是 pytest
    change = marker_repo(git_repo)
    event = bash_event("python3 -m pytest -q tests", stdout="1 failed", event="PostToolUseFailure", cwd=git_repo)

    # When: 运行 test-evidence.py
    run_hook("test-evidence", stdin=event, cwd=git_repo)

    # Then: evidence.log 最后一行标记为 FAIL
    line = (change / "evidence.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "\tFAIL\t" in line


def test_evidence_ignores_non_test_commands(git_repo):
    # Given: 同上标记；一条 Bash 事件的命令是 git status（不是测试运行器）
    change = marker_repo(git_repo)
    event = bash_event("git status --short", stdout="", cwd=git_repo)

    # When: 运行 test-evidence.py
    run_hook("test-evidence", stdin=event, cwd=git_repo)

    # Then: 不创建 evidence.log
    assert not (change / "evidence.log").exists()


# ---------------------------------------------------------------- stop-gate

def stop_event(cwd, active=False, event="Stop"):
    return json.dumps({"hook_event_name": event, "stop_hook_active": active, "cwd": str(cwd)})


def test_stop_hook_blocks_red_flight(git_repo):
    # Given: 根目录存在指向切片 S1 的 .openspec-slice 标记，stop_hook_active 为 false
    marker_repo(git_repo)

    # When: Stop 事件触发 stop-gate.py
    p = run_hook("stop-gate", stdin=stop_event(git_repo), cwd=git_repo)

    # Then: 输出 decision 为 block，reason 点名 S1
    out = json.loads(p.stdout)
    assert out["decision"] == "block"
    assert "S1" in out["reason"]


def test_stop_hook_respects_stop_hook_active(git_repo):
    # Given: 同上标记，但 stop_hook_active 为 true（本轮已经因 stop hook 续跑过）
    marker_repo(git_repo)

    # When: Stop 事件再次触发 stop-gate.py
    p = run_hook("stop-gate", stdin=stop_event(git_repo, active=True), cwd=git_repo)

    # Then: 不输出 block
    assert "block" not in p.stdout


def test_stop_hook_allows_after_two_reds(git_repo):
    # Given: .openspec-slice 标记里 red_count 已经是 2（同一门禁项连续两次红，执行体按纪律该停下上报）
    change = marker_repo(git_repo)
    write(git_repo / ".openspec-slice", json.dumps({"slice": "S1", "change_dir": str(change), "base": "HEAD", "red_count": 2}))

    # When: Stop 事件触发 stop-gate.py
    p = run_hook("stop-gate", stdin=stop_event(git_repo), cwd=git_repo)

    # Then: 不再 block（否则执行体会被强制续跑，违背「连续 2 次红即停」）
    assert "block" not in p.stdout


def test_stop_hook_silent_without_marker(git_repo):
    # Given: 根目录没有 .openspec-slice 标记
    # When: SubagentStop 事件触发 stop-gate.py
    p = run_hook("stop-gate", stdin=stop_event(git_repo, event="SubagentStop"), cwd=git_repo)

    # Then: 无输出
    assert p.stdout.strip() == ""


# ---------------------------------------------------------------- timeline

def test_timeline_record_appends(tmp_path):
    # Given: 一个空的 change 目录
    change = tmp_path / "c"
    change.mkdir()

    # When: 运行 timeline.py record approve --note 起飞
    p = run_hook("timeline", "record", "approve", "--change-dir", str(change), "--note", "起飞")

    # Then: timeline.md 存在且最后一行含 approve 与备注
    assert p.returncode == 0, p.stderr
    line = (change / "timeline.md").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "\tapprove\t起飞" in line


def test_timeline_report(tmp_path):
    # Given: timeline.md 里 approve 在 10:00:00、pr-open 在 10:30:00
    change = tmp_path / "c"
    write(change / "timeline.md", """
        <!-- timeline -->
        2026-09-10T10:00:00Z\tapprove\t
        2026-09-10T10:12:00Z\tgate\tS1 ok
        2026-09-10T10:30:00Z\tpr-open\thttps://x
    """)

    # When: 运行 timeline.py report
    p = run_hook("timeline", "report", "--change-dir", str(change))

    # Then: 输出含批准到 PR 打开的分钟数 30
    assert p.returncode == 0, p.stderr
    assert "30" in p.stdout and "approve" in p.stdout


# ---------------------------------------------------------------- session-decompose

FIXTURE = [
    {"type": "user", "timestamp": "2026-09-10T10:00:00Z", "message": {"role": "user", "content": "实现 X"}},
    {"type": "assistant", "timestamp": "2026-09-10T10:00:10Z", "requestId": "r1",
     "message": {"model": "claude-opus-5", "usage": {"input_tokens": 1, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0, "output_tokens": 50},
                 "content": [{"type": "tool_use", "id": "t1", "name": "Agent", "input": {"description": "impl S1", "prompt": "..."}}]}},
    {"type": "user", "timestamp": "2026-09-10T10:00:11Z", "toolUseResult": {"status": "async_launched", "agentId": "a1", "description": "impl S1", "resolvedModel": "claude-sonnet-5"},
     "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "launched"}]}},
    {"type": "user", "timestamp": "2026-09-10T10:05:11Z", "message": {"role": "user", "content": "<task-notification><task-id>a1</task-id><status>completed</status><result>done</result></task-notification>"}},
    {"type": "assistant", "timestamp": "2026-09-10T10:05:20Z", "requestId": "r2",
     "message": {"model": "claude-opus-5", "usage": {"input_tokens": 1, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 0, "output_tokens": 20},
                 "content": [{"type": "text", "text": "完成"}]}},
    {"type": "system", "subtype": "turn_duration", "timestamp": "2026-09-10T10:05:20Z"},
]


def test_session_decompose_prints_workflow_models(tmp_path):
    # Given: 一个 workflow journal 目录，含一个 agent 转录（assistant 消息 model 为 claude-sonnet-5）与其 meta.json（description "S4"）
    wf = tmp_path / "wf"
    wf.mkdir()
    (wf / "agent-a1.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"type": "assistant", "timestamp": "2026-09-10T10:00:00Z", "requestId": "r1", "message": {"model": "claude-sonnet-5", "usage": {}, "content": [{"type": "text", "text": "x"}]}},
        {"type": "assistant", "timestamp": "2026-09-10T10:03:00Z", "requestId": "r2", "message": {"model": "claude-sonnet-5", "usage": {}, "content": [{"type": "text", "text": "y"}]}},
    ]) + "\n", encoding="utf-8")
    (wf / "agent-a1.meta.json").write_text(json.dumps({"description": "S4", "workflowPhase": "Implement"}), encoding="utf-8")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 运行 session-decompose.py --session --workflow <dir>
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf))

    # Then: 输出的工作流 agent 表含标签 S4 与实际模型 claude-sonnet-5
    assert p.returncode == 0, p.stderr
    assert "S4" in p.stdout and "claude-sonnet-5" in p.stdout


def test_session_decompose_runs(tmp_path):
    # Given: 一个含人类消息、Agent 派发、异步结果、task-notification、收尾 assistant 的最小转录 fixture
    path = tmp_path / "sess.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 运行 session-decompose.py --session
    p = run_hook("session-decompose", "--session", str(path))

    # Then: 退出码 0，输出含「等子 agent」「模型生成」两类归因与派发数 1
    assert p.returncode == 0, p.stderr
    assert "等子 agent" in p.stdout and "模型生成" in p.stdout
    assert "派发 1" in p.stdout


# ---------------------------------------------------------------- 路由对账（scenario: model-routing#route-audit-*）


def wf_agent(wf, name, model, phase, label, agent_type=None):
    """在 workflow journal 目录里造一个 agent 转录 + meta（agent_type 对应真实 meta 的 agentType）。"""
    (wf / ("agent-%s.jsonl" % name)).write_text("\n".join(json.dumps(r) for r in [
        {"type": "assistant", "timestamp": "2026-09-10T10:00:00Z", "requestId": "r1",
         "message": {"model": model, "usage": {}, "content": [{"type": "text", "text": "x"}]}},
        {"type": "assistant", "timestamp": "2026-09-10T10:03:00Z", "requestId": "r2",
         "message": {"model": model, "usage": {}, "content": [{"type": "text", "text": "y"}]}},
    ]) + "\n", encoding="utf-8")
    meta = {"description": label, "workflowPhase": phase}
    if agent_type:
        meta["agentType"] = agent_type
    (wf / ("agent-%s.meta.json" % name)).write_text(json.dumps(meta), encoding="utf-8")


ROUTE = json.dumps({"executor": "opus", "reviewer": "opus", "integrator": "sonnet"})


def test_route_audit_flags_mismatch(tmp_path):
    # Given: 一个 workflow journal，Implement 阶段的 agent 实际跑在 claude-sonnet-5，而路由表要求 executor=opus
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-sonnet-5", "Implement", "S1")
    wf_agent(wf, "a2", "claude-opus-5", "Review", "review:S1")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带 --expect-models 运行收口分解
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 非 0 退出，输出逐条列出不符项（标签 · 阶段 · 期望别名 · 实际 id）
    assert p.returncode != 0, p.stdout
    assert "S1" in p.stdout and "opus" in p.stdout and "claude-sonnet-5" in p.stdout


def test_route_audit_passes_on_match(tmp_path):
    # Given: 各 agent 实际模型与路由表一致（[1m] 变体也应归一为 opus）
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5[1m]", "Implement", "S1")
    wf_agent(wf, "a2", "claude-opus-5", "Review", "review:S1")
    wf_agent(wf, "a3", "claude-sonnet-5", "Finalize", "final")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带 --expect-models 运行，再不带参数运行一次
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)
    plain = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf))

    # Then: 一致时退出码 0 并打印对账结论；不传参时行为与既有一致（只打印，退出码 0）
    assert p.returncode == 0, p.stderr
    assert "对账" in p.stdout
    assert plain.returncode == 0 and "claude-opus-5" in plain.stdout


def test_route_audit_keys_on_agent_type_not_phase(tmp_path):
    # Given: wave integrator（meta agentType=integrator、workflowPhase=Implement、实际 claude-sonnet-5）
    #        与同阶段的 slice-executor（claude-opus-5）、Review 的 code-reviewer（claude-opus-5）
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5", "Implement", "S1", agent_type="slice-executor")
    wf_agent(wf, "a2", "claude-sonnet-5", "Implement", "integrate:w1", agent_type="integrator")
    wf_agent(wf, "a3", "claude-opus-5", "Review", "review:S1", agent_type="code-reviewer")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带路由表运行收口对账
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 退出码 0，不把 integrate:w1 判成 executor 不符，对账结论把 integrator 记成 sonnet
    assert p.returncode == 0, p.stdout
    assert "integrate:w1" not in p.stdout.split("路由对账")[-1] and "❌" not in p.stdout
    assert "integrator=sonnet" in p.stdout

def test_route_audit_fails_on_zero_coverage(tmp_path):
    # Given: 一个空的 workflow journal 目录（--workflow 指错或该目录尚无 agent 转录）
    wf = tmp_path / "wf"
    wf.mkdir()
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带路由表运行收口对账
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 非 0 退出，逐条点名三个未采样到的角色，且不打印 ✅ 一致
    assert p.returncode != 0, p.stdout
    assert p.stdout.count("未采样到角色") == 3
    assert "✅" not in p.stdout


def test_route_audit_fails_when_one_role_missing(tmp_path):
    # Given: journal 里只有 executor 与 integrator 在阶段内被采到，reviewer 因嵌套派发根本没出现
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5", "Implement", "S1", agent_type="slice-executor")
    wf_agent(wf, "a2", "claude-sonnet-5", "Finalize", "final-gate", agent_type="integrator")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带路由表运行收口对账
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 非 0 退出，点名缺的正是 reviewer（期望 opus），不打印 ✅ 一致
    assert p.returncode != 0, p.stdout
    assert "未采样到角色 reviewer（期望 opus）" in p.stdout
    assert "✅" not in p.stdout


def test_route_audit_ignores_empty_attempt(tmp_path):
    # Given: 三个角色都被正常采样，另有一个被重试掉的空 attempt 转录（有 meta、无 assistant 轮次 → 实际模型 "?"）
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5", "Implement", "S1")
    wf_agent(wf, "a2", "claude-opus-5", "Review", "review:S1")
    wf_agent(wf, "a3", "claude-sonnet-5", "Finalize", "final")
    (wf / "agent-a4.jsonl").write_text(json.dumps(
        {"type": "user", "timestamp": "2026-09-10T10:00:00Z", "message": {"content": "x"}}) + "\n", encoding="utf-8")
    (wf / "agent-a4.meta.json").write_text(
        json.dumps({"description": "fix", "workflowPhase": "Fix", "agentType": "slice-executor"}), encoding="utf-8")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带 --expect-models 运行收口分解
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 空 attempt 只作未采样告警，不算跑错模型；三个角色都已采样故对账绿
    assert p.returncode == 0, p.stdout + p.stderr
    assert "❌" not in p.stdout
    assert "对账" in p.stdout and "未采样" in p.stdout


# ---------------------------------------------------------------- flight-preflight-and-retry（scenario: evidence-change-resolution#*）
# S2 已实现：标记 → 分支名 → 唯一候选 → 不写。

import pytest  # noqa: E402
from conftest import git  # noqa: E402


def _changes(git_repo, names):
    for n in names:
        write(git_repo / "openspec" / "changes" / n / "tasks.md", "- [ ] S1 x\n")


def test_evidence_resolves_change_from_branch(git_repo):
    # Given: 无标记；分支 worktree-c；change a 与 c 的 tasks.md 都有未勾选项（a 按字母序在前）
    _changes(git_repo, ["a", "c"])
    git(git_repo, "checkout", "-q", "-b", "worktree-c")
    event = bash_event("python3 -m pytest -q tests", stdout="1 passed", cwd=git_repo)

    # When: 运行 test-evidence.py
    run_hook("test-evidence", stdin=event, cwd=git_repo)

    # Then: 写进 c，切片列为 -；a 下没有 evidence.log
    line = (git_repo / "openspec" / "changes" / "c" / "evidence.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "\t-\t" in line and "pytest" in line
    assert not (git_repo / "openspec" / "changes" / "a" / "evidence.log").exists()


def test_evidence_skips_ambiguous_change(git_repo):
    # Given: 无标记；分支 main；change a 与 b 都有未勾选项
    _changes(git_repo, ["a", "b"])
    event = bash_event("python3 -m pytest -q tests", stdout="1 passed", cwd=git_repo)

    # When: 运行 test-evidence.py
    p = run_hook("test-evidence", stdin=event, cwd=git_repo)

    # Then: 两个目录都没有 evidence.log；退出 0
    assert not (git_repo / "openspec" / "changes" / "a" / "evidence.log").exists()
    assert not (git_repo / "openspec" / "changes" / "b" / "evidence.log").exists()
    assert p.returncode == 0


def test_evidence_single_candidate_fallback(git_repo):  # 既有行为守卫：单候选回退与标记优先在改动前后都成立，故不标 xfail
    # Given: 无标记；分支 main；只有 change a 有未勾选项
    _changes(git_repo, ["a"])
    event = bash_event("python3 -m pytest -q tests", stdout="1 passed", cwd=git_repo)

    # When: 运行 test-evidence.py；再放标记指向 c 后运行一次
    run_hook("test-evidence", stdin=event, cwd=git_repo)
    change_c = marker_repo(git_repo)
    run_hook("test-evidence", stdin=event, cwd=git_repo)

    # Then: 单候选时写进 a；有标记时写进 c 且切片列为 S1
    assert (git_repo / "openspec" / "changes" / "a" / "evidence.log").exists()
    line = (change_c / "evidence.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "\tS1\t" in line


# ---------------------------------------------------------------- 无 agentType 时按 label 判角色（scenario: route-audit-role-resolution#*）


@pytest.mark.xfail(strict=True, reason="S1：对账按 label 判 integrator 尚未实现")
def test_integrator_label_without_agent_type_matches(tmp_path):
    # Given: 一个 workflow journal，各 agent 的 meta 都没有 agentType：S1（Implement，claude-opus-5）、integrate:w1（Implement，claude-sonnet-5）、
    #        integrate:w2:retry（Implement，claude-sonnet-5）、review:S1（Review，claude-opus-5）
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5", "Implement", "S1")
    wf_agent(wf, "a2", "claude-sonnet-5", "Implement", "integrate:w1")
    wf_agent(wf, "a3", "claude-sonnet-5", "Implement", "integrate:w2:retry")
    wf_agent(wf, "a4", "claude-opus-5", "Review", "review:S1")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带路由表运行收口对账
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 退出 0；输出没有 ❌；对账结论把 integrator 记成 sonnet
    assert p.returncode == 0, p.stdout
    assert "❌" not in p.stdout, p.stdout
    assert "integrator=sonnet" in p.stdout, p.stdout


@pytest.mark.xfail(strict=True, reason="S1：对账按 label 判 integrator 尚未实现")
def test_integrator_label_on_wrong_model_flagged(tmp_path):
    # Given: 一个 workflow journal，各 agent 的 meta 都没有 agentType：S1（Implement，claude-opus-5）、integrate:w1（Implement，claude-opus-5）、
    #        review:S1（Review，claude-opus-5）
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5", "Implement", "S1")
    wf_agent(wf, "a2", "claude-opus-5", "Implement", "integrate:w1")
    wf_agent(wf, "a3", "claude-opus-5", "Review", "review:S1")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带同一路由表运行收口对账
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 退出非 0；有一条 ❌ 行点名 integrate:w1，期望 sonnet，实际 claude-opus-5
    assert p.returncode != 0, p.stdout
    bad = [line for line in p.stdout.splitlines() if "❌" in line]
    assert any("integrate:w1" in line and "期望 sonnet" in line and "claude-opus-5" in line for line in bad), p.stdout


def test_unknown_label_falls_back_to_phase(tmp_path):
    # Given: 一个 workflow journal，各 agent 的 meta 都没有 agentType，label 都不匹配显式格式：S1（Implement，claude-opus-5）、
    #        fix（Fix，claude-opus-5）、judge（Review，claude-opus-5）、final（Finalize，claude-sonnet-5）
    wf = tmp_path / "wf"
    wf.mkdir()
    wf_agent(wf, "a1", "claude-opus-5", "Implement", "S1")
    wf_agent(wf, "a2", "claude-opus-5", "Fix", "fix")
    wf_agent(wf, "a3", "claude-opus-5", "Review", "judge")
    wf_agent(wf, "a4", "claude-sonnet-5", "Finalize", "final")
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")

    # When: 带同一路由表运行收口对账
    p = run_hook("session-decompose", "--session", str(sess), "--workflow", str(wf), "--expect-models", ROUTE)

    # Then: 退出 0；输出没有 ❌；对账结论同时记有 executor=opus、reviewer=opus、integrator=sonnet
    assert p.returncode == 0, p.stdout
    assert "❌" not in p.stdout, p.stdout
    assert all(s in p.stdout for s in ("executor=opus", "reviewer=opus", "integrator=sonnet")), p.stdout
