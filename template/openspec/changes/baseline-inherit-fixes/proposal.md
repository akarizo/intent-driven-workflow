## Why

baseline 从别的来源继承结论时，有两处会继承错东西。两处都是 C2（propose-speedup，#27）留下的。

- **全量耗时继承错**：C2 的第一次 baseline 经锚点补跑了 131.6 秒，锚点条目里没有全量耗时，所以 `full_suite_sec` 留空。第二次 baseline 复用这份基线时，把它的 `test.sec`（也就是补跑的 131.6 秒）当成全量耗时记下，而真实全量约 470 秒。final 的超时上限因此只有 3 × 131.6 ≈ 395 秒，两次 final 都以「G2 test：增量重跑超时」红掉（`openspec/changes/propose-speedup/gate-report.md` 第 11、12 行）。
- **预热来源随机**：预热（`slice-gate.py warm`）按 `slices.json` 的修改时间选来源 change。新 worktree 里全部 32 个 `slices.json` 的修改时间完全相同（实测），选中的其实是目录遍历顺序里排在前面的那个。本仓库各 change 的 `gate.test` 都一样，所以没出过事；下游仓库的 `gate.test` 一旦换过，就可能沿用到旧命令。

## What Changes

- **锚点条目带全量耗时**：全量 baseline 与全量 final 写锚点时记下本次全量耗时 `full_suite_sec`；增量 baseline 与增量 final 写的新锚点沿用来源锚点的值，沿锚点链一路传下去。
- **经锚点的 baseline 继承全量耗时**：取值顺序是本 change 上一次已知的全量耗时（例如预热），再到来源锚点的 `full_suite_sec`。
- **增量来源不再拿 `test.sec` 充当全量**：复用本 change 旧基线时，只有那份旧基线是全量运行，才用它的 `test.sec`；它本身是增量时，`full_suite_sec` 留空（final 超时上限退到 600 秒）。基线池只收全量结果，行为不变。
- **预热来源按 git 最后提交时间选**：取每个 change 的 `slices.json` 在 git 里最后一次提交的时间，最新的胜出；时间相同取 change 名字典序最后一个；从没提交过的排在所有已提交的之后，它们之间也按名字定。
- **文档措辞**：`/opsx-propose` 命令与同名 skill 里「沿用最近一个 change 的 `gate.test`」改为「沿用最后提交的 change 的 `gate.test`」，两处同改。

## Capabilities

### New Capabilities
- `baseline-full-suite-sec`：baseline 与 final 写锚点、继承锚点时，全量耗时的记录与取值规则。
- `warm-source-selection`：预热选来源 change 的确定性规则。

### Modified Capabilities
（无：本仓库还没有归档进 `openspec/specs/` 的主规格）

## Impact

- **代码**：`template/.claude/hooks/slice-gate.py`，涉及 `_run_baseline` 的全量耗时取值段、全量 baseline 与全量 final 的锚点写入、`_anchor_forward`、`_warm_source`。
- **数据**：锚点池条目（`<git common dir>/flight-anchors/*.json`）新增可选字段 `full_suite_sec`。旧条目没有这个字段时按「未知」处理，不需要迁移。
- **文档**：`template/.claude/commands/opsx-propose.md`、`template/.claude/skills/openspec-propose/SKILL.md` 各一行。
- **测试**：新增 `tests/test_baseline_full_sec.py`、`tests/test_warm_source.py`。`tests/test_baseline_pool.py` 断言基线池复用时 `full_suite_sec == test.sec`，这条行为不变，需保持绿。
