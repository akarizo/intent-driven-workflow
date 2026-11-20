"""slice-gate.py warm：规划开始时预热全量，正式 baseline 等待并按本 change 旧基线规则复用
（scenario: baseline-warm#warm-runs-full-suite-as-own-baseline、#warm-adopts-latest-change-wrapper、#warm-skips-tiered-repo、
#baseline-reuses-warm-when-only-tests-changed、#baseline-waits-for-running-warm，共 5 条）。"""
import json
import subprocess
import sys
import time

from conftest import hook_path, run_hook, write
from test_baseline_incremental import PLAIN_FULL, baseline, read_bl, setup_change

NEW_TEST = "def test_new():\n    assert 2 * 2 == 4\n"
SLOW_TEST = "import time\n\n\ndef test_slow():\n    time.sleep(4)\n    assert True\n"


def new_change(git_repo, name="c"):
    d = git_repo / "openspec" / "changes" / name
    write(d / ".openspec.yaml", "schema: intent-driven\n")
    return d


def warm(git_repo, d, *args):
    return run_hook("slice-gate", "warm", "--change-dir", str(d), *args, cwd=git_repo)


def last_json(text):
    return json.loads([ln for ln in text.splitlines() if ln.startswith("{")][-1])


def test_warm_runs_full_suite_as_own_baseline(git_repo):
    # Given: change prev 的 gate.test 是直接的 pytest 全量；新 change c 只有目录
    setup_change(git_repo, change="prev", gate_test=PLAIN_FULL, old_red=False)
    d = new_change(git_repo)

    # When: 运行 warm
    p = warm(git_repo, d)

    # Then: 退出 0；c 的基线是预热结果；stdout 的 test_cmd 沿用 prev；时间线有 warm 事件
    assert p.returncode == 0, (p.stdout, p.stderr)
    bl = read_bl(d)
    assert bl["warm"] is True and bl["change"] == "c" and bl["ok"] is True and bl["mode"] == "full", bl
    assert bl["plan_sha"] is None
    assert last_json(p.stdout)["test_cmd"] == PLAIN_FULL
    assert "\twarm\t" in (d / "timeline.md").read_text(encoding="utf-8")


def test_warm_adopts_latest_change_wrapper(git_repo):
    # Given: prev 的 gate.test 运行 openspec/changes/prev/verify/full.py（setup_change 缺省）
    prev = setup_change(git_repo, change="prev", old_red=False)
    d = new_change(git_repo)

    # When: 对 c 运行 warm
    p = warm(git_repo, d)

    # Then: c/verify/full.py 被创建且内容相同；test_cmd 指向 c，不再指向 prev
    assert p.returncode == 0, (p.stdout, p.stderr)
    copied = d / "verify" / "full.py"
    assert copied.read_text(encoding="utf-8") == (prev / "verify" / "full.py").read_text(encoding="utf-8")
    cmd = last_json(p.stdout)["test_cmd"]
    assert "openspec/changes/c/verify/full.py" in cmd and "openspec/changes/prev/" not in cmd, cmd


def test_warm_skips_tiered_repo(git_repo):
    # Given: openspec 根有 test-tiers.json
    setup_change(git_repo, change="prev", gate_test=PLAIN_FULL, old_red=False)
    write(git_repo / "openspec" / "test-tiers.json", json.dumps({"unit": {"cmd": PLAIN_FULL, "paths": ["tests"]}}))
    d = new_change(git_repo)

    # When: 运行 warm
    p = warm(git_repo, d)

    # Then: 退出 0，输出以「跳过预热」开头，不写基线
    assert p.returncode == 0, (p.stdout, p.stderr)
    assert (p.stdout + p.stderr).lstrip().startswith("跳过预热"), (p.stdout, p.stderr)
    assert not (d / "gate-baseline.json").exists()


def test_baseline_reuses_warm_when_only_tests_changed(git_repo):
    # Given: c 已预热成功；之后写入 c 的计划（gate.test 同一命令）并新增 tests/test_new.py
    setup_change(git_repo, change="prev", gate_test=PLAIN_FULL, old_red=False)
    d = new_change(git_repo)
    assert warm(git_repo, d).returncode == 0
    setup_change(git_repo, change="c", gate_test=PLAIN_FULL, old_red=False, extra={"tests/test_new.py": NEW_TEST})

    # When: 运行正式 baseline
    p = baseline(git_repo, d)

    # Then: 增量，来源是 c 自己的预热，只补跑 tests/test_new.py
    assert p.returncode == 0, (p.stdout, p.stderr)
    bl = read_bl(d)
    assert bl["mode"] == "incremental", bl.get("reuse_skipped")
    assert bl["incremental"]["from"]["change"] == "c"
    assert bl["incremental"]["rerun_files"] == ["tests/test_new.py"]


def test_baseline_waits_for_running_warm(git_repo):
    # Given: prev 带一个要跑 4 秒的测试；对 c 在后台启动 warm，等它写出运行标记后写入 c 的计划（不提交）
    setup_change(git_repo, change="prev", gate_test=PLAIN_FULL, old_red=False, extra={"tests/test_slow.py": SLOW_TEST})
    d = new_change(git_repo)
    proc = subprocess.Popen([sys.executable, str(hook_path("slice-gate")), "warm", "--change-dir", str(d)],
                            cwd=git_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            f = d / "gate-baseline.json"
            if f.exists() and json.loads(f.read_text(encoding="utf-8") or "{}").get("running") is True:
                break
            time.sleep(0.1)
        setup_change(git_repo, change="c", gate_test=PLAIN_FULL, old_red=False, commit=False)

        # When: 预热还在跑时运行正式 baseline
        p = baseline(git_repo, d)
    finally:
        proc.communicate(timeout=120)

    # Then: stderr 含「等待预热结束」；结果复用 c 自己的预热
    assert "等待预热结束" in p.stderr, p.stderr
    assert p.returncode == 0, (p.stdout, p.stderr)
    bl = read_bl(d)
    assert bl["mode"] == "incremental" and bl["incremental"]["from"]["change"] == "c", bl
