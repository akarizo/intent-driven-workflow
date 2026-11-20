<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-20T08:07:12Z	warm	exit 0, 478.2s ok；全量：预热；排队 0.0s · 负载 4.8→3.7/18
2026-11-20T08:22:38Z	baseline	增量（复用 baseline-inherit-fixes 的全量 exit 0, 478.2s；补跑 2 个测试文件 16.4s） ok；排队 477.9s · 负载 6.2→6.5/18
2026-11-20T08:34:45Z	approve	2026-11-20T08:34:16Z · 起飞 授权提交
2026-11-20T08:48:22Z	gate	S1 ok
2026-11-20T08:48:33Z	integrate	wave 1
2026-11-20T08:48:39Z	wave-check	wave 1/1 · 测试跳过（受影响测试约 435.6 秒（90 个文件），超过预算 120 秒，留给 final） · 排队 0.0s · 负载 4.6→4.6/18 ok
2026-11-20T08:50:43Z	review	findings=2 blocking=0 deferred=2
2026-11-20T09:02:35Z	final	增量（锚点 9b2f62f6d8，重跑 90 个文件 / 沿用 327 个用例） 测试 691.8s · 检查 schema-validate 2.3s · 用例 +0/-0（新增 0.0s） · 排队 0.0s · 负载 7.3→7.7/18 ok
2026-11-20T09:02:38Z	apply-done	blocked=0 blocking=0
