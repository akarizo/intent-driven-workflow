<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-18T07:03:35Z	baseline	增量（经锚点 machine-test-lock@8c6191cf5e，补跑 14 个测试文件 114.3s） ok；排队 0.0s · 负载 16.9→20.8/18
2026-11-18T08:36:41Z	baseline	增量（经锚点 slice-resume-deterministic@1dabeac9c2，补跑 76 个测试文件 526.1s） ok；排队 0.0s 后放弃（test-ledger · baseline 已持有 600.6 秒，超过上限 300.0 秒） · 负载 5.2→3.0/18
2026-11-18T08:49:00Z	approve	2026-11-18T08:48:28Z · 起飞 slice-resume-deterministic 授权提交
2026-11-18T08:53:51Z	gate	S1 ok
2026-11-18T08:53:51Z	gate	S2 ok
2026-11-18T08:54:02Z	integrate	wave 1
2026-11-18T09:03:32Z	gate	S3 ok
2026-11-18T09:03:32Z	gate	S4 ok
2026-11-18T09:03:46Z	integrate	wave 2
2026-11-18T09:12:26Z	gate	S5 ok
2026-11-18T09:12:26Z	gate	S6 ok
2026-11-18T09:12:26Z	gate	S7 ok
2026-11-18T09:12:37Z	integrate	wave 3
2026-11-18T09:43:14Z	fix	blocking=1
2026-11-18T09:43:14Z	review	findings=21 blocking=1 deferred=20
2026-11-18T09:43:14Z	final	同树沿用 02a56c7d65 ok
2026-11-18T09:43:16Z	apply-done	blocked=0 blocking=1
2026-11-18T09:43:36Z	apply-done	
2026-11-18T09:43:40Z	ship	draft: 1 条 CRITICAL/HIGH 评审未闭环
2026-11-18T09:43:54Z	ship	draft: 1 条 CRITICAL/HIGH 评审未闭环
2026-11-18T10:07:05Z	ship	draft: final 过期：记录 b94e4a512e，HEAD 2254d33662；补跑将是增量（锚点 b1be3db4be，Δ 26 个文件）; 1 条 CRITICAL/HIGH 评审未闭环
2026-11-18T10:16:43Z	final	增量（锚点 b1be3db4be，重跑 81 个文件 / 沿用 100 个用例） 测试 551.9s · 检查 schema-validate 1.6s · 排队 0.0s · 负载 3.5→3.4/18 ok
