# 公开接口摘要

> 由 integrator 在合回切片后生成（每切片一节，重复合回时覆盖该节）。只列签名与一行说明。

## S1

`template/.claude/hooks/flight-lock.py`
- `lock_dir()` 锁目录（`FLIGHT_LOCK_DIR`，缺省 `~/.claude/flight-lock`）
- `class Hold` 一次持锁的句柄（含 state / why / waited，`release()`）
- `holders()` 列出在世持有者，顺手清理死进程文件
- `acquire(mode, change="", label="", expect_sec=None)` 取全机读写锁（共享 / 独占），排队轮询，超 `cap_sec` 放弃
- `note(info)` 生成写入备注的锁信息
- `main(argv=None)` CLI：`run` / `status`

`tests/lock_helpers.py`（S3 / S4 / S5 测试只读共用）
- `lock_env(lock_dir, **extra)` 构造带锁目录的子进程环境
- `wait_for(pred, timeout=10.0, step=0.02)` 轮询等条件
- `last_info(text)` 取输出里最后一条锁信息
- `class Run` 子进程运行封装；`class Locks` 锁场景工具

## S2

`template/.claude/hooks/flight-doctor.py`
- `note_costs(note)` 从备注解析耗时 / 锁等待
- `parse_note(note)` / `classify(reason)` 备注解析与归类
- `cost(change_dir)` 读时间线汇总成本（兼容旧备注）
- `cost_text(c)` 成本文本渲染

## S4

`template/.claude/hooks/flight-doctor.py`
- `load_lock()` 按路径加载 flight-lock.py，失败返回 None
- `doctor_checks(changes)` `[checks]` 节：点名耗时接近测试耗时的检查
- `doctor_lock()` `[lock]` 节：当前持有者 / 空闲 / 已关闭

## S3

`template/.claude/hooks/flight-lock.py`
- `_clear_stale_holders(hd)` 清理 pid 被复用的陈旧持有者文件

`template/.claude/hooks/slice-gate.py`
- `_load_flight_lock()` 按路径加载 flight-lock.py（只加载一次，失败记原因）
- `class _NoLock` 加载失败时的占位持有对象
- `flight_lock(mode, change="", label="", expect_sec=None)` 取锁，不抛异常
- `_lock_note(info)` 锁片段写入时间线备注
- `_lock_expect_sec(baseline, gate)` 估算预期耗时
- `_time_verdicts(failed, warnings, lock_info)` 争抢时把 G10 降为警告
- `_baseline_parts(..., lock_info=None)` / `_final_parts(..., lock_info=None)` 备注与输出带锁信息

## S5

`template/.claude/hooks/slice-gate.py`
- `_final_checks(root, change_dir, checks, baseline, final_ctx=None, secs=None)` final 检查；新增 `secs` 收集测试与检查秒数，备注带「测试 Xs」片段

`template/.claude/hooks/test-tiers.py`
- `_probe(args, top, root)` probe 子命令；run / probe 持独占锁

## S6

无代码接口（仅文档：flight-runner-contract.md 第 8 节「全机测试锁」、opsx-apply / opsx-propose 命令与 skill、test-tiers.md、README.md）。
