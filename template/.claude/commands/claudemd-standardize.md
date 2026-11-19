---
description: 按 claudemd-standard 全量对标——在正确层级(LCA)创建缺失的 CLAUDE.md(已有跳过),并对全部 CLAUDE.md 走「证据调查→合并现存→review」重生成/调整到标准
---

把整个仓库的 CLAUDE.md 体系**一次性拉到 `.claude/claudemd-standard.md` 标准**:① 在正确层级(LCA)**创建缺失**的 CLAUDE.md(已有不重建);② 对**全部** CLAUDE.md 走「证据调查 → 合并现存 → review」重生成或调整到标准。

**何时用**:初次采纳本标准、或长期漂移后做一次全量对标。与另两个的分工:`/claudemd-commit` 增量沉淀本轮变更(预算中性);`/claudemd-distill` 压缩收敛(文件变短);**本命令 = 全量对标**(创建 + 全部重生成)。三者共用 `.claude/claudemd-standard.md` 为硬基线,收尾均须 `claudemd-lint` 全绿。

**Input**: 可选子树路径(默认全仓)。例 `/claudemd-standardize executor/`。

**前置**: 读 `.claude/claudemd-standard.md`(硬约束基线)。不存在 → 提示先装/升级模板(`install.sh [--upgrade]`),终止。

**Steps**

1. **发现 + 定单元**
   ```bash
   find . -name "CLAUDE.md" -not -path "*/node_modules/*" -not -path "*/.git/*" 2>/dev/null
   ```
   - 扫目录树定「单元」(该有自己 CLAUDE.md 的 dir):① 仓库根;② 子项目/边界上下文;③ 有独立 package manifest 的模块/子包(`pyproject.toml` / `package.json` / `Cargo.toml` / `go.mod` / `Chart.yaml` / 包根 `__init__.py`)。纯资源/生成物/dotfile 目录不算单元。
   - 报告:现存 N 个 / 缺失候选 M 个 / 各自层级(root / subproject / module-leaf)。

2. **缺失清单确认**(创建用)
   - 缺 CLAUDE.md 的单元 → 创建候选;**已有一律跳过、不重建**(仅在第 3+ 步对其内容对标)。
   - 用 **AskUserQuestion** 确认创建清单;用户可剔除不该建的(避免给边角目录硬塞)。

3. **证据调查**(每个目标文件;文件多时**并行子 agent**,每 agent 一文件;每个证据调查子 agent 派发前先运行 `python3 .claude/hooks/model-routing.py get claudemd.evidence`,按其 stdout 的 `model` / `effort` 显式派发——读文件核验真实路径,取值见 `openspec/model-routing.json`)
   - 现存文件:逐条 claim / section 对照**真实代码/配置**核验,分类 `accurate` / `rotted`(与代码矛盾——引用已删文件、已改机制、过时签名)/ `derivable`(代码/cx 可推导的复述)/ `anchor`(锚点过时或缺 `path:line`)。
   - 新文件:读该单元代码,提炼「读完本单元全部代码仍会(搞错 / 不知如何扩展 / 找不到)」的不可复述知识。
   - ⚠ **反臆造硬规则(第一纪律)**:每条 `path:line`、每个扩展 seam、每个版本/端口/镜像 tag **写前必 `grep`/`read` 验真存在**,**禁编造**。不确定 → 软化为目录/文件指针(不钉易变值)或留空待核。(教训:曾把不存在的 `_DISPATCH`、错的 docker base 当事实写 → 必腐成误导。)

4. **定层级 → 用对规则**(依 `.claude/claudemd-standard.md`)
   - **仓库根 / 子项目级** → §3–§5:头部三件套(标题 + `>` scope 引用块 含路径/↑父/↔兄弟/↓子/ADR + 一句话)+ 固定段目录(核心约束→架构→入口→契约→构建/测试→部署→〈领域段〉→已废弃/禁用→表达约定→Backlog,取所需子集)。
   - **模块 / 叶子级** → §6b 两支柱:**导向**(`## 结构与职责` 组件→一句话职责 + `## 扩展点` 真实 seam:加新的步骤/契约/注册点)+ **防错**(`## 不变量 / 陷阱` 跨文件约束·时序·反直觉,**条条带 `path:line`** + `## 禁用`)。**禁镜像代码**(签名罗列 / 文件清单 / 调用机制复述);**单文件局部陷阱下沉**到出事点代码注释/docstring,CLAUDE.md 至多留指针。

