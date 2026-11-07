"""运行期守卫：baseline / final 开跑前复核选测范围（scenario: scope-runtime-guard#baseline-refuses-unapproved-full、
#baseline-runs-when-full-is-approved、#baseline-refuses-undeclared、#final-refuses-unapproved-builtin-full、
#final-runs-approved-full、#final-refuses-unapproved-cmd-full、#manual-full-flag-is-exempt、
#reasons-edited-after-approval-are-red，共 8 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。
护栏 baseline-runs-when-full-is-approved、final-runs-approved-full、manual-full-flag-is-exempt 在 base 上已成立，不带 xfail。
「测试是否运行」用仓库外的标记文件判定：gate.test / tests/test_mark.py 在设了 SCOPE_GUARD_MARK 时写出它。"""
import json
import re

from conftest import commit_all, run_hook, write
from final_helpers import baseline, change_and_commit, gate_json, make_repo
from test_slice_gate import plan, slice_, write_plan

FULL_X = "printf '{\"full\": true, \"triggers\": [\"x\"]}' > \"$GATE_SCOPE_OUT\""
MARK_CMD = 'touch "$SCOPE_GUARD_MARK"'
TEST_MARK = """
    import os


    def test_mark():
        mark = os.environ.get("SCOPE_GUARD_MARK")
        if mark:
            open(mark, "w").close()
"""
FLAG_TOOL = """
    import json
    import os

    full = os.path.exists("flag")
    with open(os.environ["GATE_SCOPE_OUT"], "w", encoding="utf-8") as out:
        json.dump({"full": full, "triggers": ["y"] if full else []}, out)
"""


def _missing(text):
    out = set()
    for group in re.findall(r"触发项 (.+?) 缺理由", text):
        out.update(group.split("、"))
    return out


def _undeclare(repo):
    path = repo / "openspec" / "gate-scope.json"
    if path.exists():
        path.unlink()


def _marker_plan(repo, gate_extra=None, owns=("a/**",)):
    """change c 的单片计划：gate.test 只写标记文件；gate_extra 并入 gate 段；提交。返回 change 目录。"""
    data = plan([slice_("S1", list(owns))], gate={"test": MARK_CMD, "lint": None, "typecheck": None})
    data["gate"].update(gate_extra or {})
    d = write_plan(repo / "openspec" / "changes" / "c", data)
    write(d / "slices" / "S1.md", "# S1\n")
    commit_all(repo, "plan")
    return d


def _baseline(repo, d, mark):
    return run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=repo, env={"SCOPE_GUARD_MARK": str(mark)})


def _final(repo, d, mark, *args):
    p = run_hook("slice-gate", "final", "--change-dir", str(d), *args, cwd=repo, env={"SCOPE_GUARD_MARK": str(mark)})
    return gate_json(p), p


def _builtin_repo(repo, **kw):
    write(repo / "openspec" / "gate-scope.json", json.dumps({"builtin": True}))
    extra = dict(kw.pop("extra", {}), **{"tests/test_mark.py": TEST_MARK})
    return make_repo(repo, extra=extra, **kw)


def test_baseline_refuses_unapproved_full(git_repo, tmp_path):
    # Given: 计划 gate.scope 报告 {"full": true, "triggers": ["x"]}，没写理由；gate.test 一运行就写出标记
    d = _marker_plan(git_repo, {"scope": FULL_X})
    mark = tmp_path / "ran.marker"

    # When: 运行 slice-gate.py baseline
    p = _baseline(git_repo, d, mark)

    # Then: 退出非 0，stderr 点名 x 缺理由；没有标记，change 目录也没有 gate-baseline.json
    assert p.returncode != 0, p.stdout + p.stderr
    assert "x" in _missing(p.stdout + p.stderr), p.stdout + p.stderr
    assert not mark.exists()
    assert not (d / "gate-baseline.json").exists()


def test_baseline_runs_when_full_is_approved(git_repo, tmp_path):
    # Given: 同上，但计划写了 {"x": "已知并接受"}
    d = _marker_plan(git_repo, {"scope": FULL_X, "scope_full_reason": {"x": "已知并接受"}})
    mark = tmp_path / "ran.marker"

    # When: 运行 baseline
    _baseline(git_repo, d, mark)

    # Then: gate.test 被运行，有标记
    assert mark.exists()


