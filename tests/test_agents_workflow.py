"""agent 定义与 opsx-apply 工作流脚本的静态契约（scenario: flight-apply#workflow-script-valid / executor-agent-contract / reviewer-no-rerun）。"""
import json
import re
import shutil
import subprocess

import pytest

from conftest import ROOT, load_hook

AGENTS = ROOT / "template" / ".claude" / "agents"
WORKFLOW = ROOT / "template" / ".claude" / "workflows" / "opsx-apply.js"


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, "%s 缺少 frontmatter" % path
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, m.group(2)


def test_workflow_script_valid():
    # Given: template/.claude/workflows/opsx-apply.js
    text = WORKFLOW.read_text(encoding="utf-8")
    body = re.sub(r"^\s*//.*$", "", text, flags=re.M).lstrip()

    # When: 静态检查脚本结构（并在有 node 时做语法检查）
    node_ok = True
    if shutil.which("node"):
        node_ok = subprocess.run(["node", "--check", str(WORKFLOW)], capture_output=True, text=True).returncode == 0

    # Then: 首条语句是 export const meta 字面量、name 为 opsx-apply、四个 phase 齐全；wave 用 parallel；评审只 push 不 await 且在 Fix 阶段之后才 Promise.all；无 Date.now / Math.random / import()；node --check 通过
    assert body.startswith("export const meta = {")
    assert "name: 'opsx-apply'" in text
    assert all(("title: '%s'" % p) in text for p in ("Implement", "Review", "Fix", "Finalize"))
    assert "await parallel(" in text
    assert "reviews.push(agent(" in text and "await reviews.push" not in text
    assert text.index("phase('Fix')") < text.index("Promise.all(reviews)")
    assert "Date.now(" not in text and "Math.random(" not in text and "import(" not in text
    assert node_ok


def test_workflow_routes_models_explicitly():
    # Given: template/.claude/workflows/opsx-apply.js
    text = WORKFLOW.read_text(encoding="utf-8")

    # When: 数 agent( 调用次数与带 model: 的调用次数，并找 models 必填校验
    calls = len(re.findall(r"\bagent\(", text))
    with_model = len(re.findall(r"model:\s*models\.", text))

    # Then: 脚本要求 args.models 含 executor / reviewer / integrator（缺则 throw）；每个 agent( 调用都显式带 model 与 effort；开头 log 路由表
    assert "args.models" in text and "throw new Error" in text
    assert all(("models.%s" % k) in text for k in ("executor", "reviewer", "integrator"))
    assert calls >= 5 and with_model == calls, (calls, with_model)
    assert len(re.findall(r"effort:\s*efforts\.", text)) == calls
    assert "log(`模型路由" in text


def test_workflow_hands_ceilings_to_record():
    # Given: template/.claude/workflows/opsx-apply.js（飞行模式默认路径：切片在临时 worktree 跑 gate，integrator 用 record 写回）
    text = WORKFLOW.read_text(encoding="utf-8")

    # When: 取 GATE 结构化输出 schema 段与 integrator 的 record 命令拼装行
    schema = text[text.index("const GATE = {"):text.index("const FINDINGS = {")]
    record_cmd = re.search(r"slice-gate\.py record [^\n`]*", text)

    # Then: GATE schema 声明 ceilings 属性（否则结构化输出会丢掉天花板行）；record 命令用 --json 传整份门禁 JSON 而不是只传 --slice/--commit
    assert "ceilings" in schema, schema
    assert record_cmd and "--json" in record_cmd.group(0), record_cmd and record_cmd.group(0)


def test_executor_agent_contract():
    # Given: template/.claude/agents/slice-executor.md
    fm, body = frontmatter(AGENTS / "slice-executor.md")

    # When: 读取 frontmatter 与正文
    tools = [t.strip() for t in fm.get("tools", "").split(",")]

    # Then: model inherit、maxTurns 40、permissionMode acceptEdits、tools 含 Read/Edit/Write/Bash；正文含 start 命令、owns 约束、一轮多动作、禁 cd && 前缀、收尾 gate 并原样返回 JSON、不写报告
    assert fm.get("model") == "inherit"
    assert fm.get("maxTurns") == "40"
    assert fm.get("permissionMode") == "acceptEdits"
    assert all(t in tools for t in ("Read", "Edit", "Write", "Bash"))
    assert "slice-gate.py start" in body
    assert "owns" in body
    assert "一轮多动作" in body
    assert "cd &&" in body
    assert "slice-gate.py gate" in body and "原样" in body and "JSON" in body
    assert "不写报告" in body


