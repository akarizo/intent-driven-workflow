"""baseline 不改计划文件、全量耗时记在基线里、gitlink 计入内容快照（scenario: plan-hygiene#baseline-leaves-plan-file-untouched、
#approval-survives-baseline-rerun、#baseline-stops-without-gate-test、#incremental-baseline-keeps-suite-sec、
#running-marker-carries-last-suite-sec、#running-baseline-hint-shows-last-suite-sec、#suite-sec-resolver-prefers-baseline、
#staged-gitlink-commit-keeps-baseline-fresh，共 8 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json
import os
import shlex
import sys
import time
from datetime import datetime, timezone

import pytest

from conftest import commit_all, load_hook, run_hook, write
from final_helpers import baseline, change_and_commit, make_repo
from submodule_helpers import g
from test_approval_gate import human, transcript
from test_slice_gate import plan, slice_, write_plan

PENDING = pytest.mark.xfail(strict=True, reason="骨架：切片 S1 实现后去掉")

PAST = 1_600_000_000  # 2020-09-13，早于任何一次测试运行

# gate.test 替身：运行期间读 gate-baseline.json，须是运行标记；设了 WANT_SUITE_SEC 时其 full_suite_sec 还须等于它
CHECK_MARKER = """
    import json
    import os
    import sys

    d = json.load(open("openspec/changes/c/gate-baseline.json", encoding="utf-8"))
    if d.get("running") is not True:
        sys.exit(1)
    want = os.environ.get("WANT_SUITE_SEC")
    sys.exit(0 if want is None or d.get("full_suite_sec") == float(want) else 1)
