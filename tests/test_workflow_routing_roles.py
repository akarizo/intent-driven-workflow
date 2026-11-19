"""opsx-apply.js 按 5 个角色派发：大片档执行体走 executor-large、修复走 fixer、缺省同 executor、effort 校验
（scenario: flight-role-routing#workflow-routes-large-slice-to-executor-large、#workflow-routes-fixes-to-fixer、
#workflow-defaults-new-roles-to-executor、#workflow-rejects-unknown-effort，共 4 条）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。"""
import json
import shutil
import subprocess

import pytest

from test_agents_workflow import HARNESS, REVIEW_HIGH, TAIL_REPLIES, WORKFLOW, flight_args, gate_json, run_workflow

ROLES = {"executor", "executor-large", "fixer", "reviewer", "integrator"}


def by_label(out):
    return {c["opts"]["label"]: c["opts"] for c in out["calls"]}


def run_raw(tmp_path, args, replies):
    """与 run_workflow 相同，但不断言无错误：返回 {calls, result} 或 {calls, error}。"""
    if not shutil.which("node"):
        pytest.skip("需要 node 驱动工作流脚本")
    body = WORKFLOW.read_text(encoding="utf-8").replace("export const meta", "const meta", 1)
    js = tmp_path / "harness.cjs"
    js.write_text(HARNESS.replace("__BODY__", body), encoding="utf-8")
    p = subprocess.run(["node", str(js)], input=json.dumps({"args": args, "replies": replies}),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_workflow_routes_large_slice_to_executor_large(tmp_path):
    # Given: 两片计划，S1 为大片档、S2 为标准档；executor-large = fable·high，executor = opus·medium
    args = flight_args(waves=[["S1", "S2"]], turns={"S1": "large"},
                       models={"executor": "opus", "executor-large": "fable", "fixer": "opus",
                               "reviewer": "opus", "integrator": "sonnet"},
                       efforts={"executor": "medium", "executor-large": "high", "fixer": "high",
                                "reviewer": "high", "integrator": "low"})
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")]] + TAIL_REPLIES

    # When: 运行工作流
    calls = by_label(run_workflow(tmp_path, args, replies))

    # Then: S1 派发带 fable·high，S2 派发带 opus·medium
    assert (calls["S1"]["model"], calls["S1"]["effort"]) == ("fable", "high"), calls["S1"]
    assert (calls["S2"]["model"], calls["S2"]["effort"]) == ("opus", "medium"), calls["S2"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_workflow_routes_fixes_to_fixer(tmp_path):
    # Given: 一片计划，评审返回一条 HIGH；fixer = fable·high
    args = flight_args(waves=[["S1"]],
                       models={"executor": "opus", "executor-large": "opus", "fixer": "fable",
                               "reviewer": "opus", "integrator": "sonnet"},
                       efforts={"executor": "medium", "executor-large": "medium", "fixer": "high",
                                "reviewer": "high", "integrator": "low"})
    replies = [["^S1$", gate_json("S1")], ["^review:S1$", REVIEW_HIGH],
               ["^fix$", gate_json("final", commit="9" * 40)]] + TAIL_REPLIES

    # When: 运行工作流
    calls = by_label(run_workflow(tmp_path, args, replies))

    # Then: label 为 fix 的派发带 fable·high
    assert (calls["fix"]["model"], calls["fix"]["effort"]) == ("fable", "high"), calls["fix"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_workflow_defaults_new_roles_to_executor(tmp_path):
    # Given: args 只有三个角色（executor = opus·medium）；S1 为大片档，评审给出 HIGH 触发批量修复
    args = flight_args(waves=[["S1"]], turns={"S1": "large"},
                       models={"executor": "opus", "reviewer": "opus", "integrator": "sonnet"},
                       efforts={"executor": "medium", "reviewer": "high", "integrator": "low"})
    replies = [["^S1$", gate_json("S1")], ["^review:S1$", REVIEW_HIGH],
               ["^fix$", gate_json("final", commit="9" * 40)]] + TAIL_REPLIES

    # When: 运行工作流
    out = run_workflow(tmp_path, args, replies)
    calls = by_label(out)

    # Then: 大片档执行体与 fix 都带 opus·medium；返回值的 models / efforts 含 5 个角色
    for label in ("S1", "fix"):
        assert (calls[label]["model"], calls[label]["effort"]) == ("opus", "medium"), calls[label]
    assert set(out["result"]["models"]) == ROLES, out["result"]["models"]
    assert set(out["result"]["efforts"]) == ROLES, out["result"]["efforts"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_workflow_rejects_unknown_effort(tmp_path):
    # Given: efforts.reviewer = huge
    args = flight_args(efforts={"executor": "high", "reviewer": "huge", "integrator": "low"})

    # When: 运行工作流
    out = run_raw(tmp_path, args, TAIL_REPLIES)

    # Then: 抛错，信息点名 reviewer 与允许的 effort 集合；没有派发任何 agent
    assert "error" in out, out.get("result")
    assert "reviewer" in out["error"] and "medium" in out["error"] and "xhigh" in out["error"], out["error"]
    assert out["calls"] == []
