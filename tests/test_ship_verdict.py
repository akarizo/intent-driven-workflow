"""slice-gate.py ship：飞行收口的机械 draft / ready 裁决（scenario: ship-verdict#*）。"""
import json
import re

import pytest

from conftest import ROOT, commit_all, git, run_hook, write

CMD = ROOT / "template" / ".claude" / "commands"
SKILL = ROOT / "template" / ".claude" / "skills" / "openspec-apply-change" / "SKILL.md"
WORKFLOW = ROOT / "template" / ".claude" / "workflows" / "opsx-apply.js"


def ship_repo(git_repo, slice_verdict="ok", final_verdict="ok", final_at_head=True, findings=None, plan=True):
    """造一个已提交工件的仓库：slices.json（S1）+ gate-report.md + 可选 review-findings.json。返回 change 目录。"""
    change = git_repo / "openspec" / "changes" / "c"
    if plan:
        write(change / "slices.json", json.dumps({
            "version": 1, "change": "c", "gate": {"test": "true"},
            "slices": [{"id": "S1", "title": "S1", "scenarios": [], "owns": ["src/**"], "deps": [], "verify": "true", "packet": "slices/S1.md"}],
            "scenario_tests": {},
        }))
    else:
        write(change / "tasks.md", "- [ ] x\n")
    head = commit_all(git_repo, "artifacts")
    final_commit = head[:10] if final_at_head else "0000000000"
    rows = ["# Gate Report", "", "| 时间 | 切片 | 结论 | commit | failed | warnings |", "|---|---|---|---|---|---|"]
    if slice_verdict:
        rows.append("| 2026-09-10T00:00:00Z | S1 | red | %s | G2 test: exit 1 | - |" % head[:10])
        rows.append("| 2026-09-10T00:01:00Z | S1 | %s | %s | %s | - |" % (slice_verdict, head[:10], "-" if slice_verdict == "ok" else "G4 gwt: test_x"))
    if final_verdict:
        rows.append("| 2026-09-10T00:02:00Z | final | %s | %s | %s | - |" % (final_verdict, final_commit, "-" if final_verdict == "ok" else "G2 test: exit 1"))
    write(change / "gate-report.md", "\n".join(rows) + "\n")
    if findings is not None:
        write(change / "review-findings.json", json.dumps(findings))
    return change


def ship(git_repo, change, *extra):
    return run_hook("slice-gate", "ship", "--change-dir", str(change), *extra, cwd=git_repo)


def test_ship_ready_when_all_green_at_head(git_repo):
    """scenario: ship-verdict#全绿对齐 HEAD 判 ready"""
    # Given: S1 最新行 ok、final ok 且 commit 为 HEAD、无 review-findings.json
    change = ship_repo(git_repo)

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 true、reasons 为空、退出码 0；timeline 记了 ship 事件
    out = json.loads(p.stdout)
    assert out["ready"] is True, out
    assert out["reasons"] == []
    assert p.returncode == 0
    assert "\tship\tready" in (change / "timeline.md").read_text(encoding="utf-8")


def test_ship_draft_when_slice_red(git_repo):
    """scenario: ship-verdict#切片门禁红判 draft"""
    # Given: S1 最新行 red（更早一行 ok 不算数），final ok 对齐 HEAD
    change = ship_repo(git_repo, slice_verdict="red")

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false，reasons 有一条点名 S1，退出码 1
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("S1" in r for r in out["reasons"]), out["reasons"]
    assert p.returncode == 1


def test_ship_draft_when_slice_has_no_row(git_repo):
    """scenario: ship-verdict#切片门禁红判 draft（无记录变体）"""
    # Given: slices.json 有 S1 但 gate-report.md 没有 S1 的任何行
    change = ship_repo(git_repo, slice_verdict=None)

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false 且 reasons 点名 S1 无门禁记录
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("S1" in r and "无门禁记录" in r for r in out["reasons"]), out["reasons"]


