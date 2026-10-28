"""baseline / final / preflight 按分层运行：单元层探针判 G10 / G11、已选区域按基线差分、区域命令与基线对账
（scenario: test-tiers#baseline-red-when-unit-test-impure … #no-tiers-file-gate-unchanged）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。
护栏（no-tiers-file-gate-unchanged）在 base 上已成立，不带 xfail。"""
import json
import shlex
import sys

from conftest import commit_all, run_hook, write

PY = shlex.quote(sys.executable)
UNIT_CMD = "%s -m pytest -q -p no:cacheprovider tests/unit" % PY
HOOKS_CMD = "%s -m pytest -q -p no:cacheprovider tests/integration/hooks" % PY
PURE = "def test_adds():\n    assert 1 + 1 == 2\n"
HOOKS_OK = "def test_old():\n    assert True\n\n\ndef test_new():\n    assert True\n"


def setup_tiers(repo, unit_files, region_files=None, integration=("hooks",), with_tiers=True):
    """被测仓库：pytest.ini、src/app.py、给定的单元层与区域测试文件；openspec/test-tiers.json（with_tiers 时）
    含区域 hooks（跑 tests/integration/hooks）与 docs（运行时在仓外写标记 ran-docs）；
    change c 单片 S1（owns src/app.py，verify 恒绿），gate.test = 单元层命令，gate.integration 按参数。返回 change 目录。"""
    write(repo / "pytest.ini", "[pytest]\n")
    write(repo / "src" / "app.py", "X = 1\n")
    for path, text in {**unit_files, **(region_files or {})}.items():
        write(repo / path, text)
    d = repo / "openspec" / "changes" / "c"
    write(d / "verify" / "docs.py", "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran')\n")
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "slices" / "S1.md", "# S1\n")
    if with_tiers:
        docs_cmd = "%s openspec/changes/c/verify/docs.py %s" % (PY, shlex.quote(str(repo.parent / "ran-docs")))
        tiers = {
            "unit": {"paths": ["tests/unit/**"], "cmd": UNIT_CMD},
            "regions": {
                "hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"], "cmd": HOOKS_CMD},
                "docs": {"paths": ["tests/integration/docs/**"], "covers": ["docs/**"], "cmd": docs_cmd},
            },
            "slow_allow": {},
        }
        write(repo / "openspec" / "test-tiers.json", json.dumps(tiers, ensure_ascii=False))
    gate = {"test": UNIT_CMD, "pytest": "%s -m pytest" % PY, "lint": None, "typecheck": None}
    if integration:
        gate["integration"] = list(integration)
    data = {
        "version": 1, "change": "c", "gate": gate,
        "slices": [{"id": "S1", "title": "S1", "owns": ["src/app.py"], "deps": [], "verify": "true",
                    "scenarios": [], "packet": "slices/S1.md"}],
        "scenario_tests": {},
    }
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return d


def baseline(repo, d):
    return run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=repo)


def read_bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def final_json(repo, d):
    p = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=repo)
    return json.loads(p.stdout)


def set_hooks_cmd(repo, cmd):
    """改分层文件里区域 hooks 的 cmd 并提交。"""
    path = repo / "openspec" / "test-tiers.json"
    t = json.loads(path.read_text(encoding="utf-8"))
    t["regions"]["hooks"]["cmd"] = cmd
    path.write_text(json.dumps(t, ensure_ascii=False), encoding="utf-8")
    commit_all(repo, "change hooks cmd")


# ---------------------------------------------------------------- baseline


def test_baseline_red_when_unit_test_impure(git_repo):
    # Given: 分层文件合法；单元层里有一个在 tmp_path 写文件的用例 tests/unit/test_u.py::test_writes
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": "def test_writes(tmp_path):\n    (tmp_path / 'f').write_text('x')\n"},
                    integration=())

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出非 0；reasons 里有一条以 G11 开头并点名 tests/unit/test_u.py::test_writes
    assert p.returncode != 0, p.stdout + p.stderr
    reasons = read_bl(d)["reasons"]
    assert any(r.startswith("G11") and "tests/unit/test_u.py::test_writes" in r for r in reasons), reasons


def test_baseline_red_when_unit_test_slow(git_repo):
    # Given: 分层文件合法、slow_allow 为空；单元层里有一个每次都睡 3.1 秒的纯函数用例 tests/unit/test_u.py::test_sleepy
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": "import time\n\n\ndef test_sleepy():\n    time.sleep(3.1)\n"},
                    integration=())

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出非 0；reasons 里有一条以 G10 开头并点名 tests/unit/test_u.py::test_sleepy
    assert p.returncode != 0, p.stdout + p.stderr
    reasons = read_bl(d)["reasons"]
    assert any(r.startswith("G10") and "tests/unit/test_u.py::test_sleepy" in r for r in reasons), reasons


