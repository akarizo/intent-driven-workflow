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
