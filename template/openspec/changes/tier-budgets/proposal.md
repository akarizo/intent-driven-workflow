## Why

测试账本（change `test-ledger`，C5a）让每次 baseline / final 留下逐用例耗时，但门禁仍然只对单元层的 3 秒线判红，其余一概不管：

- **集成层没有任何上限**。afa 体检（2026-11-18）里集成层占测试耗时的 96–98%，最慢 20 条占 42%，两周内用例数 +41%，没有一条规则会因此变红或警告。
- **放行没有边界**。`slow_allow` 的条目只有理由与人类原话，放行之后可以慢到任意秒数、永远有效，没人会再看它一眼。
- **单元层的线写死在代码里**。3 秒对多数仓库合适，但想收紧到 1 秒的仓库只能改模板。
- **层的总量没人管**。单元层每次门禁都跑，它的总耗时是所有飞行都要付的固定成本，目前只打印不判。

2026-11-18 用户在方案页 `docs/flight-fixes-and-test-governance.html` 第 04 节提出「每一层的用例每一条的执行时间都要有限制和必要的豁免设定」，Q7 选了棘轮（老债只警告，新增的判红）。本 change 是该页 C5 的后半（C5b）：把账本里的数字变成有判定的预算。范围与取舍来自方案页、Q5 / Q7 的已定结论与主会话的拆分指令，没有另开 `grill-me` 访谈。

propose 期用 afa 体检留下的数据量了噪声（`calibration/`），结论改变了方案页的一处设计，见 What Changes 的「与方案页不同」。

## What Changes

- **分层文件声明预算**（`openspec/test-tiers.json`，`slice-gate.py` 校验形状）：
  - 单元层、每个区域（简写形态与部件形态都一样）可选 `budget = {case_sec, total_sec}`，两个字段各自可选。
  - `slow_allow` 的条目新增两个可选字段：`limit_sec`（放行到多少秒）与 `expires`（`YYYY-MM-DD`，到期日当天仍有效）。
  - 没写的一律按现状：单元层单条 3 秒，区域不判，旧放行条目无上限、不过期。
- **单元层单条上限**（G10，仍由探针测、单独重跑确认）：线取 `unit.budget.case_sec`，缺省 3 秒；放行带上限时超过上限判红；放行过期后回到判红；距到期 14 天内在警告里提示。
- **集成层单条上限**（新增 `G13 slow integration test`，按账本判）：
  - 本 change 新增的用例实测超线 → 判红；
  - 基线账本里就有的用例超线 → 只警告（「老债」与「本次量到超线」分开计数）；
  - 没实测的（沿用）、没有耗时的、所在区域没写 `case_sec` 的不判。
- **层总量预算**（新增 `G14 tier budget`，按账本里该层全部用例耗时之和判）：单元层超预算判红（baseline 与 final 都判）；区域超预算只警告，并列出最慢的 3 条与本 change 新增的秒数。
- **争抢下降级**：排队放弃后不加锁跑出来的那一次，G13 / G14 与 G10 一样降为警告（沿用 `DRAFT-machine-wide-test-lock` 第 7 条的口径）。
- **预算与放行的改动要被看见**：final 把分层文件里的预算、放行名单与基线 commit 上的版本逐项比较，有变动就写进警告与 PR 正文的「## 测试变更」。
- **放行命令**（`test-tiers.py allow-slow`）：新增 `--limit-sec` 与 `--expires`；两者都没写时照常放行，但打印一行提示。
- **报告**：
  - 「## 测试变更」多出预算一段：新增超线、老债、各层合计对预算、放行的到期情况、预算变更；
  - `flight-doctor.py doctor` 的 `[tests]` 多出各层预算对实际、放行名单里已过期 / 快到期 / 没有上限的条目。
- **补上部件形态的两处缺口**（C5a 留下、挡着预算判定的）：部件区域的运行结果进账本；单元层合计按部件分开算。
- **修一处挡着层总量的既有缺陷**：有分层文件、只重跑区域的增量 final，会把没重跑的用例（整个单元层）从新锚点的逐用例结局与收口账本里丢掉，对账记成「未重测」。propose 期在一次性副本上复现并验证了修法（design D13）。
- **对账里两个噪声项收窄**（C5a 留给本 change 定的阈值）：「变慢」与「某层耗时上涨」的建议行不再对区域用例计数。
- **全机测试锁的持有上限取全量耗时**：现在取的是上次基线的 `test.sec`，增量基线里它只是补跑的秒数，于是持有上限恒为下限 300 秒；本仓 2026-11-18 一次 512 秒的补跑期间，后到的飞行直接放弃排队、不加锁并跑。改为取最近一次已知的全量耗时，不知道时用缺省 1800 秒。
- **文档**：`flight-runner-contract.md` 新增「时间预算与放行」一节；`commands/test-tiers.md` 与 `README.md` 补分层文件的新字段与放行命令的新参数。

