## Context

**现状**（读 `template/.claude/hooks/` 现行代码，main `780a686`，已含 plan-hygiene、machine-test-lock、ship-rerun-hardening、test-ledger、slice-resume-deterministic、tier-budgets）：

- **划分**：`/test-tiers` 与 `test-tiers.py`（`probe` / `check` / `canary` / `allow-slow` / `render` / `run unit`）负责第一次把测试分成单元层与集成区域，产出 `openspec/test-tiers.json`。`check` 判每个测试文件是否恰属一层（部件形态另判部件归属），只打印文本。
- **测量**：baseline / final 每次落一份账本 `<git common dir>/flight-ledger/<change>/{baseline,final}.json`，每条用例 `{o, s, t, m}`；`test-tiers.py probe --json` 另能给出逐用例的耗时与触碰记录（`{tests: {nodeid: {sec, hits}}}`），运行期间持独占锁。
- **判定**：`slice-gate.py` 的 `tier_budgets` / `budget_scope_of` / `allow_view` 把分层文件摊成预算范围与放行视图；`test-ledger.py` 的 `budget()` 判集成层单条（G13）与层总量（G14）。tier-budgets 的 design D14 把这组函数留作体检的接口。
- **`budget()` 当体检用有三处不够**（读代码确认）：每类明细只返回前 5 条（`TOP_N`）；集成层单条只判本次实测（`m == 1`）；单元层单条它不判（G10 由探针在运行时判）。体检要的是「全部超线用例」，所以需要一个返回全量清单的函数；总量与放行的汇总可以直接用 `budget()`。
- **整改没有任何机制**。`/test-tiers` 的第 6、7 步（搬文件、复核）是它自己的一次性流程，护栏只有文档里的一句「不改被测代码，也不改断言」。

**先例**：`/test-tiers` 用 `/opsx-mini` 留痕 + 审批页 + 人类批准来搬测试文件，没有走 change。它是本设计「命令内执行」轨道的依据。

**在役 ADR（约束本设计）**：

- `DRAFT-test-tiers-unit-baseline-by-audit-probe`：两层、按路径归层、纯度与耗时由探针判、放行要人类原话。体检不新造判据，纯度只认探针记录。
- `DRAFT-time-budgets-ratchet-on-ledger`：预算写在分层文件、放行有边界、集成层棘轮。本设计不改门禁的处置，只在门禁之外多一个「离标准多远」的读数。
- `DRAFT-test-ledger-outside-repo-follows-anchors`：账本在 git common dir、不入库、只报告。体检读它，不写它。
- `DRAFT-machine-wide-test-lock`：跑测试要取锁。体检不跑测试，不取锁；复测用的 `probe` 已经持独占锁。
- `DRAFT-gate-evidence-not-self-reported`：结论由脚本给。整改护栏由脚本对着 git 改动核对。
- `DRAFT-measurements-stay-out-of-plan-files`：测量不进计划文件。体检存档写到调用方指定的路径（建议临时目录或 `openspec/superpower/`），不写计划文件。

**容器图（C4 第二层，ASCII）**：

```
人类 ──/test-audit──▶ 模型（命令文档 test-audit.md）
                        │ ① 体检存档          ② 起草整改稿           ④ 处置            ⑤ 复核
                        ▼                      ▼                      ▼                  ▼
          ┌────────────────────────┐  ┌───────────────────┐  ┌──────────────┐  ┌───────────────────────┐
          │ test-tiers.py audit    │  │ test-audit.py     │  │ git mv / 拆  │  │ test-audit.py verify  │
          │ （只读，零 token）      │  │ render            │  │ 改分层文件    │  │ test-tiers.py probe   │
          └───────────┬────────────┘  │ → 审批页 ③ 停下   │  │ allow-slow   │  │ test-tiers.py audit   │
                      │               └─────────┬─────────┘  │ （人类原话）  │  │   --probe --compare   │
        读            │                         │            └──────────────┘  └───────────────────────┘
   ┌──────────────────┼──────────────────┐      │ 读
   ▼                  ▼                  ▼      ▼
 openspec/        <git common dir>/   探针结果   体检存档（JSON）
 test-tiers.json  flight-ledger/      （可选）   整改稿（JSON）
                  （测试账本）

 判定函数（不新造）：slice-gate.py  tier_budgets · budget_scope_of · allow_view · tiers_matching · gwt_violations
                     test-ledger.py budget()（总量与放行汇总）· violations()（本 change 新增，全量超线清单）
```

