## Why

2026-10-15 定下：Workflow 引擎版（`stable-v2.0` 那一套）另起独立仓库 `akarizo/intent-driven-workflow` 维护；原仓 `akarizo/intent-driven-claude-code` 的 main 继续 Mod 版，不动。新仓 main 已推为 `stable-v2.0`（`49533dd` = 原仓 PR #34），`stable-v1.0` / `stable-v2.0` 两个 tag 同时推上。取舍在决策页（原仓 worktree 的 `docs/remove-mod-decisions.html`）与会话里逐项定下，代替 grill-me 访谈。

`stable-v2.0` 之后原仓合入了 #35–#63 共 29 个 PR，大多是 flight 插件（Mod）专属。其中 12 个 PR 里有不依赖插件的通用改进，修的都是 v2.0 上实测到或从代码核实的问题：

- **G7 假绿**：只看源码文本，认不出别名 xfail，final 报「36/36」而实际 18 条仍是 xfail。证据：原仓 `flight-integrity-fixes` proposal（#35 飞行）。修复：#36。
- **抛错重派失效**：执行体 `agent()` 抛错时重派被跳过，blocked 原因却写「已重派一次」；integrator、final-gate、评审员抛错会让整个工作流 reject。证据：同上与 `flight-integrity-followups`。修复：#36 #37。
- **Stop hook 误拦**：单片 wave 的执行体在主 worktree 里写切片标记，Stop hook 误拦主会话与评审员。证据：`flight-integrity-fixes`。修复：#36。
- **G7 用错测试环境**：用会话的 `python3` 跑 scenario 测试，下游依赖装在 venv / uv 时全部判「未被收集」，且没有超时。证据：`flight-integrity-followups`。修复：#37。
- **门禁白跑**：final 先跑全量、最后才跑秒级的 G7；基线上有预存红就判红，afa 每个 change 要先跑一遍全量、手写 deselect（约 33 分钟）；审批面板要等基线跑完才出。证据：`flight-gate-speedup`（afa `dlib-recorder-param-patch` 实测）。修复：#45。
- **覆盖率漏判**：基线有预存红时，pytest-cov 覆盖率未达标被逐条差分放过。证据：#45 评审 MEDIUM。修复：#60。
- **冲突统计恒为 0**：`/pr-ship` 第 4 步统计旧版 `merge-tree` 的输出，那里的冲突标记前带 `+`。证据：#46 实际 2 个冲突文件，报 0。修复：#47。
- **安装器三处缺陷**：`--upgrade` 用模板整份覆盖用户的 `.claude/settings.json`（`copy_tree` 只保留 `preferences.md`）；把本仓自己的 change 与 ADR 草稿拷进用户项目；pipe 模式装不了 tag。证据：`install.sh` 代码、`install-openspec-seeds`、`install-from-tag`。修复：#35 #36 #38 #55。
- **路由缺口**：legacy 逐 task 守门派 code-reviewer 时不写 `model`（铁律 11）。证据：v2.0 skill 原文。修复：#51。

## What Changes

- **Workflow 引擎可靠性**（原仓 #36 #37）：
  - 执行体 `agent()` 抛错按未返回处理、重派一次；仍失败记 blocked（infra），原因如实；
  - 每个执行体（含单片 wave 与 fix）一律 `isolation: worktree`，每个 wave 都由 integrator 合回，主 worktree 不再出现切片标记；
  - fix 先做基点校验（G0），抛错 / 未返回 / G0 拒绝都重派一次，fix 的 commit 在 final 之前合回；
  - integrator 与 final-gate 抛错或未返回重派一次，仍失败记 blocked（infra），工作流照常走完；评审员抛错只记 blocked（infra）、不重派，由 `/pr-ship` 的整 PR 评审兜底；
  - `opsx-apply` 命令与同名 skill 的 Agent 回退段、`openspec-git-discipline` 的临时 worktree 例外条款同改。
- **门禁结论留存与找回**（#36 #37）：切片门禁绿时，判定器把结论写进 `refs/flight/<change>/gate-<S>`；重派的 `start --resume-checkpoint` 在基点吻合时以 3 退出、原样交出这份结论；`record` 写回后与首轮起跑时清理；改计划后不会找回旧结论。
- **G7 按实际运行结果判**（#36 #37）：对映射到 `.py` 的 scenario 实跑一次 pytest，只认 PASSED；运行方式取 `gate.pytest` → 从 `gate.test` 推导 → 退回本解释器并警告；有超时；收集失败附退出码与错误行。
- **改动口径**（#41 #46 #40）：未提交的字节码不算切片改动；G3 不把切片标记当源码；final 之后只改了同一 changes 根下任一 change 的记账文件（含 `slices/_interfaces.md`）仍算新鲜。
- **门禁提速**（#45 #60）：final 先跑 G7，红了就不跑全量；`gate.test` 是 pytest 时全量测试按基线逐条差分，度量不可信或覆盖率未达标时按退出码判；final 在脏工作树上加警告；baseline 先写运行标记，preflight 区分「仍在跑」与「已中断」；`/opsx-propose` 先渲染审批面板、基线放后台。
  - **BREAKING**：`slices.json` 必须显式写 `gate.test`（`slice-gate.py lint` 拦截），baseline 不再自动探测后写回。
  - **放宽**：基线有可度量的预存红时 baseline 判 ok、可以起飞（原先判红）。
