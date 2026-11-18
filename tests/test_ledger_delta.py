"""test-ledger.py：final 账本对基线账本的对账、时间线片段、Markdown 与建议行
（scenario: test-ledger#delta-counts-added-removed-slower 等 5 条）。
骨架：strict xfail，断言是真实的；切片 S3 实现后去掉标记即解锁。"""

from conftest import load_hook, write


def case(sec, m=1, tier=None, outcome="passed"):
    return {"o": outcome, "s": sec, "t": tier, "m": m}


def ledger(cases, mode="full", form="nodeid", commit="f" * 40, phase="final"):
    return {"v": 1, "change": "c", "commit": commit, "at": "2026-11-18T00:00:00Z", "phase": phase, "mode": mode,
            "lock": "held", "id_form": form, "tiered": any(c["t"] for c in cases.values()), "complete": True,
            "cases": cases}


def base_ledger(cases, form="nodeid"):
    return ledger(cases, form=form, commit="b" * 40, phase="baseline")


def test_delta_counts_added_removed_slower():
    # Given: 基线有 a / b / c；全量 final 有 a、变慢的 c、新增的 d 与 e
    tl = load_hook("test-ledger")
    base = base_ledger({"a": case(0.1), "b": case(0.2), "c": case(1.0)})
    final = ledger({"a": case(0.1), "c": case(2.6), "d": case(0.4), "e": case(3.0)})

    # When: 对账
    d, why = tl.delta(base, final)

    # Then: 新增 2 条共 3.4 秒、删除 1 条、变慢 1 条；最慢新增排在前面
    assert why is None, why
    assert (d["added"], d["added_sec"], d["removed"], d["unknown"], d["slower_n"]) == (2, 3.4, 1, 0, 1), d
    assert d["slower"] == [["c", 1.0, 2.6]], d
    assert d["top_added"] == [["e", 3.0, None], ["d", 0.4, None]], d
    assert (d["commit"], d["base_commit"]) == ("f" * 40, "b" * 40)
    assert d["tiers"] == {"-": {"before": [3, 1.3], "after": [4, 6.1]}}, d
    assert d["advice"] == tl.advice(d)


def test_delta_keeps_unrerun_cases_out_of_removed(tmp_path):
    # Given: 基线三条用例分属三个文件；final 是 impacted，只跑了 tests/test_b.py；tests/test_gone.py 已不存在
    tl = load_hook("test-ledger")
    write(tmp_path / "tests" / "test_a.py", "")
    write(tmp_path / "tests" / "test_b.py", "")
    base = base_ledger({"tests/test_a.py::test_a": case(0.1), "tests/test_b.py::test_b": case(0.1),
                        "tests/test_gone.py::test_g": case(0.1)})
    final = ledger({"tests/test_b.py::test_b2": case(0.1)}, mode="impacted")

    # When: 对账，给出重跑清单与仓库根
    d, why = tl.delta(base, final, rerun_files=["tests/test_b.py"], root=str(tmp_path))

    # Then: 被重跑文件里消失的用例与文件已删的用例算删除；没重测的不算
    assert why is None, why
    assert (d["added"], d["removed"], d["unknown"]) == (1, 2, 1), d


def test_delta_handles_missing_or_junit_baseline():
    # Given: 一份 nodeid 形式的 final 账本；一份 junit 形式的基线账本
    tl = load_hook("test-ledger")
    final = ledger({"tests/test_a.py::test_a": case(0.1), "tests/test_a.py::TestC::test_m": case(0.2)})
    junit_base = base_ledger({"tests.test_a::test_a": case(0.1), "tests.test_a::test_old": case(0.1)}, form="junit")

    # When: 没有基线账本时对账；基线是 junit 形式时对账
    d1, why1 = tl.delta(None, final)
    d2, why2 = tl.delta(junit_base, final)

    # Then: 没有基线账本 → 没有结果并说明原因；形式不同 → nodeid 一侧换算后照常对账
    assert d1 is None and "基线账本不在本机" in why1, why1
    assert why2 is None and (d2["added"], d2["removed"], d2["unknown"]) == (1, 1, 0), (d2, why2)
    assert d2["top_added"] == [["tests.test_a.TestC::test_m", 0.2, None]], d2


