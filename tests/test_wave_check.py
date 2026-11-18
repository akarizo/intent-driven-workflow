"""wave 集成检查：守护 + 受影响的测试、有界的测试那一半、跨片修复的范围、wave 行写回与收口裁决
（scenario: wave-check#wave-check-runs-guards-and-impacted-tests、#wave-check-reds-on-new-test-failure、
#wave-check-reds-on-guard、#wave-check-skips-tests-without-anchor、#wave-check-skips-tests-over-budget、
#wave-check-leaves-anchors-and-ledger-alone、#wave-check-fix-base-lists-files-outside-owns、
#record-writes-back-wave-row、#ship-drafts-on-red-wave-row，共 9 条）。
骨架：strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。带守护的三条在 S1 落地前红在计划校验（不认识 slice 字段），
S1 落地后红在 wave-check 子命令不存在。"""
import json
import shlex

import pytest

from conftest import commit_all, run_hook, write
from final_helpers import anchors, baseline, change_and_commit, gate_json, head, make_repo, timeline_rows
from test_runner_contract import DROPPING
from test_runner_statement import REASON

PENDING = pytest.mark.xfail(strict=True, reason="change wave-integration-guard S2 未实现")

SRC_A_TOUCHED = "def a():\n    return 1  # 改过\n"
SRC_A_BROKEN = "def a():\n    return 2\n"
NODE_A = "tests/test_a.py::test_a"


def wave(repo, d, *args):
    """跑 wave-check，返回 (JSON, CompletedProcess)。"""
    p = run_hook("slice-gate", "wave-check", "--change-dir", str(d), *args, cwd=repo)
    assert p.stdout.strip(), p.stderr
    return gate_json(p), p


def guarded_repo(repo, slice_cmd):
    """依赖图已测的被测仓库 + 带 slice 命令的检查 layering；基线已绿。返回 change 目录。"""
    d = make_repo(repo, gate_extra={"checks": [{"name": "layering", "slice": slice_cmd, "final": "true"}]})
    bl = baseline(repo, d)
    assert bl["ok"] is True, bl
    return d


def green_repo(repo):
    d = make_repo(repo)
    assert baseline(repo, d)["ok"] is True
    return d


def report_rows(d, slice_id="wave"):
    path = d / "gate-report.md"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines]
    return [r for r in rows if len(r) >= 5 and r[1] == slice_id]


def ship(repo, d):
    p = run_hook("slice-gate", "ship", "--change-dir", str(d), cwd=repo)
    return json.loads(p.stdout.strip().splitlines()[-1])


def record(repo, d, payload):
    return run_hook("slice-gate", "record", "--change-dir", str(d), "--json", json.dumps(payload, ensure_ascii=False),
                    cwd=repo)


@PENDING
def test_wave_check_runs_guards_and_impacted_tests(git_repo):
    # Given: 依赖图已测的仓库，检查 layering 带 slice 命令，基线已绿；之后提交了一处只被 tests/test_a.py 依赖的源码改动
    seen = git_repo.parent / "phase.txt"
    d = guarded_repo(git_repo, "printf '%s\\n' \"$GATE_PHASE\" >> " + shlex.quote(str(seen)))
    change_and_commit(git_repo, "src/a.py", SRC_A_TOUCHED)

    # When: 运行 wave-check --wave 1 --of 2
    out, p = wave(git_repo, d, "--wave", "1", "--of", "2")

    # Then: 通过；守护在 wave 阶段运行；只重跑受影响的测试文件；gate-report 与时间线各记一条
    assert p.returncode == 0 and out["ok"] is True, out
    assert (out["slice"], out["wave"]) == ("wave", 1), out
    assert out["guards"]["layering"]["exit"] == 0, out
    assert seen.read_text(encoding="utf-8").split()[-1] == "wave"
    assert out["tests"]["mode"] == "impacted" and out["tests"]["files"] == ["tests/test_a.py"], out["tests"]
    assert len(report_rows(d)) == 1 and report_rows(d)[0][2] == "ok"
    note = timeline_rows(d, "wave-check")[-1]
    assert note.startswith("wave 1/2") and "测试 " in note and note.endswith("ok"), note


