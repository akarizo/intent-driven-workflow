"""工作流的 wave 集成检查、跨片修复通道、停飞范围与已落地切片的跳过
（scenario: wave-fix#workflow-asks-integrator-for-wave-check、#workflow-skips-when-integrator-has-no-check、
#integrator-contract-describes-wave-check、#workflow-dispatches-cross-slice-fix-on-red、
#executor-contract-describes-cross-slice-fix、#workflow-stops-all-when-guard-still-red、
#workflow-stops-only-dependents-when-tests-red、#workflow-retries-fix-noreturn-then-blocks；
retakeoff-landed#workflow-skips-landed-slices，共 9 条）。
骨架：strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import pytest

from test_agents_workflow import AGENTS, THROW, flight_args, frontmatter, gate_json, run_workflow

PENDING = pytest.mark.xfail(strict=True, reason="change wave-integration-guard S4 未实现")

GREEN = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")], ["^S4$", gate_json("S4")]]
TAIL = [["^review:", {"findings": []}], ["^final-gate$", {"slice": "final", "ok": True, "commit": "d" * 40, "failed": []}]]
G15 = "G15 guard layering：exit 3"
G16 = "G16 wave test：新增失败 1 条：tests/test_a.py::test_a"
FIX_SHA = "9" * 40


def check(ok=True, failed=()):
    return {"slice": "wave", "ok": ok, "commit": "a" * 40, "failed": list(failed), "warnings": []}


def merged(chk=None, **over):
    out = {"ok": True, "merged": ["S1", "S2"], "failed": [], "warnings": []}
    if chk is not None:
        out["check"] = chk
    out.update(over)
    return out


def by_label(out):
    return {c["opts"]["label"]: c for c in out["calls"]}


def blocked_of(out, sid):
    return [b for b in out["result"]["blocked"] if b["slice"] == sid]


@PENDING
def test_workflow_asks_integrator_for_wave_check(tmp_path):
    # Given: 两个 wave 的飞行，全部切片门禁绿，integrator 带回的 check 是绿的
    replies = GREEN + [["^integrate:", merged(check())]] + TAIL

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    prompt = by_label(out)["integrate:w1"]["prompt"]

    # Then: 第一个 wave 的合回 prompt 在 merge 之后要求运行 wave-check 并把 JSON 放进 check；没有跨片修复；waves 记下结论
    cmd = "slice-gate.py wave-check --change-dir openspec/changes/c --wave 1 --of 2"
    assert cmd in prompt and prompt.index("slice-gate.py merge") < prompt.index(cmd), prompt
    assert "check" in prompt and "invalid choice" in prompt
    assert not [l for l in by_label(out) if l.startswith("fix:w")]
    first = out["result"]["waves"][0]
    assert first["wave"] == 1 and first["ok"] is True, out["result"]["waves"]


@PENDING
def test_workflow_skips_when_integrator_has_no_check(tmp_path):
    # Given: integrator 的返回值没有 check（hooks 未升级）
    replies = GREEN + [["^integrate:", merged()]] + TAIL

    # When: 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)

    # Then: 没有派跨片修复，blocked 为空；waves 每条都带非空的 skipped
    assert not [l for l in by_label(out) if l.startswith("fix:w")]
    assert out["result"]["blocked"] == []
    assert out["result"]["waves"] and all(w.get("skipped") for w in out["result"]["waves"]), out["result"]


@PENDING
def test_integrator_contract_describes_wave_check():
    # Given: template/.claude/agents/integrator.md
    _, body = frontmatter(AGENTS / "integrator.md")

    # When: 读正文

    # Then: 写明 wave-check 仅当 prompt 点名时运行、子命令不存在时 check 为 null；原有三件事仍在
    assert "wave-check" in body and "点名" in body and "invalid choice" in body and "null" in body, body
    assert "git merge" in body and "_interfaces.md" in body and "slice-gate.py final" in body


@PENDING
def test_workflow_dispatches_cross_slice_fix_on_red(tmp_path):
    # Given: 第一个 wave 的 check 是红的（G15）；修复执行体返回绿的 JSON，commit 为 9…9，owns 外有一个文件
    fixed = dict(check(), commit=FIX_SHA, fix={"base": "b" * 40, "files": ["pyproject.toml"],
                                                 "outside_owns": ["pyproject.toml"]})
    replies = GREEN + [["^integrate:w1$", merged(check(False, [G15]))],
                       ["^integrate:w1:fix$", merged(merged=["wavefix1"])],
                       ["^integrate:", merged(check(), merged=["S3"])], ["^fix:w1$", fixed]] + TAIL

    # When: 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    calls = by_label(out)

    # Then: 派了隔离的修复执行体（执行体模型与类型），prompt 带失败项、越权许可、基点校验与带 --fix-base 的收尾；
    #       绿了由 integrator 合回并写回结论；修复提交有一次评审；下一个 wave 照常；waves 记下修复
    fix = calls["fix:w1"]
    assert fix["opts"].get("isolation") == "worktree" and fix["opts"].get("model") == "opus", fix["opts"]
    assert fix["opts"].get("agentType") == "slice-executor", fix["opts"]
    for word in (G15, "不受", "--fix-base", "slice-gate.py wave-check", "git merge-base --is-ancestor"):
        assert word in fix["prompt"], word
    back = calls["integrate:w1:fix"]
    assert back["opts"].get("agentType") == "integrator", back["opts"]
    assert "merge wavefix1=" + FIX_SHA in back["prompt"] and "record --change-dir" in back["prompt"], back["prompt"]
    assert "review:wavefix1" in calls and FIX_SHA in calls["review:wavefix1"]["prompt"]
    assert "S3" in calls and not blocked_of(out, "wave1"), out["result"]["blocked"]
    first = out["result"]["waves"][0]
    assert first["fix"]["commit"] == FIX_SHA and first["fix"]["outside_owns"] == ["pyproject.toml"], first


@PENDING
def test_executor_contract_describes_cross_slice_fix():
    # Given: template/.claude/agents/slice-executor.md
    fm, body = frontmatter(AGENTS / "slice-executor.md")

    # When: 读 frontmatter 与正文

    # Then: 有一段写明跨片修复：不运行 start 与 gate，收尾运行带 --fix-base 的 wave-check；轮次上限不变
    assert "跨片修复" in body and "--fix-base" in body and "wave-check" in body, body
    assert fm.get("maxTurns") == "40"


@PENDING
def test_workflow_stops_all_when_guard_still_red(tmp_path):
    # Given: 第一个 wave 的 check 因 G15 红；修复执行体返回的 JSON 仍因 G15 红
    still = dict(check(False, [G15]), commit=FIX_SHA)
    replies = GREEN + [["^integrate:", merged(check(False, [G15]))], ["^fix:w1", still]] + TAIL

    # When: 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    calls = by_label(out)

    # Then: 修复不合回；第二个 wave 的切片不派发并记 blocked；wave1 记 blocked（gate）；全量门禁照常
    assert "integrate:w1:fix" not in calls and "S3" not in calls, sorted(calls)
    w = blocked_of(out, "wave1")
    assert len(w) == 1 and w[0]["kind"] == "gate", out["result"]["blocked"]
    s3 = blocked_of(out, "S3")
    assert len(s3) == 1 and s3[0]["kind"] == "infra" and "wave 1" in s3[0]["reason"], out["result"]["blocked"]
    assert "final-gate" in calls


@PENDING
def test_workflow_stops_only_dependents_when_tests_red(tmp_path):
    # Given: 第二个 wave 有依赖 S1 的 S3 与没有依赖的 S4；第一个 wave 的 check 只因 G16 红，修复后仍红
    still = dict(check(False, [G16]), commit=FIX_SHA)
    replies = GREEN + [["^integrate:w1$", merged(check(False, [G16]))], ["^integrate:", merged(check(), merged=["S4"])],
                       ["^fix:w1", still]] + TAIL
    args = flight_args(waves=[["S1", "S2"], ["S3", "S4"]], deps={"S3": ["S1"], "S4": []})

    # When: 跑完整个工作流
    out = run_workflow(tmp_path, args, replies)
    calls = by_label(out)

    # Then: S3 记 blocked 且没有被派发；S4 照常派发
    assert "S3" not in calls and len(blocked_of(out, "S3")) == 1, (sorted(calls), out["result"]["blocked"])
    assert "S4" in calls and not blocked_of(out, "S4")
    assert len(blocked_of(out, "wave1")) == 1


@PENDING
def test_workflow_retries_fix_noreturn_then_blocks(tmp_path):
    # Given: 第一个 wave 的 check 是红的；修复执行体两次都没有交回结构化结果
    replies = GREEN + [["^integrate:", merged(check(False, [G16]))], ["^fix:w1", THROW]] + TAIL

    # When: 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    calls = by_label(out)

    # Then: 派了 fix:w1 与 fix:w1:retry；wave1 记 blocked（infra），理由含「未返回」
    assert "fix:w1" in calls and "fix:w1:retry" in calls, sorted(calls)
    w = blocked_of(out, "wave1")
    assert len(w) == 1 and w[0]["kind"] == "infra" and "未返回" in w[0]["reason"], out["result"]["blocked"]


@PENDING
def test_workflow_skips_landed_slices(tmp_path):
    # Given: args.landed 含 S1（commit 为 1…1）；另一次飞行的 args.landed 含第一个 wave 的全部切片
    replies = GREEN + [["^integrate:", merged(check())]] + TAIL
    one = {"S1": "1" * 10}
    both = {"S1": "1" * 10, "S2": "2" * 10}

    # When: 各跑一遍工作流
    out1 = run_workflow(tmp_path, flight_args(landed=one), replies)
    out2 = run_workflow(tmp_path, flight_args(landed=both), replies)
    calls1, calls2 = by_label(out1), by_label(out2)

    # Then: 已落地的切片不派执行体、评审照派、返回值标 landed；整个 wave 都已落地时只做集成检查不合回，下一个 wave 照常
    assert "S1" not in calls1 and "S2" in calls1, sorted(calls1)
    assert "1" * 10 in calls1["review:S1"]["prompt"]
    s1 = next(s for s in out1["result"]["slices"] if s["slice"] == "S1")
    assert s1.get("landed") is True and s1["ok"] is True, s1
    w1 = calls2["integrate:w1"]["prompt"]
    assert "wave-check" in w1 and "slice-gate.py merge" not in w1, w1
    assert "S1" not in calls2 and "S2" not in calls2 and "S3" in calls2, sorted(calls2)
