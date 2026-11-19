"""session-decompose.py 收口对账覆盖 effort 与 fixer / executor-large 两个角色
（scenario: route-audit-efforts#audit-flags-effort-mismatch、#audit-maps-fix-labels-to-fixer、
#audit-maps-large-slices-by-turns、#audit-skips-undispatched-optional-roles、#audit-warns-when-effort-unrecorded，共 5 条）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import run_hook
from test_evidence_timeline import FIXTURE


def agent(wf, name, label, phase, model, effort=None, agent_type="workflow-subagent"):
    """造一个 workflow agent 转录 + meta；effort 非 None 时 assistant 行带顶层 effort 字段（与真实转录一致）。"""
    rows = []
    for i, ts in enumerate(("2026-11-19T10:00:00Z", "2026-11-19T10:02:00Z")):
        r = {"type": "assistant", "timestamp": ts, "requestId": "%s-r%d" % (name, i),
             "message": {"model": model, "usage": {}, "content": [{"type": "text", "text": "x"}]}}
        if effort is not None:
            r["effort"] = effort
        rows.append(r)
    (wf / ("agent-%s.jsonl" % name)).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (wf / ("agent-%s.meta.json" % name)).write_text(
        json.dumps({"description": label, "workflowPhase": phase, "agentType": agent_type}), encoding="utf-8")


def audit(tmp_path, models, efforts=None, turns=None):
    sess = tmp_path / "sess.jsonl"
    sess.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in FIXTURE) + "\n", encoding="utf-8")
    args = ["--session", str(sess), "--workflow", str(tmp_path / "wf"), "--expect-models", json.dumps(models)]
    if efforts is not None:
        args += ["--expect-efforts", json.dumps(efforts)]
    if turns is not None:
        args += ["--turns", json.dumps(turns)]
    return run_hook("session-decompose", *args)


def base_wf(tmp_path, executor_effort="medium", effort=True):
    wf = tmp_path / "wf"
    wf.mkdir()
    e = (lambda v: v) if effort else (lambda v: None)
    agent(wf, "a1", "S1", "Implement", "claude-opus-5-5", e(executor_effort))
    agent(wf, "a2", "review:S1", "Review", "claude-opus-5-5", e("high"))
    agent(wf, "a3", "integrate:w1", "Implement", "claude-sonnet-5-5", e("low"))
    return wf


MODELS3 = {"executor": "opus", "reviewer": "opus", "integrator": "sonnet"}


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_audit_flags_effort_mismatch(tmp_path):
    # Given: S1 实际 opus·high，评审 opus·high，integrate sonnet·low
    base_wf(tmp_path, executor_effort="high")

    # When: 期望 executor 为 medium，其余与实际相同
    p = audit(tmp_path, MODELS3, {"executor": "medium", "reviewer": "high", "integrator": "low"})

    # Then: exit 3，输出含 S1、期望 medium 与实际 high
    assert p.returncode == 3, (p.returncode, p.stdout, p.stderr)
    line = next(ln for ln in p.stdout.splitlines() if "S1" in ln and "medium" in ln)
    assert "high" in line, p.stdout


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_audit_maps_fix_labels_to_fixer(tmp_path):
    # Given: S1 opus·medium；fix:w1 fable·high；评审与 integrate 与期望一致
    wf = base_wf(tmp_path)
    agent(wf, "a4", "fix:w1", "Implement", "claude-fable-5-2", "high")

    # When: 期望 executor = opus·medium、fixer = fable·high
    p = audit(tmp_path, {**MODELS3, "fixer": "fable"},
              {"executor": "medium", "fixer": "high", "reviewer": "high", "integrator": "low"})

    # Then: 退出 0，对账一致且列出 fixer=fable
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "路由对账：✅" in p.stdout and "fixer=fable" in p.stdout, p.stdout


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_audit_maps_large_slices_by_turns(tmp_path):
    # Given: S2（Implement，agentType workflow-subagent）实际 fable，其余与期望一致
    wf = base_wf(tmp_path)
    agent(wf, "a5", "S2", "Implement", "claude-fable-5-2", "medium")

    # When: 期望 executor = opus、executor-large = fable，并传 --turns {"S2": "large"}
    p = audit(tmp_path, {**MODELS3, "executor-large": "fable"},
              {"executor": "medium", "executor-large": "medium", "reviewer": "high", "integrator": "low"},
              turns={"S2": "large"})

    # Then: 退出 0，S2 按 executor-large 对账通过
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "executor-large=fable" in p.stdout, p.stdout


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_audit_skips_undispatched_optional_roles(tmp_path):
    # Given: 只有执行体、评审、integrator，取值都与期望一致
    base_wf(tmp_path)

    # When: 期望表含全部 5 个角色
    p = audit(tmp_path, {**MODELS3, "fixer": "opus", "executor-large": "opus"},
              {"executor": "medium", "executor-large": "medium", "fixer": "high", "reviewer": "high", "integrator": "low"})

    # Then: 退出 0，没有 fixer / executor-large 的「未采样到角色」
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "未采样到角色 fixer" not in p.stdout and "未采样到角色 executor-large" not in p.stdout


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_audit_warns_when_effort_unrecorded(tmp_path):
    # Given: 所有 assistant 行都没有 effort 字段，模型与期望一致
    base_wf(tmp_path, effort=False)

    # When: 带 --expect-efforts 运行
    p = audit(tmp_path, MODELS3, {"executor": "medium", "reviewer": "high", "integrator": "low"})

    # Then: 退出 0，输出含跳过提示
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert "转录无 effort 字段，effort 对账跳过" in p.stdout
