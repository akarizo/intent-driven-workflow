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
