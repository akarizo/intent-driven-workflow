# 公开接口摘要

## S1

```
[21]{name,kind,signature}:
  KEEP_CHANGES,const,KEEP_CHANGES = 30
  LEDGER_DIR,const,"LEDGER_DIR = \"flight-ledger\""
  NO_TIER,const,"NO_TIER = \"-\""
  PHASES,const,"PHASES = (\"final\", \"baseline\")"
  _file_of,fn,"def _file_of(case_id, id_form, root)"
  _id_form,fn,"def _id_form(observations, universe, source)"
  _newest_mtime,fn,def _newest_mtime(d)
  _outcome,fn,def _outcome(o)
  _prune,fn,def _prune(base)
  _sec,fn,def _sec(v)
  _show,fn,def _show(args)
  _sort_key,fn,def _sort_key(item)
  _to_junit,fn,def _to_junit(nodeid)
  build,fn,"def build(meta, observations, universe=None, source=None, rerun_files=None, root=None, tier_of=None)"
  from_anchor,fn,def from_anchor(anchor)
  ledger_dir,fn,def ledger_dir(root)
  load,fn,"def load(root, change, name)"
  main,fn,def main(argv=None)
  save,fn,"def save(root, change, name, obj)"
  secs_of,fn,def secs_of(ledger)
  summary,fn,def summary(ledger)```

## S2

```
[100]{name,kind,signature}:
  ANCHOR_DIR,const,"ANCHOR_DIR = \"flight-anchors\""
  ANCHOR_HOPS,const,"ANCHOR_HOPS = \"final:anchor-hops\""
  ANCHOR_KEEP,const,ANCHOR_KEEP = 20
  ANCHOR_MAX_HOPS,const,ANCHOR_MAX_HOPS = 5
  ANSI_RE,const,"ANSI_RE = re.compile(r\"\\x1b\\[[0-9;]*[A-Za-z]\")"
  BASELINE,const,"BASELINE = \"gate-baseline.json\""
  BASELINE_NODES_IMPACTED,const,"BASELINE_NODES_IMPACTED = \"final:baseline-nodes-only-impacted\""
  BASELINE_NO_NODES,const,"BASELINE_NO_NODES = \"final:baseline-missing-failed-nodes\""
  BOOKKEEPING,const,"BOOKKEEPING = (\"timeline.md\", \"gate-report.md\", \"evidence.log\", \"review-findings.json\", \"tasks.md\","
  CEILING_COLS,const,"CEILING_COLS = \"| 时间 | 切片 | 位置 | 限制 | 升级路径 |\""
  CEILING_HEAD,const,"CEILING_HEAD = \"## 天花板\""
  CEILING_MIN,const,CEILING_MIN = 4
  CEILING_RE,const,"CEILING_RE = re.compile(r\"^\\s*(?:#|//|--|\\*)+\\s*ceiling\\s*:\\s*(.*)$\", re.I)"
  CEILING_SEP,const,"CEILING_SEP = \"|---|---|---|---|---|\""
  CEILING_SPLIT,const,"CEILING_SPLIT = re.compile(r\"->|→\")"
  CHECKS_DIR,const,"CHECKS_DIR = \"flight-gate-checks\""
  CHECK_FIELDS,const,"CHECK_FIELDS = (\"name\", \"baseline\", \"final\", \"timeout_sec\")"
  CHECK_NAME_RE,const,"CHECK_NAME_RE = re.compile(r\"[a-z0-9-]+\")"
  CONFIG_EXT,const,"CONFIG_EXT = {\".json\", \".yaml\", \".yml\", \".toml\", \".ini\", \".lock\", \".cfg\"}"
  COVERAGE_FAIL_MARKS,const,"COVERAGE_FAIL_MARKS = (\"Coverage failure: total of\", \"FAIL Required test coverage of\")"
  DECLARED_GLOBAL,const,"DECLARED_GLOBAL = \"declared-global:\""
  DEFAULT_CHECKS,const,"DEFAULT_CHECKS = \"gate-checks.json\""
  DEPS_CORE,const,"DEPS_CORE = '''import json, os, sys"
  DEPS_KIND_WHY,const,DEPS_KIND_WHY =
  DEPS_NO_OUTPUT,const,"DEPS_NO_OUTPUT = \"没有依赖图输出（不是 pytest？）\""
  DEPS_PLUGIN,const,DEPS_PLUGIN = DEPS_CORE + OUTCOME_SRC + '''
  DERIVE_UNSAFE,const,"DERIVE_UNSAFE = re.compile(r\"[;&|<>$`()*?!{}\\[\\]=~\\\\]\")"
  DERIVE_WHITELIST,const,"DERIVE_WHITELIST = {\"-q\", \"-qq\", \"-v\", \"-vv\", \"-x\", \"-s\", \"--no-header\"}"
  DIFF_HUNK_RE,const,"DIFF_HUNK_RE = re.compile(r\"^@@ .*?\\+(\\d+)\")"
  DOC_EXT,const,"DOC_EXT = {\".md\", \".mdx\", \".markdown\", \".txt\", \".rst\", \".html\"}"
  EARLY_STOP_MARKS,const,"EARLY_STOP_MARKS = (\"stopping after\", \"Interrupted:\")"
  EVIDENCE,const,"EVIDENCE = \"evidence.log\""
  FINAL_DIR,const,"FINAL_DIR = \"flight-final\""
  FLIGHT_ENV,const,"FLIGHT_ENV = (\"FLIGHT_GUARD_OWNER\", \"FLIGHT_GUARD_NESTED\", \"FLIGHT_GUARD_OK\", \"FLIGHT_GUARD_JUNIT\", \"FLIGHT_DEPS_OUT\","
  FLIGHT_PLUGIN_FAIL,const,"FLIGHT_PLUGIN_FAIL = re.compile(r'Error importing plugin \"flight_(?:guard|deps|tier_probe)\"')"
  FLIGHT_RECORDS,const,"FLIGHT_RECORDS = (TIMELINE, REPORT, EVIDENCE)"
  G7_PLUGIN,const,"G7_PLUGIN = '''import json, os"
  GITLINK_MODE,const,"GITLINK_MODE = \"160000\""
  GLOBAL_FILES,const,"GLOBAL_FILES = {\"conftest.py\", \"pytest.ini\", \"pyproject.toml\", \"setup.cfg\", \"tox.ini\", \"setup.py\", \"Pipfile\","
  GLOBAL_GLOBS,const,"GLOBAL_GLOBS = (\"requirements*.txt\",)"
  GUARD_PLUGIN,const,GUARD_PLUGIN = '''import os
  INERT_LINT_STATIC,const,"INERT_LINT_STATIC = (\"测试路径\", \"全局文件\", \"声明的 global\")"
  JS_BLOCK_START,const,"JS_BLOCK_START = re.compile(r\"^\\s*(?:test|it|describe)\\s*\\(\")"
  JS_TEST_DEF,const,"JS_TEST_DEF = re.compile(r\"^\\s*(?:test|it)\\s*\\(\\s*[\\'\\\"`](.+?)[\\'\\\"`]\")"
  LS_TREE_BATCH,const,LS_TREE_BATCH = 500
  MARKER,const,"MARKER = \".openspec-slice\""
  MARK_RE,const,"MARK_RE = re.compile(r\"xfail|skip\", re.I)"
  MAX_DEPTH,const,MAX_DEPTH = 3
  MAX_OWNS,const,MAX_OWNS = 12
  MAX_SLICES,const,MAX_SLICES = 9
  NODES_UNDIFFABLE,const,"NODES_UNDIFFABLE = \"基线只有 nodeid 形式的预存红，本次依赖图未测，无法差分；重跑 baseline --full\""
  NON_SOURCE_PREFIX,const,"NON_SOURCE_PREFIX = (\".claude/\", \"openspec/\", \"docs/\")"
  NO_ANCHOR,const,"NO_ANCHOR = \"final:no-anchor\""
  OUTCOME_LOWER,const,"OUTCOME_LOWER = {\"PASSED\": \"passed\", \"FAILED\": \"failed\", \"ERROR\": \"error\", \"SKIPPED\": \"skipped\", \"XFAIL\": \"xfailed\","
  OUTCOME_SRC,const,OUTCOME_SRC = '''
  PARTS_FULL_WHY,const,"PARTS_FULL_WHY = \"多部件分层：增量未支持（依赖图只认 pytest）\""
  PLAIN_TEST_CMDS,const,"PLAIN_TEST_CMDS = (\"npm test\", \"go test ./...\", \"cargo test\")"
  PLAN_DIRS,const,"PLAN_DIRS = (\"specs/\", \"slices/\")"
  PLAN_FILES,const,"PLAN_FILES = (\"proposal.md\", \"design.md\", \"tasks.md\", \"slices.json\", \"spec.html\", BASELINE, \".openspec.yaml\") + BOOKKEEPING"
