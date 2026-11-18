"""文档：pr-ship 先裁决再重跑；契约与规划指引写明 inert 与无图退路
（scenario: ship-rerun-decision#pr-ship-asks-ship-before-rerunning-final、inert-paths#docs-describe-inert-and-tests-only，共 2 条）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S4 实现后去掉标记即解锁。"""
import pytest

from conftest import ROOT

PENDING = pytest.mark.xfail(strict=True, reason="骨架：切片 S4 实现后去掉")

T = ROOT / "template"
PR_SHIP = T / ".claude" / "commands" / "pr-ship.md"
CONTRACT = T / ".claude" / "flight-runner-contract.md"
PROPOSE = (T / ".claude" / "commands" / "opsx-propose.md", T / ".claude" / "skills" / "openspec-propose" / "SKILL.md")
SCHEMA = T / "openspec" / "schemas" / "intent-driven" / "schema.yaml"
README = ROOT / "README.md"


def _read(p):
    return p.read_text(encoding="utf-8")


@PENDING
def test_pr_ship_asks_ship_before_rerunning_final():
    # Given: template/.claude/commands/pr-ship.md 的 step 2b（记忆层沉淀）
    text = _read(PR_SHIP)
    s2b = text[text.index("2b. **"):text.index("\n3. **")]

    # When: 取 2b 里 slice-gate.py ship 与 slice-gate.py final 的位置
    i_ship, i_final = s2b.find("slice-gate.py ship"), s2b.find("slice-gate.py final")

    # Then: 先 ship 后 final；写明只有 reasons 含「final 过期」才重跑，否则不重跑；不再写「沉淀 commit 之后重跑」这种无条件说法
    assert 0 <= i_ship < i_final, (i_ship, i_final)
    assert "final 过期" in s2b and "不重跑 final" in s2b, s2b
    assert "沉淀 commit 之后重跑：" not in s2b, s2b


@PENDING
def test_docs_describe_inert_and_tests_only():
    # Given: 运行器契约、propose 命令与同名 skill、schema 的 tasks instruction、README
    contract = _read(CONTRACT)

    # When: 找契约里讲 inert 的行与结果文件 mode 的行
    inert_rows = [l for l in contract.splitlines() if l.startswith("| `inert`")]
    mode_rows = [l for l in contract.splitlines() if l.startswith("| `mode`")]

    # Then: 契约的可选字段表有 inert 一行并写明对账；另写明依赖图未测时无法对账、哪些路径永不按 inert 处理；
    #       结果文件的 mode 列出 tests-only；接入步骤提到 inert；其余四处的可选字段清单都含 inert
    assert inert_rows and "对账" in inert_rows[0], inert_rows
    assert "无法对账" in contract and "永不" in contract, contract[-1500:]
    assert mode_rows and "tests-only" in mode_rows[0], mode_rows
    steps = contract[contract.index("## 7. 接入步骤"):]
    assert "inert" in steps, steps
    for p in PROPOSE:
        assert "`inert`" in _read(p), p
    assert "inert" in _read(SCHEMA) and "inert" in _read(README)
