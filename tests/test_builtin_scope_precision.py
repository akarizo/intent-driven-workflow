"""内建选测提供方与 final 精度（scenario: builtin-scope-precision#planned-global-file-is-trigger、
#planned-unseen-non-python-file-is-trigger、#preflight-reports-missing-anchor、#non-pytest-runner-is-by-design、
#declaration-files-do-not-force-full、#sourced-shell-file-selects-its-tests、#shell-closure-resolves-common-forms、
#unresolvable-shell-reference-stays-full，共 8 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现后去掉标记即解锁。
护栏 unresolvable-shell-reference-stays-full 在 base 上已成立（解析不到就照旧全量），不带 xfail。
各用例显式写 openspec/gate-scope.json，不依赖测试基座 git_repo 的默认声明。"""
import json
import re
import shutil

from conftest import commit_all, load_hook, run_hook, write
from final_helpers import baseline, change_and_commit, final, make_repo
from test_slice_gate import plan, slice_, write_plan

# 恒报未全选的 cmd 声明：隔离出 final 的内建判定，不受提供方复核影响
STUB = {"cmd": "printf '{\"full\": false, \"triggers\": []}' > \"$GATE_SCOPE_OUT\""}

LIB_SH = "greet() { echo hi; }\n"
TEST_RUN = """
    import os
    import subprocess

    ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


    def test_run():
        out = subprocess.run(["bash", os.path.join(ROOT, "scripts", "run.sh")], check=True,
                             capture_output=True, text=True).stdout
        assert out.strip() == "hi"
"""
RUN_FORMS = """
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    source "$SCRIPT_DIR/lib/common.sh"
    . "${BASH_SOURCE%/*}/env.sh"
    for u in a b; do
      "$SCRIPT_DIR/units/$u.sh"
    done
    bash tools/x.sh
"""


def _decl(repo, obj):
    write(repo / "openspec" / "gate-scope.json", json.dumps(obj, ensure_ascii=False))


def _missing(text):
    """违规文本里「触发项 A、B 缺理由」点名的触发项集合。"""
    out = set()
    for group in re.findall(r"触发项 (.+?) 缺理由", text):
        out.update(group.split("、"))
    return out


def _scope_lines(stderr):
    out = []
    for line in stderr.splitlines():
        s = line.strip()
        s = s[2:] if s.startswith("- ") else s
        if s.startswith("scope:"):
            out.append(s)
    return out


def test_planned_global_file_is_trigger(git_repo):
    # Given: 仓库声明 {"builtin": true}，gate.test 是 pytest 命令；切片 owns 含已跟踪的 pyproject.toml
    _decl(git_repo, {"builtin": True})
    d = make_repo(git_repo, extra={"pyproject.toml": "[tool.x]\n"}, owns=("src/**", "pyproject.toml"))

    # When: 运行 slice-gate.py lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；缺理由的触发项含 pyproject.toml
    assert p.returncode != 0, p.stderr
    assert "pyproject.toml" in _missing(p.stderr), p.stderr


def test_planned_unseen_non_python_file_is_trigger(git_repo):
    # Given: 仓库声明 builtin，基线已跑并写下依赖图；scripts/helper.sh 从未被任何用例触及，切片 owns 含它
    _decl(git_repo, {"builtin": True})
    d = make_repo(git_repo, owns=("src/**", "scripts/helper.sh"))
    baseline(git_repo, d)

    # When: 运行 slice-gate.py preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；缺理由的触发项含 scripts/helper.sh
    assert p.returncode != 0, p.stderr
    assert "scripts/helper.sh" in _missing(p.stderr), p.stderr


def test_preflight_reports_missing_anchor(git_repo):
    # Given: 仓库声明 builtin，基线绿，但锚点池随后被清空
    _decl(git_repo, {"builtin": True})
    d = make_repo(git_repo)
    baseline(git_repo, d)
    shutil.rmtree(git_repo / ".git" / "flight-anchors", ignore_errors=True)

    # When: 运行 preflight
    p = run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；缺理由的触发项含 final:no-anchor
    assert p.returncode != 0, p.stderr
    assert "final:no-anchor" in _missing(p.stderr), p.stderr


def test_non_pytest_runner_is_by_design(git_repo):
    # Given: 仓库声明 builtin，计划的 gate.test 是 npm test
    _decl(git_repo, {"builtin": True})
    data = plan([slice_("S1", ["a/**"])], gate={"test": "npm test", "lint": None, "typecheck": None})
    d = write_plan(git_repo / "openspec" / "changes" / "c", data)

    # When: 运行 lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出 0；stderr 摘要行含「设计边界」
    assert p.returncode == 0, p.stderr
    assert any("设计边界" in l for l in _scope_lines(p.stderr)), p.stderr


