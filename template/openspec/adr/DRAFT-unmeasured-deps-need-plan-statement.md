# DRAFT. 基线的依赖图未测时计划须表态

- Status: accepted
- Date: 2026-11-18
- 来源 change：plan-hygiene（design D3）

## Context

增量 final、经锚点的增量基线都靠依赖图。包装脚本不转发运行器契约变量、`gate.test` 不是 pytest 又没配 `gate.impacted` 时，依赖图测不到，每次 final 都整跑 `gate.test`。

`DRAFT-gate-test-result-handoff-and-runner-contract` 决策 4 让这件事可诊断：基线写 `deps_unmeasured`（四类原因与修法），`flight-doctor.py` 预告并体检。2026-11-09 定的处置是「只预告、不阻断」（unified-test-result-reuse design 的 Q3，没有立 ADR）。

实测结果：afa 的 executor 自 11 月上旬起每份基线都带 `plugins-dropped`，到 2026-11-18 累计 14 份，没有一份被处理；收口阶段的 final 49 次全量，原因全部是「没有可用锚点」。没有人必须回应的告警，等于没有。

选测退化为全选时，模板已有一套表态机制（`DRAFT-repo-selector-reports-scope-at-plan-time` 决策 5–7、`DRAFT-scope-provider-mandatory-with-runtime-guard` 决策 4–5）：`gate.scope_full_reason` 逐个触发项写理由，lint / preflight / final 开跑前复核，理由以 approve 提交为准并显示在 `spec.html`。

2026-11-18 用户在方案页 `docs/flight-fixes-and-test-governance.html` 的 Q5 选了 A：改为表态制。

## Decision

1. **未测即触发项**：本 change 有一份跑完的基线且带 `deps_unmeasured` 时，选测复核追加伪触发项 `runner:deps-unmeasured`，与提供方报告的触发项一起，按现有 `gate.scope_full_reason` 的规则处置。不为它另开字段、另开复核点。
2. **出路有三条**：修好运行器让依赖图测到（重跑 baseline 后触发项消失）；配 `gate.impacted` 由仓库自己选测；或在计划里写理由，由人在 `spec.html` 看着放行。
3. **判定以基线为准**：包装脚本的文本检查只在基线跑出来之前作提示，不判红；基线跑出来之前这条理由可以预写。baseline 开跑前的复核也按待定处理，不能要求先写理由才允许重测。
4. **状态随增量基线沿用**：没有新的测量时，沿用来源基线的 `deps_unmeasured`。
5. **设计边界不变**：`DRAFT-builtin-scope-provider-and-shell-closure` 定下的「内建声明下的非 pytest 运行器与部件形态恒全量，只注明、不要求写理由」继续在役，这两类不追加触发项。
6. **`flight-doctor.py` 仍只读、恒退出 0**：阻断落在门禁的复核上，体检与预告不承担阻断。

否决的方案：

- **继续只预告**：已有 14 份基线的反例。
- **`doctor` 加退出码并接会话钩子定期打印**：仍然没有人必须回应。
- **按脚本文本判红**：照常继承环境的包装脚本文本里没有契约变量名，依赖图却测得到；按文本判会逼它们写套话理由。
- **新开一个字段单独表态**：lint、final 复核、approve 绑定、审批页四处要各接一遍。

## Consequences

- **更易**：依赖图没接通的仓库在起飞前就被拦下并被告知修哪里；接受全量成为一条写在计划里、人看得见的决定。
- **更难**：这类仓库升级模板后，下一次 lint / preflight 会变红，每个在途 change 要么修运行器、要么补一条理由并重新批准。
- **中性**：unified-test-result-reuse 的「只预告、不阻断」对 `flight-doctor.py forecast` 本身仍成立；被改掉的只是「未测」这一件事的处置。内建声明下的非 pytest 仓库不受影响，要纳入须另立 ADR 取代第 5 条所指的那一条。