## Goals / Non-Goals

**Goals:**

- 合规标准写成文档里的规则表，脚本常量与它一一对应。
- 一条只读命令随时回答「哪些用例、哪些层、哪些放行不合规」，可进 CI。
- 整改有固定流程：稿子先给人批；能机械做的命令内做完并由脚本核对；要判断的交给正式的 change。
- 大仓库能分批：按范围、按类别、按最慢 N 条取子集；复核只看本轮目标。
- 简写形态与部件形态都能体检。

**Non-Goals:**

- 不改任何门禁判定（G10–G14 的处置原样）。
- 不替仓库选去向、不替仓库定预算数字。
- 不跑测试、不新造测量手段。
- 不核对非 Python 测试文件的断言。
- 不做没有分层文件时的建层——那是 `/test-tiers`。

## Decisions

### D1 · 标准是一张规则表，文档与脚本各持一份、由测试对账

八条规则写进运行器契约的新一节「测试套件合规标准」：

| 规则 | 合规判据 | 数据来源 |
|---|---|---|
| R1 | openspec 根有合法的分层文件 | 文件 |
| R2 | 每个测试文件恰属一层（部件形态：恰属一个部件、在该部件内恰落一层） | 测试文件清单 |
| R3 | 单元层用例不碰真实文件、子进程、网络 | 探针记录 |
| R4 | 单元层用例不超线（缺省 3 秒；有效放行按放行上限） | 测量 |
| R5 | 每个集成区域写了单条上限 `budget.case_sec` | 分层文件 |
| R6 | 集成区域用例不超线（有效放行按放行上限） | 测量 |
| R7 | 写了总量预算的范围，合计不超预算 | 测量 |
| R8 | 放行条目有效且有边界：所指文件还在、未过期、有 `limit_sec` 与 `expires` | 分层文件 |

- 类别名、规则号、级别、可选去向在 `test-tiers.py` 里是一个常量 `AUDIT_RULES`；去向与轨道在 `test-audit.py` 里是 `ACTIONS`。一条测试对着文档逐项查（scenario `standard-doc-matches-script-constants`），改一边不改另一边会红。
- **为什么放契约文档**：第 9、10 节（账本、预算）已经在那里，标准是它们的收口；放命令文档里的话，不跑 `/test-audit` 的人（比如只在 CI 里跑体检）看不到判据。
- **R5 是本设计加的**（方案页的原型里区域预算可选）。用户的要求是每一层每一条都有限制；没写上限的区域在门禁里照旧不判，但在体检里点名，去向只有「写预算」。这是需要人类拍板的一处，见 Open Questions。
- **备选**：标准只写在脚本的常量与 `--help` 里——被否：主会话的指令明确要求不让标准只存在于脚本里。

### D2 · 体检只读、不跑测试；测量 = 账本 ∪ 探针结果

- 输入：分层文件、`git ls-files`（已跟踪与未忽略）、一份账本、零到多份探针结果。
- 账本的选取：`--ledger PATH` > `--change-dir` 对应 change 的 `final`（没有则 `baseline`）> 本机 `flight-ledger/` 下 `at` 最新的一份；`--no-ledger` 不读。
- 探针结果覆盖账本里同一用例的耗时，并带来触碰记录。它是「人特意刚量的」，比账本新。
- **为什么不自己跑**：
  - 跑全量集成层在 afa 是一小时量级，体检就不再是「随时可跑」；
  - 取测量的手段已经有两个（飞行落账、`probe`），再造一个要重新处理锁、部件、适配器；
  - 不跑测试的命令可以放心放进 CI 与 hook。
- **代价**：本机没有账本的仓库第一次体检只能判 R1 / R2 / R5 / R8，时间类规则记「未判」，要先跑一次 baseline 或 `probe`。命令文档写明这一步。
- **备选**：`audit --measure` 自己跑各层并落一份体检账本——被否，理由如上；真有需要可以后加，输入口（`--ledger`）已经留好。

### D3 · 按当前工作树重新归层，对不上的如实丢弃

