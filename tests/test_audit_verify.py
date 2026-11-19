"""test-audit.py verify：命令内整改的护栏——改动范围、用例与断言不变、分层文件的改动与稿一致、核对不了的如实列出
（scenario: test-audit#verify-passes-pure-moves、#verify-flags-source-changes、#verify-flags-assert-and-case-changes、
#verify-flags-unplanned-budget-and-allow-changes、#verify-lists-non-python-files-as-unchecked）。
骨架：strict xfail，断言是真实的；切片 S5 实现后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, run_hook, write

PENDING = pytest.mark.xfail(strict=True, reason="change test-audit S5 未实现")

ONE = "def test_one():\n    # Given: 无\n    # When: 无\n    # Then: 恒真\n    assert 1 + 1 == 2\n"
TWO = "def test_two(tmp_path):\n    # Given: 无\n    # When: 写文件\n    # Then: 读回\n    (tmp_path / 'f').write_text('x')\n    assert (tmp_path / 'f').read_text() == 'x'\n"
OLD_B = """import pytest


def f():
    return 1


def test_x():
    assert f() == 1


def test_y():
    assert f()


@pytest.mark.parametrize("n", [1, 2, 3])
def test_z(n):
    assert n
"""
NEW_B = """import pytest


def f():
    return 1


def test_x():
    assert f() >= 1


@pytest.mark.parametrize("n", [1, 2])
def test_z(n):
    assert n


def test_w():
    assert f()
