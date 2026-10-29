---
description: 把仓库测试重划分为单元层与集成区域（多语言 monorepo 按部件划分）：发现部件 → 探针实测 → 起草划分 → 审批页等人类批准 → 搬文件 → 复核，产出 openspec/test-tiers.json
---

把已有测试重划分成**单元层**（纯函数、不碰真实文件 / 子进程 / 网络、每个用例连准备与清理 <3 秒）与按模块划分的**集成区域**，写出仓库级分层文件 `openspec/test-tiers.json`。之后 baseline 只跑单元层（带探针判 G10 / G11）与计划里选中的区域，门禁 G10 / G11 / G12 机械校验分层。命令本身即逻辑，无同名 skill。

分层文件有两种形态：顶层有 `parts` 是**部件形态**，否则是**简写形态**。

**简写形态**（单一 runner 的仓库）：

```json
{
  "unit": {"paths": ["tests/unit/**"], "cmd": "python3 -m pytest -q tests/unit"},
  "regions": {
    "hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"], "cmd": "python3 -m pytest -q tests/integration/hooks"}
  },
  "slow_allow": {"tests/unit/test_a.py::test_big": {"reason": "…", "approved": "<ISO 时间> · <原话摘要>"}}
}
```

**部件形态**（多语言 monorepo：每个子项目 × runner 是一个部件，各有单元层与区域）：

```json
{
  "parts": {
    "api-go": {
      "root": "services/api",
      "unit": {
        "list": "python3 tools/list_unit.py",
        "cmd": "gotestsum --junitfile \"$FLIGHT_JUNIT\" -- ./...",
        "probe": {
          "cmd": "python3 tools/go_probe.py",
          "canary": "go test ./canary/...",
          "canary_files": ["services/api/canary/**"],
          "sha": {"services/api/tools/go_probe.py": "<sha256>"},
          "checked": "<ISO 时间>"
        }
      },
      "regions": {
        "api-db": {"paths": ["services/api/db/**/*_test.go"], "covers": ["services/api/db/**"], "cmd": "go test ./db/... -tags=db"}
      }
    },
    "ml-py": {
      "root": "services/ml",
      "test_files": ["services/ml/tests/**/test_*.py"],
      "unit": {"paths": ["services/ml/tests/unit/**"], "cmd": "python3 -m pytest -q tests/unit"}
    },
    "billing-jvm": {
      "root": "services/billing",
      "unit": {"paths": ["services/billing/src/test/**/*Test.java"], "cmd": "mvn -q test", "junit": "target/surefire-reports/*.xml"}
    }
  },
  "slow_allow": {}
}
```

- 顶层只含 `parts` 与 `slow_allow`；`parts` 与 `unit` / `regions` 不得同时出现。部件名与区域名 `[a-z0-9-]+`，区域名全仓唯一。
- 部件字段：`root`（子项目目录，相对 git toplevel，`.` 表示顶层，不含 `..`）· `test_files`（可选，该部件测试文件的 glob；缺省为 `root` 下匹配内置命名的文件）· `unit` · `regions`（可选）。
- 单元层与每个区域恰写一个选择器：`paths`（glob 数组）或 `list`（在 `root` 下运行的命令，stdout 每行一个相对 `root` 的测试文件路径，60 秒超时；用于 Rust 内联单测、Go 同目录按 build tag 分层这类路径表达不了的布局）。区域另写 `covers` 与 `cmd`。
- 单元层另可写 `junit`（相对 `root` 的报告 glob，见下文「JUnit 契约」）与 `probe`（探针适配器，见下文「探针适配器契约」）。
- 所有命令（`unit.cmd`、区域 `cmd`、`list`、`probe.cmd`、`probe.canary`）都在部件 `root` 下运行。
- **两种形态的区别**：简写形态的字段、校验与门禁行为不变，`root` / `test_files` / `list` / `junit` / `probe` 写进简写形态按未知字段报错；新字段只在部件形态可用。部件形态下 final 恒全量（不走增量 final、不写锚点），`gate.test` 必须等于驱动命令 `python3 .claude/hooks/test-tiers.py run unit`、不得写 `gate.impacted`。

路径相对 git toplevel，glob 语义与切片 `owns` 相同；区域名 `[a-z0-9-]+`；不认识的字段由 `slice-gate.py lint` 报错。部件形态下 `list` 输出、适配器记录的用例 id、junit 的 `file` 属性相对 `root`，由库补上 `root` 前缀，门禁文本与 `slow_allow` 键一律相对顶层。