def test_ship_draft_when_final_stale(git_repo):
    """scenario: ship-verdict#final 过期判 draft"""
    # Given: final 最新行 ok 但 commit 不是 HEAD
    change = ship_repo(git_repo, final_at_head=False)
    head = git(git_repo, "rev-parse", "HEAD")

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false；reasons 有一条同时含「过期」、记录 commit 与 HEAD 前缀
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("过期" in r and "0000000000" in r and head[:10] in r for r in out["reasons"]), out["reasons"]


def test_ship_draft_when_final_missing(git_repo):
    """scenario: ship-verdict#final 过期判 draft（未运行变体）"""
    # Given: gate-report.md 没有 final 行
    change = ship_repo(git_repo, final_verdict=None)

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false 且 reasons 指出 final 未运行
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("final" in r and "未运行" in r for r in out["reasons"]), out["reasons"]


def test_ship_draft_when_blocking_findings_open(git_repo):
    """scenario: ship-verdict#阻断 finding 未闭环判 draft"""
    # Given: 门禁全绿对齐 HEAD；review-findings.json 的 blocking 含 1 条
    change = ship_repo(git_repo, findings={"blocked": [], "blocking": [{"severity": "HIGH", "file": "a.py", "line": 1, "summary": "x"}], "deferred": [], "fix": None})

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false 且 reasons 给出数量 1 与 CRITICAL/HIGH 字样
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("1" in r and "CRITICAL/HIGH" in r for r in out["reasons"]), out["reasons"]


def test_ship_blocked_is_informational_only(git_repo):
    """scenario: ship-verdict#blocked 只作说明不作裁决"""
    # Given: 门禁全绿对齐 HEAD；review-findings.json 的 blocked 含一条 kind=infra
    blocked = [{"slice": "wave1", "kind": "infra", "reason": "integrator 未返回"}]
    change = ship_repo(git_repo, findings={"blocked": blocked, "blocking": [], "deferred": [], "fix": None})

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 true，blocked 原样带出
    out = json.loads(p.stdout)
    assert out["ready"] is True, out
    assert out["blocked"] == blocked
    assert p.returncode == 0


def test_ship_ready_without_plan(git_repo):
    """scenario: ship-verdict#非飞行模式直接 ready"""
    # Given: change 目录没有 slices.json
    change = ship_repo(git_repo, plan=False, slice_verdict=None, final_verdict=None)

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 true 且退出码 0
    out = json.loads(p.stdout)
    assert out["ready"] is True, out
    assert p.returncode == 0


def test_ship_blocks_open_findings_without_plan(git_repo):
    """scenario: ship-verdict#阻断 finding 未闭环判 draft（非飞行模式变体，铁律 4 与 slices.json 无关）"""
    # Given: change 目录没有 slices.json，但 review-findings.json 的 blocking 含 1 条
    change = ship_repo(git_repo, plan=False, slice_verdict=None, final_verdict=None,
                       findings={"blocked": [], "blocking": [{"severity": "CRITICAL"}], "deferred": [], "fix": None})

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false 且退出码 1
    out = json.loads(p.stdout)
    assert out["ready"] is False, out
    assert p.returncode == 1


def test_ship_markdown_lists_reasons_and_blocked(git_repo):
    """scenario: ship-verdict#draft 时输出 reasons 段落"""
    # Given: S1 红 + 1 条阻断 finding（两条 reasons），blocked 含一条 gate 条目
    blocked = [{"slice": "S1", "kind": "gate", "reason": "G4 gwt: test_x"}]
    change = ship_repo(git_repo, slice_verdict="red", findings={"blocked": blocked, "blocking": [{"severity": "HIGH"}], "deferred": [], "fix": None})

    # When: 运行 ship --markdown
    p = ship(git_repo, change, "--markdown")

    # Then: stdout 以「## 飞行门禁未全绿」开头，两条 reasons 各占一行，blocked 段带 kind 与 reason；退出码仍为 1
    out = p.stdout
    assert out.startswith("## 飞行门禁未全绿"), out
    reason_lines = [l for l in out.splitlines() if l.startswith("- ") and ("S1" in l or "CRITICAL/HIGH" in l)]
    assert len(reason_lines) >= 2, out
    assert "### 飞行中记 blocked 的切片" in out and "infra" not in out and "gate" in out and "G4 gwt: test_x" in out
    assert p.returncode == 1