def test_reviewer_no_rerun():
    # Given: template/.claude/agents/code-reviewer.md
    fm, body = frontmatter(AGENTS / "code-reviewer.md")

    # When: 读取正文
    modes = re.findall(r"\*\*`(full|integration|follow-up)`\*\*", body)

    # Then: 只保留 full 与 follow-up 两种模式，无 integration 与水位线；铁律含不重跑测试与 evidence.log；支持结构化 findings
    assert set(modes) == {"full", "follow-up"}
    assert "水位线" not in body
    assert "不重跑测试" in body and "evidence.log" in body
    assert "findings" in body and "severity" in body


def test_integrator_agent_contract():
    # Given: template/.claude/agents/integrator.md
    fm, body = frontmatter(AGENTS / "integrator.md")

    # When: 读取 frontmatter 与正文
    tools = [t.strip() for t in fm.get("tools", "").split(",")]

    # Then: model sonnet、effort low、tools 含 Bash；正文含合回 commit、_interfaces.md、slice-gate.py final
    assert fm.get("model") == "sonnet"
    assert fm.get("effort") == "low"
    assert "Bash" in tools
    assert "git merge" in body and "_interfaces.md" in body and "slice-gate.py final" in body


def test_executor_carries_subtractive_rules():
    # Given: template/.claude/agents/slice-executor.md 这份执行体契约文件
    # When: 读它的 frontmatter 与正文
    fm, body = frontmatter(AGENTS / "slice-executor.md")

    # Then: 三条减法纪律都在（先查已有并复用 · 全部 caller 修在汇流处 · 切角标 ceiling:），且正文不含 LOC 之类的长度阈值
    assert "先查已有" in body and "复用" in body
    assert "全部 caller" in body and "汇流处" in body
    assert "ceiling:" in body
    assert "LOC" not in body


def test_reviewer_flags_symptom_fix():
    # Given: template/.claude/agents/code-reviewer.md 这份评审员契约文件
    # When: 读它的 frontmatter 与正文（含审查 checklist）
    fm, body = frontmatter(AGENTS / "code-reviewer.md")

    # Then: 正确性维度含症状修复（同类输入经其他 caller 仍失败），且既有可维护性维度的重复代码与过度设计条目一条不少
    assert "症状修复" in body and "caller" in body
    assert "重复代码" in body and "过度设计" in body


# ---------------------------------------------------------------- flight-preflight-and-retry（scenario: slice-retry-resume#workflow-* / apply-docs-*）
# S3 已解锁（骨架标记已去）。

CMD = ROOT / "template" / ".claude" / "commands"
SKILLS = ROOT / "template" / ".claude" / "skills"


def test_workflow_retry_resumes_previous_commit():
    # Given: template/.claude/workflows/opsx-apply.js
    text = WORKFLOW.read_text(encoding="utf-8")

    # When: 取 executorPrompt 函数体与 GATE schema 段
    prompt = text[text.index("const executorPrompt"):text.index("const reviewPrompt")]
    schema = text[text.index("const GATE = {"):text.index("const FINDINGS = {")]
    node_ok = subprocess.run(["node", "--check", str(WORKFLOW)], capture_output=True, text=True).returncode == 0 if shutil.which("node") else True

    # Then: 重试分支含 git cherry-pick 与 retryOf.commit，并以 --base 传 retryOf.base；schema 有 base；node --check 通过
    assert "git cherry-pick" in prompt and "retryOf.commit" in prompt
    assert "--base" in prompt and "retryOf.base" in prompt
    assert re.search(r"base:\s*\{\s*type:\s*'string'", schema), schema
    assert node_ok


def test_apply_docs_mirror_retry_and_preflight():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    cmd = (CMD / "opsx-apply.md").read_text(encoding="utf-8")
    skill = (SKILLS / "openspec-apply-change" / "SKILL.md").read_text(encoding="utf-8")

    # When: 检查 step 3 与回退路径
    def hooks(t):
        return set(re.findall(r"(slice-gate\.py|spec_html\.py|timeline\.py|session-decompose\.py)", t))

    # Then: 两者都在 lint 之后跑 preflight 并说明非 0 停飞；回退路径都含 cherry-pick 与 --base；hook 脚本集合一致
    for t in (cmd, skill):
        assert t.index("slice-gate.py lint") < t.index("slice-gate.py preflight")
        assert "停" in t[t.index("slice-gate.py preflight"):t.index("slice-gate.py preflight") + 400]
        assert "cherry-pick" in t and "--base" in t
    assert hooks(cmd) == hooks(skill)


