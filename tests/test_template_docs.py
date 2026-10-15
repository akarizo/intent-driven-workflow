"""命令 / skill / schema 文本契约（scenario: flight-apply#apply-command-zero-prompts / pr-ship-single-review,
executable-specs#schema-tasks-produce-slices / propose-command-triggers）。
骨架：xfail(strict) 直到 S5 实现；执行体去掉标记即解锁。"""
import re

import pytest

from conftest import ROOT

CMD = ROOT / "template" / ".claude" / "commands"
SKILLS = ROOT / "template" / ".claude" / "skills"
SCHEMA = ROOT / "template" / "openspec" / "schemas" / "intent-driven"


def read(path):
    return path.read_text(encoding="utf-8")


def test_apply_command_zero_prompts():
    # Given: template/.claude/commands/opsx-apply.md
    text = read(CMD / "opsx-apply.md")

    # When: 找出启动步骤与 pr-ship 步骤之间的文本
    launch = text.index("slice-gate.py lint")
    ship = text.index("/pr-ship", launch)
    middle = text[launch:ship]

    # Then: 含 lint→waves→Workflow→回退→收 JSON→收口分解→pr-ship 的要素；启动到 pr-ship 之间无 AskUserQuestion；保留 --gate=per-task 指向 legacy；不再有模式问询与水位线
    assert "Workflow" in middle and "useAgentTypes" in middle and "回退" in middle
    assert "session-decompose" in middle and "timeline.py record approve" in middle
    assert "AskUserQuestion" not in middle
    assert "--gate=per-task" in text and "legacy" in text
    assert "水位线" not in text and "整合审" not in text


def test_pr_ship_single_review():
    # Given: template/.claude/commands/pr-ship.md
    text = read(CMD / "pr-ship.md")

    # When: 统计 AskUserQuestion 出现次数并检查评审输入
    asks = text.count("AskUserQuestion")

    # Then: 问询至多 1 处；评审输入含 gate-report.md 与 evidence.log 并声明不重跑测试；自动修复至多 2 轮；无水位线
    assert asks <= 1, asks
    assert "gate-report.md" in text and "evidence.log" in text and "不重跑测试" in text
    assert re.search(r"(至多|最多|≤)\s*2\s*轮", text)
    assert "水位线" not in text and "review-log" not in text
    assert text.count('model: "<main>"') >= 2, "code-reviewer 派发（首审与复核）都必须显式带 model"
    assert "timeline.py record pr-open" in text and "review-findings.json" in text


def test_schema_tasks_produce_slices():
    # Given: template/openspec/schemas/intent-driven/schema.yaml 与 templates/tasks.md
    schema = read(SCHEMA / "schema.yaml")
    tmpl = read(SCHEMA / "templates" / "tasks.md")

    # When: 取 tasks 工件的 instruction 段
    tasks = schema[schema.index("- id: tasks"):schema.index("apply:")]

    # Then: 要求产出 slices.json、切片包、xfail 骨架与生成的 tasks.md；切片规则齐全；tasks 仍 requires specs；模板示例含 deps / verify 后缀
    assert "slices.json" in tasks and "slices/" in tasks and "xfail" in tasks and "tasks.md" in tasks
    assert "owns" in tasks and "深度" in tasks and "1–9" in tasks and "12" in tasks
    assert re.search(r"requires:\s*\n\s*- specs", tasks)
    assert "deps:" in tmpl and "verify:" in tmpl


def test_propose_command_triggers():
    # Given: opsx-propose.md 与 openspec-propose/SKILL.md
    cmd = read(CMD / "opsx-propose.md")
    skill = read(SKILLS / "openspec-propose" / "SKILL.md")

    # When: 检查两者的关键步骤
    both = [cmd, skill]

    # Then: 两者都含一次成稿、触发器表、baseline 与 spec_html.py 渲染，且不再要求模型渲染 HTML
    assert all("一次成稿" in t or "一次性写出" in t for t in both)
    assert all("触发器" in t for t in both)
    assert all("slice-gate.py baseline" in t for t in both)
    assert all("spec_html.py" in t for t in both)
    assert all("spec-html-render/SKILL.md 的流程" not in t for t in both)