def test_ship_markdown_empty_when_ready(git_repo):
    """scenario: ship-verdict#draft 时输出 reasons 段落（ready 反例）"""
    # Given: 全绿对齐 HEAD 且无 blocked
    change = ship_repo(git_repo)

    # When: 运行 ship --markdown
    p = ship(git_repo, change, "--markdown")

    # Then: stdout 为空串，退出码 0
    assert p.stdout.strip() == "", p.stdout
    assert p.returncode == 0


# ---------------------------------------------------------------- 命令 / skill / 工作流文本契约

def test_pr_ship_bidirectional_transition():
    """scenario: ship-verdict#命令文本包含双向转换"""
    # Given: template/.claude/commands/pr-ship.md
    text = (CMD / "pr-ship.md").read_text(encoding="utf-8")

    # When: 定位建 PR 步骤与自动修复步骤
    create = text.index("7. **创建 PR/MR**")
    autofix = text.index("10. **CRITICAL/HIGH 自动修复", create)

    # Then: 建 PR 前引用 ship 裁决；自动修复收尾引用 gh pr ready 与 --undo、glab 对应参数、记 pr-ready / pr-draft 事件；不再有模型自判散文
    assert "slice-gate.py ship" in text[create:autofix]
    tail = text[autofix:]
    assert "gh pr ready <num>" in tail and "gh pr ready --undo <num>" in tail
    assert "--ready" in tail and "--draft" in tail
    assert "timeline.py record pr-ready" in tail and "timeline.py record pr-draft" in tail
    assert "门禁未全绿 → 加 `--draft`" not in text


def test_apply_writes_full_findings_and_calls_ship():
    """scenario: ship-verdict#opsx-apply 收口写全量 review-findings 并调用 ship"""
    # Given: opsx-apply.md 与同名 skill
    for path in (CMD / "opsx-apply.md", SKILL):
        text = path.read_text(encoding="utf-8")

        # When: 取收口到 pr-ship 之间的文本
        tail = text[text.index("apply-done"):]

        # Then: 写入的 JSON 含 blocked；引用 slice-gate.py ship；不再有「final 未绿或有 blocked 切片」自判散文
        assert re.search(r"\{blocked, blocking, deferred, fix\}", tail), path
        assert "slice-gate.py ship" in tail, path
        assert "final 未绿或有 blocked 切片" not in text, path


def test_workflow_blocked_entries_carry_kind():
    """scenario: ship-verdict#工作流 blocked 条目带 kind"""
    # Given: opsx-apply.js
    text = WORKFLOW.read_text(encoding="utf-8")

    # When: 找出每处 blocked.push({...})
    pushes = [l for l in text.splitlines() if "blocked.push({" in l]

    # Then: 至少四处，每处都带 kind 且取值只有 'gate' / 'infra'
    assert len(pushes) >= 4, pushes
    for p in pushes:
        m = re.search(r"kind:\s*'(\w+)'", p)
        assert m and m.group(1) in ("gate", "infra"), p


# ---------------------------------------------------------------- flight-wave-fixes（scenario: ship-final-freshness#*）
# S1 已实现记账豁免；两条守卫（改源码 / 改计划仍判过期）锁住白名单边界。


def _commit_after_final(git_repo, touch):
    """ship_repo 记下 S1 与 final（commit = 当时 HEAD）；先把飞行记录入库，再提交一次 touch(change) 造成的改动。返回 change 目录。"""
    change = ship_repo(git_repo)
    commit_all(git_repo, "chore(flight): 记录")
    touch(change)
    commit_all(git_repo, "after final")
    return change