- 账本里记的层是落账那一刻的；体检时分层文件可能已经改了、文件可能已经搬了。所以每条用例按「所在文件 + 当前分层文件」重新归层（`tiers_matching` 取第一个）。
- 用例所在文件：`nodeid` 形式取 `::` 之前；`junit` 形式用 `test-ledger.py` 的 `_file_of`。
  - 文件存在 → 用它归层；
  - 像路径（含 `/` 或带扩展名）但文件不存在 → 丢弃，计入 `source.dropped`；
  - 定不出文件（适配器部件的 `<部件名>::classname::name`）→ 保留账本里记的层。
- 搬过的用例在旧账本里是旧 id：旧 id 被丢弃，新路径没有测量。这正是下面「未判」要抓的情形，也是复核必须重新取测量的原因。
- 原型验证：`audit-recomputes-layer-and-drops-missing-files` 与部件形态的骨架都在一次性副本上跑通。

### D4 · 全量超线清单：`violations()`，线的取法与 `budget()` 共用一处

```
线 = 有效放行（未过期）? 放行的 limit : 范围的 case_sec        （limit 为空 → 该用例不设线；case_sec 为空 → 不判）
超线 = 单元层且按预算线判 ? 耗时 ≥ 线 : 耗时 > 线               （单元层的 ≥ 与 G10 一致）
```

- `violations(ledger, budgets, scope_of, allow)` 对账本里每条有耗时、范围在预算里的用例判一次，实测与沿用都判，不截断。
- `budget()` 里取线的那三行换成调用同一个小函数；返回值与文本不变，`tests/test_budget_core.py` 全绿作守卫。
- 总量与放行汇总仍取自 `budget(like, None, budgets, scope_of, allow, "baseline")` 的 `totals` 与 `allow`，不另算。
- **为什么不改 `budget()` 让它返回全量**：它的返回进 final 输出 JSON 与 PR 正文，明细有上限是 test-ledger design D8 的决定；体检另开一个函数互不牵连。

### D5 · 三个级别，四个退出码

| 级别 | 含义 | 影响结论 |
|---|---|---|
| `violation` | 不合规（十个类别） | 是 → 退出 1 |
| `unjudged` | 判不了：没有测量、来源账本不完整或来自选测、某范围有测试文件没有测量、无耗时的用例超过一成 | 没有不合规时 → 退出 3 |
| `advice` | 提示：放行快到期、放行已不需要、区域里有纯用例、纯度未核对、缺 GWT 的条数 | 否 |

- **为什么要「未判」**：没有账本时，时间类规则一条都判不了；说「合规」是假话，说「不合规」也不对。单列一档，退出码 3，CI 可以自己决定 3 算不算过。
- **某范围「有测试文件没有测量」怎么认**：`check` 认的、恰落一层的测试文件里，没有任何一条用例落在它上面的。范围里有定不出文件的用例时不做这一项（分不清），不误报。
- **未判的范围不出 `total-over`**，已量到的单条超线照常列——少报总量不会冤枉人，漏报单条才会。
- **纯度不算未判**：有分层文件的仓库每次 baseline 都由 G11 判纯度；体检没带探针时只留一条提示「纯度未在体检里核对」，不把退出码推到 3。否则每次不带 `--probe` 的体检都是 3，这个码就没用了。
- **体检比门禁严的两处**：集成层老债（G13 只警告）与区域总量超预算（G14 只警告）在体检里都是不合规。门禁回答「这次变更有没有变坏」，体检回答「离标准多远」。
- **缺 GWT 只计数**：直接调 `slice-gate.py` 的 `gwt_violations`，只取条数。

### D6 · 整改分三条轨道，由去向决定（ADR 草案 `DRAFT-test-remediation-tracks`）

| 去向 | 做什么 | 轨道 | 怎么保证不越界 |
|---|---|---|---|
| `move` | 整文件搬到另一层的目录 | 命令内执行 | `/opsx-mini` 留痕 → 审批页 → 人批 → 执行 → `verify` |
| `split` | 把一条用例原样拆到另一个文件 | 命令内执行 | 同上 |
| `retier` | 改分层文件的 `paths` / 部件归属 | 命令内执行 | 同上 |
| `budget` | 写或调预算 | 命令内执行 | 同上；`verify` 核对放宽是否在稿里 |
| `drop-allow` | 删掉失效的放行条目 | 命令内执行 | 同上；`verify` 核对删除是否在稿里 |
| `allow` | 放行，或给放行补上限与期限 | 交人放行 | 只能人类原话 + `test-tiers.py allow-slow`（现有机制） |
| `speedup` / `purify` / `delete` | 提速、改纯、删用例 | 转 change | 整理成清单交 `/opsx-propose`，走起飞批准、TDD 留痕、独立评审 |
| `keep` | 本轮不处理 | — | 必须写理由 |

