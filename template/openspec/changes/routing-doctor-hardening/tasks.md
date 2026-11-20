<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->

## 切片

- [ ] S1 frontmatter 读写失败走退出码 2；doctor [routing] 段把崩溃报成不可用、UTF-8 宽松解码；doctor 用例改在临时目录跑复制的 hooks （deps: - · verify: `python3 -m pytest -q tests/test_routing_followups.py tests/test_routing_frontmatter.py tests/test_model_routing.py tests/test_flight_doctor.py tests/test_flight_doctor_lock.py tests/test_flight_doctor_tests.py`）
- [ ] S2 /clean-after-merged 文档注明 context: fork 命令未单独实测、step 1 注释措辞对齐；起点依据断言改为整句 （deps: - · verify: `python3 -m pytest -q tests/test_fork_commands_docs.py tests/test_clean_after_merged_docs.py`）
- [ ] S3 model-routing.py init 种下 / 补全 model-routing.json（11 键全写、每键 desc、顶层 $comment），校验接受 desc / $comment；install 安装与升级运行 init；本仓库配置补全；README 同步 （deps: S1 · verify: `python3 -m pytest -q tests/test_routing_seed.py tests/test_install_routing.py tests/test_model_routing.py tests/test_routing_frontmatter.py tests/test_routing_followups.py tests/test_spec_html_routing.py tests/test_docs_iron_rules.py`）
