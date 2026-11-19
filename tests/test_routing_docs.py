"""命令与 skill 的派发从路由配置取值；规划期不进路由
（scenario: routing-docs#apply-docs-resolve-routing-from-pin、#propose-docs-pin-routing、
#auxiliary-dispatches-read-routing、#planning-docs-carry-no-routing，共 4 条）。
S5 已解锁。"""
import re

from conftest import ROOT, load_hook

CMD = ROOT / "template" / ".claude" / "commands"
SKILLS = ROOT / "template" / ".claude" / "skills"


def read(p):
    return p.read_text(encoding="utf-8")


def fallback(t):
    """apply 命令 / skill 的回退路径段：从「Workflow 不可用」到「两条路径」。"""
    return t[t.index("Workflow 不可用"):t.index("两条路径")]


def frontmatter(t):
    m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
    return m.group(1) if m else ""


def test_apply_docs_resolve_routing_from_pin():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    docs = [read(CMD / "opsx-apply.md"), read(SKILLS / "openspec-apply-change" / "SKILL.md")]

    # When: 读两者全文与回退路径段
    fbs = [fallback(t) for t in docs]

    # Then: 都含 resolve / --expect-efforts / --turns，都不含 <main> / --model= / session-model.py；回退段写明 Agent 派发传 effort
    for t, fb in zip(docs, fbs):
        assert "model-routing.py resolve" in t and "--expect-efforts" in t and "--turns" in t
        assert "<main>" not in t and "--model=" not in t and "session-model.py" not in t
        assert "effort" in fb and "model-routing" in fb, fb


def test_propose_docs_pin_routing():
    # Given: opsx-propose.md 与 openspec-propose/SKILL.md
    docs = [read(CMD / "opsx-propose.md"), read(SKILLS / "openspec-propose" / "SKILL.md")]

    # When: 找 pin 与 lint 的位置
    # Then: 都含 model-routing.py pin --change-dir，且在 slice-gate.py lint 之后
    for t in docs:
        assert "model-routing.py pin --change-dir" in t
        assert t.index("slice-gate.py lint") < t.index("model-routing.py pin --change-dir")


AUX = {
    CMD / "pr-ship.md": ("ship.reviewer", "ship.followup"),
    CMD / "opsx-archive.md": ("archive.sync",),
    SKILLS / "openspec-archive-change" / "SKILL.md": ("archive.sync",),
    CMD / "claudemd-standardize.md": ("claudemd.evidence",),
    CMD / "opsx-bulk-apply.md": ("bulk.apply",),
    SKILLS / "openspec-bulk-apply-change" / "SKILL.md": ("bulk.apply",),
    SKILLS / "legacy" / "openspec-subagent-apply-change" / "SKILL.md": ("flight.executor", "flight.fixer", "flight.reviewer"),
}


def test_auxiliary_dispatches_read_routing():
    # Given: 7 个辅助派发点文件
    # When: 逐个读取
    # Then: 每个都含 model-routing.py get 与对应的键；都不含 <main> 与写死的 sonnet
    for path, keys in AUX.items():
        t = read(path)
        assert "model-routing.py get" in t, path
        for k in keys:
            assert k in t, (path, k)
        assert "<main>" not in t and 'model: "sonnet"' not in t and "model: sonnet" not in t, path


PLANNING_SKILLS = ("openspec-explore", "openspec-new-change", "openspec-continue-change", "openspec-propose")


def test_planning_docs_carry_no_routing():
    # Given: model-routing.py 登记的规划期组名，以及由它们得到的 5 个命令与 4 个规划类 skill
    groups = set(load_hook("model-routing").PLANNING_GROUPS)
    files = [CMD / ("opsx-%s.md" % g) for g in sorted(groups)] + [SKILLS / s / "SKILL.md" for s in PLANNING_SKILLS]

    # When: 读 frontmatter 与正文
    # Then: 组名正好是 5 个且都有命令文件；frontmatter 无 model / effort；正文的 subagent_type 只允许 fork、无 model: "
    assert groups == {"propose", "explore", "new", "continue", "mini"}, groups
    for f in files:
        assert f.exists(), f
        t = read(f)
        fm = frontmatter(t)
        assert not re.search(r"^(model|effort):", fm, re.M), f
        assert all(v == "fork" for v in re.findall(r'subagent_type:\s*"?([\w-]+)', t)), f
        assert 'model: "' not in t, f