- **与铁律 1 的关系**：
  - 命令内执行的五种去向都不改用例的行为：文件换地方、分层文件改几行。它与 `/test-tiers` 是同一性质，先例是 mini 留痕，本设计沿用，并补上先例没有的脚本护栏（D8）。
  - 要改用例实现的三种去向会改变「测试在测什么」，属于中级以上变更。命令不动手，产出一份清单（条目 id、现状、建议方向），由人发 `/opsx-propose`。那个 change 的验收可以直接用体检：`test-tiers.py audit --change-dir <该 change> --compare <清单对应的存档> --plan <清单>` 退出 0。
  - 放行是「人类承担这条慢用例」，模型不能代写，这条规则已有（`test-tiers.md`「放行慢单测」），本设计不动。
- **为什么不全走 change**：搬一个文件也要五工件、起飞、评审，成本与风险不成比例；而且 `/test-tiers` 的第一次划分（搬几百个文件）都没走 change，之后搬一个反而要走，说不通。
- **为什么不全在命令内**：提速要改 fixture、缩样本、换实现，最容易把断言悄悄改弱；这类改动需要评审员看 diff，也需要 TDD 留痕，命令内的护栏给不了。
- **删除为什么不在命令内**：方案页原写「审批页里人类勾了才删」。但勾选发生在浏览器里，脚本验证不了；而删用例是减覆盖。归到转 change 之后，命令内的护栏可以是一条简单的不变式：用例集合不变。
- 这一分法是需要人类拍板的一处，见 Open Questions。

### D7 · 整改稿是一份 JSON，审批页由脚本渲染

```json
{
  "items": {
    "unit-slow:tests/unit/test_dump.py::test_roundtrip": {"action": "move", "dest": "tests/integration/dev/test_dump.py"},
    "region-slow:tests/api/test_export.py::test_big":    {"action": "speedup", "note": "样本从 40MB 缩到 2MB"},
    "allow-unbounded:tests/unit/test_a.py::test_big":    {"action": "allow"},
    "no-case-limit:docs":                                {"action": "budget"}
  },
  "tiers": { "…拟写入的分层文件（有 budget / retier 去向时给出）…" },
  "support": ["tests/conftest.py", "tests/integration/dev/__init__.py"]
}
```

- `render` 校验的都是机械判据：条目是否在体检结果里、去向是否在该条目的 `fix` 里、`keep` 是否写了理由、搬与拆的落点是否恰落一层且方向对（单元层的问题不能搬回单元层）、写预算是否真给了数。
- 轨道由去向查 `ACTIONS` 得到，模型不自己分。
- 审批页沿用 `test-tiers.py render` 的形态（单文件、内联样式、批注框、导出 Markdown / 复制），每条多一个勾选框；导出的文本里带每条的勾选结果，人贴回对话即批准意见。
- 稿可以只覆盖一部分不合规项。没排进稿的在页面上数成「未安排 N 条」，不算问题——分批整改是常态。
- `support`：搬测试往往要跟着搬 `conftest.py`、`__init__.py`、测试数据。这些不是测试文件，护栏默认会判「稿外的改动」；写进 `support` 后放行，并且显示在审批页上给人看。

### D8 · 护栏：四条都对着 git 改动核对

1. **改动范围**（`git diff --name-only --no-renames <base>` 加未跟踪文件）：
   - 测试文件（内置命名）、分层文件、openspec 根之下的文件 → 允许；
   - 命中任一区域 `covers`（基线与当前两版分层文件都算）→ 「改了被测代码」，`support` 不能豁免；
   - 命中 `support` → 允许并列出；
   - 其余 →「稿外的改动」。
