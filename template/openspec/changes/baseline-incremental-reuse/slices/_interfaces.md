# 公开接口摘要

## S1

### template/.claude/hooks/slice-gate.py
[100]{name,kind,signature}:
  ANSI_RE,const,"ANSI_RE = re.compile(r\"\\x1b\\[[0-9;]*[A-Za-z]\")"
  BASELINE,const,"BASELINE = \"gate-baseline.json\""
  BOOKKEEPING,const,"BOOKKEEPING = (\"timeline.md\", \"gate-report.md\", \"evidence.log\", \"review-findings.json\", \"tasks.md\","
  CEILING_COLS,const,"CEILING_COLS = \"| 时间 | 切片 | 位置 | 限制 | 升级路径 |\""
  CEILING_HEAD,const,"CEILING_HEAD = \"## 天花板\""
  CEILING_MIN,const,CEILING_MIN = 4
  CEILING_RE,const,"CEILING_RE = re.compile(r\"^\\s*(?:#|//|--|\\*)+\\s*ceiling\\s*:\\s*(.*)$\", re.I)"
  CEILING_SEP,const,"CEILING_SEP = \"|---|---|---|---|---|\""
  CEILING_SPLIT,const,"CEILING_SPLIT = re.compile(r\"->|→\")"
  CONFIG_EXT,const,"CONFIG_EXT = {\".json\", \".yaml\", \".yml\", \".toml\", \".ini\", \".lock\", \".cfg\"}"
  COVERAGE_FAIL_MARKS,const,"COVERAGE_FAIL_MARKS = (\"Coverage failure: total of\", \"FAIL Required test coverage of\")"
  DIFF_HUNK_RE,const,"DIFF_HUNK_RE = re.compile(r\"^@@ .*?\\+(\\d+)\")"
  DOC_EXT,const,"DOC_EXT = {\".md\", \".mdx\", \".markdown\", \".txt\", \".rst\", \".html\"}"
  EVIDENCE,const,"EVIDENCE = \"evidence.log\""
  FLIGHT_RECORDS,const,"FLIGHT_RECORDS = (TIMELINE, REPORT, EVIDENCE)"
  G7_PLUGIN,const,"G7_PLUGIN = '''import json, os"
  JS_BLOCK_START,const,"JS_BLOCK_START = re.compile(r\"^\\s*(?:test|it|describe)\\s*\\(\")"
  JS_TEST_DEF,const,"JS_TEST_DEF = re.compile(r\"^\\s*(?:test|it)\\s*\\(\\s*[\\'\\\"`](.+?)[\\'\\\"`]\")"
  LS_TREE_BATCH,const,LS_TREE_BATCH = 500
  MARKER,const,"MARKER = \".openspec-slice\""
  MARK_RE,const,"MARK_RE = re.compile(r\"xfail|skip\", re.I)"
  MAX_DEPTH,const,MAX_DEPTH = 3
  MAX_OWNS,const,MAX_OWNS = 12
  MAX_SLICES,const,MAX_SLICES = 9
  NON_SOURCE_PREFIX,const,"NON_SOURCE_PREFIX = (\".claude/\", \"openspec/\", \"docs/\")"
  PLAN_DIRS,const,"PLAN_DIRS = (\"specs/\", \"slices/\")"
  PLAN_FILES,const,"PLAN_FILES = (\"proposal.md\", \"design.md\", \"tasks.md\", \"slices.json\", \"spec.html\", BASELINE, \".openspec.yaml\") + BOOKKEEPING"
  PYTEST_SUMMARY_RE,const,"PYTEST_SUMMARY_RE = re.compile(r\"^=*\\s*(\\d+ [a-z]+(?:, \\d+ [a-z]+)*) in [\\d.]+s(?: \\([^)]*\\))?\\s*=*$\")"
  PY_TEST_DEF,const,"PY_TEST_DEF = re.compile(r\"^(\\s*)(?:async\\s+)?def\\s+(test_\\w+)\\s*\\(\")"
  REPORT,const,"REPORT = \"gate-report.md\""
  TEST_DIR_NAMES,const,"TEST_DIR_NAMES = {\"tests\", \"test\", \"__tests__\", \"spec\"}"
  TEST_FILE_RE,const,"TEST_FILE_RE = re.compile(r\"(^|/)(test_[^/]*\\.py|[^/]*_test\\.py|[^/]*\\.test\\.[^/]+|[^/]*\\.spec\\.[^/]+)$\")"
  TIMELINE,const,"TIMELINE = \"timeline.md\""
  VERIFY_TOOL_RE,const,"VERIFY_TOOL_RE = re.compile(r\"\\b(tsc|typecheck|eslint|rustfmt|clippy|ruff|mypy|flake8|golangci)\\b\")"
  _base_check,fn,"def _base_check(root, branch)"
  _baseline_candidates,fn,"def _baseline_candidates(root, old, key, name, full)"
  _blobs_at,fn,"def _blobs_at(root, commit, paths)"
  _cell,fn,def _cell(text)
  _change_rel,fn,"def _change_rel(root, change_dir)"
  _checkpoint,fn,def _checkpoint(root)
  _ckpt_delete,fn,"def _ckpt_delete(root, ref):\n    # 引用不存在时 update-ref -d 也可能非 0：一律忽略"
  _ckpt_ref,fn,"def _ckpt_ref(change_dir, slice_id)"
  _ckpt_restore,fn,"def _ckpt_restore(root, ref, owns)"
  _delta,fn,"def _delta(root, cand, cur_snap, head, change_rel, same_change)"
  _die_running_baseline,fn,"def _die_running_baseline(change_dir, bl, data)"
  _dirty_paths,fn,"def _dirty_paths(root, change_dir)"
  _final_fresh,fn,"def _final_fresh(root, change_dir, final_commit)"
  _g7_diag,fn,def _g7_diag(text)
  _g7_runner,fn,def _g7_runner(gate)
  _g7_timeout,fn,def _g7_timeout(gate)
  _gate_load,fn,"def _gate_load(root, ref)"
  _gate_ref,fn,"def _gate_ref(change_dir, slice_id)"
  _gate_save,fn,"def _gate_save(root, change_dir, result)"
  _git_raw,fn,"def _git_raw(root, args, stdin=None)"
  _has_approve,fn,def _has_approve(change_dir)
  _hash_paths,fn,"def _hash_paths(root, rels)"
  _ignored,fn,def _ignored(rel)
  _is_ancestor,fn,"def _is_ancestor(root, anc, desc):\n    # 不能用 git()：--is-ancestor 不成立时退出 1，git() 会当成异常抛；任何非 0 都按「不成立」"
  _other_change,fn,"def _other_change(rel, change_rel, keep_own=True)"
  _plan_file,fn,"def _plan_file(rel, change_rel)"
  _py_decorators,fn,"def _py_decorators(source, func)"
  _py_test_bodies,fn,def _py_test_bodies(lines)
  _pytest_outcomes,fn,"def _pytest_outcomes(root, targets, gate=None)"
  _read_marker,fn,def _read_marker(root)
  _repo_rel,fn,"def _repo_rel(root, tok)"
  _run_changes,fn,"def _run_changes(root, change_rel, s0, s1, prev_byproducts)"
  _slice_owns,fn,"def _slice_owns(change_dir, slice_id)"
  _snapshot,fn,"def _snapshot(root, change_rel)"
  _summary_failed,fn,def _summary_failed(line)
  _tail,fn,"def _tail(out, n=6)"
  _test_bodies,fn,"def _test_bodies(rel, lines)"
  _try_reuse,fn,"def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache)"
  _verify_paths,fn,"def _verify_paths(root, cmd, delta)"
  _verify_rerun,fn,"def _verify_rerun(root, cmd, prev, delta)"
  added_lines,fn,"def added_lines(root, base)"
  append_report,fn,"def append_report(change_dir, result)"
  ceiling_rows,fn,"def ceiling_rows(root, base)"
  ceiling_rows_from_json,fn,def ceiling_rows_from_json(raw)
  changed_files,fn,"def changed_files(root, base)"
  cmd_baseline,fn,def cmd_baseline(args)
  cmd_checkpoint,fn,def cmd_checkpoint(args)
  cmd_final,fn,def cmd_final(args)
  cmd_gate,fn,def cmd_gate(args)
  cmd_key,fn,"def cmd_key(root, change_rel, cmd)"
  cmd_lint,fn,"def cmd_lint(args, print_waves=True)"
  cmd_preflight,fn,def cmd_preflight(args)
  cmd_record,fn,def cmd_record(args)
  cmd_ship,fn,def cmd_ship(args)
  cmd_start,fn,def cmd_start(args)
  compute_waves,fn,def compute_waves(slices)
  detect_test_cmd,fn,def detect_test_cmd(root)
  die,fn,"def die(msg, code=2)"
  evidence_state,fn,"def evidence_state(change_dir, slice_id)"
  full_suite_verdict,fn,"def full_suite_verdict(cmd, root, baseline)"
  gate_cmd_verdict,fn,"def gate_cmd_verdict(kind, cmd, root, baseline)"
  git,fn,"def git(root, *args)"
  glob_match,fn,"def glob_match(path, pattern)"
  globs_intersect,fn,"def globs_intersect(a, b)"
  gwt_violations,fn,"def gwt_violations(root, test_files)"
  is_bytecode,fn,def is_bytecode(path)
## S4

仅文档/README/测试，无公开代码接口（opsx-propose.md、openspec-propose SKILL.md 第 5 步增量复用说明）。
