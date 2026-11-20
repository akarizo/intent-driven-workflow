<!-- 本文件由 slices.json 生成，不要手写编辑；改动请改 slices.json 后重新生成。 -->

## 切片

- [ ] S1 model-routing.py：登记 cleanup.runner 与 FORK_COMMANDS，新增 frontmatter 子命令（渲染 / --check 漂移 / 非 fork 与非法配置拒写） （deps: - · verify: `python3 -m pytest -q tests/test_routing_frontmatter.py tests/test_model_routing.py`）
- [ ] S2 /clean-after-merged 改 context: fork；install.sh 安装与升级时重渲 fork 命令 frontmatter；四个命令改正切模型建议；README / WORKFLOW 登记 cleanup.runner；不变式与自举锁测试 （deps: S1 · verify: `python3 -m pytest -q tests/test_fork_commands_docs.py tests/test_install_routing.py tests/test_clean_after_merged_docs.py tests/test_close_reap_docs.py tests/test_routing_docs.py`）
