<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-20T09:53:40Z	warm	exit 0, 739.7s red；全量：预热；排队 454.9s 后放弃（test-tiers-physical · final 已持有 1259.4 秒，超过上限 1258.8 秒） · 负载 7.6→30.4/18
2026-11-20T10:08:57Z	baseline	增量（经锚点 baseline-inherit-fixes@9b2f62f6d8，补跑 91 个测试文件 888.0s） ok；排队 0.0s 后放弃（test-tiers-physical · final 已持有 2001.3 秒，超过上限 1258.8 秒） · 负载 31.7→4.9/18
2026-11-20T10:10:54Z	approve	2026-11-20T10:10:30Z · 起飞 授权提交
2026-11-20T10:25:26Z	gate	S1 ok
2026-11-20T10:25:27Z	gate	S2 ok
2026-11-20T10:25:42Z	integrate	wave 1
2026-11-20T10:25:56Z	wave-check	wave 1/1 · 测试跳过（受影响测试约 213.0 秒（48 个文件），超过预算 120 秒，留给 final） · 排队 0.0s · 负载 5.9→5.9/18 ok
2026-11-20T10:27:17Z	review	findings=3 blocking=0 deferred=3
2026-11-20T10:30:24Z	final	增量（锚点 e884c26c93，重跑 48 个文件 / 沿用 721 个用例） 测试 177.0s · 检查 schema-validate 1.4s · 用例 +0/-0（新增 0.0s） · 排队 0.0s · 负载 2.8→6.1/18 ok
2026-11-20T10:30:31Z	apply-done	blocked=0 blocking=0
2026-11-20T10:30:52Z	reap	回收 0 个 · 释放 0.0 MB · 归档 0 个 · 保留 0 个
2026-11-20T10:31:13Z	ship	ready