"""


def _bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _run_baseline(repo, d, *args, env=None):
    return run_hook("slice-gate", "baseline", "--change-dir", str(d), *args, cwd=repo, env=env)


@PENDING
def test_baseline_leaves_plan_file_untouched(git_repo):
    # Given: 已提交的 change，gate.test 是直接的 pytest 调用，slices.json 里没有 full_suite_sec；它的修改时间钉在过去
    d = make_repo(git_repo)
    plan_file = d / "slices.json"
    before = plan_file.read_bytes()
    os.utime(plan_file, (PAST, PAST))

    # When: 运行 slice-gate.py baseline
    p = _run_baseline(git_repo, d)

    # Then: 退出 0；slices.json 的字节与修改时间都没变；gate-baseline.json 顶层 full_suite_sec 是数值
    assert p.returncode == 0, p.stdout + p.stderr
    assert plan_file.read_bytes() == before
    assert plan_file.stat().st_mtime == PAST
    assert _is_number(_bl(d).get("full_suite_sec")), _bl(d)


@PENDING
def test_approval_survives_baseline_rerun(git_repo, tmp_path):
    # Given: 跑过一次 baseline 的 change；计划工件的修改时间在过去，人类此刻在会话里说「起飞」
    d = make_repo(git_repo)
    assert _run_baseline(git_repo, d).returncode == 0
    for rel in ("proposal.md", "slices.json"):
        os.utime(d / rel, (PAST, PAST))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session = transcript(tmp_path / "session.jsonl", [human("起飞", now)])

    # When: 批准之后再跑一次 baseline --full，然后运行起飞门禁
    assert _run_baseline(git_repo, d, "--full").returncode == 0
    p = run_hook("takeoff-gate", "--change-dir", str(d), "--session", str(session))

    # Then: 起飞门禁退出 0，stdout 是那条批准证据
    assert p.returncode == 0, p.stderr
    assert "起飞" in p.stdout


@PENDING
def test_baseline_stops_without_gate_test(git_repo):
    # Given: 已提交的 change，gate.test 为空；仓库里有 tests/ 目录（探测得出 pytest 命令）
    d = git_repo / "openspec" / "changes" / "c"
    write_plan(d, plan([slice_("S1", ["src/**"])], gate={"test": None, "lint": None, "typecheck": None}))
    write(git_repo / "tests" / "test_ok.py", "def test_ok():\n    assert True\n")
    commit_all(git_repo, "artifacts")
    before = (d / "slices.json").read_bytes()

    # When: 运行 slice-gate.py baseline
    p = _run_baseline(git_repo, d)

    # Then: 退出非 0，stderr 点名 gate.test；没有生成 gate-baseline.json，slices.json 字节没变
    assert p.returncode != 0, p.stdout
    assert "gate.test" in p.stderr, p.stderr
    assert not (d / "gate-baseline.json").exists()
    assert (d / "slices.json").read_bytes() == before


@PENDING
def test_incremental_baseline_keeps_suite_sec(git_repo):
    # Given: 跑过一次全量基线的 change（full_suite_sec 为某个数值）；之后只改了一个测试文件并提交
    d = make_repo(git_repo)
    first = baseline(git_repo, d)
    more = (git_repo / "tests" / "test_a.py").read_text(encoding="utf-8") + "\n\ndef test_a_again():\n    assert a() == 1\n"
    change_and_commit(git_repo, "tests/test_a.py", more)

    # When: 再运行 slice-gate.py baseline
    second = baseline(git_repo, d)

    # Then: 新基线是增量的，full_suite_sec 与第一次相同
    assert second["mode"] == "incremental", second
    assert _is_number(first.get("full_suite_sec")), first
    assert second.get("full_suite_sec") == first["full_suite_sec"], (first, second)


@PENDING
def test_running_marker_carries_last_suite_sec(git_repo):
    # Given: 跑过一次基线的 change；gate.test 是运行期间读取 gate-baseline.json 的脚本
    write(git_repo / "check_marker.py", CHECK_MARKER)
    d = git_repo / "openspec" / "changes" / "c"
    write_plan(d, plan([slice_("S1", ["src/**"])],
                       gate={"test": "%s check_marker.py" % shlex.quote(sys.executable), "lint": None, "typecheck": None}))
    commit_all(git_repo, "artifacts")
    assert _run_baseline(git_repo, d).returncode == 0
    last = _bl(d).get("full_suite_sec")
    assert _is_number(last), _bl(d)

    # When: 再运行 baseline --full，脚本检查运行标记里的 full_suite_sec 是否等于上一份基线的值
    p = _run_baseline(git_repo, d, "--full", env={"WANT_SUITE_SEC": repr(float(last))})

    # Then: 脚本看到了带该值的运行标记（退出 0，基线绿）
    assert p.returncode == 0, p.stdout + p.stderr
    assert _bl(d)["ok"] is True


@PENDING
def test_running_baseline_hint_shows_last_suite_sec(git_repo):
    # Given: gate-baseline.json 是进程仍在的运行标记，full_suite_sec 为 12.5；slices.json 里没有 full_suite_sec
    d = git_repo / "openspec" / "changes" / "c"
    write_plan(d, plan([slice_("S1", ["src/**"])], gate={"test": "true", "lint": None, "typecheck": None}))
    commit_all(git_repo, "artifacts")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write(d / "gate-baseline.json", json.dumps({"running": True, "pid": os.getpid(), "started": started,
                                                 "full_suite_sec": 12.5}))

    # When: 运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0，stderr 含「仍在跑」与「12.5 秒」
    assert p.returncode != 0, p.stdout
    assert "仍在跑" in p.stderr and "12.5 秒" in p.stderr, p.stderr


@PENDING
def test_suite_sec_resolver_prefers_baseline(tmp_path):
    # Given: 一个 change 目录，计划里旧的 gate.full_suite_sec 为 816
    sg = load_hook("slice-gate")
    d = tmp_path / "openspec" / "changes" / "c"
    legacy = plan([slice_("S1", ["src/**"])], gate={"test": "true", "full_suite_sec": 816})
    bare = plan([slice_("S1", ["src/**"])], gate={"test": "true"})
    write_plan(d, legacy)

    # When: 在四种状态下各调用一次 suite_sec
    no_baseline = sg.suite_sec(str(d), legacy)
    write(d / "gate-baseline.json", json.dumps({"ok": True, "full_suite_sec": 300.5}))
    from_baseline = sg.suite_sec(str(d), legacy)
    write(d / "gate-baseline.json", json.dumps({"ok": True, "full_suite_sec": True}))
    bool_falls_back = sg.suite_sec(str(d), legacy)
    (d / "gate-baseline.json").unlink()
    nothing = sg.suite_sec(str(d), bare)

    # Then: 依次是旧字段 816、基线的 300.5、布尔值不算数回退到 816、都没有时 None
    assert (no_baseline, from_baseline, bool_falls_back, nothing) == (816, 300.5, 816, None)


@PENDING
def test_staged_gitlink_commit_keeps_baseline_fresh(git_repo, tmp_path):
    # Given: 带子仓 mods/sub 的仓库，change 的计划已提交；子仓里新增一个提交，父仓把新 gitlink 暂存但没提交
    origin = tmp_path / "origin"
    origin.mkdir()
    g(origin, "init", "-q", "-b", "main")
    g(origin, "config", "user.email", "t@example.com")
    g(origin, "config", "user.name", "t")
    write(origin / "README.md", "# sub\n")
    g(origin, "add", "-A")
    g(origin, "commit", "-q", "-m", "s0")
    d = make_repo(git_repo)
    g(git_repo, "submodule", "add", "-q", str(origin), "mods/sub")
    commit_all(git_repo, "add submodule")
    sub = git_repo / "mods" / "sub"
    g(sub, "config", "user.email", "t@example.com")
    g(sub, "config", "user.name", "t")
    write(sub / "extra.txt", "x\n")
    g(sub, "add", "extra.txt")
    g(sub, "commit", "-q", "-m", "s1")
    g(git_repo, "add", "mods/sub")

    # When: 运行 baseline，把 gitlink 与基线文件一起提交，再运行 preflight
    out = baseline(git_repo, d)
    p = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 基线绿；preflight 退出 0，不报「基线过期」
    assert out["ok"] is True, out
    assert p.returncode == 0, p.stderr
    assert "基线过期" not in p.stderr
