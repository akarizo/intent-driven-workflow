"""baseline-full-suite-sec 的 scenario 骨架（strict xfail；切片 S1 实现后去掉标记即解锁）。"""
import json

import pytest

from conftest import commit_all
from final_helpers import TEST_A, baseline, change_and_commit, final, latest_anchor, make_repo
from test_baseline_anchor_reuse import clone_change

# 全量里垫一个固定 1.5 秒的用例：补跑只涉及 tests/test_a.py 时不会跑到它，全量耗时与补跑耗时必然拉开
SLOW = {"tests/test_slow.py": "import time\n\n\ndef test_slow():\n    time.sleep(1.5)\n"}


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def read_bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def strip_anchor_full_sec(repo):
    """把锚点池每条锚点的 full_suite_sec 去掉（模拟旧版本写的锚点）。"""
    files = [f for f in (repo / ".git" / "flight-anchors").glob("*.json") if not f.name.startswith(".tmp-")]
    assert files, "锚点池为空"
    for f in files:
        e = json.loads(f.read_text(encoding="utf-8"))
        e.pop("full_suite_sec", None)
        f.write_text(json.dumps(e, ensure_ascii=False), encoding="utf-8")


def touch_test_a(repo):
    change_and_commit(repo, "tests/test_a.py", TEST_A + "    # 改过\n")  # 与 TEST_A 同缩进：write 会整体 dedent


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_anchor_carries_full_suite_sec(git_repo):
    # Given: change c 跑过一次全量 baseline
    d = make_repo(git_repo)
    out = baseline(git_repo, d)
    assert out["mode"] == "full", out

    # When: 读取锚点池里最新的锚点
    anchor = latest_anchor(git_repo)

    # Then: 它的 `full_suite_sec` 是数值，等于 c 的 `gate-baseline.json` 里的 `full_suite_sec`
    sec = read_bl(d)["full_suite_sec"]
    assert is_num(anchor.get("full_suite_sec")), anchor.get("full_suite_sec")
    assert anchor["full_suite_sec"] == sec, (anchor.get("full_suite_sec"), sec)


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_final_anchor_keeps_full_suite_sec(git_repo):
    # Given: change c 跑过一次全量 baseline，记下的全量耗时为 T；之后提交了非测试文件 `src/a.py` 的改动
    d = make_repo(git_repo)
    baseline(git_repo, d)
    t = read_bl(d)["full_suite_sec"]
    assert is_num(t), t
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 对 c 运行 final，读取锚点池里最新的锚点；再运行 `final --full`，再读一次
    out1, p1 = final(git_repo, d)
    a1 = latest_anchor(git_repo)
    commit_all(git_repo, "final 记录")
    out2, p2 = final(git_repo, d, "--full")
    a2 = latest_anchor(git_repo)

    # Then: 第一次 final 走增量，最新锚点的 `full_suite_sec` 等于 T；`final --full` 之后，最新锚点的 `full_suite_sec` 是大于 0 的数值
    assert (out1.get("incremental") or {}).get("mode") == "incremental", (out1, p1.stderr)
    assert a1.get("change") == "c" and a1.get("full_suite_sec") == t, (a1.get("full_suite_sec"), t)
    assert a2.get("change") == "c", a2
    assert is_num(a2.get("full_suite_sec")) and a2["full_suite_sec"] > 0, (a2.get("full_suite_sec"), p2.stderr)


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_anchor_baseline_inherits_full_suite_sec(git_repo):
    # Given: change other 跑过全量 baseline，全量耗时为 T；change c 与 other 的 `gate.test` 相同，c 还没有基线
    d = make_repo(git_repo, extra=SLOW)
    other = clone_change(git_repo, "c", "other")
    baseline(git_repo, other)
    t = read_bl(other)["full_suite_sec"]
    assert is_num(t), t

    # When: 对 c 运行 baseline
    out = baseline(git_repo, d)

    # Then: c 的基线经锚点走增量，来源是 other；c 的 `full_suite_sec` 等于 T
    assert out["mode"] == "incremental", out.get("reuse_skipped")
    inc = out["incremental"]
    assert inc["source"] == "anchor" and inc["from"]["change"] == "other", inc
    assert out["full_suite_sec"] == t, (out["full_suite_sec"], t)


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_own_reuse_keeps_inherited_full_suite_sec(git_repo):
    # Given: change c 的基线经 other 的锚点走增量，`full_suite_sec` 等于 other 的全量耗时 T；之后只提交了测试文件的改动
    d = make_repo(git_repo, extra=SLOW)
    other = clone_change(git_repo, "c", "other")
    baseline(git_repo, other)
    t = read_bl(other)["full_suite_sec"]
    out1 = baseline(git_repo, d)
    assert out1["mode"] == "incremental" and out1["incremental"]["source"] == "anchor", out1.get("incremental")
    touch_test_a(git_repo)

    # When: 再对 c 运行 baseline
    out2 = baseline(git_repo, d)

    # Then: c 的基线复用本 change 旧基线（增量）；`full_suite_sec` 仍等于 T，不等于本次或上次的 `test.sec`
    assert out2["mode"] == "incremental" and out2["incremental"]["source"] == "own", out2.get("incremental")
    assert out2["full_suite_sec"] == t, (out2["full_suite_sec"], t)
    assert t not in (out1["test"].get("sec"), out2["test"].get("sec")), (t, out1["test"], out2["test"])


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_legacy_anchor_leaves_full_suite_sec_unknown(git_repo):
    # Given: change other 跑过全量 baseline，锚点池里的锚点都去掉了 `full_suite_sec`（模拟旧版本写的锚点）；change c 还没有基线
    d = make_repo(git_repo, extra=SLOW)
    other = clone_change(git_repo, "c", "other")
    baseline(git_repo, other)
    strip_anchor_full_sec(git_repo)

    # When: 对 c 运行 baseline，之后只提交测试文件的改动，再运行一次 baseline
    out1 = baseline(git_repo, d)
    touch_test_a(git_repo)
    out2 = baseline(git_repo, d)

    # Then: 两次 c 的基线都是增量，`full_suite_sec` 都为空
    assert out1["mode"] == "incremental" and out2["mode"] == "incremental", (out1.get("reuse_skipped"),
                                                                              out2.get("reuse_skipped"))
    assert out1["full_suite_sec"] is None and out2["full_suite_sec"] is None, (out1["full_suite_sec"],
                                                                               out2["full_suite_sec"])
