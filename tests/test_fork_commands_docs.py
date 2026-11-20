"""fork-mechanical-commands 与 cleanup-fork-report 的 scenario 测试（已解锁）。"""
import json
import re

from conftest import ROOT, load_hook, run_hook
import pytest

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
    builtin = mr.BUILTIN["cleanup.runner"]

    # When: 读取配置的 `cleanup.runner`，并在 `template/` 下运行 `model-routing.py frontmatter --check`
    runner = cfg.get("cleanup", {}).get("runner", {})
    p = run_hook("model-routing", "frontmatter", "--check", cwd=ROOT / "template", env=CLEAN_ENV)

    # Then: 配置里 `cleanup.runner` 的 model / effort 等于内建默认（init 补全后与 frontmatter 一致）；`--check` 退出 0
    assert "cleanup.runner" in mr.FORK_COMMANDS, mr.FORK_COMMANDS
    assert (runner.get("model"), runner.get("effort")) == (builtin["model"], builtin["effort"]), (runner, builtin)
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


def test_cleanup_fork_guards_session_cwd():
    # Given: 模板里 fork 形态的 `clean-after-merged.md`
    text = read(CMD / "clean-after-merged.md")

    # When: 查找子 agent 的 CWD 约定与原因表
    rows = [ln for ln in text.splitlines() if ln.startswith("| `session-cwd` |")]

    # Then: 正文写明 cd 不跨调用保留、plan 与 apply 都带 --protect；原因表有 session-cwd 一行
    assert "不跨调用保留" in text
    assert "merged-cleanup.py plan --markdown --fetch --protect" in text
    assert "merged-cleanup.py apply --protect" in text
    assert len(rows) == 1, rows


def test_cleanup_final_reply_carries_plan_result_verify():
    # Given: 模板的 `/clean-after-merged` 命令文件
    # When: 读取它对最后一条回复的约定，以及 step 2 与 step 5 对输出的要求
    # Then: 最后一条回复的约定依次点名 step 2 的计划原文、step 4 的 `done` / `failed` 与 manual 档代码块、step 5 的验证输出；step 2 与 step 5 都要求把输出放进最后一条回复
    text = read(CMD / "clean-after-merged.md")
    item = next((l for l in text.splitlines() if l.startswith("- **最后一条回复")), "")
    assert item, "运行方式里没有「- **最后一条回复」条目"
    marks = ["step 2", "计划", "step 4", "done", "failed", "manual", "step 5", "验证"]
    pos = [item.find(m) for m in marks]
    assert all(i >= 0 for i in pos), dict(zip(marks, pos))
    assert pos[0] < pos[2] < pos[6], dict(zip(marks, pos))
    assert pos[0] <= pos[1] < pos[2] <= pos[3] < pos[6] <= pos[7], dict(zip(marks, pos))
    assert pos[2] <= pos[4] < pos[6] and pos[2] <= pos[5] < pos[6], dict(zip(marks, pos))
    step2 = text[text.index("2. **"):text.index("3. **")]
    step5 = text[text.index("5. **"):text.index("**退出码**")]
    assert "最后一条回复" in step2, step2
    assert "最后一条回复" in step5, step5


def test_cleanup_doc_states_cwd_basis():
    # Given: 模板的 `/clean-after-merged` 命令文件
    # When: 读取运行方式一节与原因表
    # Then: 运行方式写明起始 CWD 是主会话当前所在目录、主会话 `cd` 过也一样，并给出实测日期 2026-11-20；写明 `--protect` 传绝对路径；原因表的 `session-cwd` 一行说明只保护 `--protect` 传入的路径
    text = read(CMD / "clean-after-merged.md")
    run = text[text.index("运行方式"):text.index("**Input**")]
    for k in ("主会话当前所在目录", "主会话 `cd` 过也一样", "2026-11-20", "绝对路径"):
        assert k in run, k
    row = next((l for l in text.splitlines() if l.startswith("| `session-cwd` |")), "")
    assert row, "原因表没有 session-cwd 一行"
    assert "只保护" in row and "--protect" in row, row


def test_cleanup_doc_marks_fork_command_untested():
    # Given: 模板的 `/clean-after-merged` 命令文件
    # When: 读取运行方式一节与 step 1 的代码块
    # Then: 运行方式一节含整句「主会话 `cd` 过也一样」，并写明 `context: fork` 命令本身未单独实测；step 1 代码块里 `pwd` 那一行的注释含「主会话当前所在目录」
    text = read(CMD / "clean-after-merged.md")
    run = text[text.index("运行方式"):text.index("**Input**")]
    assert "主会话 `cd` 过也一样" in run, run
    assert "`context: fork` 命令本身未单独实测" in run, run
    step1 = text[text.index("1. **"):text.index("2. **")]
    pwd_line = next((l for l in step1.splitlines() if l.strip().startswith("pwd")), "")
    assert pwd_line and "#" in pwd_line, step1
    assert "主会话当前所在目录" in pwd_line.split("#", 1)[1], pwd_line
