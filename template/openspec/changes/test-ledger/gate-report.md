# Gate Report

## 天花板

| 时间 | 切片 | 位置 | 限制 | 升级路径 |
|---|---|---|---|---|
| 2026-11-18T09:01:14Z | S4 | template/.claude/hooks/slice-gate.py:4596 | secs 让锚点文件变大，选锚点变慢时挪到旁路文件 | 把 secs 存到 flight-ledger/ 下按锚点文件名对应的文件 |
| 2026-11-18T09:01:14Z | S4 | template/.claude/hooks/slice-gate.py:4602 | secs 让锚点文件变大，选锚点变慢时挪到旁路文件 | 把 secs 存到 flight-ledger/ 下按锚点文件名对应的文件 |
| 2026-11-18T09:20:01Z | S5 | template/.claude/hooks/slice-gate.py:4236 | secs 让锚点文件变大，选锚点变慢时挪到旁路文件 | 把 secs 存到 flight-ledger/ 下按锚点文件名对应的文件 |

| 时间 | 切片 | 结论 | commit | failed | warnings |
|---|---|---|---|---|---|
| 2026-11-18T08:55:01Z | S1 e46423816fce7daf5366dea966466f005e41e9f7 | ok |  | - | - |
| 2026-11-18T08:55:01Z | S2 74d4d888a5c828d04563e44d2fe8e21b6427f5a4 | ok |  | - | - |
| 2026-11-18T08:55:01Z | S7 74528a6b97da03e9ae3ff7bce6c5ded8eeb5d4ba | ok |  | - | - |
| 2026-11-18T08:55:07Z | S1 | ok | e46423816f | - | - |
| 2026-11-18T08:55:07Z | S2 | ok | 74d4d888a5 | - | - |
| 2026-11-18T08:55:07Z | S7 | ok | 74528a6b97 | - | - |
| 2026-11-18T09:01:14Z | S3 | ok | e55fb43b51 | - | - |
| 2026-11-18T09:01:14Z | S4 | ok | 5a2bc5b489 | - | - |
| 2026-11-18T09:20:01Z | S5 | ok | 4716c1de58 | - | - |
| 2026-11-18T09:20:01Z | S6 | ok | 8869f15d46 | - | - |
