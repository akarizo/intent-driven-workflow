## Why

afa 的 `key-features-keyft` 飞行里，切片的「接着干」有四处靠运气（交接文档 F1 / F2 / F3 / F11）：

- **轮次上限不看切片大小**。执行体定义里 `maxTurns: 40` 是常数。回放本机六个仓库的 1124 个执行体转录，取其中带 40 轮上限、能对上计划的 821 个首轮：计划时 owns 展开不超过 8 个现存文件的切片，撞 40 轮或未交回的占 5.5%；超过 8 个的占 28.4%（数据与脚本在 `calibration/`）。大切片几乎注定要重派，重派又要花十几轮看清现场。
- **重派由 prompt 指挥 git**。重派的「第零步」只 `cherry-pick` 上一轮的最后一个提交，上一轮有两个提交时丢掉前一个；跨工作流续跑时沿用 prompt 回传的旧区间起点，把 change 分支后来的飞行记录提交算进切片，门禁误报「执行体不得提交飞行记录」。
- **撞上限只留一句「agent 未返回」**。看不出是哪一档、续跑过几次、半成品在哪。
- **临时 worktree 的东西回不到分支，也没人收**。切片的测试留痕写在临时 worktree 里，分支上的 `evidence.log` 没有任何切片行，评审员按 prompt 去读只能读到空；执行体跑的是包装脚本（命令里没有 `pytest` 这类字样）时一行都不记，门禁就报「无 evidence.log（hook 未安装或未触发）」，而 hook 其实在工作。合回之后临时 worktree 留在磁盘上，afa 一度积到约 64G。

这四处都能由脚本确定地做掉，不该留给模型临场处理。

## What Changes

- **接续收进 `start`**：`slice-gate.py start <S> --continue <上一轮 commit>` 由脚本把上一轮的全部提交接到当前 HEAD（能快进就快进，否则按区间逐个重放），冲突时自己回滚并以 `G0 base` 退出。工作流的重派 prompt 去掉「第零步 cherry-pick」。
- **区间起点由脚本算**：带 `--expect-branch` 时，起点恒为 HEAD 与 change 分支的合并基点，不再采用 prompt 回传的 `--base`。
- **轮次按切片大小分两档**：标准档 40 轮、大片档 80 轮。档位由 `slice-gate.py turns` 按「owns 展开后在基线 commit 上的现存文件数」算（超过 8 个为大片档），计划里可以用 `"turns": "large"` 把小片升档，不能把大片降档。工作流按档位选执行体定义文件；大片档是一份只有 frontmatter 加一句指向的薄定义 `slice-executor-large.md`。审批页的切片表显示档位。
- **撞上限说清楚**：执行体重派后仍未交回时，blocked 理由写明档位与该档上限、本次飞行内已重派一次、半成品快照所在的 ref。
- **切片留痕写进 git 共用目录**：`test-evidence.py` 在有切片标记时把留痕写到 `<git common dir>/flight-evidence/<change>/<切片>.log`，任何 Bash 调用都留一个空文件作心跳；除了认运行器名字，还认本片 `verify` 与 `gate.test` 里出现的脚本路径。门禁从共用目录读（上一轮在别的 worktree 留下的也算），integrator 记录门禁结论时把本片的行并进分支上的 `evidence.log`。
- **合回后回收临时 worktree**：`slice-gate.py merge` 成功合回一片后，把 HEAD 停在该片提交上、且除飞行记录与字节码外没有未提交改动的临时 worktree 移除，并删掉它那条已合入的临时分支。不用强制参数，删不掉就留着并写进 `warnings`。铁律 6 的措辞同步。
- 命令文档与同名 skill 的回退路径、README、安装脚本的 agent 清单随之更新。

没有 **BREAKING**：`--base`、`--resume-checkpoint` 照旧可用；旧工作流脚本配新 hooks 能跑，新工作流脚本遇到旧 hooks 时 prompt 里写了回退做法。

## Capabilities

### New Capabilities
- `slice-continue`: 重派与续跑时由 `start` 接上一轮的全部提交，区间起点由脚本按 change 分支算。
- `turn-tiers`: 执行体的轮次上限按切片大小分档，档位由脚本算、工作流据此选定义文件，撞上限时把档位与快照位置写进理由。
- `slice-evidence-shared`: 切片的测试留痕写在 git 共用目录，门禁跨 worktree 读取，记录门禁结论时并回分支。
- `slice-worktree-reap`: 切片提交合回 change 分支后，回收不再有未合回内容的临时 worktree。

### Modified Capabilities

（无。`template/openspec/specs/` 目前没有已归档的规格。）

## Impact

- `template/.claude/hooks/slice-gate.py`：`start`（`--continue`、起点规范化、首轮清留痕）、新子命令 `turns` 与 lint 的 `turns` 校验、`gate` 的留痕读取、`record` 的留痕并回、`merge` 的回收。
- `template/.claude/hooks/test-evidence.py`：留痕位置、心跳、脚本路径识别。
- `template/.claude/hooks/spec_html.py`：切片表多一列。
- `template/.claude/hooks/takeoff-gate.py`、`session-decompose.py`：各认一个新的 agent 类型名（起飞门禁与模型对账对两档同等对待）。
- `template/.claude/workflows/opsx-apply.js`：重派 prompt、按档位选定义、blocked 理由；新参数 `args.turns`（可选）。
- `template/.claude/agents/`：`slice-executor.md` 改措辞，新增 `slice-executor-large.md`，`integrator.md` 补一句。
- `template/.claude/commands/opsx-apply.md` 与 `template/.claude/skills/openspec-apply-change/SKILL.md`、`README.md`、`install.sh`、根 `CLAUDE.md` 与 `template/CLAUDE.md.snippet` 的铁律 6。
- 新增本地状态 `<git common dir>/flight-evidence/`（自带上限：只留最近 30 个 change 的目录）。
- 与在飞的 `ship-rerun-hardening`（C1b）同改 `slice-gate.py`、`README.md`；与待飞的 `test-ledger`（C5a）同改 `slice-gate.py`、`README.md`。改的函数不重叠，见 design 的风险一节。