def test_baseline_refuses_undeclared(git_repo, tmp_path):
    # Given: 没有任何选测声明，切片 owns 不含 gate-scope.json；gate.test 一运行就写出标记
    d = _marker_plan(git_repo)
    _undeclare(git_repo)
    commit_all(git_repo, "undeclare")
    mark = tmp_path / "ran.marker"

    # When: 运行 baseline
    p = _baseline(git_repo, d, mark)

    # Then: 退出非 0，输出含「未声明选测范围」；没有标记
    assert p.returncode != 0, p.stdout + p.stderr
    assert "未声明选测范围" in p.stdout + p.stderr, p.stdout + p.stderr
    assert not mark.exists()


def test_final_refuses_unapproved_builtin_full(git_repo, tmp_path):
    # Given: 仓库声明 builtin，基线已跑；随后提交了对 scripts/helper.sh 的修改（任何用例都没触及它），计划没写理由
    d = _builtin_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "scripts/helper.sh", "echo changed\n")
    mark = tmp_path / "ran.marker"

    # When: 运行 final
    out, _ = _final(git_repo, d, mark)

    # Then: final 红；失败项有一条以 G2 scope 开头、含 scripts/helper.sh；测试没有运行
    assert out["ok"] is False, out
    assert any(f.startswith("G2 scope") and "scripts/helper.sh" in f for f in out["failed"]), out["failed"]
    assert not mark.exists()


def test_final_runs_approved_full(git_repo, tmp_path):
    # Given: 同上，但计划写了 {"scripts/helper.sh": "脚本只给人用，接受全量"}，且没有 approve 提交
    d = _builtin_repo(git_repo, owns=("src/**", "scripts/helper.sh"),
                      gate_extra={"scope_full_reason": {"scripts/helper.sh": "脚本只给人用，接受全量"}})
    baseline(git_repo, d)
    change_and_commit(git_repo, "scripts/helper.sh", "echo changed\n")
    mark = tmp_path / "ran.marker"

    # When: 运行 final
    out, _ = _final(git_repo, d, mark)

    # Then: final 走全量，测试被运行
    assert out["incremental"]["mode"] == "full", out
    assert mark.exists()


def test_final_refuses_unapproved_cmd_full(git_repo, tmp_path):
    # Given: 计划 gate.scope 的替身在仓库根有 flag 时报 {"full": true, "triggers": ["y"]}，否则不全选；
    #        基线已跑（当时没有 flag）；随后提交了 flag，计划没写理由
    d = make_repo(git_repo, extra={"tools/flag_scope.py": FLAG_TOOL, "tests/test_mark.py": TEST_MARK},
                  gate_extra={"scope": "python3 tools/flag_scope.py"})
    baseline(git_repo, d)
    change_and_commit(git_repo, "flag", "1\n")
    mark = tmp_path / "ran.marker"

    # When: 运行 final
    out, _ = _final(git_repo, d, mark)

    # Then: final 红；失败项有一条以 G2 scope 开头、含 y；测试没有运行
    assert out["ok"] is False, out
    assert any(f.startswith("G2 scope") and "y" in f for f in out["failed"]), out["failed"]
    assert not mark.exists()


def test_manual_full_flag_is_exempt(git_repo, tmp_path):
    # Given: 与 final-refuses-unapproved-builtin-full 相同的仓库与修改
    d = _builtin_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "scripts/helper.sh", "echo changed\n")
    mark = tmp_path / "ran.marker"

    # When: 运行 final --full
    _final(git_repo, d, mark, "--full")

    # Then: 测试被运行
    assert mark.exists()


def test_reasons_edited_after_approval_are_red(git_repo, tmp_path):
    # Given: 仓库声明 builtin，基线已跑；随后一次提交只新增 timeline.md 的 approve 行（当时计划没写理由）；
    #        之后计划加上 {"scripts/helper.sh": "补写"} 并提交，又提交了对 scripts/helper.sh 的修改
    d = _builtin_repo(git_repo, owns=("src/**", "scripts/helper.sh"))
    baseline(git_repo, d)
    tl = d / "timeline.md"
    old = tl.read_text(encoding="utf-8") if tl.exists() else "<!-- timeline -->\n"
    tl.write_text(old + "2026-11-07T00:00:00Z\tapprove\t测试批准\n", encoding="utf-8")
    commit_all(git_repo, "chore(flight): approve")
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["gate"]["scope_full_reason"] = {"scripts/helper.sh": "补写"}
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(git_repo, "edit reasons")
    change_and_commit(git_repo, "scripts/helper.sh", "echo changed\n")
    mark = tmp_path / "ran.marker"

    # When: 运行 final
    out, _ = _final(git_repo, d, mark)

    # Then: final 红；失败项有一条以 G2 scope 开头、含「批准后被修改」；测试没有运行
    assert out["ok"] is False, out
    assert any(f.startswith("G2 scope") and "批准后被修改" in f for f in out["failed"]), out["failed"]
    assert not mark.exists()
