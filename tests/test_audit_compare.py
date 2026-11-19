"""test-tiers.py audit --compare / --plan：整改前后对比与本轮目标
（scenario: test-audit#compare-reports-resolved-remaining-new、#compare-exits-zero-when-targets-resolved、
#compare-fails-when-target-remains、#compare-unconfirmed-when-unjudged）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""
import json

from test_audit_scan import H, U, audit, setup, tiers


A, B, C = ("region-slow:" + H + n for n in ("test_a", "test_b", "test_c"))


def before(path, *item_ids):
    """之前那次体检的存档：只含比较要用的字段。"""
    items = [{"id": i, "category": i.split(":", 1)[0], "level": "violation", "rule": "R6", "scope": "hooks",
              "case": i.split(":", 1)[1], "sec": 9.0, "line": 5, "text": "", "fix": ["speedup", "allow", "delete"]}
             for i in item_ids]
    path.write_text(json.dumps({"v": 1, "at": "2026-11-18T00:00:00Z", "head": "b" * 40, "form": "shorthand",
                                "verdict": "violations", "items": items}, ensure_ascii=False), encoding="utf-8")
    return str(path)


def plan(path, items):
    path.write_text(json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8")
    return str(path)


def repo_now(repo, secs, extra_files=()):
    """当前仓库：区域 hooks 单条 5 秒；hooks 的用例耗时按 secs，单元层一条在线内。"""
    cases = {H + name: sec for name, sec in secs.items()}
    cases[U + "test_ok"] = 0.2
    setup(repo, tiers(hooks_budget={"case_sec": 5}), cases, extra_files=extra_files)


def test_compare_reports_resolved_remaining_new(git_repo, tmp_path):
    # Given: 之前 A、B 不合规；现在 A 已不超线，B 仍超线，另有新的超线用例 C
    repo_now(git_repo, {"test_a": 1.0, "test_b": 9.0, "test_c": 8.0})
    prev = before(tmp_path / "before.json", A, B)

    # When: 带 --compare 体检
    p, out = audit(git_repo, "--json", "--compare", prev)

    # Then: 三个清单各一条；有新增 → 退出 1
    assert out is not None, p.stdout + p.stderr
    cmp_ = out["compare"]
    assert (cmp_["resolved"], cmp_["remaining"], cmp_["new"]) == ([A], [B], [C]), cmp_
    assert p.returncode == 1


def test_compare_exits_zero_when_targets_resolved(git_repo, tmp_path):
    # Given: 整改稿只把 A 排进本轮（B 标 keep）；现在 A 已解决、B 仍在，没有新增，也没有未判项
    repo_now(git_repo, {"test_a": 1.0, "test_b": 9.0})
    prev = before(tmp_path / "before.json", A, B)
    pl = plan(tmp_path / "plan.json", {A: {"action": "speedup"}, B: {"action": "keep", "note": "下一批"}})

    # When: 带 --compare 与 --plan 体检（文本输出）
    p, _ = audit(git_repo, "--compare", prev, "--plan", pl)

    # Then: 目标都已解决 → 退出 0；没排进本轮的老债不挡复核
    assert p.returncode == 0, p.stdout + p.stderr
    assert any(l.startswith("前后对比：已解决 1 条 · 仍在 1 条 · 新增 0 条") for l in p.stdout.splitlines()), p.stdout


def test_compare_fails_when_target_remains(git_repo, tmp_path):
    # Given: 整改稿把 A 与 B 都排进本轮；现在 A 已解决、B 仍在
    repo_now(git_repo, {"test_a": 1.0, "test_b": 9.0})
    prev = before(tmp_path / "before.json", A, B)
    pl = plan(tmp_path / "plan.json", {A: {"action": "speedup"}, B: {"action": "speedup"}})

    # When: 带 --compare 与 --plan 体检
    p, out = audit(git_repo, "--json", "--compare", prev, "--plan", pl)

    # Then: 有目标未解决 → 退出 1 并点名
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    assert (out["compare"]["targets"], out["compare"]["targets_remaining"]) == (2, [B]), out["compare"]


def test_compare_unconfirmed_when_unjudged(git_repo, tmp_path):
    # Given: 目标 A 已不在不合规项里、没有新增；但 hooks 有一个测试文件没有测量
    repo_now(git_repo, {"test_a": 1.0}, extra_files=("tests/integration/hooks/test_h2.py",))
    prev = before(tmp_path / "before.json", A)
    pl = plan(tmp_path / "plan.json", {A: {"action": "speedup"}})
    junk = tmp_path / "junk.json"
    junk.write_text("不是 JSON", encoding="utf-8")

    # When: 带 --compare 与 --plan 体检；再拿一个不是 JSON 的文件当之前的体检
    p, _ = audit(git_repo, "--compare", prev, "--plan", pl)
    bad, _ = audit(git_repo, "--compare", str(junk))

    # Then: 判不全时不说达标：退出 3 并写明未能确认；之前的体检读不了 → 退出 2
    assert p.returncode == 3 and "未能确认" in p.stdout, p.stdout + p.stderr
    assert bad.returncode == 2, bad.stdout + bad.stderr


def test_compare_category_filter_keeps_unjudged(git_repo, tmp_path):
    # Given: 目标 A 已不在不合规项里、没有新增；但 hooks 有一个测试文件没有测量
    repo_now(git_repo, {"test_a": 1.0}, extra_files=("tests/integration/hooks/test_h2.py",))
    prev = before(tmp_path / "before.json", A)
    pl = plan(tmp_path / "plan.json", {A: {"action": "speedup"}})

    # When: 带 --compare / --plan，并按文档带上同样的 --category 复核
    p, _ = audit(git_repo, "--compare", prev, "--plan", pl, "--category", "region-slow")

    # Then: 范围级未判不被 --category 滤掉：仍退出 3、写明未能确认，不说整改达标
    assert p.returncode == 3 and "未能确认" in p.stdout, p.stdout + p.stderr
