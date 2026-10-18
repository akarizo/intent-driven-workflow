"""baseline 运行并记录检查、检查超时、preflight 按计划对账检查、未配置检查时行为不变
（scenario: gate-paired-checks#check-timeout-is-red、#baseline-*、#preflight-*、#no-checks-behavior-unchanged）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。护栏（preflight-ignores-check-final-edit、
no-checks-behavior-unchanged）在 base 上已成立，不带 xfail。本文件的夹具也供 test_gate_checks_final.py（S3）复用，S3 不改本文件。"""
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import time

import pytest

from conftest import commit_all, git, run_hook, write
from test_baseline_incremental import (PY, append, baseline, first_full, full_c, marker, preflight, read_bl, read_plan,
                                       setup_change, two_changes)

CHECKS_DIR = "flight-gate-checks"
# 检查脚本：check.py <phase> <action> <runlog> [忽略的参数…]
# 每次运行往仓外 runlog 追加一行 "<phase> <action>"，把收到的 GATE_* 与工作目录写进 $GATE_CHECK_DIR/env-<phase>.json，再按 action 行事
CHECK = (
    "import json, os, pathlib, sys\n"
    "phase, action, log = sys.argv[1], sys.argv[2], sys.argv[3]\n"
    "d = pathlib.Path(os.environ['GATE_CHECK_DIR'])\n"
    "with open(log, 'a', encoding='utf-8') as f:\n"
    "    f.write('%s %s\\n' % (phase, action))\n"
    "env = {k: os.environ.get(k) for k in ('GATE_PHASE', 'GATE_CHANGE', 'GATE_BASE_COMMIT', 'GATE_CHECK_DIR')}\n"
    "env['cwd'] = os.getcwd()\n"
    "(d / ('env-%s.json' % phase)).write_text(json.dumps(env), encoding='utf-8')\n"
    "if action == 'seed':\n"
    "    (d / 'seed.txt').write_text('from-baseline', encoding='utf-8')\n"
    "elif action == 'need-seed':\n"
    "    sys.exit(0 if (d / 'seed.txt').exists() else 4)\n"
    "elif action == 'exit3':\n"
    "    sys.exit(3)\n"
    "elif action == 'noisy':\n"
    "    for i in range(1, 31):\n"
    "        print('line-%02d' % i)\n"
    "    sys.exit(1)\n"
)


def common_dir(repo):
    """git common dir 的真实绝对路径。"""
    c = git(repo, "rev-parse", "--git-common-dir")
    return pathlib.Path(os.path.realpath(c if os.path.isabs(c) else repo / c))


def check_dir(repo, change, name):
    return common_dir(repo) / CHECKS_DIR / change / name


def check_cmd(git_repo, phase, action, change="c", log="checks.log", extra=""):
    """运行本 change 目录下 verify/check.py 的命令；runlog 在仓外。"""
    return "%s openspec/changes/%s/verify/check.py %s %s %s%s" % (
        PY, change, phase, action, shlex.quote(str(marker(git_repo, log))), extra)


def parity(git_repo, b_action="ok", f_action="ok", **kw):
    """检查 parity：baseline 与 final 都走 check.py。"""
    return {"name": "parity", "baseline": check_cmd(git_repo, "baseline", b_action, **kw),
            "final": check_cmd(git_repo, "final", f_action, **kw)}


def runs(git_repo, log="checks.log"):
    """检查脚本的运行记录（每次运行一行）。"""
    p = marker(git_repo, log)
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def set_checks(d, checks):
    data = read_plan(d)
    data["gate"]["checks"] = checks
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))


def setup_checks(git_repo, checks, change="c", commit=True):
    """setup_change（无预存红）+ 本 change 的 verify/check.py + gate.checks；默认一并提交。返回 change 目录。"""
    d = setup_change(git_repo, change=change, old_red=False, commit=False,
                     extra={"openspec/changes/%s/verify/check.py" % change: CHECK})
    set_checks(d, checks)
    if commit:
        commit_all(git_repo, "plan " + change)
    return d