def _append(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def test_ship_ready_after_bookkeeping_commits(git_repo):
    """scenario: ship-final-freshness#ship-ignores-bookkeeping-commits"""
    # Given: S1 与 final 都在 commit F 记为 ok；之后两个 commit 只改了 change 目录的 gate-report.md、timeline.md、tasks.md、evidence.log、review-findings.json
    def touch(change):
        for name in ("timeline.md", "tasks.md", "evidence.log"):
            _append(change / name, "x")
        write(change / "review-findings.json", json.dumps({"blocked": [], "blocking": [], "deferred": [], "fix": None}))
    change = _commit_after_final(git_repo, touch)

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 true，reasons 里没有「过期」，退出码 0
    out = json.loads(p.stdout)
    assert out["ready"] is True, out
    assert not any("过期" in r for r in out["reasons"]), out["reasons"]
    assert p.returncode == 0


def test_ship_stale_after_code_change(git_repo):  # 既有行为守卫：白名单之外的改动在判据引入前后都判过期，故不标 xfail
    """scenario: ship-final-freshness#ship-flags-code-change-after-final"""
    # Given: final 在 commit F 记为 ok；之后的 commit 改了源码 src/app.py
    change = _commit_after_final(git_repo, lambda change: write(git_repo / "src" / "app.py", "x = 1\n"))

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false，reasons 有一条含「过期」
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("过期" in r for r in out["reasons"]), out["reasons"]


def test_ship_stale_after_plan_change(git_repo):  # 既有行为守卫：同上
    """scenario: ship-final-freshness#ship-flags-plan-change-after-final"""
    # Given: final 在 commit F 记为 ok；之后的 commit 改了 change 目录的 slices.json（计划，不是记账）
    def touch(change):
        data = json.loads((change / "slices.json").read_text(encoding="utf-8"))
        data["slices"][0]["title"] = "S1 revised"
        write(change / "slices.json", json.dumps(data))
    change = _commit_after_final(git_repo, touch)

    # When: 运行 ship
    p = ship(git_repo, change)

    # Then: ready 为 false，reasons 有一条含「过期」
    out = json.loads(p.stdout)
    assert out["ready"] is False
    assert any("过期" in r for r in out["reasons"]), out["reasons"]

# ---------------------------------------------------------------- 摘自原仓 #40（flight-hardening）· scenario: gate-change-scope#final-fresh-*
# flight-hardening S1 的 scenario 测试。


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_final_fresh_ignores_other_change_bookkeeping(git_repo):
    # Given: changes 下有 c、b 两个 change；c 的 final 记在提交 X 且 ok；X 之后一次提交只改了 b 的 gate-report.md 与 timeline.md
    c = ship_repo(git_repo)
    b = git_repo / "openspec" / "changes" / "b"
    write(b / "gate-report.md", "# Gate Report\n")
    write(b / "timeline.md", "2026-10-10T00:00:00Z\tfinal\tok\n")
    commit_all(git_repo, "chore(flight): 记录 b")

    # When: 对 c 运行 ship；之后再提交一次代码改动，再对 c 运行 ship
    before = json.loads(ship(git_repo, c).stdout)["reasons"]
    write(git_repo / "src" / "x.py", "x = 1\n")
    commit_all(git_repo, "feat: x")
    after = json.loads(ship(git_repo, c).stdout)["reasons"]

    # Then: 前者 reasons 没有「过期」；代码改动之后 reasons 含「过期」
    assert not any("过期" in r for r in before), before
    assert any("过期" in r for r in after), after


@pytest.mark.xfail(strict=True, reason="workflow-edition S2 尚未实现")
def test_final_fresh_ignores_interfaces_summary(git_repo):
    # Given: change c 的 final 记在提交 X 且 ok；X 之后一次提交只改了 c 的 slices/_interfaces.md
    c = ship_repo(git_repo)
    write(c / "slices" / "_interfaces.md", "## S1\n- def run(x):\n")
    commit_all(git_repo, "chore(flight): 记录")

    # When: 对 c 运行 ship
    reasons = json.loads(ship(git_repo, c).stdout)["reasons"]

    # Then: reasons 没有「过期」
    assert not any("过期" in r for r in reasons), reasons
