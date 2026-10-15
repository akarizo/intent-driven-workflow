---
description: 一次成稿：一步生成完整 change 的全部工件（含切片计划），收尾把 spec.html 交给人类审批，起飞需人类自己发 /opsx-apply
---

一次成稿：并行读完全部待建工件的 instruction，再一次性写出全部工件（含切片计划），最后跑一次 `openspec status`。工件写完后渲染审批面板、在后台跑基线门禁，然后硬交接给人类：本命令到此结束，起飞由人类自己发出 `/opsx-apply`（`takeoff-gate.py` 机械校验这条批准）。

---

**Input**：change 名（kebab-case），或一段描述想构建什么的自然语言。

**Steps**

1. **补全输入**（缺失时）

   用 **AskUserQuestion tool**（开放式，无预设选项）问：
   > "What change do you want to work on? Describe what you want to build or fix."

   从描述推导 kebab-case 名（如 "add user authentication" → `add-user-auth`）。

   **IMPORTANT**：想不清楚就不要继续。

1.5 **建并进入本 change 的 worktree**（见 `.claude/skills/openspec-git-discipline/` 的 Worktree Isolation）

   在建 change 目录**之前**，先隔离工作区：

   ```bash
   git worktree add .worktrees/<name> -b worktree-<name>
   ```

   进入它（CWD = `.worktrees/<name>/`）；已存在则直接进入。之后 step 2 起的相对路径自然落 worktree 内。

2. **建 change 目录**
   ```bash
   openspec new change "<name>"
   ```
   这会在 `openspec/changes/<name>/`（worktree 内）建好 `.openspec.yaml`。

3. **一次成稿**

   - `openspec status --change "<name>" --json` 拿 `applyRequires` 与 `artifacts`。
   - **并行**对每个待建工件跑 `openspec instructions <id> --change "<name>" --json`，一次性全部读完（不要逐个来回问询）。
   - 按下面的**触发器表**决定每个可选工件要不要写实质内容：

     | 工件 | 触发条件 | 未命中时 |
     |---|---|---|
     | specs | 行为发生变化 | 本模板要求 specs 必有，不可跳过 |
     | design | 跨模块 / 新依赖 / 数据模型 / 安全或性能迁移 | 写实质设计内容；未命中 → design.md 只写一行「触发器未命中，跳过：<理由>」 |
     | adr | 长期架构承诺 | 命中才建 DRAFT-*.md；未命中不建 |
     | tasks | 恒必需 | — |

   - 一次性写出全部该建的工件（proposal → specs → design(按触发器) → adr(按触发器) → tasks）。
   - **tasks 阶段**额外产出（详见 schema 的 tasks instruction）：`slices.json`、每个切片一份 `slices/<S>.md` 切片包、每个 scenario 一个 `xfail(strict)` 测试骨架（放进所属切片 owns 的测试文件）、由 `slices.json` 生成的 `tasks.md`。
   - 随后跑：
     ```bash
     python3 .claude/hooks/slice-gate.py lint --change-dir openspec/changes/<name>
     ```
     红 → 修 `slices.json` 直到绿。

4. **渲染审批面板**
   ```bash
   python3 .claude/hooks/spec_html.py --change-dir openspec/changes/<name>
   ```
   一次性生成 `openspec/changes/<name>/spec.html`（模型不逐字渲染 HTML）。失败不阻塞主流程：捕获异常只 warn 一行，继续下一步。

5. **基线门禁（后台运行）**
   ```bash
   python3 .claude/hooks/slice-gate.py baseline --change-dir openspec/changes/<name>
   ```
   用**后台**方式运行（例如 Bash 的 `run_in_background`），不等它跑完，直接进入 step 6 交接。它跑一次全量测试，把耗时写回 `slices.json.gate.full_suite_sec`；同时跑 lint / typecheck 基线与每片 `verify`，产出 `gate-baseline.json`。
   verify 在基线上必须绿（骨架是 strict-xfail）。
   baseline 运行期间改计划文件不会被覆盖（结束时只写回耗时）；改的是 gate 命令或某片 `verify` 时基线判红（「重跑 baseline」），按下面的红处理，跑完后须重跑 baseline。
   baseline 结束（后台通知）时只报告一行：
   - 退出 0 → 「基线绿（全量 N 秒；预存红 k 条）」；
   - 退出非 0 → **停下报告** stdout 的 `reasons`，并说明：人类修 `gate.test` / `verify` / 环境后重跑本步；修改涉及计划文件（proposal / design / slices.json / specs / 切片包）时重新渲染 spec.html（step 4）并重新批准。

6. **收尾**
   ```bash
   openspec status --change "<name>"
   ```
   然后**硬交接**（四件事缺一不可）：

   1. 打印 `spec.html` 的**绝对路径**（`openspec/changes/<name>/spec.html`，用 `pwd` 拼成绝对路径再打印），请人类打开审阅飞行计划。
   2. 明确一行：**本命令到此结束。不得在同一轮继续 `/opsx-apply`；起飞需要你自己发出 `/opsx-apply <name>`（`takeoff-gate.py` 会在转录里核验这条人类批准 + 计划新鲜度，模型自证无效）。**
   3. 说明 baseline 仍在后台跑：跑完前起飞会被 preflight 拒绝（报「仍在跑」），等 baseline 报告一行后再起飞。
   4. 提示用户在 baseline 报告之后再把工件单独 commit（artifacts-only commit；baseline 结束会改写 `gate-baseline.json` 与 `slices.json` 的耗时）。

**Output**

完成后总结：change 名与位置、生成的工件清单、切片数与 wave 数、spec.html 绝对路径 + 「请你自己发出 `/opsx-apply <name>` 起飞」（本命令不代跑）。

**Artifact Creation Guidelines**

- 遵循 `openspec instructions` 返回的 `instruction` 字段。
- `context` / `rules` 是给你的约束，不要抄进正文。
- 用 `template` 作为文件骨架，逐节填充。

**Guardrails**
- 一次性写出全部工件，不要逐个工件反复问询。
- 已存在同名 change → 问用户续做还是新建。
- 每个工件写完后确认文件确实存在再继续。