def test_declaration_files_do_not_force_full(git_repo):
    # Given: 仓库声明是恒报未全选的 cmd；基线已跑并写下依赖图
    _decl(git_repo, STUB)
    d = make_repo(git_repo)
    baseline(git_repo, d)

    # When: 只改 openspec/gate-scope.json（内容仍合法）并新增 .claude/settings.json，提交后运行 final
    write(git_repo / "openspec" / "gate-scope.json", json.dumps(STUB, ensure_ascii=False, indent=2))
    write(git_repo / ".claude" / "settings.json", "{}\n")
    commit_all(git_repo, "declarations")
    out, p = final(git_repo, d)

    # Then: final 走增量（不是全量），没有 full_why
    inc = out["incremental"]
    assert inc["mode"] == "incremental" and not inc.get("full_why"), inc


def test_sourced_shell_file_selects_its_tests(git_repo):
    # Given: tests/test_run.py 用子进程运行 bash scripts/run.sh，run.sh 用 dirname 形式 source 同目录的 lib.sh；
    #        仓库声明是恒报未全选的 cmd；基线已跑
    _decl(git_repo, STUB)
    run_sh = 'source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"\ngreet\n'
    d = make_repo(git_repo, extra={"scripts/run.sh": run_sh, "scripts/lib.sh": LIB_SH, "tests/test_run.py": TEST_RUN})
    baseline(git_repo, d)

    # When: 只改 scripts/lib.sh（行为不变），提交后运行 final
    change_and_commit(git_repo, "scripts/lib.sh", "# 注释\n" + LIB_SH)
    out, p = final(git_repo, d)

    # Then: final 走增量，重跑的测试文件恰为 tests/test_run.py
    inc = out["incremental"]
    assert inc["mode"] == "incremental", inc
    assert inc["rerun"] == ["tests/test_run.py"], inc


def test_shell_closure_resolves_common_forms(git_repo):
    # Given: scripts/run.sh 用变量、BASH_SOURCE 截取、循环里的动态文件名、git 顶层相对路径五种写法引用文件；
    #        scripts/lib/common.sh 再 source ./scripts/lib/deep.sh；相关文件都存在
    sg = load_hook("slice-gate")
    write(git_repo / "scripts" / "run.sh", RUN_FORMS)
    write(git_repo / "scripts" / "lib" / "common.sh", "source ./scripts/lib/deep.sh\n")
    for rel in ("scripts/lib/deep.sh", "scripts/env.sh", "scripts/units/a.sh", "scripts/units/b.sh", "tools/x.sh"):
        write(git_repo / rel, "true\n")
    commit_all(git_repo, "scripts")

    # When: 对 {"scripts/run.sh"} 求 shell 静态闭包
    got = set(sg._shell_closure(str(git_repo), {"scripts/run.sh"}))

    # Then: 结果含 common.sh、deep.sh、env.sh、units/a.sh、units/b.sh 与仓库根下的 tools/x.sh
    want = {"scripts/lib/common.sh", "scripts/lib/deep.sh", "scripts/env.sh",
            "scripts/units/a.sh", "scripts/units/b.sh", "tools/x.sh"}
    assert want <= got, got


def test_unresolvable_shell_reference_stays_full(git_repo):
    # Given: tests/test_run.py 运行 bash scripts/run.sh，run.sh 写的是 source "$(lib_dir)/lib.sh"（目录由函数算出，静态解析不到）；
    #        仓库声明是恒报未全选的 cmd；基线已跑
    _decl(git_repo, STUB)
    run_sh = 'lib_dir() { dirname "${BASH_SOURCE[0]}"; }\nsource "$(lib_dir)/lib.sh"\ngreet\n'
    d = make_repo(git_repo, extra={"scripts/run.sh": run_sh, "scripts/lib.sh": LIB_SH, "tests/test_run.py": TEST_RUN})
    baseline(git_repo, d)

    # When: 只改 scripts/lib.sh，提交后运行 final
    change_and_commit(git_repo, "scripts/lib.sh", "# 注释\n" + LIB_SH)
    out, p = final(git_repo, d)

    # Then: final 走全量，full_why 含 scripts/lib.sh
    inc = out["incremental"]
    assert inc["mode"] == "full" and "scripts/lib.sh" in (inc.get("full_why") or ""), inc
