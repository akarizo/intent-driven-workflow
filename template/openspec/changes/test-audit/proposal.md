## Why

`test-ledger`（C5a）让每次门禁留下逐用例耗时，`tier-budgets`（C5b）给每层立了线与放行期限。但这些只在飞行经过时才判，而且只判「这次变更有没有让它更坏」：

- **存量没人问**。集成层的老债在门禁里只警告，放行到期前没人看，区域没写上限就一直不设线。标准立了，没有一条命令能回答「现在整个套件离标准差多少」。
- **体检是一次性的手工活**。2026-11-18 那次 afa 测试体检用了 15 个临时脚本，数字对了一轮才出报告，下一次还得重来。
- **「改到合规」没有路**。`/test-tiers` 只管第一次划分。之后发现单元层混进了慢用例、区域里有该下沉的纯用例、放行过期，怎么改、谁能改、改完怎么证明没改坏，都没有约定。

2026-11-18 用户在方案页 `docs/flight-fixes-and-test-governance.html` 第 04 节末尾（C6）提出：「提供一个命令能够自检当前不合规的用例然后变成我们要求的标准设计」。本 change 是该页最后一项，范围与取舍来自方案页与主会话的拆分指令，没有另开 `grill-me` 访谈；与方案页不一样的地方、需要人类拍板的地方都列在下面与 design 的 Open Questions。

## What Changes

- **标准有明文**：运行器契约新增一节「测试套件合规标准」——八条规则 R1–R8，每条的判据、数据来源、不合规时的类别名与可选去向。体检按它判，整改以它为目标。
- **体检**（`test-tiers.py audit`，零 token，只读）：
  - 读分层文件、测试文件清单与一份测量（本机最新的测试账本，可叠加 `test-tiers.py probe --json` 的结果），**不跑测试**；
  - 列出十类不合规项：没有分层文件、归层有问题、单元层不纯、单元层超线、区域没写单条上限、集成区域超线、层总量超预算、放行指向的文件已不存在、放行已过期、放行缺上限或期限；
  - 另列五类提示（不影响结论）与「未判」（没有测量、测量不全的范围）；
  - 文本或 JSON 输出；可按范围、按类别、按最慢 N 条取子集；`--out` 存档；
  - 退出码：0 合规，1 有不合规项，3 没有不合规项但有判不了的范围，2 输入不可用。
- **前后对比**（`test-tiers.py audit --compare <之前的存档> [--plan <整改稿>]`）：已解决 / 仍在 / 新增；整改稿里排进本轮的目标没解决或出现新增即失败。
- **整改稿审批页**（`test-audit.py render`）：模型逐条提去向，脚本校验（去向是否适用、落点是否恰落一层、是否仍在原层）并按去向归到三条轨道，写出带勾选框与导出按钮的单文件 HTML，停下等人类批准。
- **整改护栏**（`test-audit.py verify`）：命令内的整改做完后，脚本对着 git 改动核对四条——没动被测代码与稿外文件、用例与断言没变（Python 测试文件按语法树比）、分层文件里预算与放行的改动都在稿里、核对不了的文件如实列出。
- **命令 `/test-audit`**（命令本身即逻辑，无同名 skill）：体检存档 → 起草整改稿 → 渲染审批页并停下 → 按轨道处置 → 复核。slash 命令数从 17 变 18。
- **整改分三条轨道**（design D6、ADR 草案 `DRAFT-test-remediation-tracks`）：
  - **命令内执行**：只搬、只拆、只改分层文件、只删失效放行。沿用 `/test-tiers` 的做法——`/opsx-mini` 留痕、审批页、人类批准，再加护栏脚本；
  - **交人放行**：放行与补上限、期限只能由人类原话经 `test-tiers.py allow-slow` 写入，命令不代写；
  - **转 change**：要改用例实现的（提速、改纯、删用例）不在命令内动手，整理成清单交 `/opsx-propose` 另立 change，走起飞批准与独立评审。
- **`test-ledger.py` 新增纯函数 `violations()`**：返回账本里全部超线用例。`budget()` 只给门禁要的那几条明细（每类至多 5 条、只判本次实测、不判单元层单条），体检要的是全量；线的取法抽成一处，两个函数共用，`budget()` 的结论与文本不变。

