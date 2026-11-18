"""基线的依赖图未测时计划须表态（scenario: runner-statement#unmeasured-baseline-needs-statement、
#statement-lets-lint-and-preflight-pass、#measured-baseline-rejects-leftover-statement、#final-refuses-unstated-unmeasured、
#statement-may-be-prewritten-before-baseline、#incremental-baseline-keeps-unmeasured-state，共 6 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。
「gate.test 是否运行」用仓库外的标记文件判定：tests/test_mark.py 在设了 RUNNER_STMT_MARK 时写出它。"""
import json

from conftest import commit_all, run_hook, write
from final_helpers import baseline, change_and_commit, gate_json, make_repo
from test_runner_contract import DROPPING, FORWARDING

TRIGGER = "runner:deps-unmeasured"
REASON = {TRIGGER: "testgate 重建子进程环境，本 change 不接契约，接受 final 全量"}
TEST_MARK = """
    import os


    def test_mark():
        mark = os.environ.get("RUNNER_STMT_MARK")
        if mark:
            open(mark, "w").close()
"""


def _wrapped(repo, script, reasons=None, extra=None):
    """gate.test = bash tools/gate.sh 的 change；可预写 gate.scope_full_reason。"""
    gate = {"test": "bash tools/gate.sh"}
    if reasons is not None:
        gate["scope_full_reason"] = reasons
    files = {"tools/gate.sh": script}
    files.update(extra or {})
    return make_repo(repo, extra=files, gate_extra=gate)


def _edit_gate(repo, d, **fields):
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["gate"].update(fields)
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "edit gate")


def _lint(repo, d):
    return run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=repo)


def _lines(text, word):
    return [l.strip() for l in text.splitlines() if word in l]


def _bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def test_unmeasured_baseline_needs_statement(git_repo):
    # Given: gate.test 是丢掉 -p 插件参数的包装脚本，没配 gate.impacted，计划没写理由；baseline 已跑完（plugins-dropped）
    d = _wrapped(git_repo, DROPPING)
    baseline(git_repo, d)
    assert (_bl(d).get("deps_unmeasured") or {}).get("kind") == "plugins-dropped", _bl(d)

    # When: 运行 lint；再给计划加上 gate.impacted 运行一次
    first = _lint(git_repo, d)
    _edit_gate(git_repo, d, impacted="true")
    second = _lint(git_repo, d)

    # Then: 第一次非 0，有一行违规同时含触发项、gate.scope_full_reason、未测类别与契约文档；配了 gate.impacted 后退出 0
    assert first.returncode != 0, first.stdout
    assert any("gate.scope_full_reason" in l and "plugins-dropped" in l and "flight-runner-contract.md" in l
               for l in _lines(first.stderr, TRIGGER)), first.stderr
    assert second.returncode == 0, second.stderr


def test_statement_lets_lint_and_preflight_pass(git_repo):
    # Given: 同样的包装脚本，计划为 runner:deps-unmeasured 写了理由；baseline 已跑完并提交，依赖图未测
    d = _wrapped(git_repo, DROPPING, reasons=REASON)
    out = baseline(git_repo, d)
    assert out["ok"] is True and (out.get("deps_unmeasured") or {}).get("kind") == "plugins-dropped", out

    # When: 运行 lint 与 preflight
    lint = _lint(git_repo, d)
    pre = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 两者都退出 0
    assert lint.returncode == 0, lint.stderr
    assert pre.returncode == 0, pre.stderr


def test_measured_baseline_rejects_leftover_statement(git_repo):
    # Given: gate.test 是按契约转发两个变量的包装脚本，计划却写了 runner:deps-unmeasured 的理由；baseline 已跑完，依赖图已测到
    d = _wrapped(git_repo, FORWARDING, reasons=REASON)
    out = baseline(git_repo, d)
    assert out["ok"] is True and "deps_unmeasured" not in out, out

    # When: 运行 lint
    p = _lint(git_repo, d)

    # Then: 退出非 0，有一行违规同时含触发项与「删除」
    assert p.returncode != 0, p.stdout
    assert any("删除" in l for l in _lines(p.stderr, TRIGGER)), p.stderr


def test_final_refuses_unstated_unmeasured(git_repo, tmp_path):
    # Given: 基线依赖图未测，计划没写理由，没有 approve 提交
    d = _wrapped(git_repo, DROPPING, extra={"tests/test_mark.py": TEST_MARK})
    baseline(git_repo, d)
    mark = tmp_path / "ran.marker"

    # When: 运行 final
    p = run_hook("slice-gate", "final", "--change-dir", str(d), cwd=git_repo, env={"RUNNER_STMT_MARK": str(mark)})
    out = gate_json(p)

    # Then: final 红；失败项有一条以 G2 scope 开头、含触发项；gate.test 没有运行
    assert out["ok"] is False, out
    assert any(f.startswith("G2 scope") and TRIGGER in f for f in out["failed"]), out["failed"]
    assert not mark.exists()


def test_statement_may_be_prewritten_before_baseline(git_repo):
    # Given: 还没跑过 baseline 的 change，gate.test 是 bash tools/gate.sh，脚本文本里没有 FLIGHT_PYTEST_ARGS
    d = _wrapped(git_repo, DROPPING)

    # When: 先不写理由运行 lint；再写上理由运行一次；最后把脚本换成按契约转发的版本、去掉理由再运行一次
    bare = _lint(git_repo, d)
    _edit_gate(git_repo, d, scope_full_reason=REASON)
    stated = _lint(git_repo, d)
    write(git_repo / "tools" / "gate.sh", FORWARDING)
    _edit_gate(git_repo, d, scope_full_reason={})
    forwarding = _lint(git_repo, d)

    # Then: 三次都退出 0；第一次有一行以 runner: 开头的提示，点名脚本与 FLIGHT_PYTEST_ARGS；转发版没有这行提示
    assert bare.returncode == 0, bare.stderr
    assert stated.returncode == 0, stated.stderr
    assert forwarding.returncode == 0, forwarding.stderr
    hints = [l for l in _lines(bare.stderr, "runner:") if l.startswith("runner:")]
    assert any("tools/gate.sh" in l and "FLIGHT_PYTEST_ARGS" in l for l in hints), bare.stderr
    assert not [l for l in _lines(forwarding.stderr, "runner:") if l.startswith("runner:")], forwarding.stderr


def test_incremental_baseline_keeps_unmeasured_state(git_repo):
    # Given: 全量基线依赖图未测（plugins-dropped）；之后只改了一个测试文件并提交
    d = _wrapped(git_repo, DROPPING)
    baseline(git_repo, d)
    more = (git_repo / "tests" / "test_a.py").read_text(encoding="utf-8") + "\n\ndef test_a_again():\n    assert a() == 1\n"
    change_and_commit(git_repo, "tests/test_a.py", more)

    # When: 再运行 slice-gate.py baseline
    second = baseline(git_repo, d)

    # Then: 新基线是增量的，deps_unmeasured.kind 仍为 plugins-dropped
    assert second["mode"] == "incremental", second
    assert (second.get("deps_unmeasured") or {}).get("kind") == "plugins-dropped", second