**与方案页不同**（数据见 `calibration/noise-20261118.txt`）：

- **「从线下涨到线上」不判红，只警告**。方案页与 Q7-A 的后半是判红。afa 集成层 7 次全范围门禁运行里，以 60 秒为线，始终超线的用例 11 条，时超时不超的 26 条；同一棵树连跑两次（warm1 / warm2），以 30 秒为线有 3–6 条用例「涨过线」。照此判红，几乎每次 final 都会红在没人动过的用例上。加余量（基线须低于线的 1/2、1/3）也消不掉。
- **层总量按账本里逐用例耗时之和判，不按墙钟判**。增量 final 只重跑一部分文件，墙钟与预算不可比；账本里没重跑的用例沿用上次的耗时，合计才是整层的数。
- **不新增入库的报告文件**：预算结论进现有的 final 输出、时间线之外的警告与「## 测试变更」，不写 `gate-report.md` 的新小节（理由同 `test-ledger` design D4）。

**不做**：

- 体检与整改命令（`test-tiers.py audit`、`/test-audit`）属于 C6；本 change 只保证它要读的数据与函数已经在。
- 不替仓库定预算数字：模板只有单元层 3 秒这一个缺省值，其余都由仓库自己写。
- 不给集成层用例做「单独重跑确认」：区域命令是仓库自己的，库没有办法只跑其中几条。
- 切片门禁（`gate`）不判预算：它不落账。
- 没有分层文件的仓库没有任何变化。

## Capabilities

### New Capabilities
- `tier-budgets`: 分层文件里的时间预算与放行期限、单元层与集成层的单条上限判定、层总量预算、争抢下的降级、预算变更的可见性、放行命令的新参数、体检与「测试变更」里的预算段、部件形态的区域采集、锁持有上限的取值。

### Modified Capabilities

（无。`template/openspec/specs/` 还没有归档过的主规格；`test-tiers`、`test-ledger`、`machine-test-lock` 的行为在没写预算时全部保持原样，本 change 以新增 Requirement 描述写了预算之后的行为。）

## Impact

- **代码**：
  - `template/.claude/hooks/slice-gate.py`：分层文件形状校验、`tier_verdicts` / `part_tier_verdicts` 的线与放行判定、baseline 与 final 的预算判定接入、`_time_verdicts` 的降级范围、`_anchor_forward`、部件区域运行的采集、`_lock_expect_sec`。
  - `template/.claude/hooks/test-ledger.py`：新增预算判定与预算变更比较两个纯函数；`render` 多一段；`delta` / `advice` 收窄两个噪声项。
  - `template/.claude/hooks/test-tiers.py`：`allow-slow` 两个新参数。
  - `template/.claude/hooks/flight-doctor.py`：`[tests]` 多几行。
- **文档**：`template/.claude/flight-runner-contract.md`、`template/.claude/commands/test-tiers.md`、`README.md`。
- **已安装仓库**：升级后不写 `budget`、不给放行加新字段就没有任何行为变化。唯一无条件生效的是锁持有上限的取值（变长，不会变短）与对账里两个建议项的收窄（只影响报告）。
- **在途 change**：`slice-resume-deterministic`（C3）同改 `slice-gate.py`（`start` / `merge` / `record` / 留痕）与 `README.md`，函数与段落不重叠；谁后合入谁预合并。
- **ADR**：新增一份草案 `DRAFT-time-budgets-ratchet-on-ledger`，它修订 `DRAFT-test-tiers-unit-baseline-by-audit-probe` 里「阈值不可配置」这一句（改为「可在分层文件里按层声明，不可经环境变量或计划文件改」），其余条款继续有效。
- **依赖**：只用标准库。判定依赖 `test-ledger.py`；它缺失或出错时 G13 / G14 不判、只留警告，G10 不受影响。
