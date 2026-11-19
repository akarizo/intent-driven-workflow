---
description: 体检测试套件离合规标准多远，并把不合规项改到合规：体检 → 整改稿 → 审批页等人类批准 → 按轨道处置 → 复核
---

把已有分层文件（`openspec/test-tiers.json`）的仓库从「有分层」带到「合规」：先只读体检，列出每条不合规项及可选去向，再按经人类批准的整改稿处置。本命令不建层——没有分层文件时先跑 `/test-tiers`。合规的判据、类别、规则号、去向与退出码都以契约文档 `.claude/flight-runner-contract.md` 的「测试套件合规标准」一节为准。命令本身即逻辑，无同名 skill。

整改稿（JSON）形状：

```json
{
  "items": {
    "unit-slow:tests/unit/test_a.py::test_big": {"action": "move", "dest": "tests/integration/hooks/test_a_big.py"},
    "layering:tests/test_misc.py": {"action": "retier"},
    "no-case-limit:hooks": {"action": "budget"},
    "region-slow:tests/integration/hooks/test_b.py::test_load": {"action": "speedup"},
    "pure-in-region:tests/integration/hooks/test_c.py": {"action": "keep", "note": "依赖临时目录夹具，下轮随夹具一起改"}
  },
  "tiers": {"unit": {"paths": ["tests/unit/**"], "cmd": "python3 -m pytest -q tests/unit"}, "regions": {}},
  "support": ["tests/integration/hooks/conftest.py", "tests/integration/hooks/data/**"]
}
```

- `items` 的键是体检条目 id（`<类别>:<键>`）；`action` 取该条 `fix` 里的一个去向或 `keep`；`move` / `split` 必写 `dest`；`keep` 必写 `note`（理由）；
- `tiers`（可选）：要改分层文件时给出拟写入的完整内容；`support`（可选）：随迁的非测试文件 glob（`conftest.py`、`__init__.py`、测试数据）。

---

**Steps**

1. **体检并存档**：`python3 .claude/hooks/test-tiers.py audit --out <存档路径>`（只读、不跑测试；`--out` 写体检 JSON，供第 3 步与第 5 步对比用）。
   - 退出码：`0` 合规（汇报后结束）· `1` 有不合规项 · `2` 输入不可用（分层文件不合法、账本 / 探针 / change 目录读不了，按 stderr 修好重跑）· `3` 没有不合规项但有未判项；
   - 出现 `no-tiers`（没有分层文件）→ **停下**，让人先跑 `/test-tiers`；
   - 有「未判」→ 先取测量：任一在途 change 跑过 baseline 即有测试账本；或 `python3 .claude/hooks/test-tiers.py probe --cmd "<该层命令>" --json <文件>`，再带 `--probe <文件>` 重新体检；
   - 大仓库用 `--scope <范围>` / `--category <类别>` 取一批，本轮只处理这一批；存档那次不带 `--top`（存档只写截断后的明细，第 5 步会把批内被截掉的旧项算成新增）。`--top N` 只用于另跑一次只看不存的体检；也可以不筛选地存全量档，分批只体现在整改稿的 `items` 里。

2. **起草整改稿**（形状见上）：每条不合规项从它的 `fix` 里选一个去向，或 `keep` 并写理由；搬与拆写 `dest`；要改分层文件时给出 `tiers`；随迁的非测试文件写进 `support`。依据是体检条目、探针证据（触碰记录、耗时）与被测模块本身，**不凭文件名猜**。

3. **渲染审批页并停下**：`python3 .claude/hooks/test-audit.py render --audit <存档> --plan <整改稿> --out openspec/superpower/<YYYY-MM-DD>-test-audit-plan.html`。
   - 退出 `1` → 按 stderr 逐条改稿，重渲；退出 `2` → 输入读不了，修好重跑；
   - 退出 `0` → 打印审批页的绝对路径，**停下等人类批准**；未获批准不进入下一步。

4. **按轨道处置**：
   - **命令内执行**（`move` / `split` / `retier` / `budget` / `drop-allow`）：先 `/opsx-mini "测试整改：只搬 / 拆测试与改分层文件，不改被测代码与断言; 范围: <测试目录>, openspec/test-tiers.json"`；记下此刻的 `git rev-parse HEAD` 作基线；整文件用 `git mv`，拆用例时原样剪切、保留 Given / When / Then 注释，**不改断言**；分层文件按稿里的 `tiers` 写入。
   - **交人放行**（`allow`）：不代写；请人类在对话里写明放行哪个用例及理由，再运行 `python3 .claude/hooks/test-tiers.py allow-slow <nodeid> --reason "<人类原话摘要>" --limit-sec <秒> --expires <YYYY-MM-DD>`（判据见 `test-tiers.md`「放行慢单测」）。
   - **转 change**（`speedup` / `purify` / `delete`）：不在本命令里动手；把这些条目（id、现状、建议方向）整理成清单交给人，由人发 `/opsx-propose`；那个 change 的验收可以直接用第 5 步的对比命令。

5. **复核**（全部满足才算完成）：
   - `python3 .claude/hooks/test-audit.py verify --plan <整改稿> --base <第 4 步记下的 commit>` 退出 `0`；输出里「未核对」的文件逐个请人看 diff；
   - `python3 .claude/hooks/test-tiers.py check` 退出 `0`；
   - 对动过的层重新取测量：`python3 .claude/hooks/test-tiers.py probe --cmd "<该层命令>" --json <文件>`（它持全机测试锁；部件形态带 `--root` / `--adapter`）；
   - `python3 .claude/hooks/test-tiers.py audit --probe <文件> --compare <第 1 步的存档> --plan <整改稿>`（第 1 步筛选过的，必须带上与第 1 步相同的 `--scope` / `--category`，否则批外的旧不合规项都会被算成新增）：退出 `0` = 本轮目标都已解决且没有新增；`1` = 有目标没解决或改出了新的不合规；`3` = 未能确认（还有没量到的范围）。

6. **收尾**：`/opsx-mini --done` 清除声明；汇报已解决 / 仍在 / 转 change 的条数与清单；**不代 commit**，由人类提交。

---

## 三条轨道

| 去向 | 轨道 | 谁来做 |
| --- | --- | --- |
| `move` / `split` / `retier` / `budget` / `drop-allow` | 命令内执行 | 本命令（mini 留痕，`test-audit.py verify` 核对） |
| `allow` | 交人放行 | 人类在对话里给出原话，本命令只运行 `test-tiers.py allow-slow` |
| `speedup` / `purify` / `delete` | 转 change | 人类发 `/opsx-propose`，走完整飞行 |
| `keep` | 本轮不处理 | 整改稿写理由，审批页展示 |

## 不做的事

- 不改被测代码；
- 不改断言（搬与拆都原样剪切，`verify` 按用例集合与断言核对）；
- 不删用例（删除走转 change）；
- 不代写放行（`allow` 只凭人类原话）；
- 不代 commit。
