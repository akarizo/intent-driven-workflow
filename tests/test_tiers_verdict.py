"""单元层慢单测（G10）与不纯（G11）的纯函数判定
（scenario: test-tiers#slow-unit-test-confirmed-is-red、#slow-unit-test-not-confirmed-on-rerun-passes、
#allowed-slow-unit-test-is-warning、#impure-unit-test-is-red、#unmeasurable-unit-run-only-warns）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S2 实现 tier_verdicts 后去掉标记即解锁。
本文件只调纯函数（加载 slice-gate 走 import 机制），不碰真实文件、不起子进程。"""
import pytest

from conftest import load_hook

XF = pytest.mark.xfail(strict=True, reason="S2 尚未实现")
BIG = "tests/unit/test_a.py::test_big"


def verdicts(probe, rerun=None, allow=None, why=None):
    """调 slice-gate 的 tier_verdicts(probe, probe_why, rerun, allow) → (failed, warnings)。"""
    sg = load_hook("slice-gate")
    return sg.tier_verdicts(probe, why, rerun or {}, allow or {})


@XF
def test_slow_unit_test_confirmed_is_red():
    # Given: 单元层记录里 test_big 首跑 3.4 秒、单独重跑 3.3 秒，另一个用例 0.01 秒；slow_allow 为空
    probe = {BIG: {"sec": 3.4, "hits": {}}, "tests/unit/test_a.py::test_ok": {"sec": 0.01, "hits": {}}}

    # When: 判定单元层
    failed, _ = verdicts(probe, rerun={BIG: 3.3})

    # Then: 恰有一条以 G10 开头的失败，点名 test_big，含 3.4 与 3.3
    g10 = [f for f in failed if f.startswith("G10")]
    assert len(g10) == 1, failed
    assert BIG in g10[0] and "3.4" in g10[0] and "3.3" in g10[0], g10


@XF
def test_slow_unit_test_not_confirmed_on_rerun_passes():
    # Given: test_jitter 首跑 3.1 秒，单独重跑 0.2 秒
    nid = "tests/unit/test_a.py::test_jitter"
    probe = {nid: {"sec": 3.1, "hits": {}}}

    # When: 判定单元层
    failed, warnings = verdicts(probe, rerun={nid: 0.2})

    # Then: 没有任何 G10 失败，也没有关于它的放行警告
    assert not [f for f in failed if f.startswith("G10")], failed
    assert not [w for w in warnings if nid in w], warnings


@XF
def test_allowed_slow_unit_test_is_warning():
    # Given: test_big 首跑 3.4 秒、重跑 3.3 秒；slow_allow 里有它，approved 带时间与原话摘要
    probe = {BIG: {"sec": 3.4, "hits": {}}}
    allow = {BIG: {"reason": "fixture 要读大样本", "approved": "2026-10-28T08:00:00Z · 放行 test_big"}}

    # When: 判定单元层
    failed, warnings = verdicts(probe, rerun={BIG: 3.3}, allow=allow)

    # Then: 没有任何 G10 失败；警告里有一条点名 test_big 并含放行时间
    assert not [f for f in failed if f.startswith("G10")], failed
    assert any(BIG in w and "2026-10-28T08:00:00Z" in w for w in warnings), warnings


@XF
def test_impure_unit_test_is_red():
    # Given: test_io 碰了「文件」，样例是 open /tmp/x；耗时很短
    nid = "tests/unit/test_a.py::test_io"
    probe = {nid: {"sec": 0.02, "hits": {"文件": "open /tmp/x"}}}

    # When: 判定单元层
    failed, _ = verdicts(probe)

    # Then: 有一条以 G11 开头的失败，点名 test_io 并含样例 open /tmp/x
    g11 = [f for f in failed if f.startswith("G11")]
    assert len(g11) == 1, failed
    assert nid in g11[0] and "open /tmp/x" in g11[0], g11


@XF
def test_unmeasurable_unit_run_only_warns():
    # Given: 单元层运行不可度量（probe 为 None），原因是「没有探针输出（不是 pytest？）」
    why = "没有探针输出（不是 pytest？）"

    # When: 判定单元层
    failed, warnings = verdicts(None, why=why)

    # Then: 没有任何 G10 / G11 失败；恰有一条警告以「G10/G11 不可度量」开头并含原因
    assert not [f for f in failed if f.startswith(("G10", "G11"))], failed
    hits = [w for w in warnings if w.startswith("G10/G11 不可度量")]
    assert len(hits) == 1 and "没有探针输出" in hits[0], warnings