2. **用例与断言不变**（改动的 Python 测试文件，`ast`）：
   - 每个测试函数的签名 = `类名.函数名` + 参数化装饰器 + 断言集合；
   - 断言 = `assert` 语句、名字以 `assert` 开头的调用（`unittest` 风格）、`pytest.raises` / `pytest.warns`；
   - 基线一侧与当前一侧各收一个多重集比较：按名字计，跨文件移动不算改动；
   - 消失、新增、断言有改动、参数化有改动，各自点名。
3. **分层文件的改动与稿一致**：放行新增或改动 ↔ 稿里键为该用例的 `allow` 条目；放行删除 ↔ `drop-allow`；预算放宽（含取消）↔ 键为该范围的 `budget` 条目。变动的文本直接取 `test-ledger.py` 的 `budget_changes`，与 PR 正文「测试变更」里的预算变更是同一套措辞。
4. **核对不了的列出来**：非 Python 的测试文件、解析失败的 Python 文件进 `unchecked`，不判失败，文本里写明「未核对」，由人看 diff。

- 方案页的第四条护栏「每条整改后在独占锁下复测：绿，且达标」不在 `verify` 里，由复核步骤承担：对受影响的层跑 `test-tiers.py probe --json`（它持独占锁，失败会非 0），再 `test-tiers.py audit --probe … --compare … --plan …`。
- **为什么用函数名而不是文件名对齐**：整改的主要动作就是换文件；按文件比，每次搬动都是「全删全增」。
- **代价**：同名函数在不同文件里各有一条时，按多重集比仍然成立，但报错时只能说名字，说不出是哪个文件的那一条。
- **备选**：用 pytest `--collect-only` 比前后用例 id——被否：要跑两遍收集（基线一侧还得检出），而且搬文件之后 id 本来就全变了。

### D9 · 前后对比按条目 id，分批整改不被老债挡住

- 条目 id = `<类别>:<键>`，键是用例 id、文件路径、范围名或放行的键，跨两次体检稳定。
- `--compare` 只比不合规项：已解决 / 仍在 / 新增。
- `--plan` 把稿里去向不是 `keep` 的条目当本轮目标。退出码：有新增或目标未解决 → 1；否则有未判项 → 3；否则 0。
- **没排进本轮的老债仍在，不算失败**。否则 afa 这样的仓库永远过不了复核。
- **搬过的用例**：旧 id 消失（已解决）；如果到了新地方仍然超线，会以新 id 出现（新增）→ 退出 1。这是对的：整改把问题换了个地方。
- **有未判项时不说达标**：目标「不在不合规项里」可能只是因为搬过去之后没量。退出 3，文本写「未能确认」。

### D10 · 没有分层文件的仓库

- 体检只报一条 `no-tiers`，文本指向 `/test-tiers`，退出 1。不再往下判——没有层就没有标准（方案页「未分层：只报告」）。
- `/test-tiers` 的文档加一行：建层之后的例行体检与整改走 `/test-audit`。两条命令的分工：`/test-tiers` 从无到有，`/test-audit` 从有到合规。
- afa 现状（没有模板的分层文件，用自带的登记表）：体检会一直是 `no-tiers`，直到它迁到模板的分层文件。这是 afa 自己在体检报告第五节里列为待定的事，本 change 不替它决定。

### D11 · 两个脚本文件，体检挂在 `test-tiers.py`

- `test-tiers.py audit`：与 `check` 同文件，直接复用 `load_tiers` / `check_parts` / `read_json`；`check` 的判据抽成一个返回结构化结果的函数，`check` 与 `audit` 共用，`check` 的输出与退出码不变。
- `test-audit.py`（新）：`render` 与 `verify`。按路径加载 `slice-gate.py` 与 `test-ledger.py`，写法同 `test-tiers.py`。
- **为什么拆两个**：`test-tiers.py` 管划分与体检（都是「读分层文件下结论」）；整改稿与护栏是另一件事（读 git 改动、渲染页面）。拆开之后两条切片链可以并行。
- **备选**：全放 `test-tiers.py`——文件会到一千行以上，四条切片只能排成一串，超过 DAG 深度上限 3。

## Risks / Trade-offs

