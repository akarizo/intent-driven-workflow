"""final 的无图退路：没有可用锚点时只重跑改动的测试文件（scenario: tests-only-final#tests-only-rerun-after-green-final、
#tests-only-refused-when-source-changed、#tests-only-red-when-rerun-fails、#tests-only-result-handoff-marks-mode、
#forecast-predicts-tests-only-rerun、#cost-attributes-tests-only-rerun，
ship-rerun-decision#claude-md-commit-without-graph-or-inert-runs-full-and-names-file，共 7 条；
另有 1 条既有行为守卫：依赖图已测时只改 CLAUDE.md 的提交走增量、重跑 0 个文件）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

from conftest import SCOPE_DECL, commit_all, git, run_hook
from final_helpers import baseline, change_and_commit, final, make_repo, timeline_rows
from test_flight_doctor import forecast
from test_gate_test_result import COPY_RESULT, _copy_check
from test_runner_contract import DROPPING
from test_runner_statement import REASON

TEST_A2 = """
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    from a import a


    def test_a():
        assert a() == 1


    def test_a_again():
        assert a() + 1 == 2
"""
TEST_A_RED = TEST_A2.replace("a() + 1 == 2", "a() + 1 == 3")


def _nograph(repo, extra=None, gate_extra=None):
    """依赖图测不到的仓库：gate.test 是丢掉插件参数的包装脚本，计划已为 runner:deps-unmeasured 表态；
    gate.pytest 保留（增量重跑可等价复现）。baseline 与第一次 final（全量）都绿，飞行记录已提交。"""
    files = {"tools/gate.sh": DROPPING}
    files.update(extra or {})
    gate = {"test": "bash tools/gate.sh", "scope_full_reason": REASON}
    gate.update(gate_extra or {})
    d = make_repo(repo, extra=files, gate_extra=gate)
    bl = baseline(repo, d)
    assert bl["ok"] is True and (bl.get("deps_unmeasured") or {}).get("kind") == "plugins-dropped", bl
    out, _ = final(repo, d)
    assert out["ok"] is True and out["incremental"]["mode"] == "full", out
    commit_all(repo, "chore(flight): 记录")
    return d


def _second_repo(tmp_path):
    """与 git_repo 夹具同样的第二个临时仓库。"""
    repo = tmp_path / "repo2"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "openspec").mkdir()
    (repo / "openspec" / "gate-scope.json").write_text(json.dumps(SCOPE_DECL) + "\n", encoding="utf-8")
    commit_all(repo, "init")
    return repo


def _ship(repo, d):
    p = run_hook("slice-gate", "ship", "--change-dir", str(d), cwd=repo)
    return json.loads(p.stdout.strip().splitlines()[-1])


def test_tests_only_rerun_after_green_final(git_repo, tmp_path):
    # Given: 依赖图测不到的仓库，final 已绿；之后只提交了 tests/test_a.py 的改动。
    #        另一个同样的仓库没有 gate.pytest（增量重跑无法等价复现 gate.test）
    d = _nograph(git_repo)
    change_and_commit(git_repo, "tests/test_a.py", TEST_A2)
    other = _second_repo(tmp_path)
    d2 = _nograph(other, gate_extra={"pytest": None})
    change_and_commit(other, "tests/test_a.py", TEST_A2)

    # When: 分别运行 final
    out, p = final(git_repo, d)
    out2, p2 = final(other, d2)

    # Then: 第一个仓库只重跑 tests/test_a.py，其余沿用上次绿 final；时间线备注以「增量（无图」开头、以 ok 结尾；
    #       第二个仓库仍然全量
    inc = out.get("incremental") or {}
    assert out["ok"] is True, (out, p.stderr)
    assert inc.get("mode") == "incremental" and inc.get("source") == "tests-only", inc
    assert inc.get("rerun") == ["tests/test_a.py"] and inc.get("rerun_tests") == 2, inc
    note = timeline_rows(d, "final")[-1]
    assert note.startswith("增量（无图") and note.endswith("ok"), note
    assert (out2.get("incremental") or {}).get("mode") == "full", (out2, p2.stderr)


def test_tests_only_refused_when_source_changed(git_repo):
    # Given: 依赖图测不到的仓库，final 已绿；之后提交了 src/a.py 的改动
    d = _nograph(git_repo)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 全量；原因既说没有可用锚点，也点名上次绿 final 之后改动的非测试文件
    inc = out.get("incremental") or {}
    assert inc.get("mode") == "full", (out, p.stderr)
    assert "没有可用锚点" in inc["full_why"] and "src/a.py" in inc["full_why"], inc


def test_tests_only_red_when_rerun_fails(git_repo):
    # Given: 依赖图测不到的仓库，final 已绿；之后提交的 tests/test_a.py 里有一条会失败的新用例
    d = _nograph(git_repo)
    change_and_commit(git_repo, "tests/test_a.py", TEST_A_RED)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 退出 1；仍是无图退路（不退回全量），failed 有一条 G2 test 新增失败并点名该用例
    assert p.returncode == 1 and out["ok"] is False, out
    assert (out.get("incremental") or {}).get("source") == "tests-only", out
    assert any(f.startswith("G2 test") and "新增失败" in f and "tests/test_a.py::test_a_again" in f
               for f in out["failed"]), out["failed"]


def test_tests_only_result_handoff_marks_mode(git_repo, tmp_path):
    # Given: 同样的仓库，计划配了一项把 GATE_TEST_RESULT 复制到仓库外的检查；final 已绿；之后只改了 tests/test_a.py
    out_path = tmp_path / "result.json"
    d = _nograph(git_repo, extra={"tools/copy_result.py": COPY_RESULT}, gate_extra={"checks": _copy_check(out_path)})
    change_and_commit(git_repo, "tests/test_a.py", TEST_A2)

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 结果文件 mode 为 tests-only；nodes 与 inherited 为 null、complete 为假、failed_nodes 为空
    assert out["ok"] is True, (out, p.stderr)
    rec = json.loads(out_path.read_text(encoding="utf-8"))
    assert rec is not None and rec["mode"] == "tests-only", rec
    assert rec["nodes"] is None and rec["inherited"] is None and rec["complete"] is False, rec
    assert rec["failed_nodes"] == [], rec


def test_forecast_predicts_tests_only_rerun(git_repo):
    # Given: 依赖图测不到的仓库，final 已绿；之后只提交了 tests/test_a.py 的改动
    d = _nograph(git_repo)
    change_and_commit(git_repo, "tests/test_a.py", TEST_A2)

    # When: 运行 flight-doctor.py forecast --json 与 slice-gate.py ship
    p, j = forecast(git_repo, d)
    res = _ship(git_repo, d)

    # Then: 预告 final 走增量并说明是无图退路、重跑 1 个测试文件；ship 的过期理由带同一句预告
    assert p.returncode == 0, p.stderr
    assert j["final"]["mode"] == "incremental" and "无图" in j["final"]["why"] and "1 个测试文件" in j["final"]["why"], j
    assert any("final 过期" in r and "补跑将是增量" in r and "无图" in r for r in res["reasons"]), res["reasons"]


def test_cost_attributes_tests_only_rerun(git_repo):
    # Given: 依赖图测不到的仓库先跑了一次全量 final，之后只改测试文件又跑了一次 final
    d = _nograph(git_repo)
    change_and_commit(git_repo, "tests/test_a.py", TEST_A2)
    out, p = final(git_repo, d)
    assert out["ok"] is True, (out, p.stderr)

    # When: 运行 flight-doctor.py cost --json
    c = run_hook("flight-doctor", "cost", "--change-dir", str(d), "--json", cwd=git_repo)
    j = json.loads(c.stdout)

    # Then: final 记 1 次全量、1 次增量
    assert c.returncode == 0, c.stderr
    assert j["final"]["full"] == 1 and j["final"]["incremental"] == 1, j


def test_claude_md_commit_without_graph_or_inert_runs_full_and_names_file(git_repo):
    # Given: 依赖图测不到、也没有声明 inert 的仓库，final 已绿；之后只提交了 CLAUDE.md 的改动
    d = _nograph(git_repo, extra={"CLAUDE.md": "# 记忆\n"})
    change_and_commit(git_repo, "CLAUDE.md", "# 记忆\n\n- 新沉淀的一条\n", msg="docs(memory): 沉淀本轮知识")

    # When: 依次运行 forecast、ship、final
    p, j = forecast(git_repo, d)
    res = _ship(git_repo, d)
    out, pf = final(git_repo, d)

    # Then: 预告与 ship 的过期理由都事先说明是全量并点名 CLAUDE.md；final 全量，原因点名 CLAUDE.md
    assert p.returncode == 0, p.stderr
    assert j["final"]["mode"] == "full" and "CLAUDE.md" in j["final"]["why"], j
    assert any("final 过期" in r and "补跑将是全量" in r and "CLAUDE.md" in r for r in res["reasons"]), res["reasons"]
    inc = out.get("incremental") or {}
    assert inc.get("mode") == "full" and "CLAUDE.md" in inc["full_why"], (out, pf.stderr)


def test_claude_md_commit_with_measured_graph_reruns_nothing(git_repo):  # 既有行为守卫：依赖图已测时本来就走增量，故不标 xfail
    # Given: 基线测到了依赖图、没有声明 inert；final 已绿；之后只提交了 CLAUDE.md 的改动
    d = make_repo(git_repo, extra={"CLAUDE.md": "# 记忆\n"})
    assert baseline(git_repo, d)["ok"] is True
    out, _ = final(git_repo, d)
    assert out["ok"] is True, out
    commit_all(git_repo, "chore(flight): 记录")
    change_and_commit(git_repo, "CLAUDE.md", "# 记忆\n\n- 新沉淀的一条\n", msg="docs(memory): 沉淀本轮知识")

    # When: 再运行 final
    out, p = final(git_repo, d)

    # Then: 增量，重跑 0 个文件
    inc = out.get("incremental") or {}
    assert out["ok"] is True and inc.get("mode") == "incremental", (out, p.stderr)
    assert inc.get("rerun") == [], inc