# ---------------------------------------------------------------- flight-wave-fixes（scenario: slice-base-check#workflow-* / executor-* · integrator-merge-contract#*）
# S2 已解锁（骨架标记已去）。
# run_workflow 用 node 把脚本正文包进 async 函数，mock 掉 agent / parallel / phase / log 后真跑一遍，按 label 正则回放预设结果。

HARNESS = r"""
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const args = input.args;
const calls = [];
async function agent(prompt, opts) {
  calls.push({ prompt, opts });
  const label = (opts && opts.label) || '';
  for (const [pat, reply] of input.replies) {
    if (!new RegExp(pat).test(label)) continue;
    // 运行时实测（2.1.295，wf_393c81e6-c64）：执行体没调结构化输出时 agent() 抛错，不是返回 null
    if (reply && reply.__throw__) throw new Error(reply.__throw__);
    return reply;
  }
  return null;
}
// 同一实测：parallel 不因单个 thunk 抛错整体 reject，失败的位置得空值
const parallel = (thunks) => Promise.all(thunks.map((t) => Promise.resolve().then(t).catch(() => null)));
const phase = () => {};
const log = () => {};
(async () => { __BODY__ })()
  .then((result) => process.stdout.write(JSON.stringify({ calls, result })))
  .catch((e) => process.stdout.write(JSON.stringify({ calls, error: String((e && e.stack) || e) })));
"""


def run_workflow(tmp_path, args, replies):
    """跑 opsx-apply.js：replies 是 [[label 正则, 返回值], ...]；返回 {calls: [{prompt, opts}], result}。"""
    if not shutil.which("node"):
        pytest.skip("需要 node 驱动工作流脚本")
    body = WORKFLOW.read_text(encoding="utf-8").replace("export const meta", "const meta", 1)
    js = tmp_path / "harness.cjs"
    js.write_text(HARNESS.replace("__BODY__", body), encoding="utf-8")
    p = subprocess.run(["node", str(js)], input=json.dumps({"args": args, "replies": replies}),
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert "error" not in out, out["error"]
    return out


def flight_args(**over):
    args = {"change": "c", "changeDir": "openspec/changes/c", "hooksDir": ".claude/hooks", "agentsDir": ".claude/agents",
            "waves": [["S1", "S2"], ["S3"]], "useAgentTypes": True, "branch": "worktree-c",
            "models": {"executor": "opus", "reviewer": "opus", "integrator": "sonnet"}}
    args.update(over)
    return args


def gate_json(s, ok=True, commit="c" * 40, failed=(), base="b" * 40):
    return {"slice": s, "ok": ok, "commit": commit, "failed": list(failed), "warnings": [], "base": base}


def start_cmds(prompt):
    """prompt 里真正的 start 命令（带 --change-dir 的那几处），不含说明文字里提到的 start。"""
    return re.findall(r"slice-gate\.py start \S+ --change-dir [^`\n]*", prompt)


TAIL_REPLIES = [
    ["^integrate:", {"ok": True, "merged": ["S1", "S2"], "failed": [], "warnings": []}],
    ["^review:", {"findings": []}],
    ["^final-gate$", {"slice": "final", "ok": True, "commit": "d" * 40, "failed": []}],
]


def test_workflow_start_carries_expect_branch(tmp_path):
    # Given: branch=worktree-c，waves [[S1, S2], [S3]]；S1 首轮被 start 以 G0 拒绝（commit 为空），S2 首轮门禁红（带 commit 与 base），两者重派后都绿
    replies = [
        ["^S1$", {"slice": "S1", "ok": False, "commit": "", "failed": ["G0 base: HEAD 不是分支 worktree-c 的后代"]}],
        ["^S1:retry$", gate_json("S1")],
        ["^S2$", gate_json("S2", ok=False, commit="e" * 40, failed=["G1 verify: exit 1"])],
        ["^S2:retry$", gate_json("S2")],
        ["^S3$", gate_json("S3")],
    ] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流，取全部执行体派发（label 为 S<n> 或 S<n>:retry）及其中的 start 命令
    out = run_workflow(tmp_path, flight_args(), replies)
    execs = {c["opts"]["label"]: c["prompt"] for c in out["calls"] if re.fullmatch(r"S\d+(:retry)?", c["opts"]["label"])}
    starts = {label: start_cmds(prompt) for label, prompt in execs.items()}

    # Then: 五次执行体派发的 start 命令都带 --expect-branch worktree-c；S1 重派不 cherry-pick 且走首轮任务行（含「按切片包 TDD 实现」、不含「只修这些门禁项」），S2 重派 cherry-pick 且 start 带上一轮 --base；脚本不再出现 expectHead
    assert sorted(execs) == ["S1", "S1:retry", "S2", "S2:retry", "S3"], sorted(execs)
    for label, cmds in starts.items():
        assert cmds and all("--expect-branch worktree-c" in c for c in cmds), (label, cmds)
    assert "cherry-pick" not in execs["S1:retry"]
    assert "按切片包 TDD 实现" in execs["S1:retry"] and "只修这些门禁项" not in execs["S1:retry"]
    assert "cherry-pick" in execs["S2:retry"] and any("--base " + "b" * 40 in c for c in starts["S2:retry"])
    assert "expectHead" not in WORKFLOW.read_text(encoding="utf-8")


def test_workflow_merge_dispatch_forbids_final(tmp_path):
    # Given: waves [[S1, S2], [S3]]，全部切片与合回都成功
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]] + TAIL_REPLIES

    # When: 用 mock agent 跑完工作流，取全部合回派发
    out = run_workflow(tmp_path, flight_args(), replies)
    merges = [c for c in out["calls"] if c["opts"]["label"].startswith("integrate:")]

    # Then: 一律隔离后每个 wave 各一次合回（integrate:w1、integrate:w2）；首次合回派发的返回结构必填项含 ok 与 failed、不含 slice 与 commit；prompt 含「不要运行第 3 项」；blocked 里没有 wave 开头的条目
    assert [c["opts"]["label"] for c in merges] == ["integrate:w1", "integrate:w2"], [c["opts"]["label"] for c in merges]
    required = set(merges[0]["opts"]["schema"]["required"])
    assert {"ok", "failed"} <= required and not ({"slice", "commit"} & required), required
    assert "不要运行第 3 项" in merges[0]["prompt"]
    assert not [b for b in out["result"]["blocked"] if b["slice"].startswith("wave")], out["result"]["blocked"]


