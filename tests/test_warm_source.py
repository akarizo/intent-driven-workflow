"""warm-source-selection 的 scenario 骨架（strict xfail；切片 S1 实现后去掉标记即解锁）。"""
import os
import subprocess

from conftest import commit_all
from test_baseline_incremental import PLAIN_FULL, setup_change
from test_baseline_warm import last_json, new_change, warm

# 结果都绿、又彼此不同的全量命令（只改输出样式）
CMD_A = PLAIN_FULL + " -o console_output_style=classic"
CMD_B = PLAIN_FULL + " -o console_output_style=progress"


def commit_at(repo, msg, epoch):
    """以固定的 author / committer 时间提交全部改动（committer 时间精度是秒）。"""
    env = dict(os.environ, GIT_AUTHOR_DATE="%d +0000" % epoch, GIT_COMMITTER_DATE="%d +0000" % epoch)
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=str(repo), check=True, capture_output=True, env=env)


def touch_later(path, offset=100):
    """把文件修改时间推到「现在 + offset 秒」，让按 mtime 选来源的旧规则选中它。"""
    t = os.path.getmtime(path) + offset
    os.utime(path, (t, t))


def test_warm_picks_latest_committed_change(git_repo):
    # Given: change old 与 new 的 `gate.test` 不同；new 的 `slices.json` 在 old 之后提交；之后把 old 的 `slices.json` 的修改时间改得比 new 晚
    old = setup_change(git_repo, change="old", gate_test=CMD_A, old_red=False, commit=False)
    commit_at(git_repo, "plan old", 1700000000)
    setup_change(git_repo, change="new", gate_test=CMD_B, old_red=False, commit=False)
    commit_at(git_repo, "plan new", 1700000100)
    touch_later(old / "slices.json")
    d = new_change(git_repo)

    # When: 对新 change c 运行 warm
    p = warm(git_repo, d)

    # Then: 退出 0，stdout 的 `test_cmd` 是 new 的 `gate.test`
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert last_json(p.stdout)["test_cmd"] == CMD_B


def test_warm_breaks_commit_tie_by_name(git_repo):
    # Given: change alpha 与 beta 的 `gate.test` 不同，两者的 `slices.json` 在同一次提交里
    alpha = setup_change(git_repo, change="alpha", gate_test=CMD_A, old_red=False, commit=False)
    setup_change(git_repo, change="beta", gate_test=CMD_B, old_red=False, commit=False)
    commit_all(git_repo, "plan alpha + beta")
    touch_later(alpha / "slices.json")
    d = new_change(git_repo)

    # When: 对新 change c 运行 warm
    p = warm(git_repo, d)

    # Then: 退出 0，stdout 的 `test_cmd` 是 beta 的 `gate.test`
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert last_json(p.stdout)["test_cmd"] == CMD_B


def test_warm_ranks_uncommitted_after_committed(git_repo):
    # Given: change kept 的 `slices.json` 已提交；change draft 的 `slices.json` 从没提交过，修改时间更晚；两者 `gate.test` 不同
    setup_change(git_repo, change="kept", gate_test=CMD_A, old_red=False)
    draft = setup_change(git_repo, change="draft", gate_test=CMD_B, old_red=False, commit=False)
    touch_later(draft / "slices.json")
    d = new_change(git_repo)

    # When: 对新 change c 运行 warm
    p = warm(git_repo, d)

    # Then: 退出 0，stdout 的 `test_cmd` 是 kept 的 `gate.test`
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert last_json(p.stdout)["test_cmd"] == CMD_A