- **`/pr-ship` 预合并检查**（#47）：改为 `git merge-tree --write-tree --name-only` 按退出码判断冲突；需要 git ≥ 2.38。
- **legacy 守门的评审派发显式 model**（#51 的通用部分）：先跑 `session-model.py` 判出 `<main>`，三处 code-reviewer 派发都带 `model`。
- **安装器**（#35 #36 #38 #55 + 本仓新增）：
  - `REPO_URL` 缺省改为本仓 `https://github.com/akarizo/intent-driven-workflow`，`IDT_BRANCH` 缺省仍是 `main`；
  - pipe 模式 `IDT_BRANCH` 认分支或 tag，下载后交给归档自带的 `install.sh` 执行；
  - `--upgrade` 保留用户的 `.claude/settings.json`，只补模板里缺失的顶层键；
  - `openspec/` 只下发种子清单，列出疑似旧版误拷的本库开发工件（不代删）；
  - 目标项目已启用 `flight@intent-driven` 插件时醒目提示并打印卸载命令（不代执行）；列出 Mod 版遗留的 `.claude/hooks/ledger.py`、`plan_fp.py` 可手动删除。
- **README**：仓库名与安装地址改为本仓；新增「安装指定版本」「与 Mod 版的关系 / 从 Mod 版切换」两段。
- **ADR**：新增 `DRAFT-workflow-edition-repo`；原样带入原仓两份通用 ADR：`DRAFT-installer-versioned-with-template`、`DRAFT-test-gate-baseline-diff`。

**不改**：
- 起飞批准仍是会话转录里人发的 `/opsx-apply` + 计划工件 mtime；铁律、`CLAUDE.md`、`template/CLAUDE.md.snippet`、`docs/WORKFLOW_zh.md` 维持 v2.0 原文。
- G5 仍读 `evidence.log`，「未见先红」仍只警告。
- 原仓 Mod 时代的其余机制一律不带：批准带、账本、计划指纹、测量协议与护栏、能力包络、无人值守、`--reuse-fix`、「blocked 即停飞」、落地前预合并等。
- 在 Workflow 引擎上重做 Mod 时期的优化（决策页 R1–R6）留作后续 change。

## Capabilities

### New Capabilities

- `workflow-engine-recovery`：执行体、fix、integrator、final-gate、评审员的抛错与未返回处理；执行体一律隔离；门禁结论的留存与找回；命令、skill 与 git 纪律的同步说明。
- `gate-scenario-run`：G7 按 pytest 实际结果判定，运行方式、超时与诊断信息。
- `gate-change-scope`：字节码与切片标记不算改动；final 新鲜度的记账文件口径。
- `gate-full-suite-baseline`：final 先 G7、全量测试按基线逐条差分、覆盖率失败、脏工作树警告、`gate.test` 必填、基线运行标记与 preflight 识别。
- `propose-parallel-baseline`：`/opsx-propose` 先渲染审批面板、基线后台运行；schema 写明 `gate.test` 必填与基线差分。
- `pr-ship-premerge-check`：`/pr-ship` 预合并冲突检查按 `merge-tree` 退出码判断。
- `legacy-review-routing`：legacy 逐 task 守门的评审派发显式指定 `model`。
- `installer-edition`：安装器缺省从本仓下载、pipe 按分支或 tag 交接、保留用户 settings、只下发种子、Mod 版退场提示，以及 README 的版本说明。

### Modified Capabilities

<!-- 无：openspec/specs/ 下还没有已归档的 capability -->

## Impact

- 引擎与 agent：`template/.claude/workflows/opsx-apply.js`、`template/.claude/agents/integrator.md`、`template/.claude/agents/slice-executor.md`。
- 判定器：`template/.claude/hooks/slice-gate.py`。
- 命令与 skill：`template/.claude/commands/{opsx-apply,opsx-propose,pr-ship}.md` 与同名 skill、`template/.claude/skills/openspec-git-discipline/SKILL.md`、`template/.claude/skills/legacy/openspec-subagent-apply-change/SKILL.md`。
- schema：`template/openspec/schemas/intent-driven/schema.yaml`（tasks instruction 的说明文字）。
- 分发：`install.sh`、`README.md`。
- 测试：`test_agents_workflow`、`test_slice_gate`、`test_ship_verdict`、`test_template_docs`、`test_install` 增改；新增 `test_slice_gate_final`、`test_slice_gate_baseline_preflight`、`test_slice_gate_coverage`。
- ADR：`template/openspec/adr/` 新增 1 份、带入 2 份。
- 来源（原仓提交）：#35 `5a110aa` · #36 `a1c64a0` · #37 `85d56b0` · #38 `4c5d432` · #40 `8cffd43` · #41 `4d0ccd1` · #45 `0b44d09` · #46 `3aa6235` · #47 `bb8a2d2` · #51 `ac5d051` · #55 `b11a49f` · #60 `dc7a5aa`；引擎、agent、判定器与测试以 #48 `36d91c3` 为摘取基底（Workflow 引擎删除前的最后一版）。
