# 公开接口摘要

## S1
### template/.claude/hooks/slice-gate.py
118:def _outcome(report):
137:def pytest_runtest_logreport(report):
162:def pytest_configure(config):
181:def pytest_unconfigure(config):
192:def pytest_configure_node(node):
205:def _nested():
209:def _abs_rel(p):
216:def _repo_rel(path, cwd=None):
237:def _argv(args):
246:def _is_blind(executable, argv, env):
265:def _observe(event, args, deps):
285:def _emit(recs):
325:def _hook(event, args):
343:def _key(node):
348:def _enter(key):
355:def _leave():
360:def pytest_configure(config):
365:def pytest_sessionstart(session):
371:def pytest_make_collect_report(collector):
380:def _window(item):
393:def pytest_fixture_setup(fixturedef, request):
403:def _run_window(item):
413:def pytest_runtest_setup(item):
418:def pytest_runtest_call(item):
423:def pytest_runtest_teardown(item):
427:def _rootdir():
432:def pytest_runtest_logreport(report):
444:def _chain(path):
455:def _resolve(mod, level, path, roots):
483:def _imports(path, roots):
511:def _closure(key, roots):
524:def _conftests(key):
535:def pytest_sessionfinish(session):
570:def _flight_site():
655:def _hook(event, args):
675:def _write(rec):
688:def pytest_runtest_setup(item):
700:def pytest_runtest_call(item):
707:def pytest_runtest_teardown(item):
713:def pytest_sessionstart(session):
717:def pytest_runtest_logreport(report):
739:def now_iso():
743:def die(msg, code=2):
748:def git(root, *args):
755:def toplevel(cwd=None):
762:def load_plan(change_dir):
770:def save_plan(change_dir, data):
776:def run_cmd_full(cmd, cwd):
781:def _tail(out, n=6):
785:def run_cmd(cmd, cwd):
794:def _summary_failed(line):
804:def _read_probe(path, by_top=False):
838:def _drop_inherited(env):
862:def _flight_plugins(tmp, env, root, deps):
883:def _read_deps(path):
936:def _deps_merge(a, b):
949:def run_test_gate(cmd, root, probe=False, deps=False, _plain=False, extra_env=None, cwd=None):
1039:def normalize_lines(text):
1050:def plan_sha(data):
1066:def load_baseline(change_dir):
1077:def gate_cmd_verdict(kind, cmd, root, baseline):
1101:def _diff_verdict(label, tg, known_failed):
1115:def _tg_measurable(tg):
1124:def _selected_regions(gate):
1130:def slow_candidates(probe):
1137:def tier_verdicts(probe, probe_why, rerun, allow):
1162:def _root_id(root, nid):
1168:def _junit_secs(paths, root, name):
1189:def run_part(top, name, part, probe=True):
1231:def part_tier_verdicts(name, res, rerun, allow):
1264:def part_tier_verdict(top, name, part, res, allow):
1279:def _baseline_parts(top, tiers, reasons, warnings):
1305:def _final_parts(top, tiers, gate, baseline, failed, warnings):
1341:def glob_match(path, pattern):
1349:def globs_intersect(a, b):
1360:def compute_waves(slices):
1378:def _nonblank(v):
1382:def _lint_checks(gate):
1426:def _repo_default_checks(change_dir):
1454:def _tiers_path(change_dir):
1467:def _scope_decl_path(change_dir):
1472:def _git_top(cwd):
1481:def _scope_decl(change_dir):
1513:def _scope_provider(gate, change_dir):
1523:def _plain_test_cmd(cmd):
1538:def _planned_owns(data):
1544:def _establishes_decl(data, change_dir):
1554:def _builtin_by_design(gate, tiers):
1559:def _builtin_report(root, change_dir, data, phase):
1615:def _scope_report_errors(r):
1641:def _run_scope(cmd, root, planned=(), change_rel=""):
1669:def _scope_reason_errors(report, reasons, pending=()):
1686:def _undeclared_msg(change_dir):
1692:def _lint_scope(gate, change_dir, run_scope, data=None, phase="lint"):
1744:def _tier_shape(label, obj, fields, selector=False):
1768:def _tier_root_ok(root):
1772:def _probe_shape(label, probe):
1795:def _parts_shape(tiers):
1852:def _load_tiers_file(path):
1904:def _load_tiers(change_dir):
1908:def _tier_root_errors(top, parts):
1914:def _tiers_raw(path):
1923:def tiers_is_parts(tiers):
1927:def tier_parts(tiers):
1934:def _tier_regions(tiers):
1942:def tier_list(top, part, layer):
1964:def layer_matches(top, part, layer, path):
1972:def _layer_hit(top, part, layer, path):
1980:def part_test_files(top, part, path):
1994:def is_canary(tiers, path):
1999:def parts_of(top, tiers, path):
2006:def probe_files(top, root, cmd):
2020:def tier_adapter_errors(top, tiers):
2060:def _g12_parts(top, tiers, chosen, files):
2084:def tiers_matching(path, tiers, top=None):
2099:def tier_seconds(durations, tiers):
2119:def _tier_add(ts, unit=0.0, regions=None):
2129:def _tier_note(ts):
2133:def _tier_parts_sec(top, tiers, durations=None, unit=None, regions=None):
2153:def _lint_tiers(data, change_dir):
2231:def lint_plan(data, change_dir=None, run_scope=False, phase="lint"):
2288:def timeline_record(change_dir, event, note=""):
2300:def append_report(change_dir, result):
2316:def _cell(text):
2320:def ceiling_rows_from_json(raw):
2339:def record_ceilings(change_dir, slice_id, rows):
2371:def evidence_state(change_dir, slice_id):
2390:def report_has_row(change_dir, slice_id, commit):
2404:def is_test_path(path):
2411:def is_doc_or_config(path):
2418:def source_files(files, change_rel):
2424:def is_bytecode(path):
2429:def changed_files(root, base):
2451:def _gitlinks(root):
2462:def _sub_ready(root, p):
2466:def _sub_git(root, p, *args):
2470:def _sub_has(root, p, sha):
2474:def _sub_head(root, p):
2479:def _recorded_gitlink(root, p):
2485:def _sub_diff_names(root, p, old, new):
2490:def _gitlink_raw_diff(root, base):
2501:def _expand_committed(root, base, committed):
2509:def _expand_uncommitted(root, links, uncommitted):
2530:def gitlink_violations(root):
2543:def anchor_submodules(root, base, change_dir, slice_id):
2562:def added_lines(root, base):
2586:def ceiling_rows(root, base):
2609:def gwt_violations(root, test_files):
2629:def _py_test_bodies(lines):
2645:def _test_bodies(rel, lines):
2680:def ownership_violations(files, owns, change_rel, committed=()):
2696:def _py_decorators(source, func):
2710:def _pytest_head(cmd):
2732:def _derive_paths(rest):
2750:def _uncovered_opts(root, rest, runner):
2764:def _derive_verify(root, full_head, vcmd, cases, failed):
2789:def _g7_runner(gate):
2800:def _g7_timeout(gate):
2811:def _pytest_outcomes(root, targets, gate=None, durations=None, deps_out=None, probe_out=None):
2880:def _tier_rerun(root, gate, nodeids):
2902:def _unit_tier_verdict(root, gate, tg, allow):
2909:def _g7_diag(text):
2915:def scenario_status(root, data, slice_ids=None, durations=None):
2984:def detect_test_cmd(root):
2998:def cmd_lint(args, print_waves=True):
3008:def _is_ancestor(root, anc, desc):
3014:def _base_check(root, branch):
3027:def _ckpt_ref(change_dir, slice_id):
3031:def _ckpt_delete(root, ref):
3036:def _gate_ref(change_dir, slice_id):
3040:def _gate_save(root, change_dir, result):
3059:def _gate_load(root, ref):
3070:def _slice_owns(change_dir, slice_id):
3079:def _checkpoint(root):
3130:def cmd_checkpoint(args):
3147:def _ckpt_restore(root, ref, owns):
3179:def cmd_start(args):
3223:def _read_marker(root):
3234:def cmd_gate(args):
3339:def cmd_record(args):
3368:def _dirty_paths(root, change_dir):
3387:def cmd_final(args):
3678:def cmd_baseline(args):
3954:def _die_running_baseline(change_dir, bl, data):
3978:def cmd_preflight(args):
4030:def _has_approve(change_dir):
4039:def report_latest(change_dir):
4065:def _change_rel(root, change_dir):
4069:def _plan_file(rel, change_rel):
4076:def _other_change(rel, change_rel, keep_own=True):
4084:def _ignored(rel):
4089:def _git_raw(root, args, stdin=None):
4097:def _hash_paths(root, rels):
4104:def _snapshot(root, change_rel):
4135:def _blobs_at(root, commit, paths):
4150:def _repo_rel(root, tok):
4167:def cmd_key(root, change_rel, cmd):
4187:def _delta(root, cand, cur_snap, head, change_rel, same_change, strict=False):
4211:def _baseline_candidates(root, old, key, name, full):
4228:def _pool_dir(root, sub=POOL_DIR):
4242:def _check_dir(root, change, name):
4254:def _final_env(final_ctx, ddir):
4266:def _check_env(phase, change, base_commit, cdir, final_ctx=None):
4276:def _run_check(cmd, root, env, timeout):
4297:def _check_log(cdir, phase, out):
4309:def _check_msg(head, log, out):
4317:def _final_checks(root, change_dir, checks, baseline, final_ctx=None):
4346:def _pool_order(name, entry):
4352:def _pool_read(pdir, name):
4361:def _pool_write(root, entry, sub=POOL_DIR, keep=POOL_KEEP, label="基线池"):
4401:def _anchor_key(root, change_rel, test_cmd, gate):
4410:def _anchor_write(root, entry):
4415:def _anchor_candidates(root, cmd_key, tiers_key, limit=10):
4430:def _json_sha1(obj):
4434:def _tiers_key(root, change_dir, tiers):
4447:def _tiers_detail(tiers):
4456:def _node_counts(nodeids):
4465:def _py_test_file(rel):
4469:def _global_file(rel):
4474:def _final_fps(root, change_rel, data, tiers):
4492:def _final_rec_read(root, name):
4499:def _final_rec_write(root, name, rec):
4519:def _final_reusable(root, rec, cur_snap, head, change_rel, fps):
4530:def _last_green(rec):
4540:def _impacted_anchor(root, rec, baseline, cur_snap, head, change_rel, name, fps):
4560:def _pick_anchor(root, key, tkey, cur_snap, head, change_rel, name):
4575:def _decl_rels(root, change_dir):
4581:def _unreproducible_why(root, gate):
4594:def _full_triggers(root, delta, anchor, baseline, gate, tier_rel=None, decl_rels=(), impacted=False):
4630:def _full_why(root, full, pick, baseline, snap_why, impacted=False, gate=None, tier_rel=None, decl_rels=()):
4654:def _approved_reasons(root, change_dir):
4669:def _g2_scope(err):
4674:def _final_scope_guard(root, change_dir, data, why, triggers):
4722:def _is_shell(root, rel):
4735:def _sh_refs(root, rel):
4788:def _shell_closure(root, files, memo=None):
4810:def _final_select(root, anchor, delta):
4821:def _anchor_forward(root, old, sel, d, fails, outcomes):
4840:def _pool_candidates(root, key, limit=10, sub=POOL_DIR, pred=None):
4858:def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache):
4907:def _run_changes(root, change_rel, s0, s1, prev_byproducts):
4929:def _verify_paths(root, cmd, delta):
4943:def _verify_rerun(root, cmd, prev, delta):
4953:def _is_bookkeeping(rel, changes_rel):
4962:def _final_fresh(root, change_dir, final_commit):
4973:def cmd_ship(args):
5020:def cmd_scope_seed(args):
5064:def main():
### tests/submodule_helpers.py
31:def test_{fn}():
41:def g(cwd, *args):
47:def git_rc(cwd, *args):
51:def _ident(repo):
56:def _slice(sid, mod, deps=()):
67:def plan_data():
76:def make_super(tmp_path):
116:def iso(env, name, ref=BRANCH):
123:def start(cwd, sid, *extra):
127:def gate(cwd, sid):
132:def write_impl(cwd, mod, extra=""):
140:def commit_sub(cwd, msg, paths):
147:def commit_parent(cwd, msg, *paths):
153:def run_executor(env, sid, mod, name=None):

## S4
### template/.claude/workflows/opsx-apply.js
20:export const meta = {
(其余为文档 / 提示词文件，无公开签名)
