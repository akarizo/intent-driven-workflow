"""仓库可用 gate.impacted 代替内建选测
（scenario: incremental-final#impacted-command-replaces-builtin-selection、#lint-rejects-bad-impacted）。"""
from conftest import run_hook
from final_helpers import baseline, change_and_commit, final, make_repo

IMPACTED = """
    import os
    import subprocess
    import sys

    path = os.environ.get("GATE_DELTA_FILE") or ""
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(open(path, encoding="utf-8").read() if path else "")
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_a.py"]))
"""


def test_impacted_command_replaces_builtin_selection(git_repo, tmp_path):
    # Given: gate.impacted 把 GATE_DELTA_FILE 的内容写到仓库外，再用 pytest 跑 tests/test_a.py；baseline 绿后只改了 src/a.py
    rec = tmp_path / "delta.txt"
    d = make_repo(git_repo, extra={"tools/impacted.py": IMPACTED},
                  gate_extra={"impacted": "python3 tools/impacted.py %s" % rec})
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: final 绿，incremental.source 为 impacted；写出的 Δ 含 src/a.py
    assert out["ok"] is True, out
    assert out["incremental"]["source"] == "impacted", out["incremental"]
    assert "src/a.py" in rec.read_text(encoding="utf-8").split()


def test_lint_rejects_bad_impacted(git_repo):
    # Given: slices.json 的 gate.impacted 是空串
    d = make_repo(git_repo, gate_extra={"impacted": ""})

    # When: 运行 slice-gate.py lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: lint 失败，stderr 点名 gate.impacted
    assert p.returncode != 0, p.stdout
    assert "gate.impacted" in p.stderr, p.stderr
