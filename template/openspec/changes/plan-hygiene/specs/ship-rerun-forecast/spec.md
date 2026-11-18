## ADDED Requirements

### Requirement: ship 的「final 过期」理由带补跑预告
`slice-gate.py ship` 判定 final 过期时，SHALL 在该条理由后追加补跑预告：预计走增量时写「补跑将是增量」与锚点、Δ 文件数；预计走全量时写「补跑将是全量」与原因；计划配了 `gate.impacted` 时写「补跑由 gate.impacted 选测」。预告 SHALL 由 `slice-gate.py` 自己的判定函数给出，MUST NOT 调用 `flight-doctor.py`；预告算不出或出错时 MUST NOT 影响裁决与退出码，该条理由保持原样。
Feature: 说「过期」的同时说清补一次要多大代价
Rule: 裁决不因预告而失败

#### Scenario: stale-final-reason-says-incremental-rerun
- **GIVEN** 一个 change 的基线测到了依赖图，final 已绿并留下锚点
- **AND** 之后提交了对一个源码文件的修改
- **WHEN** 运行 `slice-gate.py ship`
- **THEN** 退出码为 1
- **AND** 有一条理由同时含「final 过期」与「补跑将是增量」

#### Scenario: stale-final-reason-says-full-rerun-with-why
- **GIVEN** 同样的 change，final 已绿并留下锚点
- **AND** 之后提交了对全局文件 `pytest.ini` 的修改
- **WHEN** 运行 `slice-gate.py ship`
- **THEN** 退出码为 1
- **AND** 有一条理由同时含「final 过期」「补跑将是全量」与 `pytest.ini`

### Requirement: 成本预告与 ship 用同一个判定，耗时取自基线
`flight-doctor.py forecast` 对 final 的预告 SHALL 调用 `slice-gate.py` 的同一个判定函数，输出的 `mode` 与 `why` 文字 MUST 与改动前一致；`final.sec` SHALL 经 `suite_sec` 取值（基线优先，旧计划字段作回退）。`flight-doctor.py` MUST 仍恒退出 0。
Feature: 一个判定，两处使用
Rule: 预告的文字是 spec.html 与人读的输出，搬家不改字

#### Scenario: forecast-reads-suite-sec-from-baseline
- **GIVEN** 一个 change 的 `slices.json` 里没有 `full_suite_sec`，`gate-baseline.json` 的 `full_suite_sec` 为 300.5
- **WHEN** 运行 `flight-doctor.py forecast --json`
- **THEN** 退出码为 0，`final.sec` 为 300.5
- **AND** 另一个 change 的基线没有该字段、计划里旧的 `gate.full_suite_sec` 为 816 时，`final.sec` 为 816