def test_executor_returns_start_refusal():
    # Given: template/.claude/agents/slice-executor.md
    fm, body = frontmatter(AGENTS / "slice-executor.md")

    # When: 取「开工」段
    opening = body[body.index("## 开工"):body.index("## 纪律")]

    # Then: 开工段含 --expect-branch，并写明 start 非 0 时不做任何改动、把它打印的 JSON 原样返回
    assert "--expect-branch" in opening
    assert "非 0" in opening and "不做任何改动" in opening and "原样" in opening


def test_integrator_final_only_when_named():
    # Given: template/.claude/agents/integrator.md
    fm, body = frontmatter(AGENTS / "integrator.md")

    # When: 取第 3 项「全量门禁」段
    item3 = body[body.index("## 3. 全量门禁"):body.index("## 4.")]

    # Then: 该段写明仅当 prompt 点名才运行、wave 合回不跑；仍给出 slice-gate.py final 命令
    assert "点名" in item3 and "合回" in item3
    assert "slice-gate.py final" in item3


# ---------------------------------------------------------------- slice-noreturn-resume（scenario: noreturn-retry#*）
# S2 已解锁（骨架标记已去）：执行体未返回重派一次、回退路径 / 执行体契约 / hook 注册同改。

def exec_prompts(out):
    return {c["opts"]["label"]: c["prompt"] for c in out["calls"] if re.fullmatch(r"S\d+(:retry)?", c["opts"]["label"])}


