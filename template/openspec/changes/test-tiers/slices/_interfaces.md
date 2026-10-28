# 公开接口摘要

## S1
92:def pytest_runtest_logreport(report):
132:def _hook(event, args):
152:def _write(rec):
165:def pytest_runtest_setup(item):
172:def pytest_runtest_call(item):
179:def pytest_runtest_teardown(item):
185:def pytest_sessionstart(session):
189:def pytest_runtest_logreport(report):
208:def now_iso():
212:def die(msg, code=2):
217:def git(root, *args):
224:def toplevel(cwd=None):
231:def load_plan(change_dir):
239:def save_plan(change_dir, data):
245:def run_cmd_full(cmd, cwd):
250:def _tail(out, n=6):
254:def run_cmd(cmd, cwd):
263:def _summary_failed(line):
273:def _read_probe(path):
304:def run_test_gate(cmd, root, probe=False):
374:def normalize_lines(text):
385:def plan_sha(data):
399:def load_baseline(change_dir):
410:def gate_cmd_verdict(kind, cmd, root, baseline):
434:def full_suite_verdict(cmd, root, baseline):
449:def glob_match(path, pattern):
457:def globs_intersect(a, b):
468:def compute_waves(slices):
486:def _nonblank(v):
490:def _lint_checks(gate):
534:def _repo_default_checks(change_dir):
562:def _tiers_path(change_dir):
567:def _tier_shape(label, obj, fields):
585:def _load_tiers_file(path):
634:def _load_tiers(change_dir):
638:def tiers_matching(path, tiers):
646:def _lint_tiers(data, change_dir):
700:def lint_plan(data, change_dir=None):
749:def timeline_record(change_dir, event, note=""):
761:def append_report(change_dir, result):
777:def _cell(text):
781:def ceiling_rows_from_json(raw):
800:def record_ceilings(change_dir, slice_id, rows):
832:def evidence_state(change_dir, slice_id):
851:def report_has_row(change_dir, slice_id, commit):
865:def is_test_path(path):
872:def is_doc_or_config(path):
879:def source_files(files, change_rel):
885:def is_bytecode(path):
890:def changed_files(root, base):
904:def added_lines(root, base):
928:def ceiling_rows(root, base):
951:def gwt_violations(root, test_files):
971:def _py_test_bodies(lines):
987:def _test_bodies(rel, lines):
1022:def ownership_violations(files, owns, change_rel, committed=()):
1038:def _py_decorators(source, func):
1052:def _pytest_head(cmd):
1074:def _derive_paths(rest):
1092:def _derive_verify(root, full_head, vcmd, cases, failed):
1117:def _g7_runner(gate):
1128:def _g7_timeout(gate):
1139:def _pytest_outcomes(root, targets, gate=None):
1177:def _g7_diag(text):
1183:def scenario_status(root, data, slice_ids=None):
1252:def detect_test_cmd(root):
1266:def cmd_lint(args, print_waves=True):
1276:def _is_ancestor(root, anc, desc):
1282:def _base_check(root, branch):
1295:def _ckpt_ref(change_dir, slice_id):
1299:def _ckpt_delete(root, ref):
1304:def _gate_ref(change_dir, slice_id):
1308:def _gate_save(root, change_dir, result):
1327:def _gate_load(root, ref):
1338:def _slice_owns(change_dir, slice_id):
1347:def _checkpoint(root):
1398:def cmd_checkpoint(args):
1415:def _ckpt_restore(root, ref, owns):
1447:def cmd_start(args):
1491:def _read_marker(root):
1502:def cmd_gate(args):
1593:def cmd_record(args):
1622:def _dirty_paths(root, change_dir):
1641:def cmd_final(args):
1694:def cmd_baseline(args):
1888:def _die_running_baseline(change_dir, bl, data):
1912:def cmd_preflight(args):
1947:def _has_approve(change_dir):
1956:def report_latest(change_dir):
1982:def _change_rel(root, change_dir):
1986:def _plan_file(rel, change_rel):
1993:def _other_change(rel, change_rel, keep_own=True):
2001:def _ignored(rel):
2006:def _git_raw(root, args, stdin=None):
2014:def _hash_paths(root, rels):
2021:def _snapshot(root, change_rel):
2052:def _blobs_at(root, commit, paths):
2067:def _repo_rel(root, tok):
2084:def cmd_key(root, change_rel, cmd):
2104:def _delta(root, cand, cur_snap, head, change_rel, same_change, strict=False):
2128:def _baseline_candidates(root, old, key, name, full):
2145:def _pool_dir(root):
2154:def _check_dir(root, change, name):
2166:def _check_env(phase, change, base_commit, cdir):
2172:def _run_check(cmd, root, env, timeout):
2193:def _check_log(cdir, phase, out):
2205:def _check_msg(head, log, out):
2213:def _final_checks(root, change_dir, checks, baseline):
2242:def _pool_order(name, entry):
2248:def _pool_read(pdir, name):
2257:def _pool_write(root, entry):
2297:def _pool_candidates(root, key, limit=10):
2315:def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache):
2364:def _run_changes(root, change_rel, s0, s1, prev_byproducts):
2386:def _verify_paths(root, cmd, delta):
2400:def _verify_rerun(root, cmd, prev, delta):
2410:def _final_fresh(root, change_dir, final_commit):
2430:def cmd_ship(args):
2477:def main():

## S4
仅文档/命令/schema 文件，无源码接口：template/.claude/commands/test-tiers.md 等。
