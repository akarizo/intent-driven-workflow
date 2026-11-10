# 公开接口摘要

## S1

`template/.claude/hooks/takeoff-gate.py`（`tests/test_goal_takeoff.py` 为测试）

```
59:def parse_ts(value):
77:def iso(dt):
81:def row_time(row):
89:def queued_prompt(row):
101:def human_text(row):
140:def approval_of(text):
149:def summarize(text):
158:def load_rows(path):
174:def latest_approval(rows):
192:def active_goal(rows):
212:def plan_mtime(change_dir):
220:def verdict(change_dir, session):
245:def locate_cli(session_arg):
252:def locate_by_sid(sid):
260:def run_cli(args):
279:def emit_deny(reason):
287:def find_change_dir(payload):
307:def locate_hook(payload):
316:def is_takeoff_dispatch(payload):
334:def run_hook(raw):
350:def main(argv=None):
```