**内置命名**（部件形态下没写 `test_files` 的部件按它认测试文件）：`test_*.py` / `*_test.py` / `*.test.*` / `*.spec.*`，另加 Go `*_test.go`、JVM `*Test.java` / `*Tests.java` / `*IT.java`（`.kt` 同）、C# `*Tests.cs` / `*Test.cs`、Ruby `*_spec.rb` / `test_*.rb` / `*_test.rb`、Rust 部件 `root` 下 `tests/` 里的 `*.rs`。全仓测试文件（匹配内置命名或任一部件 `test_files`，减去金丝雀文件）须恰属一个部件、在该部件内恰落一层。

---

**Steps**

1. **mini 留痕**：先 `/opsx-mini "重划分测试分层：只搬测试、不改被测代码与断言; 范围: <测试目录>, openspec/test-tiers.json"`。重划分不改任何被测代码，也不改断言。

2. **发现部件**：扫描 manifest 与 workspace 文件——`go.mod` / `go.work`、`package.json` / pnpm workspace（`pnpm-workspace.yaml`）、`pyproject.toml`、`Cargo.toml` workspace、`pom.xml` / `build.gradle` 等——列出候选部件（子项目 × runner）：每个候选写 `root`、runner、测试命令、测试文件命名。只有一个 pytest 子项目时用简写形态，跳过第 3 步里的适配器与金丝雀。

3. **逐部件调研并实测**（每个候选部件都做）：
   - **切法**：单元层与区域用 `paths` 还是 `list`；
   - **junit 怎么出**：runner 能把报告写到指定路径 → 单元命令读 `$FLIGHT_JUNIT`；只能写固定位置（如 surefire）→ 写 `unit.junit`；
   - **纯度怎么测**：pytest 部件不写 `probe`，走内置探针；其他语言写**探针适配器**（契约见下文：执行 `FLIGHT_UNIT_CMD`，往 `FLIGHT_TIER_OUT` 写 JSONL）+ **金丝雀用例**（四个命名、读 `FLIGHT_CANARY_TOKEN` / `FLIGHT_CANARY_DIR`、无令牌时跳过）；
   - 写好后先用独立模式验证适配器（不读写分层文件）：
     ```bash
     python3 .claude/hooks/test-tiers.py canary --root <部件 root> --adapter "<适配器命令>" --canary "<金丝雀命令>"
     ```
     退出 0 才算适配器可用；退出 1 时 stdout 逐条点名未满足的条件，改适配器重跑。

4. **探针实测**（逐部件）：
   ```bash
   python3 .claude/hooks/test-tiers.py probe --json /tmp/test-tiers-probe.json
   python3 .claude/hooks/test-tiers.py probe --root <部件 root> --cmd "<单元命令>" [--adapter "<适配器命令>"] --json /tmp/test-tiers-probe-<部件>.json
   ```
   缺省在 git toplevel 跑 `<当前解释器> -m pytest -q`，需要别的命令时加 `--cmd "<命令>"`；`--root` 在该目录下运行，`--adapter` 按适配器契约运行，输出与 JSON 里的路径都相对顶层。stdout 每个测试文件一行：层级（单元 / 集成 / 混合）、单元与集成用例数、最慢耗时、一条触碰样例；末行是合计与「耗时 ≥ 3 秒且无触碰」的用例数。**记下每个部件的合计数**，第 7 步复核用。退出 2 = 不可度量，见下文「非 pytest 仓库」。

5. **起草划分稿并渲染审批页，停下**：
   - 划分稿 `{tiers, moves}`（写到临时文件，如 `/tmp/test-tiers-plan.json`）：
     - `tiers`：拟写入的分层文件内容。区域按模块 / package / library 划分；`covers` 写该区域测试所覆盖的**被测源码 glob**（切片 `owns` 与它相交时 lint 逼计划表态）；`cmd` 只跑该区域的测试。
     - `moves`：`{<源文件或 nodeid>: <目标文件>}`。整文件同层时按文件搬；混合文件按 nodeid 拆，纯函数用例进单元层、有触碰的用例进对应区域。
     - 依据是第 4 步的探针证据与测试的 import / 被测模块，不凭文件名猜。
   - 渲染：
     ```bash
     python3 .claude/hooks/test-tiers.py render --probe /tmp/test-tiers-probe.json --plan /tmp/test-tiers-plan.json --out openspec/superpower/<YYYY-MM-DD>-test-tiers-plan.html
     ```
     脚本生成单文件 HTML（每个源、目标、目标所属层、探针证据，每层用例数与耗时合计，问题清单，导出按钮）；模型不逐字写 HTML。退出 1 = 有落点不属于恰好一层、或单元层落进了有触碰 / ≥3 秒的用例：stderr 逐条点名，改划分稿重渲。
   - 审批页与划分说明列出**「未覆盖」清单**：仓库里既不命中内置命名、也没被任何部件 `test_files` 收进来的语言 / 测试目录（门禁认不出它们，G12 也管不到）。
   - 退出 0 后**打印审批页的绝对路径，停下等人类批准**（含「未覆盖」清单的去留）；未获批准不进入第 6 步。