def test_command_skill_sync():
    # Given: 四对命令与同名 skill
    pairs = [("opsx-apply.md", "openspec-apply-change"), ("opsx-propose.md", "openspec-propose"),
             ("opsx-verify.md", "openspec-verify-change"), ("opsx-continue.md", "openspec-continue-change")]

    # When: 提取每对文件里提到的 hook 脚本名集合
    def hooks(t):
        return set(re.findall(r"(slice-gate\.py|spec_html\.py|timeline\.py|session-decompose\.py)", t))
    diffs = [(c, s, hooks(read(CMD / c)) ^ hooks(read(SKILLS / s / "SKILL.md"))) for c, s in pairs]

    # Then: 每对提到的 hook 脚本集合一致（命令与 skill 不漂移）
    assert all(not d for _, _, d in diffs), diffs


def test_git_discipline_wave_parallel_carveout():
    # Given: template/.claude/skills/openspec-git-discipline/SKILL.md 的 Worktree Isolation 节
    text = read(SKILLS / "openspec-git-discipline" / "SKILL.md")
    section = text[text.index("## Worktree Isolation"):text.index("## Gates")]

    # When: 检查该节文字
    # Then: 核心禁令原文保留（禁止嵌套子 worktree）；新增 carve-out 说明 wave 内并行切片的临时 worktree
    #       由 Workflow/Agent 运行时创建与清理、由 integrator 合回、不 push / 不 merge main，
    #       与 opsx-apply.js 的 isolation: worktree 并行机制不再自相矛盾
    assert "禁止为单个 task 各开 worktree，也禁止在 change worktree 内再嵌套子 worktree" in section
    assert "wave" in section and "isolation" in section
    assert "integrator" in section
    assert "运行时" in section
    assert "不 push" in section


# ---------------------------------------------------------------- 起飞判据（scenario: model-routing#apply-resolves-main-model /
# pr-ship-resolves-main-model, takeoff-approval#apply-checks-approval-gate）。


def test_apply_resolves_main_model():
    # Given: /opsx-apply 命令与 openspec-apply-change skill
    cmd = read(CMD / "opsx-apply.md")
    skill = read(SKILLS / "openspec-apply-change" / "SKILL.md")

    # When: 检查两份文件里 <main> 的来源与失败处置
    texts = [cmd, skill]

    # Then: <main> 取自 session-model.py；判定失败停下报告并提示 --model=；.flight 记录路由与来源；收口带 --expect-models；不再有"看 /model"式自述
    for t in texts:
        assert "session-model.py" in t
        assert "看 `/model`" not in t
        assert "--expect-models" in t
    assert "--model=" in cmd and "停下报告" in cmd
    assert ".flight" in cmd and '"models"' in cmd


def test_pr_ship_resolves_main_model():
    # Given: /pr-ship 命令
    text = read(CMD / "pr-ship.md")

    # When: 检查两处 code-reviewer 派发的 <main> 来源
    asks = text.count('model: "<main>"')

    # Then: 两处仍显式带 model；<main> 注明取自 session-model.py；不再有"看 /model"式自述
    assert asks >= 2, asks
    assert "session-model.py" in text
    assert "看 `/model`" not in text


def test_apply_checks_approval_gate():
    # Given: /opsx-apply 命令与 openspec-apply-change skill
    cmd = read(CMD / "opsx-apply.md")
    skill = read(SKILLS / "openspec-apply-change" / "SKILL.md")

    # When: 切出 step 0「批准自检」实体（step 1「选 change」之前），而非开头的流程摘要句
    assert "0. **批准自检" in cmd, "step 0 批准自检整块缺失"
    step0 = cmd[cmd.index("0. **批准自检"): cmd.index("1. **选 change**")]

    # Then: step 0 内实跑 takeoff-gate.py --change-dir 并交出 spec.html、不问询；门禁调用早于 step 1；skill 一致；approve 事件带批准证据
    assert "takeoff-gate.py --change-dir" in step0 and "spec.html" in step0
    assert "AskUserQuestion" not in step0
    assert cmd.index("takeoff-gate.py") < cmd.index("1. **选 change**")
    assert "takeoff-gate.py" in skill
    assert "record approve" in cmd and "批准证据" in cmd


# ---------------------------------------------------------------- flight-preflight-and-retry（scenario: flight-doc-contracts#*）


