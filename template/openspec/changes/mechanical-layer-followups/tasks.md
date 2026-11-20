<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->

## 切片

- [ ] S1 model-routing.py frontmatter 保留换行风格、识别文件末尾的收尾 ---；flight-doctor doctor 新增 [routing] 段；install.sh 补救提示给出 --upgrade 出路；顺手清 C3 遗留 LOW （deps: - · verify: `python3 -m pytest -q tests/test_routing_followups.py tests/test_routing_frontmatter.py tests/test_install_routing.py tests/test_flight_doctor.py tests/test_flight_doctor_lock.py tests/test_flight_doctor_tests.py`）
- [ ] S2 /clean-after-merged 最后一条回复带计划、结果与验证；起始 CWD 依据与 --protect 绝对路径写进文档；merged-cleanup.py 头注释同步 （deps: - · verify: `python3 -m pytest -q tests/test_fork_commands_docs.py tests/test_merged_cleanup.py`）