6. **按批准的划分搬文件并自检适配器**：整文件用 `git mv`；混合文件手工拆（保留每个用例的 GWT 注释，不改断言）；写 `openspec/test-tiers.json`（即划分稿里的 `tiers`）。部件形态下逐个写了 `probe` 的部件运行：
   ```bash
   python3 .claude/hooks/test-tiers.py canary --part <P>
   ```
   通过才写入该部件的 `probe.sha` 与 `probe.checked`（未自检或 sha 不符时 lint 红）。

7. **复核**（全部满足才算完成）：
   ```bash
   python3 .claude/hooks/test-tiers.py check
   python3 .claude/hooks/test-tiers.py run unit
   python3 .claude/hooks/test-tiers.py probe --json /tmp/test-tiers-probe-after.json
   ```
   - `check` 退出 0：每个测试文件恰好属于一层（退出 1 点名未归层或匹配多层的文件；部件形态下另点名「不属于任何部件」「属于多个部件」；金丝雀文件不参与；退出 2 = 分层文件缺失或不合法）；
   - `run unit` 退出 0：各部件在自己 `root` 下跑 `unit.cmd`，每部件一行「部件 P：exit N · T s」，全绿；
   - 再 `probe`（部件形态逐部件带 `--root` / `--adapter`）：用例合计与第 4 步相等；单元层零触碰；单元层没有 ≥3 秒的用例（有则提速，或走下文「放行慢单测」）；
   - 每个区域的 `cmd` 各跑一次（部件形态在所属部件 `root` 下），全绿。

8. **收尾提示**：进行中的 change 把 `slices.json` 的 `gate.test` 改成 `unit.cmd`（简写形态）或驱动命令 `python3 .claude/hooks/test-tiers.py run unit`（部件形态，同时删掉 `gate.impacted`）——lint 会报不等——并按需写 `gate.integration` / `gate.integration_skip`，改完重跑 baseline；`/opsx-mini --done` 清除声明；**不代 commit**，由人类提交。

---

## 驱动命令

`python3 .claude/hooks/test-tiers.py run unit [--part P]`：在每个部件的 `root` 下依次运行其 `unit.cmd`，每部件打印一行「部件 P：exit N · T s」；全部为 0 时退出 0，否则退出 1；分层文件缺失或不合法退出 2。简写形态视作 `root` 为 `.` 的单个部件，同样可用。它是全仓单元层的统一入口，人与 CI 都跑它；部件形态下 `gate.test` 逐字等于它，但门禁不实际执行这条命令，而是逐部件运行并逐部件判定（基线记 `test.parts.<P>`，final 按部件差分，部件命令改动由 preflight 判「基线过期」）。

## JUnit 契约（G10 逐用例耗时）

- 库每次运行部件单元层都设 `FLIGHT_JUNIT=<临时路径>`：runner 能指定报告路径时，让 `unit.cmd` 把 JUnit XML 写到 `$FLIGHT_JUNIT`；
- runner 只能写到固定位置时写 `unit.junit`（相对 `root` 的 glob），库只读本次运行开始后新写的文件；
- 读取次序：探针 / 适配器记录的 `sec` → `$FLIGHT_JUNIT` → `unit.junit`；三处都没有 → 该部件 G10 不可度量；
- 用例 id：testcase 带 `file` 属性 → `<root>/<file>::<name>`；不带 → `<部件名>::<classname>::<name>`；用作 `slow_allow` 的键与门禁文本。

## 探针适配器契约（G11 触碰）

pytest 部件不写 `probe`，走内置探针。其他语言的部件写 `unit.probe.cmd`，库在 `root` 下运行它，环境变量：

- `FLIGHT_UNIT_CMD`：要跑的测试命令（单元层运行时为 `unit.cmd`，自检时为 `probe.canary`）。适配器**自己执行它**，退出码即测试结果；适配器不自带选测逻辑；
- `FLIGHT_TIER_OUT`：适配器往这里追加 JSONL——先一行 `{"probe": "start"}`，每个用例一行 `{"nodeid": "<相对 root 的文件>::<用例名>", "sec": 秒, "hits": {"文件"|"子进程"|"网络": 样例}}`，与内置 pytest 探针同一格式；
- `FLIGHT_JUNIT`：同 JUnit 契约。

