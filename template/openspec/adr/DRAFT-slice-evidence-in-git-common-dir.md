# DRAFT. 切片的测试留痕写在 git 共用目录，记录门禁结论时并回分支

- Status: accepted
- Date: 2026-11-18
- 关联：DRAFT-gate-evidence-not-self-reported（hook 留痕是门禁的真值源之一）· DRAFT-post-merge-cleanup-by-tiered-script（新增本地状态要登记清理规则或写明保留）
- 来源 change：slice-resume-deterministic（design 调查一 · D6）

## Context

铁律 3 要求测试运行由 hook 留痕。`test-evidence.py` 把留痕追加到 change 目录下的 `evidence.log`，门禁读同一个文件判 G5。

切片在临时 worktree 里执行之后，这个安排有两处断开：

- 留痕写在临时 worktree 的工作树里。执行体不得提交它（并行切片合回会冲突），integrator 只提交 change 家的那份，所以分支上的 `evidence.log` 没有任何切片行。评审员按 prompt 去读，读不到。
- 重派开的是新 worktree，上一轮的留痕看不见；执行体用包装脚本跑测试时命令文本里没有运行器名字，一行都不记，门禁把「没有文件」解释成「hook 没装」。

## Decision

1. **切片留痕的真值在 `<git common dir>/flight-evidence/<change>/<切片>.log`**。同一仓库的所有 worktree 共用它；一片一个文件，行格式不变。没有切片标记时（主会话）仍写工作树里的 `evidence.log`。
2. **文件存在即心跳**：有切片标记时 hook 对任何 Bash 调用都确保文件存在。门禁据此区分「hook 没触发」（警告）与「hook 在工作而本片没跑过测试」（红）。
3. **认定测试运行**：运行器名字，或命令文本里出现本片 `verify` / `gate.test` 写到的脚本路径。
4. **门禁读两处之和**：所在工作树的 `evidence.log` 与共用目录里本片的文件。
5. **并回分支由 `record` 做**：integrator 在 change 家记录门禁结论时，把该片的行追加进分支上的 `evidence.log`，然后删除共用目录里的文件。分支上的 `evidence.log` 仍是给人和评审员读的那一份。
6. **清理规则**：首轮 `start` 删除该片的残留；`flight-evidence/` 只保留最近 30 个 change 的目录。`merged-cleanup.py` 不处理这个目录（保留）。

否决的方案：

- **让执行体提交 `evidence.log`**：并行切片合回必冲突。
- **门禁自己跑 verify 时也记一行**：「执行体亲眼看过红」这条证据就失去意义。
- **hook 同时写工作树与共用目录**：两份真值。

## Consequences

- **更易**：重派与续跑看得到上一轮的留痕；评审员在分支上读得到每片的留痕；「hook 没装」与「没跑测试」不再混为一谈。
- **更难**：G5 的「没跑过测试」在临时 worktree 里开始按原意判红；执行体若用既不含运行器名字、也不在 `verify` / `gate.test` 里的命令跑测试，会被拦下，需要先跑一次本片的 verify。
- **约束后续变更**：其他只在临时 worktree 里产生、又需要回到分支的记录，沿用「共用目录存真值、`record` 并回」这条路，不新增执行体可提交的记录文件。
- **不影响**：没有切片标记的会话、`--gate=per-task` 以外的 legacy 流程读写的仍是工作树里的 `evidence.log`。
