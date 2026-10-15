## ADDED Requirements

### Requirement: 代码树没变时 lint / typecheck 沿用上次结论
`slice-gate.py baseline` 记录 lint / typecheck 时，SHALL 带上 `cmd` 与 `key`：`key` 是按 `cmd_key` 同样的方法对该命令算出的指纹。

下面全部满足时，SHALL 不运行该命令，沿用本 change 上一次基线里该项的 `exit` 与 `lines`，并标 `reused: true`：
- 本次走增量，且候选是本 change 现有的基线；
- 严格差异为空：候选所测代码树与当前代码树按内容比较，只不计字节码、`.pytest_cache`、本 change 的计划工件，以及候选 `byproducts` 中在候选 commit 与当前 HEAD 都未跟踪的路径；`<changes 根>` 下其他 change 目录里的改动照计；
- 上一次该项记录的 `cmd` 与 `key` 都与当前相同。

其余情况照跑。给了 `--full` 时一律照跑。

#### Scenario: lint-reused-when-tree-unchanged
- **GIVEN** change `c` 已有一次全量绿基线，`gate.lint` 运行时会写一个标记文件；之后只改了本 change 的 proposal.md，并清掉 lint 标记
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；lint 标记文件不存在
- **AND** `lint.reused` 为 true，`lint.exit` 与第一次相同

#### Scenario: lint-rerun-when-other-change-edited
- **GIVEN** change `c` 已有一次全量绿基线，`gate.lint` 运行时会写一个标记文件；之后在 `openspec/changes/other/verify/` 下新建了一个文件，并清掉 lint 标记
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** 退出 0；`mode` 为 `incremental`；lint 标记文件存在；`lint` 没有 `reused`

#### Scenario: lint-rerun-when-referenced-plan-file-changed
- **GIVEN** `gate.lint` 的命令里直接写出了本 change 的 `proposal.md`，运行时会写一个标记文件；change `c` 已有一次全量绿基线；之后只改了 proposal.md，并清掉 lint 标记
- **WHEN** 再运行 `slice-gate.py baseline`
- **THEN** `mode` 为 `incremental`；lint 标记文件存在；`lint` 没有 `reused`

### Requirement: 全量可度量时 verify 从全量结果推导
本次跑了全量 `gate.test`、且结果可度量（exit 0，或记有 `test.failed`）时，某片 verify 满足下面全部条件，SHALL 不单独运行，记为 `{exit: 0, cmd, derived: "full"}`：
- **同一前缀**：`gate.test` 与该 verify 按 shell 规则切词后，都以同一个 pytest 启动前缀开头，前缀之前不能有 `cd`、环境变量赋值或管道等。前缀之后，两者都只含白名单选项与路径。白名单选项为 `-q`、`-qq`、`-v`、`-vv`、`-x`、`-s`、`--no-header`、`--tb=…`、`-p no:cacheprovider`；
- **路径**：verify 至少给出一个路径。每个路径都是仓库内已存在、文件名形如 `test_*.py` 或 `*_test.py` 的文件，且不带 `::` 选择；
- **全量里有、且都通过**：每个路径对应一个模块名（去掉 `.py`，`/` 换成 `.`）。全量的 junit 结果里至少有一条用例的 classname 等于该模块名或以「该模块名 + .」开头；全量的失败与错误里，没有这样的用例。

其余情况照旧单独运行 verify。增量基线不推导。

#### Scenario: verify-derived-from-full-suite
- **GIVEN** `gate.test` 是直接的 `python -m pytest -q -p no:cacheprovider tests`；S1 的 verify 是同一前缀加 `tests/test_cap.py`；`tests/test_cap.py` 的用例每运行一次就往仓外计数文件追加一个字符，且会通过
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；计数文件恰好 1 个字符
- **AND** `verify.S1.exit` 为 0，`verify.S1.derived` 为 `full`

#### Scenario: verify-run-when-scope-has-preexisting-red
- **GIVEN** `gate.test` 是直接的 pytest 调用；`tests/test_old.py` 有一个失败用例；S2 的 verify 是同一前缀加 `tests/test_old.py`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出非 0；`verify.S2.exit` 非 0，`verify.S2` 没有 `derived`

#### Scenario: verify-run-when-not-derivable
- **GIVEN** `gate.test` 是直接的 pytest 调用；`tests/test_cap.py` 的用例每运行一次就往仓外计数文件追加一个字符。三片的 verify 分别是：
  - S1：包装脚本（运行时写标记）再跑 `tests/test_cap.py`；
  - S2：同一前缀加 `tests/test_cap.py::test_adds`；
  - S3：同一前缀加 `-k adds tests/test_cap.py`
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；S1 的标记文件存在；计数文件恰好 4 个字符
- **AND** 三片的 verify 记录都没有 `derived`

#### Scenario: verify-run-when-gate-test-not-plain-pytest
- **GIVEN** `gate.test` 是本 change 目录下的包装脚本（内部调用 pytest 跑 `tests`）；S1 的 verify 是直接的 pytest 加 `tests/test_cap.py`；`tests/test_cap.py` 的用例每运行一次就往仓外计数文件追加一个字符
- **WHEN** 运行 `slice-gate.py baseline`
- **THEN** 退出 0；计数文件恰好 2 个字符；`verify.S1` 没有 `derived`
