"""test-tiers.py allow-slow 的 --limit-sec / --expires
（scenario: tier-budgets#allow-slow-writes-limit-and-expires、#allow-slow-rejects-bad-limit-or-date）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import datetime
import json

from conftest import run_hook, write
from test_tiers_cli import human, transcript

BIG = "tests/unit/test_a.py::test_big"
OTHER = "tests/unit/test_a.py::test_other"


def setup(repo):
    """分层文件 slow_allow 为空；转录里最新一条人类消息同时放行 test_big 与 test_other。→ (分层文件路径, 转录路径)。"""
    path = repo / "openspec" / "test-tiers.json"
    write(path, json.dumps({"unit": {"paths": ["tests/unit/**"], "cmd": "true"}, "regions": {}, "slow_allow": {}}))
    session = repo.parent / "session.jsonl"
    transcript(session, [human("放行 test_big 与 test_other，读 40MB 真实样本", "2026-11-18T03:12:00Z")])
    return path, session


def in_days(n):
    return (datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=n)).isoformat()


def test_allow_slow_writes_limit_and_expires(git_repo):
    # Given: 分层文件的 slow_allow 为空；最新一条人类消息放行了 test_big 与 test_other
    path, session = setup(git_repo)
    expires = in_days(30)

    # When: 带 --limit-sec 90 --expires <30 天后> 放行 test_big；跑 check；再不带这两个参数放行 test_other
    p1 = run_hook("test-tiers", "allow-slow", BIG, "--reason", "读大样本", "--limit-sec", "90", "--expires", expires,
                  "--session", str(session), cwd=git_repo)
    chk = run_hook("test-tiers", "check", cwd=git_repo)
    p2 = run_hook("test-tiers", "allow-slow", OTHER, "--reason", "同上", "--session", str(session), cwd=git_repo)

    # Then: 第一条带上限与期限，分层文件仍合法；第二条照常写入并提示可以写上限与期限
    assert p1.returncode == 0, p1.stdout + p1.stderr
    allow = json.loads(path.read_text(encoding="utf-8"))["slow_allow"]
    assert (allow[BIG]["limit_sec"], allow[BIG]["expires"], allow[BIG]["reason"]) == (90, expires, "读大样本"), allow
    assert "放行 test_big" in allow[BIG]["approved"], allow
    assert chk.returncode == 0, chk.stdout + chk.stderr
    assert p2.returncode == 0 and OTHER in allow and "limit_sec" not in allow[OTHER], p2.stdout + p2.stderr
    assert any("--limit-sec" in l and "--expires" in l for l in p2.stderr.splitlines()), p2.stderr


def test_allow_slow_rejects_bad_limit_or_date(git_repo):
    # Given: 同样的分层文件与转录
    path, session = setup(git_repo)
    before = path.read_text(encoding="utf-8")
    base = ("allow-slow", BIG, "--reason", "读大样本", "--session", str(session))

    # When: 上限为 0、到期日不是真实日期、到期日早于今天
    runs = [run_hook("test-tiers", *base, *extra, cwd=git_repo)
            for extra in (("--limit-sec", "0"), ("--expires", "2027-13-40"), ("--expires", "2000-01-01"))]

    # Then: 都以 2 退出并各自说明原因，分层文件不变
    assert [p.returncode for p in runs] == [2, 2, 2], [(p.returncode, p.stderr) for p in runs]
    assert "大于 0" in runs[0].stderr and "日期" in runs[1].stderr and "早于今天" in runs[2].stderr, [p.stderr for p in runs]
    assert path.read_text(encoding="utf-8") == before