- [体检读的是「最近一次」测量，可能来自别的分支的 change] → 输出第二行写明来源（change、阶段、commit、时间、模式）；对不上的用例被丢弃并计数，没测量的文件进「未判」。要准就带 `--change-dir` 或先 `probe`。
- [单元层超线只凭一次测量，没有 G10 那样的重跑确认] → 体检是报告，不判红任何飞行；tier-budgets 的校准数据里单元层 9710 条只有 3 条时超时不超。整改前的复测（`probe`）会再量一次。
- [`junit` 形式的账本从 `classname` 反推文件是有损的] → 推不出的用例保留账本里记的层，所在范围不做「文件没有测量」的判断，不误报。
- [护栏的断言比较只懂 Python] → 其他语言列进「未核对」。部件形态的仓库（Go、JVM）搬测试时这一条要靠人看 diff，命令文档写明。
- [`support` 可以被用来放行任意文件] → 它显示在审批页上、由人批；被测代码（`covers`）无论如何不能进。没有写 `covers` 的仓库这道硬线不存在，只剩「稿外的改动」这一层。
- [审批页上的勾选不被脚本验证] → 与 `/test-tiers` 的审批页同样是软约束；硬约束在 `verify`（改了什么）与 `allow-slow`（谁放行的）。
- [R5 让所有没写上限的区域一夜之间「不合规」] → 只影响体检的读数，不影响任何门禁；去向明确（写预算），体检同时打印该区域的 p50 / p95 / 最慢供人定数。
- [与在飞的 `wave-integration-guard`（C4）同改 `flight-runner-contract.md` 与 `README.md`] → 两边都在契约文档末尾加一节，后合入的预合并时保留两节、顺延节号；本 change 的测试按标题「测试套件合规标准」找这一节。README 本 change 改两处计数与命令表，C4 改的是飞行机制的条目，不重叠。C4 改的 `slice-gate.py`、`flight-doctor.py`、`spec_html.py`、工作流与 agent 定义本 change 都不碰。
- [命令计数被两个旧测试钉住] → `tests/test_tiers_docs.py`、`tests/test_clean_after_merged_docs.py` 并入文档切片 S7 的 owns。

## Migration Plan

- 随 `install.sh --upgrade` 分发：`test-audit.py` 与 `commands/test-audit.md` 是新文件，其余是既有文件的增量改动。
- 升级后门禁行为不变。第一次用：
  1. 有分层文件、有在途 change 的仓库：直接 `python3 .claude/hooks/test-tiers.py audit`；
  2. 有分层文件、没有账本：先 `python3 .claude/hooks/test-tiers.py probe --cmd "<单元层命令>" --json <文件>`，再带 `--probe` 体检；
  3. 没有分层文件：体检提示先跑 `/test-tiers`。
- 回退：删掉 `test-audit.py`、`commands/test-audit.md` 与契约文档那一节即可；`violations()` 与 `audit` 子命令没有调用方依赖。

## Open Questions

需要人类在审批时拍板的：

1. **整改走哪条路**（D6）：按去向分三条轨道（推荐）；备选 A 一律命令内执行 + mini 留痕；备选 B 一律转 change。
2. **R5 进不进标准**（D1）：没写单条上限的区域记不合规（推荐，对应「每一层每一条都有限制」）；备选是降为提示。
3. **集成层老债与区域总量超预算在体检里算不合规**（D5）：推荐算；备选是与门禁一致、只列为提示。算的话 afa 这类仓库的体检在很长时间里都是「不合规」，靠 `--compare --plan` 分批收。
4. **「未判」单列退出码 3**（D5）：推荐单列；备选是并进 1（保守）或并进 0（宽松）。
5. **删除用例不在命令内做**（D6）：推荐一律转 change；备选是按方案页原样，审批页勾选后命令内删。
6. **命令名与文件名**：`/test-audit`、`test-tiers.py audit`、`test-audit.py`（推荐，与 `/test-tiers` ↔ `test-tiers.py` 对称）。

留给后续的：

- 体检进门禁：C4 合入后，仓库可以在 `gate-checks.json` 里把 `test-tiers.py audit --change-dir …` 声明成带 `slice` 或 `final` 的检查。本 change 不替仓库做这个选择。
- `flight-doctor.py doctor` 的 `[tests]` 加一行体检结论：等 C4 合入后再动这个文件。
- 非 Python 测试文件的断言核对：需要逐语言的解析，按需再做。
