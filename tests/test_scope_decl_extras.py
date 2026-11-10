"""gate-scope.json 的可选字段 global / blind / anchor_max_hops（scenario: flight-runner-contract#declared-* / scope-decl-extras-shape-checked）。"""
import json

from conftest import SCOPE_DECL, run_hook
from final_helpers import baseline, change_and_commit, final, make_repo


def _decl(repo, **extra):
    (repo / "openspec" / "gate-scope.json").write_text(json.dumps(dict(SCOPE_DECL, **extra)) + "\n", encoding="utf-8")


def test_declared_global_forces_full(git_repo):
    # Given: gate-scope.json 声明 global ["plugins/**"]；baseline 后只提交了没有任何用例加载的 plugins/p.py
    _decl(git_repo, **{"global": ["plugins/**"]})
    d = make_repo(git_repo, extra={"plugins/p.py": "X = 1\n"})
    baseline(git_repo, d)
    change_and_commit(git_repo, "plugins/p.py", "X = 2\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: incremental.mode 为 full，full_why 含 plugins/**
    inc = out.get("incremental") or {}
    assert inc.get("mode") == "full", (out, p.stderr)
    assert "plugins/**" in (inc.get("full_why") or ""), inc


def test_declared_blind_always_rerun(git_repo):
    # Given: gate-scope.json 声明 blind ["tests/test_c.py"]；baseline 后只提交了 src/a.py 的改动
    _decl(git_repo, blind=["tests/test_c.py"])
    d = make_repo(git_repo)
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 增量；重跑 2 个文件（依赖命中的 test_a 与声明盲区的 test_c）
    inc = out.get("incremental") or {}
    assert inc.get("mode") == "incremental", (out, p.stderr)
    assert inc.get("rerun") == ["tests/test_a.py", "tests/test_c.py"], inc


def test_scope_decl_extras_shape_checked(git_repo):
    # Given: gate-scope.json 的 global 是字符串、anchor_max_hops 是 0
    _decl(git_repo, **{"global": "plugins/**", "anchor_max_hops": 0})
    d = make_repo(git_repo)

    # When: 运行 lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；stderr 点名 global 须是字符串数组、anchor_max_hops 须是正整数
    assert p.returncode != 0, p.stdout
    assert "global 须是字符串数组" in p.stderr, p.stderr
    assert "anchor_max_hops 须是正整数" in p.stderr, p.stderr
