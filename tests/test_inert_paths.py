"""gate-scope.json 的 inert 声明：改动不影响测试结论的路径（scenario: inert-paths#inert-shape-checked、
#final-reuses-same-tree-across-inert-change、#baseline-reuse-ignores-inert-change、#anchor-delta-drops-inert-path、
#inert-never-covers-test-files-added-later、#graph-wins-when-inert-contradicts，
ship-rerun-decision#claude-md-commit-with-inert-keeps-ship-fresh，共 7 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import SCOPE_DECL, commit_all, run_hook, write
from final_helpers import baseline, change_and_commit, final, make_repo
from test_runner_contract import DROPPING
from test_runner_statement import REASON

PENDING = pytest.mark.xfail(strict=True, reason="骨架：切片 S1 实现后去掉")


def _decl(repo, **extra):
    (repo / "openspec" / "gate-scope.json").write_text(json.dumps(dict(SCOPE_DECL, **extra)) + "\n", encoding="utf-8")


def _green_final(repo, d):
    """baseline 与 final 都绿、飞行记录已提交。"""
    bl = baseline(repo, d)
    assert bl["ok"] is True, bl
    out, _ = final(repo, d)
    assert out["ok"] is True, out
    commit_all(repo, "chore(flight): 记录")


def _ship(repo, d):
    p = run_hook("slice-gate", "ship", "--change-dir", str(d), cwd=repo)
    return json.loads(p.stdout.strip().splitlines()[-1])


@PENDING
def test_inert_shape_checked(git_repo):
    # Given: gate-scope.json 的 inert 写成了字符串而不是数组
    _decl(git_repo, inert="docs/**")
    d = make_repo(git_repo)

    # When: 运行 lint
    p = run_hook("slice-gate", "lint", "--change-dir", str(d), cwd=git_repo)

    # Then: 退出非 0；stderr 点名 inert 须是字符串数组
    assert p.returncode != 0, p.stdout
    assert "inert 须是字符串数组" in p.stderr, p.stderr


@PENDING
def test_claude_md_commit_with_inert_keeps_ship_fresh(git_repo):
    # Given: gate-scope.json 声明 inert ["CLAUDE.md"]；final 已绿；之后只提交了 CLAUDE.md 的改动
    _decl(git_repo, inert=["CLAUDE.md"])
    d = make_repo(git_repo, extra={"CLAUDE.md": "# 记忆\n"})
    _green_final(git_repo, d)
    change_and_commit(git_repo, "CLAUDE.md", "# 记忆\n\n- 新沉淀的一条\n", msg="docs(memory): 沉淀本轮知识")

    # When: 运行 ship
    res = _ship(git_repo, d)

    # Then: reasons 里没有「过期」
    assert not [r for r in res["reasons"] if "过期" in r], res["reasons"]


@PENDING
def test_final_reuses_same_tree_across_inert_change(git_repo):
    # Given: 声明 inert ["CLAUDE.md"]；final 已绿；之后只提交了 CLAUDE.md 的改动
    _decl(git_repo, inert=["CLAUDE.md"])
    d = make_repo(git_repo, extra={"CLAUDE.md": "# 记忆\n"})
    _green_final(git_repo, d)
    change_and_commit(git_repo, "CLAUDE.md", "# 记忆\n\n- 新沉淀的一条\n")

    # When: 再运行 final
    out, p = final(git_repo, d)

    # Then: 同树沿用上一次的结论，不运行任何测试
    assert out["ok"] is True, (out, p.stderr)
    assert (out.get("incremental") or {}).get("mode") == "reused", out
    assert "同树沿用" in out["summary"], out


@PENDING
def test_baseline_reuse_ignores_inert_change(git_repo):
    # Given: 依赖图测不到的仓库（包装脚本丢掉插件参数，计划已表态），声明 inert ["docs/**"]；
    #        baseline 跑过一次全量；之后只提交了 docs/notes.md
    _decl(git_repo, inert=["docs/**"])
    d = make_repo(git_repo, extra={"tools/gate.sh": DROPPING, "docs/notes.md": "v1\n"},
                  gate_extra={"test": "bash tools/gate.sh", "scope_full_reason": REASON})
    first = baseline(git_repo, d)
    assert first["ok"] is True and first["mode"] == "full", first
    change_and_commit(git_repo, "docs/notes.md", "v2\n")

    # When: 重跑 baseline
    second = baseline(git_repo, d)

    # Then: 复用上一份基线的全量结论，不补跑任何测试文件
    assert second["ok"] is True and second["mode"] == "incremental", second
    assert second["incremental"]["source"] == "own" and second["incremental"]["rerun_files"] == [], second


@PENDING
def test_anchor_delta_drops_inert_path(git_repo):
    # Given: 声明 inert ["assets/**"]；基线测到了依赖图；assets/logo.bin 没有任何用例读它；之后只提交了它的改动
    _decl(git_repo, inert=["assets/**"])
    d = make_repo(git_repo, extra={"assets/logo.bin": "v1\n"})
    assert baseline(git_repo, d)["ok"] is True
    change_and_commit(git_repo, "assets/logo.bin", "v2\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 增量，重跑 0 个文件（不因「未被任何用例触及的非 Python 文件」退回全量）
    inc = out.get("incremental") or {}
    assert out["ok"] is True and inc.get("mode") == "incremental", (out, p.stderr)
    assert inc.get("rerun") == [], inc


@PENDING
def test_inert_never_covers_test_files_added_later(git_repo):
    # Given: 声明 inert ["extras/**"]，声明时该目录下只有说明文件；final 已绿；之后提交了新的测试文件 extras/test_new.py
    _decl(git_repo, inert=["extras/**"])
    d = make_repo(git_repo, extra={"extras/readme.txt": "说明\n"})
    _green_final(git_repo, d)
    change_and_commit(git_repo, "extras/test_new.py", "def test_new():\n    assert True\n")

    # When: 运行 ship
    res = _ship(git_repo, d)

    # Then: 测试文件永不按 inert 处理：final 过期
    assert [r for r in res["reasons"] if "final 过期" in r], res["reasons"]


@PENDING
def test_graph_wins_when_inert_contradicts(git_repo):
    # Given: 基线测到 tests/test_b.py 读 data/b.json；之后才把 data/** 声明成 inert，并提交了 data/b.json 的改动
    d = make_repo(git_repo)
    assert baseline(git_repo, d)["ok"] is True
    _decl(git_repo, inert=["data/**"])
    commit_all(git_repo, "declare inert")
    change_and_commit(git_repo, "data/b.json", '{"b": 2, "x": 1}\n')

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 依赖图优先：test_b 照常重跑；warnings 点名矛盾的文件与依赖它的测试文件
    inc = out.get("incremental") or {}
    assert inc.get("mode") == "incremental" and "tests/test_b.py" in (inc.get("rerun") or []), (out, p.stderr)
    assert any("inert" in w and "data/b.json" in w and "tests/test_b.py" in w for w in out["warnings"]), out["warnings"]
