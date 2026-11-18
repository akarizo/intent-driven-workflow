"""test-evidence.py 把切片留痕写进 git 共用目录（scenario: slice-evidence-shared#hook-writes-slice-rows-to-common-dir、
#hook-leaves-heartbeat-on-any-bash、#hook-recognizes-verify-script-runs，共 3 条）。
切片 S2 已实现，骨架标记已去。"""
import json

from conftest import run_hook, write
from test_evidence_timeline import bash_event, marker_repo


def shared_log(git_repo, slice_id="S1", change="c"):
    """<git common dir>/flight-evidence/<change>/<切片>.log。"""
    return git_repo / ".git" / "flight-evidence" / change / (slice_id + ".log")


def rows(path):
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fire(git_repo, cmd, stdout="", event="PostToolUse"):
    return run_hook("test-evidence", stdin=bash_event(cmd, stdout=stdout, event=event, cwd=git_repo), cwd=git_repo)


def test_hook_writes_slice_rows_to_common_dir(git_repo):
    # Given: 根目录有指向切片 S1 的标记；一条 pytest 通过的 Bash 事件，接着一条 pytest 失败的事件
    change = marker_repo(git_repo)

    # When: 两次运行 test-evidence.py
    fire(git_repo, "python3 -m pytest -q tests", stdout="3 passed in 0.1s")
    fire(git_repo, "python3 -m pytest -q tests", stdout="1 failed", event="PostToolUseFailure")

    # Then: 两行都写进共用目录里本片的留痕文件，格式不变；工作树里的 evidence.log 不出现
    got = rows(shared_log(git_repo))
    assert [(r[1], r[2]) for r in got] == [("S1", "PASS"), ("S1", "FAIL")], got
    assert all("pytest" in r[3] for r in got)
    assert not (change / "evidence.log").exists()


def test_hook_leaves_heartbeat_on_any_bash(git_repo):
    # Given: 根目录有指向切片 S1 的标记；一条不是测试运行的 Bash 事件（git status）
    change = marker_repo(git_repo)

    # When: 运行 test-evidence.py
    p = fire(git_repo, "git status --short")

    # Then: 退出 0；共用目录里本片的留痕文件已存在但没有任何行（心跳：hook 在工作）；工作树里的 evidence.log 不出现
    assert p.returncode == 0
    assert shared_log(git_repo).is_file() and rows(shared_log(git_repo)) == []
    assert not (change / "evidence.log").exists()


def test_hook_recognizes_verify_script_runs(git_repo):
    # Given: 切片 S1 的 verify 是包装脚本 `bash openspec/changes/c/verify/viewer.sh test src`，gate.test 是 `bash tools/full.sh`；
    #        命令文本里都没有 pytest / vitest 之类的运行器名字
    change = marker_repo(git_repo)
    write(change / "slices.json", json.dumps({"version": 1, "change": "c", "gate": {"test": "bash tools/full.sh"}, "slices": [
        {"id": "S1", "title": "S1", "scenarios": [], "owns": ["src/**"], "deps": [],
         "verify": "bash openspec/changes/c/verify/viewer.sh test src"}], "scenario_tests": {}}))

    # When: 依次喂三条 Bash 事件：跑 verify 脚本、跑 gate.test 脚本、ls
    fire(git_repo, "bash openspec/changes/c/verify/viewer.sh test src/x 2>&1 | tail -5", stdout="2 passed")
    fire(git_repo, "bash tools/full.sh", stdout="1 failed")
    fire(git_repo, "ls tools")

    # Then: 前两条各记一行（PASS、FAIL），ls 不记
    got = rows(shared_log(git_repo))
    assert [(r[1], r[2]) for r in got] == [("S1", "PASS"), ("S1", "FAIL")], got
    assert "viewer.sh" in got[0][3] and "tools/full.sh" in got[1][3]