"""
K_OLD, K_NEW = "tests/unit/test_a.py::test_one", "tests/unit/test_a.py::test_two"
ENTRY = {"reason": "读大样本", "approved": "2026-11-18T03:12:00Z · 放行", "limit_sec": 10, "expires": "2099-01-01"}


def tiers(total=100, allow=None):
    return {"unit": {"paths": ["tests/unit/**"], "cmd": "true"},
            "regions": {"hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/**"], "cmd": "true",
                                  "budget": {"case_sec": 30, "total_sec": total}}},
            "slow_allow": allow or {}}


def base_repo(repo, tiers_obj=None, extra=None):
    """基线提交：分层文件、src/a.py、tests/unit/test_a.py（test_one 与 test_two）；extra = {路径: 内容}。→ 基线 commit。"""
    (repo / "openspec" / "test-tiers.json").write_text(json.dumps(tiers_obj or tiers(), ensure_ascii=False),
                                                       encoding="utf-8")
    write(repo / "src" / "a.py", "def a():\n    return 1\n")
    (repo / "tests" / "unit").mkdir(parents=True)
    (repo / "tests" / "unit" / "test_a.py").write_text(ONE + "\n\n" + TWO, encoding="utf-8")
    for rel, text in (extra or {}).items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    return commit_all(repo, "base")


def split_two(repo):
    """把 test_two 原样拆到区域 hooks 下的新文件，test_one 留在原处。"""
    (repo / "tests" / "unit" / "test_a.py").write_text(ONE, encoding="utf-8")
    (repo / "tests" / "integration" / "hooks").mkdir(parents=True)
    (repo / "tests" / "integration" / "hooks" / "test_a_io.py").write_text(TWO, encoding="utf-8")


def verify(repo, tmp_path, base, plan, name="plan.json"):
    pl = tmp_path / name
    pl.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    p = run_hook("test-audit", "verify", "--plan", str(pl), "--base", base, "--json", cwd=repo)
    try:
        out = json.loads(p.stdout)
    except ValueError:
        out = None
    return p, out


@PENDING
def test_verify_passes_pure_moves(git_repo, tmp_path):
    # Given: 基线里 tests/unit/test_a.py 有两条用例；之后把 test_two 原样拆到区域 hooks 下的新文件
    base = base_repo(git_repo)
    split_two(git_repo)
    plan = {"items": {"unit-impure:" + K_NEW: {"action": "split", "dest": "tests/integration/hooks/test_a_io.py"}}}

    # When: 跑护栏
    p, out = verify(git_repo, tmp_path, base, plan)

    # Then: 通过；改动的测试文件两个
    assert p.returncode == 0 and out is not None, p.stdout + p.stderr
    assert out["ok"] is True and out["violations"] == [] and out["changed"]["tests"] == 2, out


@PENDING
def test_verify_flags_source_changes(git_repo, tmp_path):
    # Given: 拆文件的同时还改了 src/a.py（命中区域 hooks 的 covers）、新增 tools/helper.py 与 tests/conftest.py；
    #        稿的 support 只写了 tests/conftest.py 与 src/**
    base = base_repo(git_repo)
    split_two(git_repo)
    write(git_repo / "src" / "a.py", "def a():\n    return 2\n")
    write(git_repo / "tools" / "helper.py", "X = 1\n")
    write(git_repo / "tests" / "conftest.py", "import pytest\n")
    plan = {"items": {}, "support": ["tests/conftest.py", "src/**"]}

    # When: 跑护栏
    p, out = verify(git_repo, tmp_path, base, plan)

    # Then: 被测代码不能靠 support 豁免；稿外文件点名；support 里的文件放行并列出
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    v = out["violations"]
    assert any("改了被测代码" in x and "src/a.py" in x for x in v), v
    assert any("稿外的改动" in x and "tools/helper.py" in x for x in v), v
    assert not any("tests/conftest.py" in x for x in v) and "tests/conftest.py" in out["changed"]["support"], out


@PENDING
def test_verify_flags_assert_and_case_changes(git_repo, tmp_path):
    # Given: 基线里 tests/unit/test_b.py 有 test_x / test_y / test_z（三组参数）；之后搬到区域 hooks，同时
    #        test_x 的断言改了、test_y 删了、test_z 少了一组参数、新加了 test_w
    base = base_repo(git_repo, extra={"tests/unit/test_b.py": OLD_B})
    (git_repo / "tests" / "unit" / "test_b.py").unlink()
    (git_repo / "tests" / "integration" / "hooks").mkdir(parents=True)
    (git_repo / "tests" / "integration" / "hooks" / "test_b.py").write_text(NEW_B, encoding="utf-8")

    # When: 跑护栏
    p, out = verify(git_repo, tmp_path, base, {"items": {}})

    # Then: 四处各点名一条
    assert p.returncode == 1 and out is not None, p.stdout + p.stderr
    v = out["violations"]
    for word, name in (("断言有改动", "test_x"), ("用例消失", "test_y"), ("参数化有改动", "test_z"), ("用例新增", "test_w")):
        assert any(word in x and name in x for x in v), (word, name, v)


@PENDING
def test_verify_flags_unplanned_budget_and_allow_changes(git_repo, tmp_path):
    # Given: 分层文件相对基线：hooks 的总量预算从 100 秒放宽到 200 秒，放行名单少了 K_OLD、多了 K_NEW
    base = base_repo(git_repo, tiers(allow={K_OLD: ENTRY}))
    (git_repo / "openspec" / "test-tiers.json").write_text(
        json.dumps(tiers(total=200, allow={K_NEW: ENTRY}), ensure_ascii=False), encoding="utf-8")
    matching = {"items": {"total-over:hooks": {"action": "budget"}, "unit-slow:" + K_NEW: {"action": "allow"},
                          "allow-stale:" + K_OLD: {"action": "drop-allow"}}}

    # When: 先用没有对应条目的整改稿跑护栏，再换成带对应条目的
    p1, bare = verify(git_repo, tmp_path, base, {"items": {}})
    p2, planned = verify(git_repo, tmp_path, base, matching, name="plan2.json")

    # Then: 稿外的预算放宽、放行新增、放行删除各一条，变动清单照打；稿里有对应条目时通过
    assert p1.returncode == 1 and bare is not None, p1.stdout + p1.stderr
    v = bare["violations"]
    assert any("稿外" in x and "放宽" in x and "hooks" in x for x in v), v
    assert any("稿外" in x and K_NEW in x for x in v) and any("稿外" in x and K_OLD in x for x in v), v
    assert len(v) == 3 and bare["budget_changes"] and bare["changed"]["tiers"] is True, bare
    assert p2.returncode == 0 and planned is not None and planned["ok"] is True, p2.stdout + p2.stderr


@PENDING
def test_verify_lists_non_python_files_as_unchecked(git_repo, tmp_path):
    # Given: 改动里有一个非 Python 的测试文件与一个语法错误的 Python 测试文件
    base = base_repo(git_repo)
    write(git_repo / "web" / "a.test.ts", "test('a', () => {})\n")
    (git_repo / "tests" / "unit" / "test_bad.py").write_text("def test_(:\n", encoding="utf-8")

    # When: 跑护栏；再拿一个不存在的 commit 当基线
    p, out = verify(git_repo, tmp_path, base, {"items": {}})
    bad, _ = verify(git_repo, tmp_path, "0" * 40, {"items": {}})

    # Then: 核对不了的列进未核对、不判失败；基线不是本仓库的 commit → 退出 2
    assert p.returncode == 0 and out is not None, p.stdout + p.stderr
    assert {"web/a.test.ts", "tests/unit/test_bad.py"} <= set(out["unchecked"]) and out["violations"] == [], out
    assert bad.returncode == 2, bad.stdout + bad.stderr