5. **合并现存模式**(富文件知识必保留)
   - 产出 = 把现存内容**清洗到标准**,**不是删成空壳**;所有真实硬知识 / 领域陷阱 / 已知 bug / 历史遗留务必保留(并补锚点)。
   - 删纯 derivable;治理具体代码的事实补 `path:line`;修 rotted;决策 / 破坏性契约 / 急救态 / 废弃态带 `（YYYY-MM-DD）`;遵 §11 排除清单(代码可推导结构 / git 历史 / 瞬时状态 禁入)+ §12 尺寸预算(根≤~140 / 子≤~120 / 叶≤~40 行)。

6. **review**(自查,落盘前)
   - 逐条 litmus:「刚读完本单元全部代码的专家,还会(搞错 / 不知如何扩展 / 找不到)吗?」否 → 删。
   - 每条 `path:line` / seam 用 `git grep` / read **验真存在**;无臆造、无悬空指针、无与代码矛盾。

7. **逐文件确认**(**AskUserQuestion**):`全部接受` / `挑选接受`(边界条目逐条)/ `跳过此文件` / `取消`。monorepo 多文件各自独立确认,**不打包一刀切**。

8. **应用**
   - 用 Write 落盘目标 CLAUDE.md(新建或整文件重写);**保留 install marker 段**(`<!-- intent-driven:begin --> ... <!-- intent-driven:end -->` 原样不动)。
   - 模块级:把单文件陷阱**下沉为出事点代码注释/docstring**(⚠ 这步**动代码**,逐处确认或拆独立提交;CLAUDE.md 同步改为指针)。

9. **报告**
   ```
   ## CLAUDE.md 对标报告
   | 文件 | 层级 | 创建/重写 | 行数(前→后) | 修 rot | 补锚点 | 下沉注释 | 状态 |
   ```
   附:创建清单、跳过项、每个修正的 rotted claim(claim → 证据)、新增 `path:line` 列表。

**Guardrails**

- **反臆造第一**:宁缺毋造;不确定的 path:line/seam/版本/端口/tag → 软化为目录或文件指针(不钉易变值),禁凭记忆写。
- **知识保留**:富的子项目文件是清洗不是清空;领域陷阱 / 已知 bug / 历史遗留是高价值 IRREDUCIBLE,务必留(带锚点)。
- **LCA 放置**:子单元的事实不写进父层;父层已有则子层只留指针、禁重复。
- **不碰无关**:只动 CLAUDE.md(+ 明确同意的下沉注释);不顺手改工作树里别的脏文件,提交时只 stage 本命令相关文件。
- **git**:按仓库纪律(分支 / MR);不代用户 merge;⚠ squash 合并前确认源分支已含全部提交(避免「分支后续 push 漏合」)。
- **何时不跑**:仓库处于活跃重构期(知识快速变动,跑了很快又得重写)→ 等稳态;只想沉淀本轮变更 → 用 `/claudemd-commit`;只想压缩 → 用 `/claudemd-distill`。

**与 `/claudemd-commit`、`/claudemd-distill` 的分工**

| 命令 | 用途 | 时机 | 体量倾向 |
| --- | --- | --- | --- |
| `/claudemd-standardize`(本) | 全量对标:创建缺失 + 全部重生成到标准 | 初次采纳 / 大幅漂移后 | 一次性大动 |
| `/claudemd-commit` | 增量沉淀本轮变更 | 每轮变更结束 / PR 前 | 预算中性（净增 ≤ 0） |
| `/claudemd-distill` | 压缩收敛已沉淀 | 合 main 后 / 累积多轮 | 文件变短 |