@PENDING
def test_wave_check_reds_on_new_test_failure(git_repo):
    # Given: 依赖图已测的仓库，基线已绿；之后提交的源码改动让 tests/test_a.py::test_a 失败
    d = green_repo(git_repo)
    change_and_commit(git_repo, "src/a.py", SRC_A_BROKEN)

    # When: 运行 wave-check
    out, p = wave(git_repo, d)

    # Then: 退出 1；failed 有一项以 G16 wave test 开头并点名该用例；时间线备注以 red 结尾
    assert p.returncode == 1 and out["ok"] is False, out
    assert any(f.startswith("G16 wave test") and NODE_A in f for f in out["failed"]), out["failed"]
    assert timeline_rows(d, "wave-check")[-1].endswith("red")


@PENDING
def test_wave_check_reds_on_guard(git_repo):
    # Given: 检查 layering 的 slice 命令在基线上是绿的；之后提交的改动让它以非 0 退出
    d = guarded_repo(git_repo, "test ! -f src/bad.py")
    change_and_commit(git_repo, "src/bad.py", "X = 1\n")

    # When: 运行 wave-check
    out, p = wave(git_repo, d)

    # Then: 退出 1；failed 有一项以 G15 guard layering 开头；gate-report 里 wave 的最新一行是红的
    assert p.returncode == 1, out
    assert any(f.startswith("G15 guard layering") for f in out["failed"]), out["failed"]
    assert report_rows(d)[-1][2] == "red"


@PENDING
def test_wave_check_skips_tests_without_anchor(git_repo):
    # Given: 依赖图测不到的仓库（gate.test 是丢掉插件参数的包装脚本），基线已绿；之后提交了一处源码改动
    d = make_repo(git_repo, extra={"tools/gate.sh": DROPPING},
                  gate_extra={"test": "bash tools/gate.sh", "scope_full_reason": REASON})
    assert baseline(git_repo, d)["ok"] is True
    change_and_commit(git_repo, "src/a.py", SRC_A_TOUCHED)

    # When: 运行 wave-check
    out, p = wave(git_repo, d)

    # Then: 不红；测试那一半跳过并写明原因，没有重跑任何文件；时间线备注含「测试跳过」
    assert p.returncode == 0 and out["ok"] is True, out
    t = out["tests"]
    assert t["mode"] == "skipped" and t["why"] and not t["files"], t
    assert "测试跳过" in timeline_rows(d, "wave-check")[-1]


@PENDING
def test_wave_check_skips_tests_over_budget(git_repo):
    # Given: 依赖图已测的仓库，基线已绿，锚点里 tests/test_a.py::test_a 的耗时被记为 500 秒；
    #        之后提交了一处只影响 tests/test_a.py 的改动
    d = green_repo(git_repo)
    for f in (git_repo / ".git" / "flight-anchors").glob("*.json"):
        entry = json.loads(f.read_text(encoding="utf-8"))
        entry["secs"] = dict({n: 0.01 for n in entry.get("nodes") or {}}, **{NODE_A: 500.0})
        f.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    change_and_commit(git_repo, "src/a.py", SRC_A_TOUCHED)

    # When: 运行 wave-check；再把计划的 gate.wave_test_budget_sec 设为 1000 后运行
    first, p1 = wave(git_repo, d)
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["gate"]["wave_test_budget_sec"] = 1000
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    second, _ = wave(git_repo, d)

    # Then: 第一次跳过（估算 500 秒超过缺省预算），不红；第二次照常重跑
    t = first["tests"]
    assert p1.returncode == 0 and t["mode"] == "skipped" and t["est_sec"] == 500.0 and "预算" in t["why"], first
    assert second["tests"]["mode"] == "impacted", second["tests"]


@PENDING
def test_wave_check_leaves_anchors_and_ledger_alone(git_repo):
    # Given: 依赖图已测的仓库，基线已绿
    d = green_repo(git_repo)
    before = len(anchors(git_repo))

    # When: 先在没有任何改动时运行 wave-check，再提交一处源码改动后运行一次
    idle, _ = wave(git_repo, d)
    change_and_commit(git_repo, "src/a.py", SRC_A_TOUCHED)
    busy, _ = wave(git_repo, d)

    # Then: 不写锚点、不写收口账本；没有要跑的测试时持共享锁，要跑时持独占锁
    assert len(anchors(git_repo)) == before
    assert not (git_repo / ".git" / "flight-ledger" / "c" / "final.json").exists()
    assert idle["tests"]["mode"] == "none" and idle["lock"]["mode"] == "shared", idle
    assert busy["tests"]["mode"] == "impacted" and busy["lock"]["mode"] == "exclusive", busy


