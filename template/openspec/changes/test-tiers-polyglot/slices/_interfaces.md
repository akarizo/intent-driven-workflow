# 公开接口摘要

## S1

文件：template/.claude/hooks/slice-gate.py
```
616:TIER_FILE = "test-tiers.json"
618:TIER_NAME_RE = re.compile(r"[a-z0-9-]+")
621:TIER_DRIVER_CMD = "python3 .claude/hooks/test-tiers.py run unit"
622:TIER_LIST_TIMEOUT = 60
623:TIER_TEST_NAME_RE = re.compile(TEST_FILE_RE.pattern + r"|(^|/)([^/]*_test\.go|[^/]*(?:Tests?|IT)\.(?:java|kt)|[^/]*Tests?\.cs"
628:TIER_PROBE_PLUGIN = '''import json, os, sys
1359:def _load_tiers_file(path):
1430:def tiers_is_parts(tiers):
1434:def tier_parts(tiers):
1449:def tier_list(top, part, layer):
1471:def layer_matches(top, part, layer, path):
1487:def part_test_files(top, part, path):
1501:def is_canary(tiers, path):
1506:def parts_of(top, tiers, path):
1513:def tier_adapter_errors(top, tiers):
1562:def tiers_matching(path, tiers, top=None):
1611:def _lint_tiers(data, change_dir):
```

## S5

仅文档/命令/schema 改动，无公开代码接口。
