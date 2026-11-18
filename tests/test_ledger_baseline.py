"""slice-gate.py baseline 写基线账本、摘要进 gate-baseline.json、锚点带逐用例耗时
（scenario: test-ledger#full-baseline-writes-ledger-and-summary 等 5 条）。
骨架：strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import json
import shutil
import subprocess
import sys

from conftest import HOOKS
from final_helpers import PY, TEST_A, baseline, change_and_commit, gate_json, latest_anchor, make_repo
from test_tiers_gate import HOOKS_OK, PURE, setup_tiers


NODE_A, NODE_B, NODE_C = "tests/test_a.py::test_a", "tests/test_b.py::test_b", "tests/test_c.py::test_c"
# 只把 --junitxml 传给 pytest、丢掉 -p 插件参数的包装脚本（与 tests/test_runner_contract.py 的 DROPPING 同形）
DROPPING = """#!/usr/bin/env bash
J=$(printf '%%s\\n' $PYTEST_ADDOPTS | grep '^--junitxml=' || true)
unset PYTEST_ADDOPTS
exec %s -m pytest -q -p no:cacheprovider $J tests
""" % PY


def read_ledger(repo, change, name):
    """<git common dir>/flight-ledger/<change>/<name>.json；没有返回 None。"""
    path = repo / ".git" / "flight-ledger" / change / (name + ".json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def strip_anchor_secs(repo):
    """把锚点池里每条锚点的 secs 去掉（模拟升级前写的锚点）。"""
    for f in (repo / ".git" / "flight-anchors").glob("*.json"):
        if f.name.startswith(".tmp-"):
            continue
        entry = json.loads(f.read_text(encoding="utf-8"))
        entry.pop("secs", None)
        f.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")


def test_full_baseline_writes_ledger_and_summary(git_repo):
    # Given: gate.test 是直接的 pytest 调用，共 3 条用例
    d = make_repo(git_repo)

    # When: 运行 baseline
    out = baseline(git_repo, d)

    # Then: 基线账本 3 条用例都是本次实测且有耗时；gate-baseline.json 只多摘要；锚点带 secs
    led = read_ledger(git_repo, "c", "baseline")
    assert led is not None, out.get("warnings")
    assert (led["phase"], led["mode"], led["id_form"], led["commit"]) == ("baseline", "full", "nodeid", out["commit"])
    assert led["lock"] == out["lock"]["state"]
    assert set(led["cases"]) == {NODE_A, NODE_B, NODE_C}, led
    assert all(c["m"] == 1 and isinstance(c["s"], float) and c["o"] == "passed" for c in led["cases"].values()), led
    raw = (d / "gate-baseline.json").read_text(encoding="utf-8")
    bl = json.loads(raw)
    assert (bl["ledger"]["cases"], bl["ledger"]["measured"], bl["ledger"]["no_sec"]) == (3, 3, 0), bl.get("ledger")
    assert '"cases": {' not in raw
    assert set(latest_anchor(git_repo)["secs"]) == {NODE_A, NODE_B, NODE_C}


def test_anchor_baseline_inherits_seconds(git_repo):
    # Given: change c 有一次测到依赖图的全量基线；之后提交了 src/a.py 的改动
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 再运行 baseline；然后去掉锚点的 secs、再改一次 src/a.py、再运行 baseline
    out = baseline(git_repo, d)
    led = read_ledger(git_repo, "c", "baseline")
    anchor = latest_anchor(git_repo)
    strip_anchor_secs(git_repo)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 再改\n")
    out2 = baseline(git_repo, d)
    led2 = read_ledger(git_repo, "c", "baseline")

    # Then: 经锚点增量；补跑的用例是实测，其余沿用锚点的耗时；来源锚点没有 secs 时如实记 null
    assert out["mode"] == "incremental" and out["incremental"]["source"] == "anchor", out
    assert led["mode"] == "incremental" and led["cases"][NODE_A]["m"] == 1, led
    assert all(led["cases"][n]["m"] == 0 and led["cases"][n]["s"] is not None for n in (NODE_B, NODE_C)), led
    assert set(anchor["secs"]) == {NODE_A, NODE_B, NODE_C}, anchor.get("secs")
    assert out2["ok"] is True and out2["mode"] == "incremental", out2
    assert all(led2["cases"][n]["m"] == 0 and led2["cases"][n]["s"] is None for n in (NODE_B, NODE_C)), led2
    assert out2["ledger"]["no_sec"] == 2, out2["ledger"]


def test_reused_baseline_keeps_source_ledger(git_repo):
    # Given: gate.test 是丢掉插件参数的包装脚本；change c 已有一次全量基线；之后只改了一个测试文件
    d = make_repo(git_repo, extra={"tools/gate.sh": DROPPING}, gate_extra={"test": "bash tools/gate.sh"})
    baseline(git_repo, d)
    first = read_ledger(git_repo, "c", "baseline")
    change_and_commit(git_repo, "tests/test_a.py", TEST_A + "\n\n    def test_a2():\n        assert a() == 1\n")

    # When: 再运行 baseline（复用旧基线，只补跑 tests/test_a.py）
    out = baseline(git_repo, d)
    led = read_ledger(git_repo, "c", "baseline")

    # Then: 账本仍是 junit 形式；被改文件的用例是实测，其余沿用旧账本的耗时
    assert first is not None and first["id_form"] == "junit" and first["mode"] == "full", first
    assert out["mode"] == "incremental" and out["incremental"]["source"] == "own", out
    assert (led["id_form"], led["mode"], led["complete"]) == ("junit", "incremental", True), led
    assert set(led["cases"]) == {"tests.test_a::test_a", "tests.test_a::test_a2", "tests.test_b::test_b",
                                 "tests.test_c::test_c"}, led
    assert led["cases"]["tests.test_a::test_a2"]["m"] == 1 and led["cases"]["tests.test_a::test_a"]["m"] == 1
    for cid in ("tests.test_b::test_b", "tests.test_c::test_c"):
        assert led["cases"][cid] == dict(first["cases"][cid], m=0), (cid, led["cases"][cid])


def test_tiered_baseline_attributes_tiers(git_repo):
    # Given: 配了分层文件：单元层一条用例，已选区域 hooks 两条用例
    d = setup_tiers(git_repo, {"tests/unit/test_u.py": PURE}, {"tests/integration/hooks/test_h.py": HOOKS_OK})

    # When: 运行 baseline
    p = subprocess.run([sys.executable, str(HOOKS / "slice-gate.py"), "baseline", "--change-dir", str(d)],
                       cwd=git_repo, capture_output=True, text=True)

    # Then: 每条用例带层；摘要按层计数
    assert p.returncode == 0, p.stdout + p.stderr
    led = read_ledger(git_repo, "c", "baseline")
    assert led is not None and led["tiered"] is True, led
    assert led["cases"]["tests/unit/test_u.py::test_adds"]["t"] == "unit", led
    assert {led["cases"]["tests/integration/hooks/test_h.py::" + n]["t"] for n in ("test_old", "test_new")} == {"hooks"}
    tiers = json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))["ledger"]["tiers"]
    assert (tiers["unit"]["cases"], tiers["hooks"]["cases"]) == (1, 2), tiers


def test_ledger_failure_does_not_fail_baseline(git_repo, tmp_path):
    # Given: 一份不含 test-ledger.py 的 hooks 目录副本
    d = make_repo(git_repo)
    hooks = tmp_path / "hooks"
    shutil.copytree(HOOKS, hooks, ignore=shutil.ignore_patterns("test-ledger.py", "__pycache__"))
    assert not (hooks / "test-ledger.py").exists()

    # When: 用副本里的 slice-gate.py 运行 baseline
    p = subprocess.run([sys.executable, str(hooks / "slice-gate.py"), "baseline", "--change-dir", str(d)],
                       cwd=git_repo, capture_output=True, text=True)

    # Then: baseline 照常通过，只多一条警告；没有摘要，锚点的 secs 为 null
    out = gate_json(p)
    assert p.returncode == 0 and out["ok"] is True and out["reasons"] == [], p.stdout + p.stderr
    assert any(w.startswith("测试账本未写") for w in out.get("warnings") or []), out.get("warnings")
    assert "ledger" not in out
    assert latest_anchor(git_repo).get("secs", "缺键") is None