def test_pr_ship_asks_before_autofix():
    # Given: template/.claude/commands/pr-ship.md
    text = read(CMD / "pr-ship.md")

    # When: 切出 step 10、step 11 与 Guardrails
    step10 = text[text.index("10. **"):text.index("11. **")]
    step11 = text[text.index("11. **"):text.index("**Output Summary")]
    guard = text[text.index("**Guardrails**"):]

    # Then: step 10 有 AskUserQuestion 且写明默认只贴评论；step 11 不再问询；Guardrails 不再把唯一问询指向 step 11；全文 AskUserQuestion ≤ 1
    assert "AskUserQuestion" in step10
    assert "默认" in step10 and "只贴评论" in step10
    assert "AskUserQuestion" not in step11
    assert "仅 step 11" not in guard
    assert text.count("AskUserQuestion") <= 1


def test_propose_baseline_red_stops():
    # Given: opsx-propose.md 与 openspec-propose/SKILL.md
    cmd = read(CMD / "opsx-propose.md")
    skill = read(SKILLS / "openspec-propose" / "SKILL.md")

    # When: 取两者的 baseline 步骤段（从 slice-gate.py baseline 到下一个步骤标题）
    def step4(t):
        at = t.index("slice-gate.py baseline")
        nxt = re.search(r"\n\d+(?:\.\d+)?\.? \*\*", t[at:])
        return t[at:at + nxt.start()]

    # Then: 两者都含 gate-baseline.json 与「停下报告」，并说明 verify 在基线上必须绿；hook 脚本集合一致
    for t in (cmd, skill):
        s = step4(t)
        assert "gate-baseline.json" in s and "停下报告" in s
        assert "verify" in s and "绿" in s
    hooks = lambda t: set(re.findall(r"(slice-gate\.py|spec_html\.py|timeline\.py|session-decompose\.py)", t))
    assert hooks(cmd) == hooks(skill)


def test_schema_verify_excludes_typecheck():
    # Given: schema.yaml 的 tasks 工件 instruction
    schema = read(SCHEMA / "schema.yaml")

    # When: 取 Slicing rules 段
    tasks = schema[schema.index("- id: tasks"):schema.index("apply:")]
    rules = tasks[tasks.index("Slicing rules"):]

    # Then: 含 verify 只跑测试类规则，点名 typecheck 与 gate.lint / gate.typecheck
    assert "verify" in rules and "typecheck" in rules
    assert "gate.typecheck" in rules and "gate.lint" in rules


# ---------------------------------------------------------------- flight-wave-fixes（scenario: slice-base-check#apply-docs-pass-branch ·
# flight-doc-contracts#fallback-effort-from-frontmatter · review-diff-fallback#*）
# S3 已解锁。

AGENTS = ROOT / "template" / ".claude" / "agents"


def apply_docs():
    return read(CMD / "opsx-apply.md"), read(SKILLS / "openspec-apply-change" / "SKILL.md")


def fallback(t):
    """apply 命令 / skill 的回退路径段：从「Workflow 不可用」到「两条路径」。"""
    return t[t.index("Workflow 不可用"):t.index("两条路径")]


def test_apply_docs_pass_branch():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    cmd, skill = apply_docs()

    # When: 取两者全文与回退路径段
    fallbacks = [fallback(t) for t in (cmd, skill)]

    # Then: 两者的 Workflow args 用 branch（取自 git branch --show-current），全文不再出现 expectHead；回退段含 --expect-branch 与「原样」
    for t, fb in zip((cmd, skill), fallbacks):
        assert 'branch: "<git branch --show-current>"' in t
        assert "expectHead" not in t
        assert "--expect-branch" in fb and "原样" in fb


def test_fallback_effort_from_frontmatter():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    cmd, skill = apply_docs()

    # When: 取两者的回退路径段
    fallbacks = [fallback(t) for t in (cmd, skill)]

    # Then: 回退段都不把 effort 写成 Agent 派发参数（无 effort: high / effort: low），并写明 effort 由 agent frontmatter 决定
    for fb in fallbacks:
        assert "effort: high" not in fb and "effort: low" not in fb, fb
        assert "frontmatter" in fb


def test_pr_ship_review_diff_fallback():
    # Given: template/.claude/commands/pr-ship.md
    text = read(CMD / "pr-ship.md")

    # When: 切出 step 8（呼叫 code-reviewer 评审 diff）
    step8 = text[text.index("8. **"):text.index("9. **")]

    # Then: 含回退命令 git diff origin/<target>...HEAD 与「取 diff 失败」；不再出现「为空或拉不到」这种合并写法
    assert "git diff origin/<target>...HEAD" in step8
    assert "取 diff 失败" in step8
    assert "为空或拉不到" not in step8