@PENDING
def test_wave_check_fix_base_lists_files_outside_owns(git_repo):
    # Given: 切片 S1 的 owns 是 src/**；从某个 commit 起先后提交了 src/a.py 与 data/b.json 的改动
    d = green_repo(git_repo)
    base = head(git_repo)
    change_and_commit(git_repo, "src/a.py", SRC_A_TOUCHED)
    change_and_commit(git_repo, "data/b.json", '{"b": 2}\n\n')

    # When: 以该 commit 为 --fix-base 运行；再提交一处时间线文件的改动后运行；再以对象库里没有的 sha 运行
    first, _ = wave(git_repo, d, "--fix-base", base)
    note = timeline_rows(d, "wave-check")[-1]
    commit_all(git_repo, "chore(flight): 记录")
    second, _ = wave(git_repo, d, "--fix-base", base)
    third, _ = wave(git_repo, d, "--fix-base", "0" * 40)

    # Then: 第一次列出两个文件、owns 外一个，时间线写明；第二次判 G6 flight-record；第三次判 G0 base
    assert sorted(first["fix"]["files"]) == ["data/b.json", "src/a.py"], first["fix"]
    assert first["fix"]["outside_owns"] == ["data/b.json"], first["fix"]
    assert "跨片修复 2 个文件（owns 外 1 个）" in note, note
    assert any(f.startswith("G6 flight-record") for f in second["failed"]), second["failed"]
    assert any(f.startswith("G0 base") for f in third["failed"]), third["failed"]


@PENDING
def test_record_writes_back_wave_row(git_repo):
    # Given: 一份 slice 为 wave 的 JSON：wave 2/3，守护 layering 1.2 秒，测试跳过并带原因
    d = make_repo(git_repo)
    payload = {"slice": "wave", "ok": True, "commit": head(git_repo), "failed": [], "warnings": [], "wave": 2, "of": 3,
               "guards": {"layering": {"exit": 0, "sec": 1.2}},
               "tests": {"mode": "skipped", "why": "没有可用锚点", "files": [], "sec": 0.0}}

    # When: 运行 record --json
    p = record(git_repo, d, payload)

    # Then: gate-report 有 wave 行；时间线记 wave-check 事件且备注拼出各段；不另记 gate 事件
    assert p.returncode == 0, p.stderr
    assert len(report_rows(d)) == 1
    notes = timeline_rows(d, "wave-check")
    assert len(notes) == 1, notes
    assert notes[0].startswith("wave 2/3") and "守护 layering 1.2s" in notes[0] and "测试跳过" in notes[0], notes[0]
    assert notes[0].endswith("ok")
    assert not [n for n in timeline_rows(d, "gate") if n.startswith("wave")]


@PENDING
def test_ship_drafts_on_red_wave_row(git_repo):
    # Given: gate-report 里 wave 的最新一行是红的，失败项是 G15 guard layering
    d = make_repo(git_repo)
    red = {"slice": "wave", "ok": False, "commit": head(git_repo), "failed": ["G15 guard layering：exit 3"],
           "warnings": [], "wave": 1, "of": 2}
    assert record(git_repo, d, red).returncode == 0

    # When: 运行 ship；再写回一行绿的 wave 后运行
    first = ship(git_repo, d)
    commit_all(git_repo, "chore(flight): 记录")
    assert record(git_repo, d, dict(red, ok=True, failed=[], commit=head(git_repo))).returncode == 0
    second = ship(git_repo, d)

    # Then: 第一次判 draft，理由以「wave 集成检查红」开头并含 G15；第二次没有这条理由；输出键不变
    assert first["ready"] is False
    assert any(r.startswith("wave 集成检查红") and "G15" in r for r in first["reasons"]), first["reasons"]
    assert not [r for r in second["reasons"] if r.startswith("wave 集成检查红")], second["reasons"]
    assert set(first) == {"ready", "commit", "reasons", "blocked"}
