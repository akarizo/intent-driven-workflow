"""同一棵代码树的 final 沿用上次结论；ship 按树判 final 新鲜
（scenario: incremental-final#same-tree-final-reuses-result、#red-final-is-not-reused、#ship-fresh-when-tree-unchanged）。
护栏（red-final-is-not-reused）在 base 上已成立，不带标记。"""
import json

from conftest import commit_all, git, run_hook
from final_helpers import baseline, final, make_repo, timeline_rows


def counting_test(path, ok=True):
    """每次运行都往仓库外的计数文件追加一行的用例。"""
    return ("def test_count():\n    with open(%r, 'a') as f:\n        f.write('x\\n')\n    assert %s\n"
            % (str(path), "True" if ok else "False"))


def count(path):
    return len(path.read_text().splitlines()) if path.exists() else 0


def test_same_tree_final_reuses_result(git_repo, tmp_path):
    # Given: scenario 映射到计数用例；final 刚刚绿过，之后只提交了飞行记录文件
    counter = tmp_path / "count.txt"
    d = make_repo(git_repo, extra={"tests/test_count.py": counting_test(counter)},
                  scenario="tests/test_count.py::test_count")
    baseline(git_repo, d)
    first, _ = final(git_repo, d)
    assert first["ok"] is True, first
    commit_all(git_repo, "flight")
    n1 = count(counter)

    # When: 再运行一次 final
    out, p = final(git_repo, d)

    # Then: final 绿且沿用；计数文件没有增加；timeline 备注含「同树沿用」
    assert out["ok"] is True, out
    assert out["incremental"]["mode"] == "reused", out.get("incremental")
    assert count(counter) == n1
    assert "同树沿用" in timeline_rows(d, "final")[-1]


def test_red_final_is_not_reused(git_repo, tmp_path):
    # Given: scenario 映射到一个必然失败的计数用例；上一次 final 红，之后代码没有变
    counter = tmp_path / "count.txt"
    d = make_repo(git_repo, extra={"tests/test_count.py": counting_test(counter, ok=False)},
                  scenario="tests/test_count.py::test_count")
    run_hook("slice-gate", "baseline", "--change-dir", str(d), cwd=git_repo)
    commit_all(git_repo, "baseline")
    first, _ = final(git_repo, d)
    assert first["ok"] is False, first
    n1 = count(counter)

    # When: 再运行一次 final
    out, p = final(git_repo, d)

    # Then: final 照常运行（计数增加），不是沿用
    assert (out.get("incremental") or {}).get("mode") != "reused", out.get("incremental")
    assert count(counter) > n1


def test_ship_fresh_when_tree_unchanged(git_repo):
    # Given: final 在 commit X 上绿过；随后把 X 改写成内容只多了飞行记录、但不是 X 后代的 commit Y
    d = make_repo(git_repo)
    baseline(git_repo, d)
    out, _ = final(git_repo, d)
    assert out["ok"] is True, out
    x = git(git_repo, "rev-parse", "HEAD")
    git(git_repo, "add", "-A")
    git(git_repo, "commit", "-q", "--amend", "-m", "改写后的提交")
    y = git(git_repo, "rev-parse", "HEAD")
    assert y != x

    # When: 运行 ship
    p = run_hook("slice-gate", "ship", "--change-dir", str(d), cwd=git_repo)

    # Then: reasons 里没有「过期」
    res = json.loads(p.stdout.strip().splitlines()[-1])
    assert not [r for r in res["reasons"] if "过期" in r], res["reasons"]


def test_final_not_reused_when_slice_scenarios_change(git_repo):
    # Given: final 刚刚绿过；之后只在 slices.json 给 S1 加了一个没有测试映射的 scenario id（slices.json 不进 Δ）
    d = make_repo(git_repo)
    baseline(git_repo, d)
    first, _ = final(git_repo, d)
    assert first["ok"] is True, first
    data = json.loads((d / "slices.json").read_text(encoding="utf-8"))
    data["slices"][0]["scenarios"].append("c#unmapped")
    (d / "slices.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    commit_all(git_repo, "add scenario")

    # When: 再运行一次 final
    out, p = final(git_repo, d)

    # Then: 指纹含每片 scenarios，不沿用；G7 判新 scenario 无测试映射而红
    assert (out.get("incremental") or {}).get("mode") != "reused", out.get("incremental")
    assert out["ok"] is False, out


def test_final_record_write_failure_warned_in_report(git_repo):
    # Given: baseline 绿；final 记录目录 <git common dir>/flight-final 被一个同名普通文件占住（记录写不进去）
    d = make_repo(git_repo)
    baseline(git_repo, d)
    (git_repo / ".git" / "flight-final").write_text("占位\n", encoding="utf-8")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: 写入失败的警告既在 stdout JSON 里，也进了 gate-report 的 final 行
    assert any("final 记录写入失败" in w for w in out["warnings"]), out["warnings"]
    last = [l for l in (d / "gate-report.md").read_text(encoding="utf-8").splitlines() if "| final |" in l][-1]
    assert "final 记录写入失败" in last, last
