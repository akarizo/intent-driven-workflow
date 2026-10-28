---
name: openspec-verify-change
description: Run the final slice gate, report scenario coverage, and do a short coherence check before archiving. Use when the user wants to validate that implementation is complete, correct, and coherent before archiving.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "2.0"
  generatedBy: "1.3.1"
---

跑一次门禁 `final`（默认增量的 test + lint/typecheck + 全部 scenario 状态）、对照 `slices.json` 打印每条 scenario 的映射状态、再做一次简短 coherence 检查（实现是否遵循 design 的关键决策），综合给出可否 archive 的结论。

**Input**：可选指定 change 名。留空时若能从会话上下文推断，或只有一个活跃 change，就直接用；仍歧义才用 **AskUserQuestion tool** 让用户选。

**Steps**

1. **选 change（可推断则用，不必每次都问）**
   - 有参数用参数；能从上下文推断则用；只有一个活跃 change → 自动选。
   - 仍歧义 → `openspec list --json` + **AskUserQuestion** 让用户选。

2. **跑门禁 final**
   ```bash
   python3 .claude/hooks/slice-gate.py final --change-dir openspec/changes/<name>
   ```
   拿到 JSON：test/lint/typecheck 结果 + `scenarios{total, passed}` + `incremental`。
   **final 默认增量**：以锚点池（`<git common dir>/flight-anchors/`）里可用的锚点为基准，只重跑受影响的测试文件（依赖与改动相交的、改动里的测试文件、锚点里有失败用例的、盲文件），其余用例沿用锚点结论；重跑出的新失败（不在基线 `failed_nodes` 里）记 `G2 test`；跑完把锚点前移到本次。
   - **自动全量**：没有可用锚点（池空 / `gate.test` 或分层指纹变了 / 锚点不是 HEAD 的祖先 / 依赖图没测到）、基线有预存红但缺 `failed_nodes`、改动含全局文件（任何 `conftest.py`、`pytest.ini` / `pyproject.toml` / `setup.cfg` / `tox.ini` / `setup.py` / `requirements*.txt` / 各类锁文件 / `.python-version` / `test-tiers.json`），或改动含从未被任何用例触及的非 `.py`、非文档文件 → 改跑全量，`incremental.full_why` 写明原因。
   - **`--full`**：`slice-gate.py final --full` 强制全量。
   - **同树沿用**：代码树、计划（`plan_sha` / `scenario_tests`）、各门禁命令（含 `gate.impacted`）都没变且上次 final 绿 → 直接沿用上次结论秒回，不跑任何测试或检查，`incremental.mode` 为 `reused`；上次红照常运行。
   - 配置了 `gate.impacted` 时，增量改由它运行，经 `GATE_DELTA_FILE` / `GATE_ANCHOR_COMMIT` 拿到改动清单与锚点（`incremental.source` 为 `impacted`）。
   配置了 `gate.checks` 时，final 在全量之后运行每个检查的 `final` 命令（G7 红时不跑），红记 `G9 check <name>`，完整输出在 `$GATE_CHECK_DIR/.gate-final.log`。
   配置了测试分层（openspec 根有 `test-tiers.json`）时，G7 绿后 final 以探针跑单元层：按基线差分，并判 `G10 slow unit test`（单元层用例耗时 ≥3 秒、重跑仍超线且未经 `allow-slow` 放行）与 `G11 impure unit test`（单元层用例触碰真实文件 / 子进程 / 网络），不可度量时只警告 `G10/G11 不可度量`；再逐个跑 `gate.integration` 选中的区域，按该区域的基线失败差分，新增失败记 `G2 region <NAME>`，基线缺记录或区域 `cmd` 已变记 `G2 region <NAME>：基线缺记录或命令已变，重跑 baseline`；输出带分层耗时 `tier_sec`。

3. **打印 scenario 映射状态**
   对照 `openspec/changes/<name>/slices.json` 的 `scenario_tests`，逐条列出每个 scenario 的当前状态：
   - `pending`：测试骨架仍标 `xfail`/`skip`
   - `unlocked`：骨架标记已去掉，但门禁记录里还没见过它 pass
   - `passed`：`gate-report.md` 里该切片曾以 ok 收尾

   全部 `passed` 才算完整覆盖；否则列出未覆盖的 scenario id。

4. **简短 coherence 检查**（design 决策是否被遵循）
   - `design.md` 存在 → 抽取其 Decisions 小节列出的关键决策，逐条快速核对实现是否遵循；只报有明显背离的条目。
   - `design.md` 不存在（触发器未命中的跳过声明）→ 跳过本项，注明「design.md 为跳过声明，无实质决策可核对」。

5. **给出结论**
   - final 全绿 + 全部 scenario `passed` + 无 coherence 背离 → `Ready for archive`。
   - 结论里列出 `incremental.mode`（`incremental` / `full` / `reused`）：增量带锚点 commit 与重跑 / 沿用数，全量带 `full_why`，沿用带被沿用的 commit。
   - 否则列出阻塞项（final 的 `failed` 数组 / 未 `passed` 的 scenario / coherence 背离），每条给具体修复建议。

**Output Format**

使用清晰的 markdown：
- 门禁 final 结果表（test / lint / typecheck / scenarios / incremental.mode）
- scenario 映射表（id / 状态）
- coherence 背离列表（若有）
- 结论：Ready for archive / 需要先修 <N> 项，每项带 `file:line` 与具体建议

**Guardrails**
- 能推断 change 就不问；只有真正歧义才问。
- final 是唯一判据来源，不靠关键字搜索猜测实现是否存在。
- coherence 检查只挑明显背离，不因风格差异报 issue。
