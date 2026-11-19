<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-18T11:28:34Z	baseline	增量（经锚点 tier-budgets@2cc616742f，补跑 9 个测试文件 44.3s） ok；排队 0.0s · 负载 4.9→3.2/18
2026-11-18T11:37:52Z	baseline	增量（经锚点 wave-integration-guard@2cc616742f，补跑 6 个测试文件 37.1s） ok；排队 0.0s · 负载 2.9→5.5/18
2026-11-18T12:06:38Z	approve	2026-11-18T12:06:03Z · 起飞 授权提交
2026-11-18T12:17:58Z	gate	S1 ok
2026-11-18T12:17:59Z	gate	S4 ok
2026-11-18T12:17:59Z	gate	S6 ok
2026-11-18T12:18:11Z	integrate	wave 1
2026-11-18T12:30:16Z	approve	2026-11-18T12:28:47Z · 起飞 授权提交
2026-11-18T12:35:25Z	gate	S2 ok
2026-11-18T12:35:36Z	integrate	wave 2
2026-11-18T12:46:32Z	gate	S3 b5d6709cc6b6c0912a1c4b060131b1b16ff59d9b ok
2026-11-18T12:46:32Z	gate	S5 d47925bfb4e68fe451e49375d213e6c4eab58ffd ok
2026-11-18T12:46:32Z	gate	S7 405bb6c8cec320c6937317d8c5ddba6880ddbd9c ok
2026-11-18T12:46:41Z	integrate	wave 3
2026-11-18T12:46:41Z	wave-check	wave 3/3 · 测试跳过（受影响测试约 516.7 秒（92 个文件），超过预算 120 秒，留给 final） · 排队 0.0s · 负载 8.0→8.0/18 ok
2026-11-18T12:48:41Z	review	findings=16 blocking=0 deferred=16
2026-11-18T12:49:17Z	review	findings=21 blocking=0 deferred=21
2026-11-18T12:58:32Z	final	增量（锚点 2cc616742f，重跑 92 个文件 / 沿用 141 个用例） 测试 564.2s · 检查 schema-validate 1.7s · 用例 +0/-0（新增 0.0s） · 排队 0.0s · 负载 2.9→5.4/18 ok
2026-11-18T12:58:38Z	apply-done	blocked=1 blocking=0
2026-11-18T12:59:20Z	ship	draft: 切片 S3 无门禁记录; 切片 S5 无门禁记录; 切片 S7 无门禁记录
2026-11-18T13:03:37Z	final	增量（锚点 2cc616742f，重跑 92 个文件 / 沿用 141 个用例） 测试 566.1s · 检查 schema-validate 2.2s · 用例 +0/-0（新增 0.0s） · 排队 264.8s 后放弃（wave-integration-guard · final 已持有 301.0 秒，超过上限 300.0 秒） · 负载 2.1→3.5/18 ok
2026-11-18T13:03:46Z	apply-done	blocked=1 blocking=0
2026-11-18T13:06:31Z	gate	S3 ok
2026-11-18T13:06:31Z	gate	S5 ok
2026-11-18T13:06:31Z	gate	S7 ok
2026-11-18T13:06:31Z	ship	ready
2026-11-19T01:01:32Z	ship	ready
2026-11-19T01:02:09Z	ship	draft: final 过期：记录 993962911b，HEAD b6ced9b456；补跑将是增量（锚点 993962911b，Δ 1 个文件）
2026-11-19T01:14:07Z	final	增量（锚点 993962911b，重跑 96 个文件 / 沿用 189 个用例） 测试 600.2s · 检查 schema-validate 2.6s · 用例 +38/-59（新增 34.4s） · 排队 0.0s · 负载 4.7→5.9/18 red
2026-11-19T01:25:57Z	final	增量（锚点 993962911b，重跑 96 个文件 / 沿用 189 个用例） 测试 637.7s · 检查 schema-validate 2.7s · 用例 +38/-0（新增 34.8s） · 排队 0.0s · 负载 6.7→2.8/18 ok