**与方案页不同**：

- **体检不止挂在 `test-tiers.py` 上**。体检子命令 `audit` 仍在 `test-tiers.py`（方案页如此）；整改稿渲染与护栏放进新文件 `test-audit.py`。理由：`test-tiers.py` 管划分，已 505 行；两个文件的切片可以并行。
- **体检不跑测试，也不做「每条整改后独占锁下复测」这一步的调度**。复测用现成的 `test-tiers.py probe`（它本来就持独占锁），结果经 `--probe` 喂回体检，由 `--compare --plan` 判目标是否解决。
- **「每个集成区域都要写单条上限」进了标准（R5）**。方案页的分层文件原型里区域预算是可选的；但用户的要求是「每一层的用例每一条的执行时间都进行限制」，没写上限的区域在体检里记不合规，去向是写预算。门禁行为不变（没写仍然不判）。
- **集成层老债与区域总量超预算在体检里是不合规**，在门禁里仍只警告。体检问的是「离标准多远」，门禁问的是「这次变更有没有变坏」。
- **删除用例不在命令内做**。方案页写的是「审批页里人类勾了删除才能删」；改为一律转 change，命令内的护栏因此可以简单地要求「用例集合不变」。
- **多出「未判」一档与退出码 3**。方案页只有「有违规退出 1」；没有测量时说「合规」是假话。

**不做**：

- 不替仓库决定用例该删、该拆还是该提速：体检只列可选去向，选哪个由整改稿与人定。
- 不给预算定数：体检打印每个范围的 p50 / p95 / 最慢，数字由仓库自己写。
- 缺 Given / When / Then 注释只计数，不进整改（方案页的假设）。
- 不把体检接进门禁：C4 合入后可以把它声明成带 `slice` 的检查，那是仓库自己的选择，本 change 不依赖 C4。
- 非 Python 测试文件的断言与用例数不核对，只列进「未核对」交人。
- `flight-doctor.py doctor` 不加提示行（C4 正在改同一文件）。

## Capabilities

### New Capabilities
- `test-audit`: 测试套件合规标准的明文、只读体检及其前后对比、整改稿审批页、整改护栏、`/test-audit` 命令。

### Modified Capabilities

（无。`template/openspec/specs/` 还没有归档过的主规格；`test-tiers`、`test-ledger`、`tier-budgets` 的既有行为全部保持原样，本 change 只新增。）

## Impact

- **代码**：
  - `template/.claude/hooks/test-ledger.py`：新增 `violations()`，线的取法抽成共用的一小段；
  - `template/.claude/hooks/test-tiers.py`：新增子命令 `audit` 与模块常量 `AUDIT_RULES`；`check` 的判据抽成可复用的函数，输出不变；
  - `template/.claude/hooks/test-audit.py`：新文件，`render` 与 `verify`。
- **文档**：`template/.claude/flight-runner-contract.md`（新增一节）、`template/.claude/commands/test-tiers.md`（一行指针）、`template/.claude/commands/test-audit.md`（新命令）、`README.md` 与 `install.sh`（命令计数 17 → 18 与清单）。
- **钉计数的旧测试**：`tests/test_tiers_docs.py`、`tests/test_clean_after_merged_docs.py` 钉着「17 个 slash 命令 / command」，并入文档切片的 owns。
- **已安装仓库**：升级后门禁行为没有任何变化；多出一个子命令、一个脚本、一条 slash 命令。旧版 hooks 没有 `audit`，命令文档须与 hooks 一起升级（`install.sh --upgrade` 本来就一起刷新）。
- **在途 change**：`wave-integration-guard`（C4，收口中）同改 `flight-runner-contract.md` 与 `README.md`。两边都在契约文档末尾加一节，后合入的一方预合并时保留两节并顺延节号；本 change 的测试按标题找这一节，不按节号。C4 改的其余文件本 change 都没碰。
- **ADR**：新增两份草案 `DRAFT-test-suite-standard-audited-outside-gates`、`DRAFT-test-remediation-tracks`。不修订任何在役 ADR。
- **依赖**：只用标准库。
