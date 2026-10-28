---
description: 把仓库测试重划分为单元层与集成区域：探针实测 → 起草划分 → 审批页等人类批准 → 搬文件 → 复核，产出 openspec/test-tiers.json
---

把已有测试重划分成**单元层**（纯函数、不碰真实文件 / 子进程 / 网络、每个用例连准备与清理 <3 秒）与按模块划分的**集成区域**，写出仓库级分层文件 `openspec/test-tiers.json`。之后 baseline 只跑单元层（带探针判 G10 / G11）与计划里选中的区域，门禁 G10 / G11 / G12 机械校验分层。命令本身即逻辑，无同名 skill。

分层文件形状：

```json
{
  "unit": {"paths": ["tests/unit/**"], "cmd": "python3 -m pytest -q tests/unit"},
  "regions": {
    "hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"], "cmd": "python3 -m pytest -q tests/integration/hooks"}
  },
  "slow_allow": {"tests/unit/test_a.py::test_big": {"reason": "…", "approved": "<ISO 时间> · <原话摘要>"}}
}
```

路径相对 git toplevel，glob 语义与切片 `owns` 相同；区域名 `[a-z0-9-]+`；不认识的字段由 `slice-gate.py lint` 报错。

---

**Steps**

1. **mini 留痕**：先 `/opsx-mini "重划分测试分层：只搬测试、不改被测代码与断言; 范围: <测试目录>, openspec/test-tiers.json"`。重划分不改任何被测代码，也不改断言。

2. **探针实测**：
   ```bash
   python3 .claude/hooks/test-tiers.py probe --json /tmp/test-tiers-probe.json
   ```
   缺省在 git toplevel 跑 `<当前解释器> -m pytest -q`，需要别的命令时加 `--cmd "<命令>"`。stdout 每个测试文件一行：层级（单元 / 集成 / 混合）、单元与集成用例数、最慢耗时、一条触碰样例；末行是合计与「耗时 ≥ 3 秒且无触碰」的用例数。**记下合计数**，第 6 步复核用。退出 2 = 不可度量，见下文「非 pytest 仓库」。

3. **起草划分稿** `{tiers, moves}`（写到临时文件，如 `/tmp/test-tiers-plan.json`）：
   - `tiers`：拟写入的分层文件内容。区域按模块 / package / library 划分；`covers` 写该区域测试所覆盖的**被测源码 glob**（切片 `owns` 与它相交时 lint 逼计划表态）；`cmd` 只跑该区域的 `paths`。
   - `moves`：`{<源文件或 nodeid>: <目标文件>}`。整文件同层时按文件搬；混合文件按 nodeid 拆，纯函数用例进单元层、有触碰的用例进对应区域。
   - 依据是第 2 步的探针证据与测试的 import / 被测模块，不凭文件名猜。

4. **渲染审批页并停下**：
   ```bash
   python3 .claude/hooks/test-tiers.py render --probe /tmp/test-tiers-probe.json --plan /tmp/test-tiers-plan.json --out openspec/superpower/<YYYY-MM-DD>-test-tiers-plan.html
   ```
   脚本生成单文件 HTML（每个源、目标、目标所属层、探针证据，每层用例数与耗时合计，问题清单，导出按钮）；模型不逐字写 HTML。退出 1 = 有落点不属于恰好一层、或单元层落进了有触碰 / ≥3 秒的用例：stderr 逐条点名，改划分稿重渲。退出 0 后**打印审批页的绝对路径，停下等人类批准**；未获批准不进入第 5 步。

5. **按批准的划分搬文件**：整文件用 `git mv`；混合文件手工拆（保留每个用例的 GWT 注释，不改断言）；写 `openspec/test-tiers.json`（即划分稿里的 `tiers`）。

6. **复核**（全部满足才算完成）：
   ```bash
   python3 .claude/hooks/test-tiers.py check
   python3 .claude/hooks/test-tiers.py probe --json /tmp/test-tiers-probe-after.json
   ```
   - `check` 退出 0：每个测试文件恰好属于一层（退出 1 点名未归层或匹配多层的文件；退出 2 = 分层文件缺失或不合法）；
   - 再 `probe`：用例合计与第 2 步相等；单元层零触碰；单元层没有 ≥3 秒的用例（有则提速，或走下文「放行慢单测」）；
   - `unit.cmd` 与每个区域的 `cmd` 各跑一次，全绿。

7. **收尾提示**：进行中的 change 把 `slices.json` 的 `gate.test` 改成 `unit.cmd`（lint 会报不等）并按需写 `gate.integration` / `gate.integration_skip`，改完重跑 baseline；`/opsx-mini --done` 清除声明；**不代 commit**，由人类提交。

---

## 放行慢单测

单元层用例确需 ≥3 秒（如 fixture 要读大样本）而又不该移入集成区域时：

1. 门禁报 `G10 slow unit test: <nodeid> …` 后飞行停下；
2. 由**人类**在对话里写明「放行 <用例函数名>，理由…」；
3. 模型随即运行：
   ```bash
   python3 .claude/hooks/test-tiers.py allow-slow <nodeid> --reason "<理由>"
   ```
   脚本按 takeoff-gate 的方式定位会话转录，**只认时间最新的一条人类消息**：须同时含该用例的函数名（nodeid 最后一个 `::` 之后、去掉参数化后缀 `[...]`）与放行词（放行 / 允许 / allow / approve）。成立 → 写入 `slow_allow[<nodeid>] = {reason, approved}`，退出 0；不成立或找不到转录 → 退出 3、不改文件。模型不得自己写这句话，也不得直接编辑 `slow_allow`。

放行后该用例超线只给警告（带 `approved`），不再判红。

## 非 pytest 仓库

探针只支持 pytest（`probe` 退出 2 = 不可度量）。此时跳过第 2 步，按测试的 import 与被测模块**静态推断**划分，审批页与划分说明里标「未实测」；第 6 步的 `probe` 复核换成各层命令各跑一次全绿。门禁侧 G10 / G11 降级为一条警告 `G10/G11 不可度量：<原因>`，不判红；G12 照常校验。

## 门禁的分层耗时

配置了分层后，`slice-gate.py` 的 `gate` / `baseline` / `final` 在输出 JSON 里给出 `tier_sec`：

- 形状 `{"unit": 秒, "integration": 秒, "regions": {区域名: 秒}}`，`integration` = `regions` 之和；有未归层用例时另加 `unclassified`（出现即说明有漏网测试文件）；
- 口径：G7 实跑 scenario 测试时按用例文件归层累加每个用例 setup + call + teardown 耗时；baseline / final 里单元层运行（含探针回退重跑与 G10 候选重跑）与每个已选区域 `cmd` 运行计墙钟；lint、typecheck、verify、`gate.checks` 不计；
- 输出位置：`summary` 末尾追加「单元 X.Xs · 集成 Y.Ys」，飞行记录（timeline 备注）在结论词之前插入同样文字；baseline 同时写进 `gate-baseline.json`；
- 未配置分层时没有 `tier_sec`，输出不变。