适配器、金丝雀用例都是仓库内文件，审批页与 PR diff 里可见；它只能证明「报得出三类触碰」，不证明没有盲区。

## 金丝雀自检与 sha 锁定

- **金丝雀用例**：用部件的语言写，放在 `probe.canary_files` 的 glob 里（这些文件不参与 `check` / G12）；没有 `FLIGHT_CANARY_TOKEN` 环境变量时跳过。用例名去掉非字母数字、转小写后分别含 `flightcanarypure` / `flightcanaryfile` / `flightcanaryproc` / `flightcanarynet`：
  - pure 只做计算；
  - file 写文件 `$FLIGHT_CANARY_DIR/$FLIGHT_CANARY_TOKEN`；
  - proc 起一个子进程；
  - net 在 127.0.0.1 上 bind 或 connect 一个套接字。
- **库出题**：`canary` 每次生成随机令牌（`FLIGHT_CANARY_TOKEN`）与临时目录（`FLIGHT_CANARY_DIR`），以 `FLIGHT_UNIT_CMD = probe.canary` 运行适配器。通过条件全部满足：有开跑记录；四个用例都有记录；pure 无触碰；file 有「文件」触碰且样例含令牌，并且令牌文件确实落盘；proc 有「子进程」触碰；net 有「网络」触碰。不通过 → stdout 逐条点名未满足的条件，不改文件，退出 1。
- **两种模式**：`canary --root DIR --adapter CMD --canary CMD` 只出题判定，划分前验证用；`canary --part P` 读分层文件里部件 P 的 `probe`，通过后写回 `probe.sha`（`probe.cmd` 里每个解析为仓库内文件的词 → sha256）与 `probe.checked`，其余内容原样保留。`probe.cmd` 里没有仓库内文件 → 退出 2（无从锁定）。
- **sha 锁定**：lint 逐个重算 `probe.sha` 里的文件哈希；没有 `sha` / `checked` 报「未自检」，文件缺失或哈希不符报该路径——改了适配器就重跑 `canary --part P`。逐部件自检：同一适配器文件可被多个部件共用，sha 按部件各存一份。

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

内置探针只支持 pytest（`probe` 不带 `--adapter` 时对非 pytest 命令退出 2 = 不可度量）。非 pytest 的部件按下面取证，门禁逐部件判：

- **有 junit**（`$FLIGHT_JUNIT` 或 `unit.junit`）→ 有逐用例耗时，G10 照常判；
- **有自检过的适配器**（`canary --part P` 通过、sha 未变）→ 有触碰记录，G11 照常判；
- **都没有**才降级：G10 / G11 各给一条警告 `G10 不可度量：部件 P：<原因>` / `G11 不可度量：部件 P：<原因>`（两者都不可度量时合成 `G10/G11 不可度量：部件 P：<原因>`），不判红；此时第 4 步按测试的 import 与被测模块**静态推断**划分，审批页与划分说明里标「未实测」，第 7 步的 `probe` 复核换成各层命令各跑一次全绿。

G12 照常校验。非 pytest 部件按退出码判，不做逐条失败差分；基线已红时先修红或把红用例移出单元层。

## 门禁的分层耗时

配置了分层后，`slice-gate.py` 的 `gate` / `baseline` / `final` 在输出 JSON 里给出 `tier_sec`：

- 形状 `{"unit": 秒, "integration": 秒, "regions": {区域名: 秒}}`，`integration` = `regions` 之和；有未归层用例时另加 `unclassified`（出现即说明有漏网测试文件）；
- 部件形态另加 `tier_sec.parts`：`{部件名: {"unit": 秒, "integration": 秒}}`，`unit` = 该部件单元层运行墙钟（含 G10 候选重跑）+ G7 里归到它的用例耗时，`integration` = 该部件区域之和；简写形态不出现 `parts`；
- 口径：G7 实跑 scenario 测试时按用例文件归层累加每个用例 setup + call + teardown 耗时；baseline / final 里单元层运行（含探针回退重跑与 G10 候选重跑）与每个已选区域 `cmd` 运行计墙钟；lint、typecheck、verify、`gate.checks` 不计；
- 输出位置：`summary` 末尾追加「单元 X.Xs · 集成 Y.Ys」，飞行记录（timeline 备注）在结论词之前插入同样文字；baseline 同时写进 `gate-baseline.json`；
- 未配置分层时没有 `tier_sec`，输出不变。