def test_delta_skips_incomplete_baseline():
    # Given: 基线账本不完整（复用的基线没有可沿用的来源账本，只收录了补跑的 a）；全量 final 的用例集合与原来相同
    tl = load_hook("test-ledger")
    base = base_ledger({"a": case(0.1)})
    base["complete"] = False
    final = ledger({"a": case(0.1), "b": case(2.0), "c": case(2.0)})

    # When: 对账
    d, why = tl.delta(base, final)

    # Then: 不对账，给出原因，不把没补跑的 b / c 编成新增
    assert d is None and "基线账本不完整" in (why or ""), (d, why)


def test_segment_and_markdown_are_bounded():
    # Given: 新增 14 条（其中 12 条有耗时，共 8.4 秒）、删除 1 条、变慢 7 条的对账结果
    tl = load_hook("test-ledger")
    fd = load_hook("flight-doctor")
    slow = ["tests/test_s.py::test_s%02d" % i for i in range(7)]
    new = ["tests/test_n.py::test_n%02d" % i for i in range(14)]
    base = base_ledger(dict({"tests/test_r.py::test_r": case(0.1), "tests/test_k.py::test_k": case(0.1)},
                            **{n: case(1.0) for n in slow}))
    cases = dict({"tests/test_k.py::test_k": case(0.1)}, **{n: case(3.0) for n in slow})
    cases.update({n: case(0.7 if i < 12 else None) for i, n in enumerate(new)})
    d, _ = tl.delta(base, ledger(cases))
    plain = "全量（没有可用锚点） 测试 524.3s · 检查 ratchet 3.1s / linkage 2.4s · 排队 212.0s · 负载 2.9→17.8/18 ok"

    # When: 取片段与 Markdown，把片段插进 final 备注的「检查」之后、锁片段之前
    seg = tl.segment(d)
    note = plain.replace(" · 排队", " · %s · 排队" % seg)
    md = tl.render(d).splitlines()

    # Then: 片段格式固定且能取回；现有解析结果不变；Markdown 的清单各不超过 5 条
    assert seg == "用例 +14/-1（新增 8.4s）", seg
    assert tl.parse_segment(note) == {"added": 14, "removed": 1, "added_sec": 8.4}
    assert tl.parse_segment(plain) is None
    assert fd.note_costs(note) == fd.note_costs(plain) and fd.parse_note(note) == fd.parse_note(plain)
    assert fd.note_costs(note)["checks"] == {"ratchet": 3.1, "linkage": 2.4}
    assert note.endswith(" ok")
    assert md[0] == "## 测试变更", md[:2]
    assert 1 <= sum(1 for l in md if l.strip().startswith("- tests/test_n.py::")) <= 5, md
    assert 1 <= sum(1 for l in md if l.strip().startswith("- tests/test_s.py::")) <= 5, md
    assert (d["slower_n"], len(d["slower"]), len(d["top_added"]), d["no_sec"]) == (7, 5, 5, 2), d


def test_advice_lines_follow_fixed_rules():
    # Given: 四份对账结果——新增耗时主要在集成层；单元层耗时涨了 6 秒（30%）；三成用例无耗时；以上都不满足
    tl = load_hook("test-ledger")
    h1 = "tests/integration/hooks/test_h.py::test_h1"
    d1, _ = tl.delta(base_ledger({"u0": case(1.0, tier="unit")}),
                     ledger({"u0": case(1.0, tier="unit"), "u1": case(0.9, tier="unit"),
                             h1: case(4.0, tier="hooks"), "h2": case(3.5, tier="hooks")}))
    units = {"u%02d" % i: case(1.0, tier="unit") for i in range(20)}
    d2, _ = tl.delta(base_ledger(units), ledger(dict(units, u00=case(7.0, tier="unit"))))
    many = {"c%03d" % i: case(None if i < 30 else 0.1, m=0 if i < 30 else 1) for i in range(100)}
    d3, _ = tl.delta(base_ledger(many), ledger(many))
    d4, _ = tl.delta(base_ledger({"a": case(0.1)}), ledger({"a": case(0.1)}))

    # When: 取建议行
    a1, a2, a3, a4 = tl.advice(d1), tl.advice(d2), tl.advice(d3), tl.advice(d4)

    # Then: 各自命中对应的一条规则；都不满足时没有建议
    assert any(h1 in line for line in a1), a1
    assert any("unit" in line for line in a2), a2
    assert any("全量" in line for line in a3), a3
    assert a4 == [], a4
