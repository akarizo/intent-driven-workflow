## ADDED Requirements

### Requirement: 切片门禁把 gitlink 展开成子仓内的文件
Rule: `slice-gate.py gate` 统计区间改动时，对 mode 为 160000 的条目（gitlink），SHALL 用子仓内的真实文件代替 gitlink 伪路径，路径带 `<子仓路径>/` 前缀：
- **已提交部分**：取区间前后 gitlink 之间的子仓 diff。
- **未提交部分**：取子仓 status，含未跟踪文件，遵守子仓自己的 `.gitignore`；外加子仓检出领先父仓 HEAD gitlink 的那一段。

展开后的路径与父仓路径一起参与 G3 配对、G6 所有权、GWT 判定，字节码副产物照旧不计。以下情况 SHALL 保留伪路径，交 G6 点名：子仓未填充、gitlink 一侧为空（新增或删除 submodule）、子仓里找不到 gitlink 指向的提交。

门禁绿时，对区间内 gitlink 有变化、且已填充的子仓，SHALL 在子仓写 `refs/flight-sub/<change>/<S>` 指向新的 gitlink 提交，防止子仓提交被 gc。

没有 gitlink 的仓库，门禁结果 SHALL 与改前一致。

#### Scenario: gate-expands-gitlink-to-files
- **GIVEN** change 家里 start S1，子仓已初始化
- **AND** 子仓里写了 owns 内的 `lib1.py` 与配对测试并提交，父仓把 gitlink 并入切片 commit
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁绿，`failed` 为空
- **AND** 子仓里 `refs/flight-sub/c/S1` 指向本片的子仓提交

#### Scenario: gate-flags-unowned-submodule-file
- **GIVEN** 同上，但子仓提交里还多了一个 owns 之外的 `stray.py`
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁红，`failed` 里有一条 G6 点名 `mods/sub/stray.py`

### Requirement: 子仓检出未记录进父仓即红
Rule: 已填充的子仓，其检出提交与父仓 HEAD 记录的 gitlink 不一致时（子仓提交了，但没有 `git add <子仓路径>` 并入切片 commit），`gate` SHALL 判红。失败项以 `G6 gitlink` 开头，点名子仓路径与检出提交前缀，并给出修法：`git add <子仓路径>` 后并入本切片 commit。这种提交在合回时会丢。

#### Scenario: gate-flags-unrecorded-gitlink
- **GIVEN** 子仓里提交了 owns 内的改动，父仓没有提交 gitlink
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁红，`failed` 里有一条以 `G6 gitlink` 开头，含 `mods/sub` 与该子仓提交的前 10 位

### Requirement: 子仓内的 ceiling 标记进 G8
Rule: G8 扫描新增源码行时，SHALL 同时扫描区间内 gitlink 变化所对应的子仓 diff。门禁 JSON 的 `ceilings` 行位置为 `<子仓路径>/<文件>` 与子仓文件内的行号。

#### Scenario: gate-collects-ceiling-in-submodule
- **GIVEN** 子仓 `lib1.py` 第 3 行新增 `# ceiling: 全局锁串行写入 -> 按键分片后并发写入`，已提交并钉 gitlink
- **WHEN** 运行 `slice-gate.py gate S1`
- **THEN** 门禁 JSON 的 `ceilings` 含 `["mods/sub/lib1.py", 3, "全局锁串行写入", "按键分片后并发写入"]`
