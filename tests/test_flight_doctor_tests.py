"""flight-doctor.py doctor 的 [tests] 一节：最近一份账本的各层与最慢用例、最近几个 change 的测试变更、没有账本时的说明
（scenario: test-ledger#doctor-tests-lists-tiers-and-slowest 等 3 条）。
骨架：strict xfail，断言是真实的；切片 S6 实现后去掉标记即解锁。"""
import json

from conftest import run_hook, write

HEADER = "<!-- timeline: ISO时间\\t事件\\t备注（由 hooks 自动追加） -->\n"
BIG = "tests/integration/hooks/test_h.py::test_big"


def add_change(repo, name, timeline=None):
    d = repo / "openspec" / "changes" / name
    write(d / "slices.json", json.dumps({"gate": {"test": "true"}, "slices": []}))
    if timeline is not None:
        (d / "timeline.md").write_text(HEADER + timeline, encoding="utf-8")
    return d


def doctor(repo):
    return run_hook("flight-doctor", "doctor", "--openspec-root", str(repo / "openspec"), cwd=repo)


def section(text, head="[tests]"):
    """doctor 输出里某一节的正文行（不含节标题）；没有这一节返回 []。"""
    lines = text.splitlines()
    if head not in lines:
        return []
    out = []
    for line in lines[lines.index(head) + 1:]:
        if line.startswith("["):
            break
        out.append(line)
    return out


def test_doctor_tests_lists_tiers_and_slowest(git_repo):
    # Given: 在途 change c 存有一份 final 账本：单元层 12 条共 3.0 秒，区域 hooks 2 条（9.0 秒与无耗时各一条）
    add_change(git_repo, "c")
    cases = {"tests/unit/test_u.py::test_u%02d" % i: {"o": "passed", "s": 0.25, "t": "unit", "m": 1} for i in range(12)}
    cases[BIG] = {"o": "passed", "s": 9.0, "t": "hooks", "m": 1}
    cases["tests/integration/hooks/test_h.py::test_old"] = {"o": "passed", "s": None, "t": "hooks", "m": 0}
    led = {"v": 1, "change": "c", "commit": "a" * 40, "at": "2026-11-18T03:00:00Z", "phase": "final", "mode": "full",
           "lock": "held", "id_form": "nodeid", "tiered": True, "complete": False, "cases": cases}
    write(git_repo / ".git" / "flight-ledger" / "c" / "final.json", json.dumps(led, ensure_ascii=False))

    # When: 运行 doctor
    p = doctor(git_repo)

    # Then: [tests] 写出来源、各层条数与秒数、无耗时条数；最慢清单不超过 10 条且最慢的排第一
    sec = section(p.stdout)
    assert p.returncode == 0 and sec, p.stdout + p.stderr
    assert any("c" in l and "final" in l and "aaaaaaaaaa" in l for l in sec), sec
    assert any("unit" in l and "12 条" in l and "3.0" in l for l in sec), sec
    assert any("hooks" in l and "2 条" in l and "9.0" in l for l in sec), sec
    assert any("无耗时 1 条" in l for l in sec), sec
    slow = [l for l in sec if "::" in l]
    assert 1 <= len(slow) <= 10 and BIG in slow[0], slow


def test_doctor_tests_lists_recent_change_deltas(git_repo):
    # Given: c1 / c2 的时间线各有一条带「用例 +A/-R（新增 Xs）」片段的 final 行，c3 的 final 行没有片段
    add_change(git_repo, "c1", "2026-11-18T01:00:00Z\tfinal\t全量（没有可用锚点） 测试 10.0s · 用例 +3/-1（新增 2.5s） · 排队 0.0s ok\n")
    add_change(git_repo, "c2", "2026-11-18T02:00:00Z\tfinal\t增量（锚点 abcdef0123，重跑 1 个文件 / 沿用 9 个用例） 测试 1.0s · "
                               "用例 +0/-0（新增 0.0s） · 排队 0.0s ok\n")
    add_change(git_repo, "c3", "2026-11-18T03:00:00Z\tfinal\t全量（没有可用锚点） 测试 9.0s · 排队 0.0s ok\n")

    # When: 运行 doctor
    p = doctor(git_repo)

    # Then: [tests] 按 change 列出前两个的三个数；第三个不出现
    sec = section(p.stdout)
    assert p.returncode == 0 and sec, p.stdout + p.stderr
    assert any("c1" in l and "+3/-1" in l and "2.5" in l for l in sec), sec
    assert any("c2" in l and "+0/-0" in l and "0.0" in l for l in sec), sec
    assert not any("c3" in l for l in sec), sec


def test_doctor_tests_explains_missing_ledger(git_repo):
    # Given: 本机没有任何账本，openspec 根没有 test-tiers.json
    add_change(git_repo, "c")

    # When: 运行 doctor
    p = doctor(git_repo)

    # Then: [tests] 说明没有账本并提示 /test-tiers；其余各节照常输出
    sec = section(p.stdout)
    assert p.returncode == 0 and sec, p.stdout + p.stderr
    assert any(l.strip().startswith("没有账本数据") for l in sec), sec
    assert any("/test-tiers" in l for l in sec), sec
    for head in ("[runner]", "[anchors]", "[gate.test]", "[declare]", "[checks]", "[lock]"):
        assert head in p.stdout.splitlines(), (head, p.stdout)
