<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->

## 切片

- [x] S1 slice-gate.py：锚点条目带 full_suite_sec 并沿链继承、增量来源不拿补跑秒数充当全量；_warm_source 按 git 最后提交时间选来源；/opsx-propose 措辞同改 （deps: - · verify: `python3 -m pytest -q tests/test_baseline_full_sec.py tests/test_warm_source.py tests/test_baseline_warm.py tests/test_baseline_pool.py tests/test_baseline_anchor_reuse.py`）
