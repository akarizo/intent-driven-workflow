<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->
2026-11-20T06:48:03Z	warm	exit 0, 475.8s ok；全量：预热；排队 0.0s · 负载 4.0→3.2/18
2026-11-20T07:06:42Z	baseline	增量（经锚点 mechanical-command-layer@e557aed737，补跑 3 个测试文件 4.2s） ok；排队 329.3s · 负载 7.8→7.0/18
2026-11-20T07:19:15Z	approve	2026-11-20T07:18:24Z · 起飞 授权提交
2026-11-20T07:23:06Z	gate	S1 ok
2026-11-20T07:23:17Z	integrate	wave 1
2026-11-20T07:24:59Z	wave-check	wave 1/2 · 测试 88.4s（9 个文件） · 排队 0.0s · 负载 6.0→4.0/18 ok
2026-11-20T07:35:38Z	gate	S2 ok
2026-11-20T07:35:58Z	integrate	wave 2
2026-11-20T07:37:46Z	wave-check	wave 2/2 · 测试 98.5s（32 个文件） · 排队 0.0s · 负载 4.7→4.7/18 ok
2026-11-20T07:39:33Z	review	findings=6 blocking=0 deferred=6
2026-11-20T07:41:38Z	final	增量（锚点 e557aed737，重跑 32 个文件 / 沿用 778 个用例） 测试 104.4s · 检查 schema-validate 2.1s · 用例 +0/-0（新增 0.0s） · 排队 0.0s · 负载 3.2→3.5/18 ok
2026-11-20T07:41:39Z	apply-done	blocked=0 blocking=0
2026-11-20T07:42:17Z	reap	回收 0 个 · 释放 0.0 MB · 归档 0 个 · 保留 0 个
2026-11-20T07:42:43Z	ship	ready
2026-11-20T07:43:33Z	ship	ready
2026-11-20T07:44:09Z	pr-open	https://github.com/akarizo/intent-driven-workflow/pull/28
2026-11-20T07:52:07Z	final	增量（锚点 d07855ae03，重跑 10 个文件 / 沿用 826 个用例） 测试 108.7s · 检查 schema-validate 1.5s · 用例 +2/-0（新增 1.3s） · 排队 0.0s · 负载 2.7→3.9/18 ok
