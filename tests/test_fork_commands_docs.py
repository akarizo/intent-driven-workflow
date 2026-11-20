"""fork-mechanical-commands 的 scenario 骨架（strict xfail；切片 S2 实现后去掉标记即解锁）。"""
import json
import re


from conftest import ROOT, load_hook, run_hook

CMD = ROOT / "template" / ".claude" / "commands"
SKILLS = ROOT / "template" / ".claude" / "skills"
PLANNING_SKILLS = ("openspec-explore", "openspec-new-change", "openspec-continue-change", "openspec-propose")
ADVICE_FILES = ("opsx-sync.md", "spec-html.md", "claudemd-commit.md", "opsx-explore.md")
NOTE = ("> **模型**：不要为本命令中途用 `/model` 切换模型：切换后的首个请求要把整段上下文重发给新模型、"
        "不命中缓存，切回来还要再付一次。")
CLEAN_ENV = {"CLAUDE_CODE_EFFORT_LEVEL": "", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": ""}


def read(p):
    return p.read_text(encoding="utf-8")


def frontmatter(text):
    """取首个 --- 块，按行解析成 {键: 值}。"""
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def docs():
    return sorted(CMD.glob("*.md")) + sorted(SKILLS.glob("**/SKILL.md"))


def test_cleanup_command_runs_as_fork():
    # Given: 模板里的 `clean-after-merged.md` 与 `model-routing.py` 的内建默认
    mr = load_hook("model-routing")
    builtin = mr.BUILTIN["cleanup.runner"]
    text = read(CMD / "clean-after-merged.md")

    # When: 读取它的 frontmatter 与正文
    fm = frontmatter(text)

    # Then: frontmatter 有 `context: fork`、`agent: general-purpose`、`background: false`，`model` / `effort` 等于 `cleanup.runner` 的内建默认；正文含「不继承对话」与「最后一条回复」，不含 AskUserQuestion，仍含 `merged-cleanup.py plan --markdown` 与 `merged-cleanup.py apply`
    assert fm.get("context") == "fork", fm
    assert fm.get("agent") == "general-purpose", fm
    assert fm.get("background") == "false", fm
    assert fm.get("model") == builtin["model"] and fm.get("effort") == builtin["effort"], (fm, builtin)
    for k in ("不继承对话", "最后一条回复", "merged-cleanup.py plan --markdown", "merged-cleanup.py apply"):
        assert k in text, k
    assert "AskUserQuestion" not in text


def test_only_fork_commands_carry_model():
    # Given: `template/.claude/commands/*.md` 与 `template/.claude/skills/**/SKILL.md`
    mr = load_hook("model-routing")
    files = docs()
    planning = [CMD / ("opsx-%s.md" % g) for g in sorted(mr.PLANNING_GROUPS)] + \
               [SKILLS / s / "SKILL.md" for s in PLANNING_SKILLS]

    # When: 逐个解析 frontmatter
    fms = {f: frontmatter(read(f)) for f in files}

    # Then: 每个写了 `model` 的文件都写了 `context: fork`；写了 `context: fork` 的命令文件名集合等于 `FORK_COMMANDS` 的值集合，规划类命令与 skill 都没有 `context`
    for f, fm in fms.items():
        if "model" in fm:
            assert fm.get("context") == "fork", f
    forked = {f.name for f, fm in fms.items() if f.parent == CMD and fm.get("context") == "fork"}
    assert forked == set(mr.FORK_COMMANDS.values()), forked
    for f in planning:
        assert f.exists(), f
        assert "context" not in frontmatter(read(f)), f


def test_stale_model_advice_removed():
    # Given: 模板里的全部命令与 skill
    files = docs()

    # When: 搜索 `/model sonnet` 与新的说明行
    stale = [f for f in files if "/model sonnet" in read(f)]
    missing = [n for n in ADVICE_FILES if NOTE not in read(CMD / n).splitlines()]

    # Then: 没有文件含 `/model sonnet`；四个命令都含同一行说明，说明里有「不命中缓存」
    assert not stale, stale
    assert not missing, missing
    assert "不命中缓存" in NOTE


def test_self_hosting_config_leaves_fork_keys():
    # Given: 本仓库的 `template/openspec/model-routing.json` 与模板命令
    mr = load_hook("model-routing")
    cfg = json.loads(read(ROOT / "template" / "openspec" / "model-routing.json"))
    groups = {k.split(".")[0] for k in mr.FORK_COMMANDS}

    # When: 读取配置的组名，并在 `template/` 下运行 `model-routing.py frontmatter --check`
    p = run_hook("model-routing", "frontmatter", "--check", cwd=ROOT / "template", env=CLEAN_ENV)

    # Then: 配置里没有 `cleanup` 组；`--check` 退出 0
    assert "cleanup" in groups and not (groups & set(cfg)), (groups, sorted(cfg))
    assert p.returncode == 0, p.stdout + p.stderr


def test_docs_register_cleanup_runner():
    # Given: `README.md` 与 `docs/WORKFLOW_zh.md`
    readme = read(ROOT / "README.md")
    workflow = read(ROOT / "docs" / "WORKFLOW_zh.md")

    # When: 查找路由表与键清单
    row = re.search(r"^\| `cleanup\.runner`.*$", readme, re.M)

    # Then: README 有一行以 `` | `cleanup.runner` `` 开头，含 `/clean-after-merged` 与 `sonnet · low`；两份文档都含 `cleanup.runner` 与 `model-routing.py frontmatter`
    assert row, "README 路由表缺 cleanup.runner"
    assert "/clean-after-merged" in row.group(0) and "sonnet · low" in row.group(0), row.group(0)
    for name, text in (("README.md", readme), ("WORKFLOW_zh.md", workflow)):
        assert "cleanup.runner" in text and "model-routing.py frontmatter" in text, name