def test_baseline_records_selected_regions_only(git_repo):
    # Given: 分层文件有区域 hooks 与 docs，计划只选了 hooks；hooks 里 test_old 预存失败；单元层全绿且纯
    region = {"tests/integration/hooks/test_h.py": "def test_old():\n    assert False\n\n\ndef test_fine():\n    assert True\n"}
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, region, integration=("hooks",))

    # When: 运行两次 slice-gate.py baseline
    p1 = baseline(git_repo, d)
    bl1 = read_bl(d)
    p2 = baseline(git_repo, d)
    bl2 = read_bl(d)

    # Then: 两次都退出 0，mode 都是 full；regions 只有 hooks，failed 含 test_old；docs 的命令一次都没跑
    assert p1.returncode == 0, p1.stdout + p1.stderr
    assert p2.returncode == 0, p2.stdout + p2.stderr
    assert bl1["mode"] == "full" and bl2["mode"] == "full", (bl1.get("mode"), bl2.get("mode"))
    assert set(bl2["regions"]) == {"hooks"}, bl2
    assert any("test_old" in f for f in bl2["regions"]["hooks"]["failed"]), bl2["regions"]
    assert not (git_repo.parent / "ran-docs").exists()


# ---------------------------------------------------------------- final


def test_final_diffs_regions_against_baseline(git_repo):
    # Given: 基线已记录区域 hooks 的预存失败 test_old；之后的提交让 hooks 里的 test_new 也失败
    region = {"tests/integration/hooks/test_h.py": "def test_old():\n    assert False\n\n\ndef test_new():\n    assert True\n"}
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, region, integration=("hooks",))
    b = baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    write(git_repo / "tests" / "integration" / "hooks" / "test_h.py",
          "def test_old():\n    assert False\n\n\ndef test_new():\n    assert False\n")
    commit_all(git_repo, "break test_new")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: 失败；有一条以 G2 region hooks 开头并点名 test_new；没有任何失败项点名 test_old
    assert out["ok"] is False, out
    region_items = [f for f in out["failed"] if f.startswith("G2 region hooks")]
    assert region_items and "test_new" in region_items[0], out
    assert not any("test_old" in f for f in out["failed"]), out


def test_final_red_on_new_impure_unit_test(git_repo):
    # Given: 基线绿；之后的提交在单元层新增一个起子进程的用例 tests/unit/test_u.py::test_spawns
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, integration=())
    b = baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    write(git_repo / "tests" / "unit" / "test_u.py", PURE + (
        "\n\nimport subprocess\nimport sys\n\n\n"
        "def test_spawns():\n    subprocess.run([sys.executable, '-c', 'pass'], check=True)\n"))
    commit_all(git_repo, "add impure unit test")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: 失败；有一条以 G11 开头并点名 tests/unit/test_u.py::test_spawns
    assert out["ok"] is False, out
    assert any(f.startswith("G11") and "tests/unit/test_u.py::test_spawns" in f for f in out["failed"]), out


def test_final_red_when_region_record_stale(git_repo):
    # Given: 基线记录了区域 hooks 的结果；之后分层文件里 hooks 的 cmd 被改成另一条命令
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {"tests/integration/hooks/test_h.py": HOOKS_OK},
                    integration=("hooks",))
    b = baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    set_hooks_cmd(git_repo, HOOKS_CMD + " -x")

    # When: 运行 slice-gate.py final
    out = final_json(git_repo, d)

    # Then: 失败；有一条以 G2 region hooks 开头并含「重跑 baseline」
    assert out["ok"] is False, out
    assert any(f.startswith("G2 region hooks") and "重跑 baseline" in f for f in out["failed"]), out


# ---------------------------------------------------------------- preflight


def test_preflight_stale_when_region_cmd_changed(git_repo):
    # Given: 基线绿且记录了区域 hooks；之后分层文件里 hooks 的 cmd 被改成另一条命令
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {"tests/integration/hooks/test_h.py": HOOKS_OK},
                    integration=("hooks",))
    b = baseline(git_repo, d)
    assert b.returncode == 0, b.stdout + b.stderr
    set_hooks_cmd(git_repo, HOOKS_CMD + " -x")

    # When: 运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；stderr 含「基线过期」并点名 hooks
    assert p.returncode != 0, p.stdout + p.stderr
    assert "基线过期" in p.stderr and "hooks" in p.stderr, p.stderr


# ---------------------------------------------------------------- 护栏：无分层文件时不变


def test_no_tiers_file_gate_unchanged(git_repo):
    # Given: openspec 根目录下没有 test-tiers.json；计划没有 gate.integration；单元测试纯且全绿
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, integration=(), with_tiers=False)

    # When: 运行 slice-gate.py baseline，再运行 slice-gate.py final
    p = baseline(git_repo, d)
    bl = read_bl(d)
    out = final_json(git_repo, d)

    # Then: 两者都绿；gate-baseline.json 没有 tiers 与 regions 键；final 的 failed / warnings 里没有 G10、G11、G12、G2 region
    assert p.returncode == 0, p.stdout + p.stderr
    assert "tiers" not in bl and "regions" not in bl, bl
    assert out["ok"] is True, out
    for item in out["failed"] + out["warnings"]:
        assert not item.startswith(("G10", "G11", "G12", "G2 region")), out
