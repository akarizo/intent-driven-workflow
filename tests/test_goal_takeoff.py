"""起飞门禁认会话 /goal 与人类中途插话（scenario: goal-takeoff-authorization#goal-active-approves-without-approval-word、
#goal-active-waives-freshness、#goal-ended-restores-freshness、#goal-sidechain-ignored、
#queued-command-counts-only-human-origin，共 5 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。
夹具形状取自 Claude Code v2.1.319 真实转录（afa d2d21d53 · stc-foundation 6408285e / fe89e6cc）。"""
import json
import os
from datetime import datetime, timezone

from conftest import run_hook

LONG_GOAL = ("后续的修订都按你推荐选择最优选择推荐，继续完成，从uat拉取更多的航班进行验证，"
             "至少每个dlib 10-30个，一切稳妥后pr-ship，再发布test环境跑更多的8月份验证，有问题就修，直到逻辑可靠")


def epoch(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def human(text, ts):
    return {"type": "user", "isSidechain": False, "isMeta": False, "userType": "external",
            "timestamp": ts, "message": {"role": "user", "content": text}}


def goal(ts, met=False, sentinel=None, reason=None, sidechain=False):
    """goal_status 附件：设立 = met False + sentinel；评估 = 带 reason；/goal clear = met True + sentinel。"""
    att = {"type": "goal_status", "met": met, "condition": LONG_GOAL}
    if sentinel is not None:
        att["sentinel"] = sentinel
    if reason is not None:
        att["reason"] = reason
    return {"type": "attachment", "isSidechain": sidechain, "userType": "external",
            "timestamp": ts, "attachment": att}


def queued(prompt, ts, kind="human"):
    """模型工作中途进来的消息：只留 queued_command 附件，没有对应 user 行。"""
    att = {"type": "queued_command", "prompt": prompt, "commandMode": "prompt",
           "origin": {"kind": kind}, "timestamp": ts}
    if kind == "human":
        att["humanTurn"] = True
    return {"type": "attachment", "isSidechain": False, "userType": "external",
            "timestamp": ts, "attachment": att}


def transcript(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path


def change_dir(tmp_path, plan_iso):
    """最小 change 目录，计划工件 mtime 钉在 plan_iso。"""
    d = tmp_path / "openspec" / "changes" / "demo"
    (d / "specs" / "cap").mkdir(parents=True)
    for rel in ("proposal.md", "design.md", "tasks.md", "slices.json", "spec.html", "specs/cap/spec.md"):
        (d / rel).write_text("x", encoding="utf-8")
    for rel in ("proposal.md", "design.md", "tasks.md", "slices.json", "specs/cap/spec.md"):
        os.utime(d / rel, (epoch(plan_iso), epoch(plan_iso)))
    return d


def cli(d, sess):
    return run_hook("takeoff-gate", "--change-dir", str(d), "--session", str(sess))


def afa_rows():
    """afa 实测序列：15:18 口头批准 → 16:01 设立 goal → 16:47 评估未达成（计划在 16:47:11 又改过）。"""
    return [
        human("起飞 授权提交", "2026-11-09T15:18:56Z"),
        goal("2026-11-09T16:01:36Z", sentinel=True),
        goal("2026-11-09T16:47:47Z", reason="S6 尚未实施"),
    ]


def test_goal_active_approves_without_approval_word(tmp_path):
    # Given: 人类只发过长指令（无 /opsx-apply、无短批准词），随后设立了长条件 goal；计划工件早于 goal
    d = change_dir(tmp_path, "2026-11-09T15:00:00Z")
    sess = transcript(tmp_path / "s.jsonl", [
        human("完成后每个dlib都需要去uat拉取5-10个航班进行实际验证，并把结论写进 MR 正文里", "2026-11-09T15:29:58Z"),
        goal("2026-11-09T16:01:36Z", sentinel=True),
    ])

    # When: 以 CLI 模式判定
    p = cli(d, sess)

    # Then: 批准成立，证据行含 goal 设立时间且摘要以 /goal 开头
    assert p.returncode == 0, p.stderr
    assert "2026-11-09T16:01:36Z" in p.stdout
    assert p.stdout.split(" · ", 1)[1].startswith("/goal"), p.stdout


def test_goal_active_waives_freshness(tmp_path):
    # Given: afa 实测序列，计划工件在 16:47:11 又改过（晚于批准与 goal 设立）
    d = change_dir(tmp_path, "2026-11-09T16:47:11Z")
    sess = transcript(tmp_path / "s.jsonl", afa_rows())
    dispatch = {"tool_name": "Agent", "cwd": str(tmp_path), "transcript_path": str(sess),
                "tool_input": {"subagent_type": "slice-executor",
                               "prompt": "切片包：`openspec/changes/demo/slices/S6.md`"}}

    # When: 分别以 CLI 模式与 hook 模式判定
    p = cli(d, sess)
    h = run_hook("takeoff-gate", stdin=json.dumps(dispatch))

    # Then: CLI 放行且证据来自 /goal；hook 静默放行，不再报「批准已过期」
    assert p.returncode == 0, p.stderr
    assert p.stdout.split(" · ", 1)[1].startswith("/goal"), p.stdout
    assert h.returncode == 0 and h.stdout.strip() == "", h.stdout


def test_goal_ended_restores_freshness(tmp_path):
    # Given: afa 实测序列与过期的计划 mtime；两种 goal 结束形状（评估达成 / /goal clear）
    d = change_dir(tmp_path, "2026-11-09T16:47:11Z")
    active = transcript(tmp_path / "active.jsonl", afa_rows())
    achieved = transcript(tmp_path / "achieved.jsonl",
                          afa_rows() + [goal("2026-11-10T01:00:00Z", met=True, reason="条件已满足")])
    cleared = transcript(tmp_path / "cleared.jsonl",
                         afa_rows() + [goal("2026-11-10T01:00:00Z", met=True, sentinel=True)])

    # When: 分别判定
    p0, p1, p2 = cli(d, active), cli(d, achieved), cli(d, cleared)

    # Then: goal 生效时放行；结束后回到原判据——批准早于计划改动，非 0 且点名重新批准，两种结束形状结论相同
    assert p0.returncode == 0, p0.stderr
    for p in (p1, p2):
        assert p.returncode != 0, p.stdout
        assert "重新批准" in p.stderr


def test_goal_sidechain_ignored(tmp_path):
    # Given: 两份转录只差一处——同一条 met=false 的 goal_status，一份在主链，一份 isSidechain=true；都没有人类批准
    d = change_dir(tmp_path, "2026-11-09T15:00:00Z")
    main = transcript(tmp_path / "main.jsonl", [human("继续", "2026-11-09T15:10:00Z"),
                                                 goal("2026-11-09T16:01:36Z", sentinel=True)])
    side = transcript(tmp_path / "side.jsonl", [human("继续", "2026-11-09T15:10:00Z"),
                                                 goal("2026-11-09T16:01:36Z", sentinel=True, sidechain=True)])

    # When: 分别判定
    pm, ps = cli(d, main), cli(d, side)

    # Then: 主链那份放行；sidechain 那份不代表主会话授权，非 0
    assert pm.returncode == 0, pm.stderr
    assert ps.returncode != 0, ps.stdout


def test_queued_command_counts_only_human_origin(tmp_path):
    # Given: 计划 00:41 改过；之后只有一条 00:42 的 queued_command「起飞」，没有对应 user 行；五种 origin.kind
    d = change_dir(tmp_path, "2026-11-10T00:41:10Z")
    base = [human("起飞", "2026-11-09T23:58:51Z")]
    kinds = ("human", "peer", "task-notification", "coordinator", "auto-continuation")
    sessions = {k: transcript(tmp_path / ("%s.jsonl" % k), base + [queued("起飞", "2026-11-10T00:42:07Z", kind=k)])
                for k in kinds}

    # When: 分别判定
    results = {k: cli(d, s) for k, s in sessions.items()}

    # Then: 只有 human 插话构成批准，证据含 00:42 时间与「起飞」；其余来源都不是人，仍判批准过期
    ok = results["human"]
    assert ok.returncode == 0, ok.stderr
    assert "2026-11-10T00:42:07Z" in ok.stdout and "起飞" in ok.stdout
    for k in kinds[1:]:
        assert results[k].returncode != 0, (k, results[k].stdout)
