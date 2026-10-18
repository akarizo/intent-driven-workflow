"""schema、propose / verify 命令与同名 skill、README 写明检查的配置、时机与契约（scenario: gate-paired-checks#docs-describe-paired-checks）。
切片 S4 已解锁。"""
import pytest

from conftest import ROOT
from test_baseline_incremental_docs import _baseline_step, _has_line

CMD = ROOT / "template" / ".claude" / "commands"
SKILLS = ROOT / "template" / ".claude" / "skills"
SCHEMA = ROOT / "template" / "openspec" / "schemas" / "intent-driven" / "schema.yaml"
README = ROOT / "README.md"
GATE_VARS = ("GATE_PHASE", "GATE_CHANGE", "GATE_BASE_COMMIT", "GATE_CHECK_DIR")


def read(path):
    return path.read_text(encoding="utf-8")


def test_docs_describe_paired_checks():
    # Given: schema.yaml、opsx-propose 与 opsx-verify 两个命令及其同名 skill、README.md
    schema = read(SCHEMA)
    propose = [read(CMD / "opsx-propose.md"), read(SKILLS / "openspec-propose" / "SKILL.md")]
    verify = [read(CMD / "opsx-verify.md"), read(SKILLS / "openspec-verify-change" / "SKILL.md")]
    readme = read(README)

    # When: 取 schema 的 tasks 工件 instruction 与两份 propose 文档的基线步骤段
    tasks = schema[schema.index("- id: tasks"):schema.index("apply:")]
    steps = [_baseline_step(t) for t in propose]

    # Then: tasks instruction 同时含 gate.checks、checks_skip 与 gate-checks.json；
    #       两份 propose 文档的基线步骤各有一行同时含 gate.checks 与「基线红」；两份 verify 文档各有一行同时含 gate.checks 与 G9；
    #       README 含四个 GATE_* 环境变量，且有一行同时含 gate.checks 与「退出码」
    assert all(w in tasks for w in ("gate.checks", "checks_skip", "gate-checks.json")), tasks
    assert all(_has_line(s, "gate.checks", "基线红") for s in steps)
    assert all(_has_line(t, "gate.checks", "G9") for t in verify)
    assert all(v in readme for v in GATE_VARS)
    assert _has_line(readme, "gate.checks", "退出码")