def test_reviewer_diff_empty_vs_unreachable():
    # Given: template/.claude/agents/code-reviewer.md
    text = read(AGENTS / "code-reviewer.md")

    # When: 切出「评审流程」段
    flow = text[text.index("## 评审流程"):text.index("## 审查 checklist")]

    # Then: 同时含「无变更」（diff 为空时）与「取 diff 失败」（拉不到时）；不再出现「为空或拉不到」这种合并写法
    assert "无变更" in flow and "取 diff 失败" in flow
    assert "为空或拉不到" not in flow


# ---------------------------------------------------------------- 摘自原仓 #45（flight-gate-speedup）· scenario: propose-parallel-baseline#*

def test_propose_renders_panel_before_baseline():
    # Given: opsx-propose.md 与 openspec-propose/SKILL.md
    cmd = read(CMD / "opsx-propose.md")
    skill = read(SKILLS / "openspec-propose" / "SKILL.md")

    # When: 定位两者里 spec_html.py 与 slice-gate.py baseline 首次出现的位置，取 baseline 之后的正文
    def parts(t):
        at = t.index("slice-gate.py baseline")
        return t.index("spec_html.py"), at, t[at:]

    # Then: 两者都是 spec_html.py 在前；baseline 之后写明后台运行、跑完报告一行、跑完前起飞会被 preflight 拒绝；hook 集合一致
    for t in (cmd, skill):
        html_at, base_at, tail = parts(t)
        assert html_at < base_at
        assert "后台" in tail and "报告一行" in tail
        assert "preflight" in tail and "拒绝" in tail
    hooks = lambda t: set(re.findall(r"(slice-gate\.py|spec_html\.py|timeline\.py|session-decompose\.py)", t))
    assert hooks(cmd) == hooks(skill)


def test_schema_requires_gate_test():
    # Given: schema.yaml 的 tasks 工件 instruction
    schema = read(SCHEMA / "schema.yaml")

    # When: 取 tasks 工件段
    tasks = schema[schema.index("- id: tasks"):schema.index("apply:")]

    # Then: 写明 gate.test 必填；写明预存红按基线差分、无需手写 deselect
    assert "gate.test" in tasks and "必填" in tasks
    assert "预存红" in tasks and "差分" in tasks and "deselect" in tasks


# ---------------------------------------------------------------- 摘自原仓 #47 / #51 · scenario: pr-ship-premerge-check#* · legacy-review-routing#*


def test_pr_ship_premerge_uses_merge_tree_exit_code():
    # Given: template/.claude/commands/pr-ship.md
    text = read(CMD / "pr-ship.md")

    # When: 取第 4 步「预合并冲突检查」到第 5 步之间的内容
    step4 = text[text.index("4. **预合并冲突检查**"):text.index("5. **")]

    # Then: 含 merge-tree --write-tree --name-only、「退出 0」「退出 1」与 2.38；不含旧的 grep 统计
    assert "git merge-tree --write-tree --name-only" in step4
    assert "退出 0" in step4 and "退出 1" in step4 and "2.38" in step4
    assert 'grep -c "^<<<<<<<"' not in step4


def test_legacy_review_dispatch_names_model():
    # Given: legacy 逐 task 守门 skill
    text = read(SKILLS / "legacy" / "openspec-subagent-apply-change" / "SKILL.md")

    # When: 取每一处派发 code-reviewer 的位置（4b 守门、修复后的聚焦复核、整个 change 的累计评审）所在的整段
    sites = [m.start() for m in re.finditer(r"subagent_type: code-reviewer|派一个 fresh `code-reviewer`|派一个 `code-reviewer` subagent", text)]

    def para(at):
        end = text.find("\n\n", at)
        return text[text.rfind("\n\n", 0, at) + 2:end if end != -1 else len(text)]

    paras = [para(at) for at in sites]

    # Then: 三处都带 model: "<main>"，且写明 <main> 由 session-model.py 判定（或同 4b）；全文没有 flight: 前缀的 agent 名
    assert len(paras) == 3, sites
    for p in paras:
        assert 'model: "<main>"' in p, p
        assert "session-model.py" in p or "同 4b" in p, p
    assert "flight:" not in text
