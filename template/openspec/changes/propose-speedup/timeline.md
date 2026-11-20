<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-19T15:11:29Z	baseline	增量（经锚点 model-routing-config@dc6c26a128，补跑 51 个测试文件 131.6s） red；排队 0.0s · 负载 6.1→4.7/18
2026-11-19T15:14:16Z	baseline	增量（复用 propose-speedup 的全量 exit 0, 131.6s；补跑 1 个测试文件 0.8s） ok；排队 32.2s · 负载 3.2→3.0/18
2026-11-19T16:01:11Z	approve	2026-11-19T16:00:39Z · 起飞 propose-speedup 授权提交
2026-11-19T16:24:00Z	gate	S1 ok
2026-11-19T16:24:01Z	gate	S2 ok
2026-11-19T16:24:02Z	gate	S3 ok
2026-11-19T16:24:29Z	integrate	wave 1
2026-11-19T16:24:45Z	wave-check	wave 1/2 · 测试跳过（受影响测试约 424.8 秒（107 个文件），超过预算 120 秒，留给 final） · 排队 0.0s · 负载 5.9→5.9/18 ok
2026-11-19T16:40:09Z	gate	S4 ok
2026-11-19T16:40:19Z	integrate	wave 2
2026-11-19T16:40:24Z	wave-check	wave 2/2 · 测试跳过（受影响测试约 424.8 秒（107 个文件），超过预算 120 秒，留给 final） · 排队 0.0s · 负载 10.0→10.0/18 ok
2026-11-19T17:06:53Z	fix	blocking=1
2026-11-19T17:06:53Z	review	findings=16 blocking=1 deferred=15
2026-11-19T17:13:48Z	final	增量（锚点 dc6c26a128，重跑 107 个文件 / 沿用 181 个用例） 测试 394.9s · 检查 schema-validate 1.8s · 用例 +2/-289（新增 0.5s） · 排队 0.0s · 负载 4.3→3.7/18 red
2026-11-19T17:21:40Z	final	增量（锚点 dc6c26a128，重跑 107 个文件 / 沿用 181 个用例） 测试 394.9s · 检查 schema-validate 1.8s · 用例 +1/-312（新增 0.3s） · 排队 0.0s · 负载 4.7→2.2/18 red
2026-11-20T05:16:53Z	final	增量（锚点 dc6c26a128，重跑 107 个文件 / 沿用 181 个用例） 测试 609.6s · 检查 schema-validate 2.7s · 用例 +2/-0（新增 0.4s） · 排队 75.3s · 负载 3.4→4.4/18 ok
2026-11-20T05:17:10Z	apply-done	
2026-11-20T05:17:17Z	reap	回收 1 个 · 释放 10.6 MB · 归档 1 个 · 保留 0 个
2026-11-20T05:17:30Z	ship	ready
2026-11-20T05:18:03Z	ship	draft: 1 条 CRITICAL/HIGH 评审未闭环
2026-11-20T05:18:46Z	ship	ready
