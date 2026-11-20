# backlog · 切片 owns 漏掉钉住文档的旧测试（2026-11-09）

## 现象（E 类反复错误，本轮 2 次）

change `post-ship-hygiene` 的 S2 要把命令计数从 16 改成 17，但旧测试 `tests/test_tiers_docs.py` 钉死了 README「16 个 slash 命令」和 install.sh「16 个 slash command」，这个文件只写进了 S2 的 verify，没写进 owns：

- 首轮：执行体没改这个测试 → `G1 verify` 红；
- 重派：执行体改了它 → `G6 ownership: tests/test_tiers_docs.py 不在 owns 内` 红。

S2 记 blocked，final 停在 scenario 17/22。补救做法：修正计划（`af06811`）→ 重渲染 → 人类重新批准 → 单独重派 S2。整个过程多花了约 2 小时，还多了一次人类批准。

证据：`template/openspec/changes/post-ship-hygiene/review-findings.json` 的 `blocked[S2]`（resolution 记了两次红）；`timeline.md` 的 `final red` / `apply-done blocked=1`。

同类前例：`submodule-aware-flight` 的 S3 因 deps 漏写而 blocked（auto-memory `self-hosting-slice-deps`）。两例都是计划写错，门禁要到执行时才发现。

## 防线（Q4 ✓：可机械判定）

在 `slice-gate.py lint` 加一条规则：对每片 verify 里列出的测试文件，如果它不在任何一片的 owns 里，但文件内容以字面量引用了本片 owns 里的路径（例如 `read("README.md")`、`read("install.sh")`），就报 warn。warn 内容是「verify 读了本片要改的文件，改动可能打破它的断言；考虑并入 owns」，并在 spec.html 里显示，供人类批准时看到。

不报 ERROR：只引用某个文件不等于钉住了它的措辞，误报由人类在批准面板裁决。

## 落地后

把根 `CLAUDE.md`「本仓库开发纪律」里这条过渡条目改成防线索引，一行指向这条 lint 规则（B 类）。

## 再犯（2026-11-18 · machine-test-lock，第 3 次）

S3 给 final 输出加 `lock` 键，但 `tests/test_gate_checks_baseline.py:280` 用 `set(out) <= {…}` 钉死了 final 输出键集合；该文件只在 S3 verify、不在 owns → 首轮 G1 红、重派 G1 + G6 红，S3 blocked，S5 / S6 随之跳过。补救同上：补 owns（`30a0c51`）→ 重渲染 → 人类重批 → 单独补飞 S3 / S5 / S6。

证据：`template/openspec/changes/machine-test-lock/timeline.md` 的首飞 `final red` 与第二次 `approve`；首飞工作流 `wf_c4c88960-c82` 的 `blocked[S3]`。

对防线的补充：上面「字面量引用 owns 路径」的规则拦不住这一例——测试经 `run_hook("slice-gate", …)` 按 hook 名调用，且钉的是输出 JSON 键而非文档措辞。lint 规则还应匹配：① `run_hook("<owns 里 hook 的文件名去后缀>")`；② 本片 spec / 切片包声明新增输出键时，verify 里含 `set(out) <=` / `set(out) ==` 的测试。

## 再犯（2026-11-20 · routing-doctor-hardening，第 4 次）

S3 让 `model-routing.py init` 把 `template/openspec/model-routing.json` 补全到 11 键（含 `cleanup` 组），install 也改成运行 init（D5）。但 `tests/test_fork_commands_docs.py` 的 `test_self_hosting_config_leaves_fork_keys` 钉死「配置里没有 `cleanup` 组」，`tests/test_install.py` 的 `test_fresh_install_ships_only_seeds` 钉死全新安装后 `openspec/` 的文件集合；两者都不在 S3 的 verify / owns 里 → 切片门禁 ok=true，全量 pytest 红，由评审挡下、跨片 fix 补救。这两个测试本应并入 S3 的 owns。

对防线的补充：这一例连 verify 都没列，lint 规则只扫 verify 不够；还应扫全量 `tests/` 里以字面量引用本片 owns 路径（`model-routing.json`）或按 hook 名调用（`run_hook("model-routing")` / `install.sh`）的测试。