def final_json(repo, d):
    p = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=repo)
    return json.loads(p.stdout)


# ---------------------------------------------------------------- 运行契约：超时


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_check_timeout_is_red(git_repo):
    # Given: 检查 slow 的 baseline 命令是 sleep 30; echo done，timeout_sec 为 1
    d = setup_checks(git_repo, [{"name": "slow", "baseline": "sleep 30; echo done", "final": "true", "timeout_sec": 1}])

    # When: 运行 slice-gate.py baseline
    t0 = time.time()
    p = baseline(git_repo, d)
    elapsed = time.time() - t0

    # Then: 退出非 0，整体用时不到 20 秒；reasons 有一条点名 slow 并含「超时」
    assert p.returncode != 0, p.stdout + p.stderr
    assert elapsed < 20, elapsed
    assert any("slow" in r and "超时" in r for r in read_bl(d)["reasons"]), read_bl(d)["reasons"]


# ---------------------------------------------------------------- baseline 运行并记录检查


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_baseline_red_when_check_fails(git_repo):
    # Given: 检查 parity 的 baseline 命令退出 3；全量、lint 与 verify 都绿
    d = setup_checks(git_repo, [parity(git_repo, b_action="exit3")])

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出非 0；ok 为 false；reasons 有一条以 check parity 开头并含 exit 3；checks.parity.exit 为 3
    assert p.returncode != 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["ok"] is False
    assert any(r.startswith("check parity") and "exit 3" in r for r in bl["reasons"]), bl["reasons"]
    assert bl["checks"]["parity"]["exit"] == 3, bl["checks"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_baseline_clears_check_dir_before_run(git_repo):
    # Given: 检查 parity 的共用目录里有上一次留下的 stale.txt；本次 baseline 要实跑这个检查
    d = setup_checks(git_repo, [parity(git_repo)])
    cdir = check_dir(git_repo, "c", "parity")
    write(cdir / "stale.txt", "old\n")

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；stale.txt 不存在，本次检查写下的文件存在
    assert p.returncode == 0, p.stdout + p.stderr
    assert not (cdir / "stale.txt").exists()
    assert (cdir / "env-baseline.json").exists()


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_baseline_check_reused_when_tree_unchanged(git_repo):
    # Given: change c 已有一次全量绿基线，检查 parity 实跑过一次；之后只改了本 change 的 proposal.md
    d = setup_checks(git_repo, [parity(git_repo)])
    first_full(git_repo, d)
    assert runs(git_repo) == ["baseline ok"]
    append(d / "proposal.md", "补一句。\n")

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；检查没有再运行；checks.parity.reused 为 true，checks.parity.exit 为 0
    assert p.returncode == 0, p.stdout + p.stderr
    assert runs(git_repo) == ["baseline ok"]
    c = read_bl(d)["checks"]["parity"]
    assert c.get("reused") is True and c["exit"] == 0, c


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_baseline_check_rerun_when_command_changed(git_repo):
    # Given: change c 已有一次全量绿基线，检查 parity 实跑过一次；之后把它的 baseline 命令末尾多加一个参数
    d = setup_checks(git_repo, [parity(git_repo)])
    first_full(git_repo, d)
    set_checks(d, [parity(git_repo, extra=" x")])

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；检查又运行了一次；checks.parity 没有 reused
    assert p.returncode == 0, p.stdout + p.stderr
    assert runs(git_repo) == ["baseline ok", "baseline ok"]
    assert "reused" not in read_bl(d)["checks"]["parity"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_baseline_check_rerun_when_dir_missing(git_repo):
    # Given: change c 已有一次全量绿基线，检查 parity 实跑过一次；之后删掉了它的共用目录，并改了本 change 的 proposal.md
    d = setup_checks(git_repo, [parity(git_repo)])
    first_full(git_repo, d)
    assert runs(git_repo) == ["baseline ok"]
    shutil.rmtree(check_dir(git_repo, "c", "parity"))
    append(d / "proposal.md", "补一句。\n")

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；检查又运行了一次；checks.parity 没有 reused
    assert p.returncode == 0, p.stdout + p.stderr
    assert runs(git_repo) == ["baseline ok", "baseline ok"]
    assert "reused" not in read_bl(d)["checks"]["parity"]


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_baseline_check_rerun_on_cross_change_reuse(git_repo):
    # Given: change c 跑过一次全绿的全量基线并进了基线池；change d 的全量脚本与 c 相同，配了检查 parity
    c, d = two_changes(git_repo, old_red=False)
    full_c(git_repo, c)
    write(d / "verify" / "check.py", CHECK)
    set_checks(d, [parity(git_repo, change="d")])

    # When: 对 d 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；d 的 mode 为 incremental、复用来源是 c；d 的检查运行了一次；checks.parity 没有 reused
    assert p.returncode == 0, p.stdout + p.stderr
    bd = read_bl(d)
    assert bd["mode"] == "incremental" and bd["incremental"]["from"]["change"] == "c", bd
    assert runs(git_repo) == ["baseline ok"]
    assert "reused" not in bd["checks"]["parity"]


# ---------------------------------------------------------------- preflight 按计划对账检查


@pytest.mark.xfail(strict=True, reason="S2 未实现")
def test_preflight_stale_when_check_added(git_repo):
    # Given: change c 已有一次绿基线，当时计划里没有检查；之后在计划里加了检查 parity（baseline 与 final 都是 true）并提交
    d = setup_change(git_repo, old_red=False)
    first_full(git_repo, d)
    set_checks(d, [{"name": "parity", "baseline": "true", "final": "true"}])
    commit_all(git_repo, "add check")

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出非 0；stderr 含「基线过期」
    assert p.returncode != 0, p.stdout
    assert "基线过期" in p.stderr, p.stderr


def test_preflight_ignores_check_final_edit(git_repo):
    # Given: change c 的计划有检查 parity（baseline 与 final 都是 true），已有一次绿基线；之后只把它的 final 改成 true x 并提交
    d = setup_checks(git_repo, [{"name": "parity", "baseline": "true", "final": "true"}])
    first_full(git_repo, d)
    set_checks(d, [{"name": "parity", "baseline": "true", "final": "true x"}])
    commit_all(git_repo, "edit final")

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


# ---------------------------------------------------------------- 未配置检查时行为不变


def test_no_checks_behavior_unchanged(git_repo):
    # Given: change c 的计划没有 gate.checks，仓库没有 gate-checks.json
    d = setup_change(git_repo, old_red=False)

    # When: 依次运行 slice-gate.py baseline 与 slice-gate.py final
    b = baseline(git_repo, d)
    f = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=git_repo)

    # Then: 两次都退出 0；gate-baseline.json 没有 checks 键，plan_sha 等于原算法结果；
    #       final 的 JSON 只有原有字段，failed 与 warnings 都不含 G9；git common dir 下没有 flight-gate-checks
    assert b.returncode == 0, b.stdout + b.stderr
    assert f.returncode == 0, f.stdout + f.stderr
    bl = read_bl(d)
    assert "checks" not in bl, bl
    data = read_plan(d)
    g = data["gate"]
    key = [g.get("test"), g.get("lint"), g.get("typecheck"), [[s.get("id"), s.get("verify")] for s in data["slices"]]]
    assert bl["plan_sha"] == hashlib.sha1(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    out = json.loads(f.stdout)
    assert set(out) <= {"slice", "ok", "commit", "failed", "warnings", "scenarios", "summary", "dirty"}, out
    assert not any("G9" in x for x in out["failed"] + out["warnings"]), out
    assert not (common_dir(git_repo) / CHECKS_DIR).exists()
