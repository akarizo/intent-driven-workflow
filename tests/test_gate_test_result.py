"""final 把本次测试结果交给检查；gate.test 环境带阶段与 change 名（scenario: gate-test-result-handoff#*）。"""
import json
import os

import pytest

from final_helpers import PY, baseline, change_and_commit, final, make_repo

COPY_RESULT = """
    import os
    import sys

    src = os.environ.get("GATE_TEST_RESULT") or ""
    with open(sys.argv[1], "w", encoding="utf-8") as f:
        f.write(open(src, encoding="utf-8").read() if src and os.path.isfile(src) else "null")
"""

RECORD_VAR = """
    import os
    import sys

    with open(sys.argv[1], "a", encoding="utf-8") as f:
        f.write((os.environ.get("GATE_TEST_RESULT") or "") + "\\n")
"""


def _copy_check(path):
    return [{"name": "copy", "baseline": None, "final": "python3 tools/copy_result.py %s" % path, "timeout_sec": 120}]


@pytest.mark.xfail(strict=True, reason="S1 未实现：final 不写 .gate-test-result.json、不设 GATE_TEST_RESULT")
def test_final_full_hands_result_to_checks(git_repo, tmp_path):
    # Given: 计划配了一项检查，final 命令把 GATE_TEST_RESULT 指向的文件复制到仓库外；baseline 已跑过
    out_path = tmp_path / "result.json"
    d = make_repo(git_repo, extra={"tools/copy_result.py": COPY_RESULT}, gate_extra={"checks": _copy_check(out_path)})
    baseline(git_repo, d)

    # When: 运行 final --full
    out, p = final(git_repo, d, "--full")

    # Then: 结果 mode 为 full、inherited 为 0、complete 为真；test_a 结局 passed；junit 副本存在
    assert out["ok"] is True, out
    rec = json.loads(out_path.read_text(encoding="utf-8"))
    assert rec is not None, "检查没有拿到 GATE_TEST_RESULT"
    assert rec["mode"] == "full", rec
    assert rec["inherited"] == 0 and rec["complete"] is True, rec
    assert rec["nodes"]["tests/test_a.py::test_a"] == "passed", rec["nodes"]
    assert rec["junit"] and os.path.isfile(rec["junit"]), rec


@pytest.mark.xfail(strict=True, reason="S1 未实现：增量 final 不交出合成结局（锚点不带 nodes）")
def test_final_incremental_result_composes_anchor_outcomes(git_repo, tmp_path):
    # Given: baseline 写下测到依赖图的锚点；之后只提交了 src/a.py 的改动；检查复制结果文件
    out_path = tmp_path / "result.json"
    d = make_repo(git_repo, extra={"tools/copy_result.py": COPY_RESULT}, gate_extra={"checks": _copy_check(out_path)})
    baseline(git_repo, d)
    change_and_commit(git_repo, "src/a.py", "def a():\n    return 1  # 改过\n")

    # When: 运行 final
    out, p = final(git_repo, d)

    # Then: mode 为 incremental、complete 为真、inherited ≥ 1；nodes 同时含重跑的 test_a 与沿用的 test_b
    assert out["ok"] is True and out["incremental"]["mode"] == "incremental", out
    rec = json.loads(out_path.read_text(encoding="utf-8"))
    assert rec is not None, "检查没有拿到 GATE_TEST_RESULT"
    assert rec["mode"] == "incremental" and rec["complete"] is True, rec
    assert rec["inherited"] >= 1, rec
    assert rec["nodes"]["tests/test_a.py::test_a"] == "passed", rec["nodes"]
    assert rec["nodes"]["tests/test_b.py::test_b"] == "passed", rec["nodes"]


@pytest.mark.xfail(strict=True, reason="S1 未实现：final 阶段检查拿不到 GATE_TEST_RESULT")
def test_baseline_checks_get_no_test_result(git_repo, tmp_path):
    # Given: 一项检查的 baseline 与 final 命令都把 GATE_TEST_RESULT 的值追加记到仓库外
    log = tmp_path / "var.log"
    cmd = "python3 tools/record_var.py %s" % log
    checks = [{"name": "rec", "baseline": cmd, "final": cmd, "timeout_sec": 120}]
    d = make_repo(git_repo, extra={"tools/record_var.py": RECORD_VAR}, gate_extra={"checks": checks})

    # When: 依次运行 baseline 与 final --full
    baseline(git_repo, d)
    final(git_repo, d, "--full")

    # Then: baseline 阶段记录为空；final 阶段记录指向一个存在的文件
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, lines
    assert lines[0] == "", lines
    assert lines[1] and os.path.isfile(lines[1]), lines


@pytest.mark.xfail(strict=True, reason="S1 未实现：gate.test 环境没有 GATE_PHASE / GATE_CHANGE")
def test_gate_test_env_carries_phase_and_change(git_repo, tmp_path):
    # Given: change c 的 gate.test 是包装脚本：先把 GATE_PHASE 与 GATE_CHANGE 追加写到仓库外，再运行 pytest
    log = tmp_path / "phase.log"
    wrapper = '#!/usr/bin/env bash\necho "$GATE_PHASE $GATE_CHANGE" >> %s\nexec %s -m pytest -q -p no:cacheprovider tests\n' % (
        log, PY)
    d = make_repo(git_repo, extra={"tools/gate.sh": wrapper}, gate_extra={"test": "bash tools/gate.sh"})

    # When: 依次运行 baseline 与 final --full
    baseline(git_repo, d)
    final(git_repo, d, "--full")

    # Then: 记录依次为「baseline c」与「final c」
    assert log.read_text(encoding="utf-8").splitlines() == ["baseline c", "final c"]