```

## S7

仅文档（flight-runner-contract.md / test-tiers.md / pr-ship.md / README.md），无公开代码接口。

## S3

```
[9]{name,kind,signature}:
  NO_SEC_RATIO/SLOW_MIN_SEC/SLOW_RATIO/TIER_GROWTH_MIN_SEC/TIER_GROWTH_RATIO/TOP_N,const,草案常量
  advice,fn,def advice(d)  # 固定规则建议行，零 token
  delta,fn,"def delta(base, final, rerun_files=None, root=None)"  # -> (dict | None, str | None)
  parse_segment,fn,def parse_segment(note)  # 时间线备注 -> {added, removed, added_sec} | None
  render,fn,def render(d)  # Markdown，首行 "## 测试变更"
  segment,fn,def segment(d)  # "用例 +A/-R（新增 X.Xs）"
  _delta_cmd,fn,def _delta_cmd(args)  # delta 子命令
```

## S4

```
[4]{name,kind,signature}:
  _ledger_mod,fn,def _ledger_mod()  # 加载 test-ledger.py，失败返回原因字符串
  _ledger_commit,fn,"def _ledger_commit(root, name, meta, tiers, universe=None, source=None, rerun_files=None)"
  _ledger_secs,fn,def _ledger_secs(led)
  _ledger_source,fn,"def _ledger_source(root, change, commit)"
```

## S5

```
[0]{name,kind,signature}:
  （无新增公开符号：cmd_final 内部落账，输出 JSON 增 tests 键，经 S4 的 _ledger_* 完成）
```

## S6

```
[5]{name,kind,signature}:
  load_ledger,fn,def load_ledger()
  SLOWEST_N,const,SLOWEST_N = 10  # [tests] 最慢清单至多列 10 条
  RECENT_N,const,RECENT_N = 5  # [tests] 最近的测试变更至多列 5 个 change
  _last_segment,fn,"def _last_segment(change_dir, tl)"
  doctor_tests,fn,"def doctor_tests(openspec_root, changes)"
```