def test_workflow_retries_noreturn_with_checkpoint(tmp_path):
    # Given: waves [[S1, S2], [S3]]、S3 依赖 S1；S1 首轮 agent 得 null（未返回），重派后门禁绿；S2、S3 一次绿
    replies = [["^S1:retry$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(deps={"S3": ["S1"]}), replies)
    execs = exec_prompts(out)

    # Then: 执行体派发恰为 S1、S1:retry、S2、S3；S1:retry 的 start 带 --resume-checkpoint 与 --expect-branch worktree-c，prompt 不含 cherry-pick、含「未返回」；S1 首轮 prompt 不含 --resume-checkpoint；blocked 为空
    assert sorted(execs) == ["S1", "S1:retry", "S2", "S3"], sorted(execs)
    cmds = start_cmds(execs["S1:retry"])
    assert cmds and all("--resume-checkpoint" in c and "--expect-branch worktree-c" in c for c in cmds), cmds
    assert "cherry-pick" not in execs["S1:retry"] and "未返回" in execs["S1:retry"]
    assert "--resume-checkpoint" not in execs["S1"]
    assert out["result"]["blocked"] == [], out["result"]["blocked"]


def test_workflow_noreturn_twice_blocks(tmp_path):
    # Given: waves [[S1, S2], [S3]]、S3 依赖 S1；S1 首轮与重派都得 null
    replies = [["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(deps={"S3": ["S1"]}), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: S1 与 S1:retry 各派发一次；blocked 中 S1 的 kind 为 infra、reason 含「未返回」与「重派」；S3 因依赖记 blocked 且未派发
    assert labels.count("S1") == 1 and labels.count("S1:retry") == 1, labels
    assert blocked["S1"]["kind"] == "infra" and "未返回" in blocked["S1"]["reason"] and "重派" in blocked["S1"]["reason"], blocked
    assert "S3" in blocked and "S3" not in labels


def test_apply_docs_mirror_noreturn_retry():
    # Given: opsx-apply.md、openspec-apply-change/SKILL.md、slice-executor.md 与 hooks/hooks.json
    cmd = (CMD / "opsx-apply.md").read_text(encoding="utf-8")
    skill = (SKILLS / "openspec-apply-change" / "SKILL.md").read_text(encoding="utf-8")
    fm, body = frontmatter(AGENTS / "slice-executor.md")
    hooks = json.loads((ROOT / "template" / ".claude" / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]

    # When: 取两份回退路径段、执行体开工段，以及注册了 slice-gate.py checkpoint 的 hook 条目
    def fallback(t):
        i = t.index("Workflow 不可用")
        return t[i:t.index("两条路径最终都产出", i)]

    def entries(event):
        return [e for e in hooks.get(event, []) if any("slice-gate.py" in h["command"] and "checkpoint" in h["command"] for h in e["hooks"])]

    opening = body[body.index("## 开工"):body.index("## 纪律")]

    # Then: 两份回退路径都含「未返回」与 --resume-checkpoint；开工段含 --resume-checkpoint 与 restored；PostToolUse 有一条 matcher 同时覆盖 Write、Edit、Bash，PostToolUseFailure 也注册了它
    for t in (cmd, skill):
        f = fallback(t)
        assert "未返回" in f and "--resume-checkpoint" in f
    assert "--resume-checkpoint" in opening and "restored" in opening
    assert any(all(tool in e.get("matcher", "") for tool in ("Write", "Edit", "Bash")) for e in entries("PostToolUse"))
    assert entries("PostToolUseFailure")


# ---------------------------------------------------------------- 摘自原仓 #36（flight-integrity-fixes）· scenario: workflow-engine-recovery#workflow-* / single-slice-* / apply-docs-*
# 上方 HARNESS 已按运行时实测改为 agent() 可抛错、parallel 逐个兜底。

THROW = {"__throw__": "agent({schema}): subagent completed without calling StructuredOutput (after in-conversation nudge)"}
REVIEW_HIGH = {"findings": [{"severity": "HIGH", "file": "a.py", "line": 1, "summary": "漏判空值", "fix": "补判空"}]}


def fallback_section(text):
    i = text.index("Workflow 不可用")
    return text[i:text.index("两条路径最终都产出", i)]


def test_workflow_retries_when_executor_throws(tmp_path):
    # Given: waves [[S1, S2], [S3]]；S1 首轮 agent 调用抛错（执行体没交回结构化结果），重派后门禁绿；S2、S3 一次绿
    replies = [["^S1$", THROW], ["^S1:retry$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    execs = exec_prompts(out)

    # Then: 派发了 S1:retry，其 start 带 --resume-checkpoint；blocked 为空
    assert "S1:retry" in execs, sorted(execs)
    cmds = start_cmds(execs["S1:retry"])
    assert cmds and all("--resume-checkpoint" in c for c in cmds), cmds
    assert out["result"]["blocked"] == [], out["result"]["blocked"]


def test_workflow_blocks_after_retry_throws(tmp_path):
    # Given: waves [[S1, S2], [S3]]、S3 依赖 S1；S1 首轮与重派的 agent 调用都抛错
    replies = [["^S1(:retry)?$", THROW], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(deps={"S3": ["S1"]}), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: S1 与 S1:retry 各派发一次；blocked 中 S1 的 kind 为 infra、原因含「未返回」与「已重派」；S3 记 blocked 且未派发
    assert labels.count("S1") == 1 and labels.count("S1:retry") == 1, labels
    s1 = blocked["S1"]
    assert s1["kind"] == "infra" and "未返回" in s1["reason"] and "已重派" in s1["reason"], blocked
    assert "S3" in blocked and "S3" not in labels


def test_apply_docs_describe_recovered_gate():
    # Given: slice-executor.md、opsx-apply.md 与 openspec-apply-change/SKILL.md
    fm, body = frontmatter(AGENTS / "slice-executor.md")
    cmd = (CMD / "opsx-apply.md").read_text(encoding="utf-8")
    skill = (SKILLS / "openspec-apply-change" / "SKILL.md").read_text(encoding="utf-8")

    # When: 取执行体开工段与两份回退路径段
    opening = body[body.index("## 开工"):body.index("## 纪律")]
    fallbacks = [fallback_section(t) for t in (cmd, skill)]

    # Then: 开工段写明「以 3 退出」时打印的是已留存的门禁结论、原样返回；两份回退路径都写明 agent 调用抛错与未返回同样重派
    assert "以 3 退出" in opening and "留存" in opening and "原样" in opening, opening
    assert all("抛错" in f for f in fallbacks), fallbacks


def test_single_slice_wave_runs_isolated(tmp_path):
    # Given: waves [[S1, S2], [S3]]，全部一次门禁绿，S3 的 commit 为 f…f
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3", commit="f" * 40)]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    calls = {c["opts"]["label"]: c for c in out["calls"]}
    merges = [c for c in out["calls"] if c["opts"]["label"].startswith("integrate:")]

    # Then: S3 的派发带 isolation worktree；wave 2 之后有一次合回派发，其 prompt 含 f…f
    assert calls["S3"]["opts"].get("isolation") == "worktree", calls["S3"]["opts"]
    assert any("f" * 40 in c["prompt"] for c in merges), [c["opts"]["label"] for c in merges]


def test_fix_runs_isolated_and_merges_before_final(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 返回的 commit 为 9…9
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
               ["^review:S1$", REVIEW_HIGH], ["^fix$", gate_json("final", commit="9" * 40)]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    calls = {c["opts"]["label"]: c for c in out["calls"]}
    prompt = calls["final-gate"]["prompt"]

    # Then: fix 的派发带 isolation worktree；finalize 派发的 prompt 含 9…9，且它出现在 slice-gate.py final 之前
    assert calls["fix"]["opts"].get("isolation") == "worktree", calls["fix"]["opts"]
    assert "9" * 40 in prompt and prompt.index("9" * 40) < prompt.index("slice-gate.py final"), prompt


def test_apply_docs_mirror_always_isolate():
    # Given: opsx-apply.md、openspec-apply-change/SKILL.md 与 openspec-git-discipline/SKILL.md
    cmd = (CMD / "opsx-apply.md").read_text(encoding="utf-8")
    skill = (SKILLS / "openspec-apply-change" / "SKILL.md").read_text(encoding="utf-8")
    rules = (SKILLS / "openspec-git-discipline" / "SKILL.md").read_text(encoding="utf-8")

    # When: 取两份回退路径段与 git 纪律的 Worktree Isolation 节（临时 worktree 例外条款在其中）
    fallbacks = [fallback_section(t) for t in (cmd, skill)]
    isolation = rules[rules.index("## Worktree Isolation"):rules.index("## Gates")]

    # Then: 两份回退路径都含 isolation: worktree 并点明单片 wave 与 fix 也隔离，且不再有「同 wave 多切片各自」「多切片 wave 各自」的限定；例外条款点明单片 wave 与 fix 同样适用
    for f in fallbacks:
        assert "isolation: worktree" in f and "单片" in f and "fix" in f, f
        assert "同 wave 多切片各自" not in f and "多切片 wave 各自" not in f, f
    assert "单片" in isolation and "fix" in isolation, isolation


# ---------------------------------------------------------------- 摘自原仓 #36（flight-integrity-fixes 评审修复）· scenario: workflow-engine-recovery#fix-* / workflow-*-fix-*

def test_workflow_finalizes_when_fix_throws(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 首轮与重派的 agent 调用都抛错
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
               ["^review:S1$", REVIEW_HIGH], ["^fix(:retry)?$", THROW]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: fix 与 fix:retry 各派发一次；final-gate 仍被派发；blocked 中 fix 的 kind 为 infra、原因含「未返回」与「已重派」
    assert labels.count("fix") == 1 and labels.count("fix:retry") == 1, labels
    assert "final-gate" in labels, labels
    assert blocked["fix"]["kind"] == "infra" and "未返回" in blocked["fix"]["reason"] and "已重派" in blocked["fix"]["reason"], blocked


def test_workflow_retries_fix_after_throw(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 首轮 agent 调用抛错，重派返回 commit 9…9
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
               ["^review:S1$", REVIEW_HIGH], ["^fix$", THROW], ["^fix:retry$", gate_json("final", commit="9" * 40)]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    calls = {c["opts"]["label"]: c for c in out["calls"]}

    # Then: fix:retry 带 isolation worktree；finalize 派发的 prompt 含 9…9；blocked 为空
    assert calls["fix:retry"]["opts"].get("isolation") == "worktree", calls["fix:retry"]["opts"]
    assert "9" * 40 in calls["final-gate"]["prompt"], calls["final-gate"]["prompt"]
    assert out["result"]["blocked"] == [], out["result"]["blocked"]


def test_fix_prompt_checks_base_first(tmp_path):
    # Given: branch=worktree-c，waves [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
               ["^review:S1$", REVIEW_HIGH], ["^fix$", gate_json("final", commit="9" * 40)]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流，取 fix 派发的 prompt
    out = run_workflow(tmp_path, flight_args(), replies)
    prompt = next(c["prompt"] for c in out["calls"] if c["opts"]["label"] == "fix")

    # Then: prompt 含基点校验命令 git merge-base --is-ancestor $(git rev-parse worktree-c) HEAD 且它先于 start；不成立时返回 G0 base；start fix 带 --expect-branch worktree-c
    check = "git merge-base --is-ancestor $(git rev-parse worktree-c) HEAD"
    assert check in prompt and prompt.index(check) < prompt.index("slice-gate.py start fix"), prompt
    assert "G0 base" in prompt, prompt
    assert all("--expect-branch worktree-c" in c for c in start_cmds(prompt)) and start_cmds(prompt), prompt


def test_apply_docs_mirror_fix_base_check():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    cmd = (CMD / "opsx-apply.md").read_text(encoding="utf-8")
    skill = (SKILLS / "openspec-apply-change" / "SKILL.md").read_text(encoding="utf-8")

    # When: 取两份回退路径段
    fallbacks = [fallback_section(t) for t in (cmd, skill)]

    # Then: 两份回退路径都写明 fix 先做 merge-base --is-ancestor 基点校验，且 fix 抛错 / 未返回时重派一次后仍跑 final
    for f in fallbacks:
        assert "merge-base --is-ancestor" in f, f
        assert "fix 未返回" in f, f


def test_workflow_skips_merge_when_fix_base_rejected(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；S1 的评审给出 1 条 HIGH；fix 首轮与重派都以 G0 base 拒绝，返回的 commit 为 8…8
    g0 = {"slice": "fix", "ok": False, "commit": "8" * 40, "failed": ["G0 base: HEAD 不是分支 worktree-c 的后代"]}
    replies = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")],
               ["^review:S1$", REVIEW_HIGH], ["^fix(:retry)?$", g0]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]
    final_prompt = next(c["prompt"] for c in out["calls"] if c["opts"]["label"] == "final-gate")
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: fix:retry 派发了一次；finalize 的 prompt 不含 8…8；blocked 中 fix 的原因含 G0 base
    assert labels.count("fix:retry") == 1, labels
    assert "8" * 40 not in final_prompt, final_prompt
    assert "G0 base" in blocked["fix"]["reason"], blocked


# ---------------------------------------------------------------- 摘自原仓 #37（flight-integrity-followups）· scenario: workflow-engine-recovery#mechanical-roles-* / reviewer-failure-recorded / apply-docs-mirror-agent-failure-handling
# THROW / fallback_section 复用上方定义。

ALL_GREEN = [["^S1$", gate_json("S1")], ["^S2$", gate_json("S2")], ["^S3$", gate_json("S3")]]


def test_mechanical_roles_retry_once(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；wave 1 的合回与 final-gate 的首次 agent 调用都抛错，重派后都成功
    retried_final = {"slice": "final", "ok": True, "commit": "a" * 40, "failed": []}
    replies = ALL_GREEN + [["^integrate:w1$", THROW], ["^final-gate$", THROW],
                           ["^final-gate:retry$", retried_final]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]

    # Then: 派发了 integrate:w1:retry 与 final-gate:retry；blocked 为空，返回的 final 是重派的结果
    assert "integrate:w1:retry" in labels and "final-gate:retry" in labels, labels
    assert out["result"]["blocked"] == [], out["result"]["blocked"]
    assert out["result"]["final"] == retried_final, out["result"]["final"]


def test_mechanical_roles_blocked_after_retry(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；wave 1 的合回与 final-gate 的首次和重派调用都抛错
    replies = ALL_GREEN + [["^integrate:w1(:retry)?$", THROW], ["^final-gate(:retry)?$", THROW]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: 工作流正常结束，S3 仍被派发；blocked 里有 wave1 与 final，kind 为 infra，原因含「未返回」与「已重派」
    assert "S3" in labels, labels
    for key in ("wave1", "final"):
        assert key in blocked, blocked
        assert blocked[key]["kind"] == "infra" and "未返回" in blocked[key]["reason"] and "已重派" in blocked[key]["reason"], blocked


def test_reviewer_failure_recorded(tmp_path):
    # Given: waves [[S1, S2], [S3]] 全部门禁绿；S1 的评审员调用抛错，S2 的评审给出 1 条 MEDIUM
    medium = {"severity": "MEDIUM", "file": "b.py", "line": 2, "summary": "命名不一致", "fix": "统一命名"}
    replies = ALL_GREEN + [["^review:S1$", THROW], ["^review:S2$", {"findings": [medium]}]] + TAIL_REPLIES

    # When: 用 mock agent 跑完整个工作流
    out = run_workflow(tmp_path, flight_args(), replies)
    labels = [c["opts"]["label"] for c in out["calls"]]
    blocked = {b["slice"]: b for b in out["result"]["blocked"]}

    # Then: blocked 里有 review:S1（infra、原因含「评审未返回」）；deferred 含 S2 的那条 MEDIUM；final-gate 已派发
    assert blocked["review:S1"]["kind"] == "infra" and "评审未返回" in blocked["review:S1"]["reason"], blocked
    assert medium in out["result"]["deferred"], out["result"]["deferred"]
    assert "final-gate" in labels, labels


def test_apply_docs_mirror_agent_failure_handling():
    # Given: opsx-apply.md 与 openspec-apply-change/SKILL.md
    cmd = (CMD / "opsx-apply.md").read_text(encoding="utf-8")
    skill = (SKILLS / "openspec-apply-change" / "SKILL.md").read_text(encoding="utf-8")

    # When: 取两份回退路径段
    fallbacks = [fallback_section(t) for t in (cmd, skill)]

    # Then: 都写明 integrator 与 final 抛错或未返回时重派一次；都写明「评审未返回」只记录、不重派
    for f in fallbacks:
        assert "integrator 与 final" in f, f
        assert "评审未返回" in f and "不重派" in f, f


# ---------------------------------------------------------------- label 契约（scenario: route-audit-role-resolution#label-contract-matches-workflow-script）


def test_label_contract_matches_workflow_script():
    # Given: template/.claude/workflows/opsx-apply.js 与 template/.claude/hooks/session-decompose.py
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    decompose = load_hook("session-decompose")

    # When: 读出脚本里 integrator 与 code-reviewer 的 label 模板所在的派发调用；把样例 label 交给对账的 label 判定
    templates = {"`integrate:w${i + 1}`": "integrator", "'final-gate'": "integrator", "`review:${s}`": "code-reviewer"}
    calls = {t: [line for line in lines if "label:" in line and t in line] for t in templates}
    samples = {"integrate:w1": "integrator", "integrate:w1:retry": "integrator", "final-gate": "integrator",
               "final-gate:retry": "integrator", "review:S1": "reviewer"}

    # Then: 每个模板都和它对应的 typed(...) 写在同一个派发调用里；前四个样例判为 integrator，review:S1 判为 reviewer
    for t, agent_type in templates.items():
        assert len(calls[t]) == 1 and ("typed('%s')" % agent_type) in calls[t][0], (t, calls[t])
    for label, role in samples.items():
        assert decompose.label_role(label) == role, (label, decompose.label_role(label))
