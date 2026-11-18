"""门禁读共用目录的留痕、record 并回分支、首轮 start 清残留（scenario: slice-evidence-shared#gate-reads-rows-written-from-another-worktree、
#gate-fails-when-hook-alive-but-no-test-run、#record-merges-slice-rows-into-branch-log、#first-round-start-clears-stale-evidence，共 4 条）。
骨架：strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import json

from conftest import git, run_hook, write
from test_slice_gate import gate_repo

RED = "2026-11-18T00:00:01Z\tS1\tFAIL\tpython3 -m pytest -q tests/test_mod.py\n"
GREEN = "2026-11-18T00:00:02Z\tS1\tPASS\tpython3 -m pytest -q tests/test_mod.py\n"
OTHER = "2026-11-18T00:00:03Z\tS2\tPASS\tpython3 -m pytest -q tests/test_other.py\n"


def shared_log(git_repo, slice_id="S1"):
    path = git_repo / ".git" / "flight-evidence" / "c" / (slice_id + ".log")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def gate(cwd, change_dir="openspec/changes/c"):
    return json.loads(run_hook("slice-gate", "gate", "S1", "--change-dir", change_dir, cwd=cwd).stdout)


def test_gate_reads_rows_written_from_another_worktree(git_repo):
    # Given: 上一轮在别的 worktree 里留下了本片先红后绿的留痕（在共用目录）；本轮的门禁跑在另一间新开的 worktree 里，
    #        那里的 change 目录没有 evidence.log
    gate_repo(git_repo)
    base = json.loads((git_repo / ".openspec-slice").read_text(encoding="utf-8"))["base"]
    shared_log(git_repo).write_text(RED + GREEN, encoding="utf-8")
    other = git_repo.parent / "iso-round2"
    git(git_repo, "worktree", "add", "-q", "--detach", str(other), "HEAD")
    assert run_hook("slice-gate", "start", "S1", "--change-dir", "openspec/changes/c", "--base", base, cwd=other).returncode == 0

    # When: 在新 worktree 里运行 gate S1
    out = gate(other)

    # Then: 通过；读到了共用目录里的留痕：不报「无 evidence.log」，hooks_missing 为 false，没有 G5 项
    assert out["ok"] is True, out
    assert out["hooks_missing"] is False
    assert not [x for x in out["failed"] + out["warnings"] if x.startswith("G5")], out


def test_gate_fails_when_hook_alive_but_no_test_run(git_repo):
    # Given: 共用目录里本片的留痕文件存在但没有任何行（hook 在工作，执行体一次测试都没跑过）
    gate_repo(git_repo)
    shared_log(git_repo).write_text("", encoding="utf-8")

    # When: 运行 gate S1
    out = gate(git_repo)

    # Then: 判红，failed 含 G5 且写明没跑过测试；hooks_missing 为 false（不是 hook 没装）
    assert out["ok"] is False
    assert any(f.startswith("G5 evidence") and "没跑过测试" in f for f in out["failed"]), out["failed"]
    assert out["hooks_missing"] is False


def test_record_merges_slice_rows_into_branch_log(git_repo):
    # Given: 分支上的 evidence.log 已有一行主会话的记录；共用目录里有 S1 的两行与 S2 的一行
    change = gate_repo(git_repo)
    head = git(git_repo, "rev-parse", "HEAD")
    main_row = "2026-11-17T00:00:00Z\t-\tPASS\tpython3 -m pytest -q tests\n"
    write(change / "evidence.log", main_row)
    shared_log(git_repo).write_text(RED + GREEN, encoding="utf-8")
    shared_log(git_repo, "S2").write_text(OTHER, encoding="utf-8")
    payload = json.dumps({"slice": "S1", "ok": True, "commit": head, "failed": [], "warnings": []})

    # When: 连续两次运行 record --json（integrator 重派时会重复执行）
    for _ in range(2):
        p = run_hook("slice-gate", "record", "--change-dir", str(change), "--json", payload, cwd=git_repo)
        assert p.returncode == 0, p.stderr

    # Then: 分支上的 evidence.log 在原有行之后恰好多出 S1 的两行（不重复）、没有 S2 的行；
    #       共用目录里 S1 的文件已收走，S2 的还在
    assert (change / "evidence.log").read_text(encoding="utf-8") == main_row + RED + GREEN
    assert not shared_log(git_repo).exists()
    assert shared_log(git_repo, "S2").read_text(encoding="utf-8") == OTHER


def test_first_round_start_clears_stale_evidence(git_repo):
    # Given: 共用目录里留着上一次飞行的 S1 留痕；当前 worktree 没有标记
    change = gate_repo(git_repo)
    (git_repo / ".openspec-slice").unlink()
    head = git(git_repo, "rev-parse", "HEAD")

    def start(*extra):
        shared_log(git_repo).write_text(RED, encoding="utf-8")
        p = run_hook("slice-gate", "start", "S1", "--change-dir", str(change), *extra, cwd=git_repo)
        assert p.returncode == 0, (p.stdout, p.stderr)
        (git_repo / ".openspec-slice").unlink()
        return shared_log(git_repo).exists()

    # When: 分别以首轮（不带接续参数）、--continue、--resume-checkpoint 运行 start S1
    first, cont, resume = start(), start("--continue", head), start("--resume-checkpoint")

    # Then: 首轮把残留清掉；两种接续都保留上一轮的留痕
    assert (first, cont, resume) == (False, True, True)
