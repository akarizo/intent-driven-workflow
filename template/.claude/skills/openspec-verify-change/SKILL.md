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

跑一次门禁 `final`（全量 test/lint/typecheck + 全部 scenario 状态）、对照 `slices.json` 打印每条 scenario 的映射状态、再做一次简短 coherence 检查（实现是否遵循 design 的关键决策），综合给出可否 archive 的结论。

**Input**：可选指定 change 名。留空时若能从会话上下文推断，或只有一个活跃 change，就直接用；仍歧义才用 **AskUserQuestion tool** 让用户选。

**Steps**

1. **选 change（可推断则用，不必每次都问）**
   - 有参数用参数；能从上下文推断则用；只有一个活跃 change → 自动选。
   - 仍歧义 → `openspec list --json` + **AskUserQuestion** 让用户选。

2. **跑门禁 final**
   ```bash
   python3 .claude/hooks/slice-gate.py final --change-dir openspec/changes/<name>
   ```
   拿到 JSON：全量 test/lint/typecheck 结果 + `scenarios{total, passed}`。
   配置了 `gate.checks` 时，final 在全量之后运行每个检查的 `final` 命令（G7 红时不跑），红记 `G9 check <name>`，完整输出在 `$GATE_CHECK_DIR/.gate-final.log`。

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
   - 否则列出阻塞项（final 的 `failed` 数组 / 未 `passed` 的 scenario / coherence 背离），每条给具体修复建议。

**Output Format**

使用清晰的 markdown：
- 门禁 final 结果表（test / lint / typecheck / scenarios）
- scenario 映射表（id / 状态）
- coherence 背离列表（若有）
- 结论：Ready for archive / 需要先修 <N> 项，每项带 `file:line` 与具体建议

**Guardrails**
- 能推断 change 就不问；只有真正歧义才问。
- final 是唯一判据来源，不靠关键字搜索猜测实现是否存在。
- coherence 检查只挑明显背离，不因风格差异报 issue。
