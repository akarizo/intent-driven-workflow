# Gate Report

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-11-20T12:57:20Z | S1 | ok | a26bbcaf73 | - | - |
| 2026-11-20T12:57:21Z | S2 | ok | d0e3c17a06 | - | - |
| 2026-11-20T12:57:39Z | wave | ok | f489397498 | - | - |
| 2026-11-20T13:21:06Z | S3 | ok | 3a4ba305da | - | 执行体附注（不是门禁输出）：在切片 commit 上跑全量 pytest，结果 934 passed、2 failed。两条失败都来自 owns 之外、钉住旧行为的测试，本切片按纪律没有改它们，需要主会话或跨片修复处理：; tests/test_fork_commands_docs.py::test_self_hosting_config_leaves_fork_keys 断言 template/openspec/model-routing.json 里没有 cleanup 组。S3 按切片包要求用 init 补全到 11 键（含 cleanup.runner = sonnet · low，与内建默认一致），所以这条断言和 S3 的要求冲突；同一测试里的 frontmatter --check 部分仍然退出 0。; tests/test_install.py::test_fresh_install_ships_only_seeds 断言全新安装后 openspec/ 里只有种子清单、gate-scope.json 和 schemas/。现在 install 会额外种下 model-routing.json（D5 要求），文件集合要加上 model-routing.json。; 门禁运行时 flight-lock 等了约 438 秒后超时（另一个 final 持有锁），门禁照常给出结果；对应 JSON 里的 lock.state=timeout。 |
