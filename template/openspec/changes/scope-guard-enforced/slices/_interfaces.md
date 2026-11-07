# 公开接口摘要

## S1

### template/.claude/hooks/slice-gate.py
```
118:def _outcome(report):
205:def _nested():
209:def _abs_rel(p):
216:def _repo_rel(path, cwd=None):
237:def _argv(args):
246:def _is_blind(executable, argv, env):
285:def _emit(recs):
343:def _key(node):
348:def _enter(key):
355:def _leave():
380:def _window(item):
403:def _run_window(item):
427:def _rootdir():
444:def _chain(path):
455:def _resolve(mod, level, path, roots):
483:def _imports(path, roots):
511:def _closure(key, roots):
524:def _conftests(key):
570:def _flight_site():
675:def _write(rec):
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
```
### template/.claude/hooks/spec_html.py
```
49:def now_iso(now_arg):
58:def read_text(path):
65:def esc(s):
69:def inline_md(text):
76:def split_sections(text, level="##"):
94:def paragraphs(text):
98:def list_items(text):
107:def substitute_block(html_text, name, content):
117:def render_why(proposal_text):
130:def render_what(proposal_text):
149:def render_capabilities(proposal_text):
176:def render_scenario(name, body):
187:def render_requirement(heading, body):
201:def render_specs(change_dir):
231:def extract_diagrams(design_text):
246:def render_diagrams(design_text):
260:def strip_mermaid(text):
264:def render_generic_md(text):
283:def render_design(design_text):
311:def project_root(change_dir):
316:def scan_adrs(change_dir):
356:def render_tasks(tasks_text):
386:def compute_waves(slices):
400:def find_def_line(lines, func):
411:def decorator_source(source, func):
424:def scenario_flight_status(root, rel, func):
450:def gate_report_passed_slices(change_dir):
466:def load_timeline_rows(change_dir):
481:def scope_provider(gate, change_dir):
501:def establishes_scope_decl(gate_owns, change_dir):
518:def render_scope(gate, change_dir, owns=()):
539:def render_flight(change_dir):
605:def compute_meta_chips(change_dir, change_name):
644:def render_footer(now, section_count, diagram_count, task_count):
656:def render(change_dir, template_path, out_path, now_arg):
707:def main():
```
### tests/conftest.py
```
16:def hook_path(name: str) -> pathlib.Path:
38:def git(repo, *args: str) -> str:
42:def write(path: pathlib.Path, text: str) -> pathlib.Path:
48:def commit_all(repo, msg: str) -> str:
59:def git_repo(tmp_path):
```

## S2

### template/.claude/hooks/slice-gate.py（内建提供方精度，签名见 S1 节同文件，以下为当前全量）
```
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
1554:def _builtin_report(root, change_dir, data, phase):
1610:def _scope_report_errors(r):
1636:def _run_scope(cmd, root, planned=(), change_rel=""):
1664:def _scope_reason_errors(report, reasons, pending=()):
1681:def _lint_scope(gate, change_dir, run_scope, data=None, phase="lint"):
1734:def _tier_shape(label, obj, fields, selector=False):
1758:def _tier_root_ok(root):
1762:def _probe_shape(label, probe):
1785:def _parts_shape(tiers):
1842:def _load_tiers_file(path):
1894:def _load_tiers(change_dir):
1898:def _tier_root_errors(top, parts):
1904:def _tiers_raw(path):
1913:def tiers_is_parts(tiers):
1917:def tier_parts(tiers):
1924:def _tier_regions(tiers):
1932:def tier_list(top, part, layer):
1954:def layer_matches(top, part, layer, path):
1962:def _layer_hit(top, part, layer, path):
1970:def part_test_files(top, part, path):
1984:def is_canary(tiers, path):
1989:def parts_of(top, tiers, path):
1996:def probe_files(top, root, cmd):
2010:def tier_adapter_errors(top, tiers):
2050:def _g12_parts(top, tiers, chosen, files):
2074:def tiers_matching(path, tiers, top=None):
2089:def tier_seconds(durations, tiers):
2109:def _tier_add(ts, unit=0.0, regions=None):
2119:def _tier_note(ts):
2123:def _tier_parts_sec(top, tiers, durations=None, unit=None, regions=None):
2143:def _lint_tiers(data, change_dir):
2221:def lint_plan(data, change_dir=None, run_scope=False, phase="lint"):
2278:def timeline_record(change_dir, event, note=""):
2290:def append_report(change_dir, result):
2306:def _cell(text):
2310:def ceiling_rows_from_json(raw):
2329:def record_ceilings(change_dir, slice_id, rows):
2361:def evidence_state(change_dir, slice_id):
2380:def report_has_row(change_dir, slice_id, commit):
2394:def is_test_path(path):
2401:def is_doc_or_config(path):
2408:def source_files(files, change_rel):
2414:def is_bytecode(path):
2419:def changed_files(root, base):
2433:def added_lines(root, base):
2457:def ceiling_rows(root, base):
2480:def gwt_violations(root, test_files):
2500:def _py_test_bodies(lines):
2516:def _test_bodies(rel, lines):
2551:def ownership_violations(files, owns, change_rel, committed=()):
2567:def _py_decorators(source, func):
2581:def _pytest_head(cmd):
2603:def _derive_paths(rest):
2621:def _uncovered_opts(root, rest, runner):
2635:def _derive_verify(root, full_head, vcmd, cases, failed):
2660:def _g7_runner(gate):
2671:def _g7_timeout(gate):
2682:def _pytest_outcomes(root, targets, gate=None, durations=None, deps_out=None, probe_out=None):
2751:def _tier_rerun(root, gate, nodeids):
2773:def _unit_tier_verdict(root, gate, tg, allow):
2780:def _g7_diag(text):
2786:def scenario_status(root, data, slice_ids=None, durations=None):
2855:def detect_test_cmd(root):
2869:def cmd_lint(args, print_waves=True):
2879:def _is_ancestor(root, anc, desc):
2885:def _base_check(root, branch):
2898:def _ckpt_ref(change_dir, slice_id):
2902:def _ckpt_delete(root, ref):
2907:def _gate_ref(change_dir, slice_id):
2911:def _gate_save(root, change_dir, result):
2930:def _gate_load(root, ref):
2941:def _slice_owns(change_dir, slice_id):
2950:def _checkpoint(root):
3001:def cmd_checkpoint(args):
3018:def _ckpt_restore(root, ref, owns):
3050:def cmd_start(args):
3094:def _read_marker(root):
3105:def cmd_gate(args):
3208:def cmd_record(args):
3237:def _dirty_paths(root, change_dir):
3256:def cmd_final(args):
3534:def cmd_baseline(args):
3806:def _die_running_baseline(change_dir, bl, data):
3830:def cmd_preflight(args):
3882:def _has_approve(change_dir):
3891:def report_latest(change_dir):
3917:def _change_rel(root, change_dir):
3921:def _plan_file(rel, change_rel):
3928:def _other_change(rel, change_rel, keep_own=True):
3936:def _ignored(rel):
3941:def _git_raw(root, args, stdin=None):
3949:def _hash_paths(root, rels):
3956:def _snapshot(root, change_rel):
3987:def _blobs_at(root, commit, paths):
4002:def _repo_rel(root, tok):
4019:def cmd_key(root, change_rel, cmd):
4039:def _delta(root, cand, cur_snap, head, change_rel, same_change, strict=False):
4063:def _baseline_candidates(root, old, key, name, full):
4080:def _pool_dir(root, sub=POOL_DIR):
4094:def _check_dir(root, change, name):
4106:def _final_env(final_ctx, ddir):
4118:def _check_env(phase, change, base_commit, cdir, final_ctx=None):
4128:def _run_check(cmd, root, env, timeout):
4149:def _check_log(cdir, phase, out):
4161:def _check_msg(head, log, out):
4169:def _final_checks(root, change_dir, checks, baseline, final_ctx=None):
4198:def _pool_order(name, entry):
4204:def _pool_read(pdir, name):
4213:def _pool_write(root, entry, sub=POOL_DIR, keep=POOL_KEEP, label="基线池"):
4253:def _anchor_key(root, change_rel, test_cmd, gate):
4262:def _anchor_write(root, entry):
4267:def _anchor_candidates(root, cmd_key, tiers_key, limit=10):
4282:def _json_sha1(obj):
4286:def _tiers_key(root, change_dir, tiers):
4299:def _tiers_detail(tiers):
4308:def _node_counts(nodeids):
4317:def _py_test_file(rel):
4321:def _global_file(rel):
4326:def _final_fps(root, change_rel, data, tiers):
4344:def _final_rec_read(root, name):
4351:def _final_rec_write(root, name, rec):
4371:def _final_reusable(root, rec, cur_snap, head, change_rel, fps):
4382:def _last_green(rec):
4392:def _impacted_anchor(root, rec, baseline, cur_snap, head, change_rel, name, fps):
4412:def _pick_anchor(root, key, tkey, cur_snap, head, change_rel, name):
4427:def _decl_rels(root, change_dir):
4433:def _unreproducible_why(root, gate):
4446:def _full_triggers(root, delta, anchor, baseline, gate, tier_rel=None, decl_rels=(), impacted=False):
4482:def _full_why(root, full, pick, baseline, snap_why, impacted=False, gate=None, tier_rel=None, decl_rels=()):
4516:def _is_shell(root, rel):
4529:def _sh_refs(root, rel):
4582:def _shell_closure(root, files, memo=None):
4604:def _final_select(root, anchor, delta):
4615:def _anchor_forward(root, old, sel, d, fails, outcomes):
4634:def _pool_candidates(root, key, limit=10, sub=POOL_DIR, pred=None):
4652:def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache):
4701:def _run_changes(root, change_rel, s0, s1, prev_byproducts):
4723:def _verify_paths(root, cmd, delta):
4737:def _verify_rerun(root, cmd, prev, delta):
4747:def _is_bookkeeping(rel, changes_rel):
4756:def _final_fresh(root, change_dir, final_commit):
4767:def cmd_ship(args):
4814:def cmd_scope_seed(args):
4858:def main():
```

## S4

无公开代码接口：仅文档 / schema / install.sh / template/openspec/gate-scope.json（{"builtin": true}）。

## S3

### template/.claude/hooks/slice-gate.py
```
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
1554:def _builtin_report(root, change_dir, data, phase):
1610:def _scope_report_errors(r):
1636:def _run_scope(cmd, root, planned=(), change_rel=""):
1664:def _scope_reason_errors(report, reasons, pending=()):
1681:def _undeclared_msg(change_dir):
1687:def _lint_scope(gate, change_dir, run_scope, data=None, phase="lint"):
1739:def _tier_shape(label, obj, fields, selector=False):
1763:def _tier_root_ok(root):
1767:def _probe_shape(label, probe):
1790:def _parts_shape(tiers):
1847:def _load_tiers_file(path):
1899:def _load_tiers(change_dir):
1903:def _tier_root_errors(top, parts):
1909:def _tiers_raw(path):
1918:def tiers_is_parts(tiers):
1922:def tier_parts(tiers):
1929:def _tier_regions(tiers):
1937:def tier_list(top, part, layer):
1959:def layer_matches(top, part, layer, path):
1967:def _layer_hit(top, part, layer, path):
1975:def part_test_files(top, part, path):
1989:def is_canary(tiers, path):
1994:def parts_of(top, tiers, path):
2001:def probe_files(top, root, cmd):
2015:def tier_adapter_errors(top, tiers):
2055:def _g12_parts(top, tiers, chosen, files):
2079:def tiers_matching(path, tiers, top=None):
2094:def tier_seconds(durations, tiers):
2114:def _tier_add(ts, unit=0.0, regions=None):
2124:def _tier_note(ts):
2128:def _tier_parts_sec(top, tiers, durations=None, unit=None, regions=None):
2148:def _lint_tiers(data, change_dir):
2226:def lint_plan(data, change_dir=None, run_scope=False, phase="lint"):
2283:def timeline_record(change_dir, event, note=""):
2295:def append_report(change_dir, result):
2311:def _cell(text):
2315:def ceiling_rows_from_json(raw):
2334:def record_ceilings(change_dir, slice_id, rows):
2366:def evidence_state(change_dir, slice_id):
2385:def report_has_row(change_dir, slice_id, commit):
2399:def is_test_path(path):
2406:def is_doc_or_config(path):
2413:def source_files(files, change_rel):
2419:def is_bytecode(path):
2424:def changed_files(root, base):
2438:def added_lines(root, base):
2462:def ceiling_rows(root, base):
2485:def gwt_violations(root, test_files):
2505:def _py_test_bodies(lines):
2521:def _test_bodies(rel, lines):
2556:def ownership_violations(files, owns, change_rel, committed=()):
2572:def _py_decorators(source, func):
2586:def _pytest_head(cmd):
2608:def _derive_paths(rest):
2626:def _uncovered_opts(root, rest, runner):
2640:def _derive_verify(root, full_head, vcmd, cases, failed):
2665:def _g7_runner(gate):
2676:def _g7_timeout(gate):
2687:def _pytest_outcomes(root, targets, gate=None, durations=None, deps_out=None, probe_out=None):
2756:def _tier_rerun(root, gate, nodeids):
2778:def _unit_tier_verdict(root, gate, tg, allow):
2785:def _g7_diag(text):
2791:def scenario_status(root, data, slice_ids=None, durations=None):
2860:def detect_test_cmd(root):
2874:def cmd_lint(args, print_waves=True):
2884:def _is_ancestor(root, anc, desc):
2890:def _base_check(root, branch):
2903:def _ckpt_ref(change_dir, slice_id):
2907:def _ckpt_delete(root, ref):
2912:def _gate_ref(change_dir, slice_id):
2916:def _gate_save(root, change_dir, result):
2935:def _gate_load(root, ref):
2946:def _slice_owns(change_dir, slice_id):
2955:def _checkpoint(root):
3006:def cmd_checkpoint(args):
3023:def _ckpt_restore(root, ref, owns):
3055:def cmd_start(args):
3099:def _read_marker(root):
3110:def cmd_gate(args):
3213:def cmd_record(args):
3242:def _dirty_paths(root, change_dir):
3261:def cmd_final(args):
3552:def cmd_baseline(args):
3828:def _die_running_baseline(change_dir, bl, data):
3852:def cmd_preflight(args):
3904:def _has_approve(change_dir):
3913:def report_latest(change_dir):
3939:def _change_rel(root, change_dir):
3943:def _plan_file(rel, change_rel):
3950:def _other_change(rel, change_rel, keep_own=True):
3958:def _ignored(rel):
3963:def _git_raw(root, args, stdin=None):
3971:def _hash_paths(root, rels):
3978:def _snapshot(root, change_rel):
4009:def _blobs_at(root, commit, paths):
4024:def _repo_rel(root, tok):
4041:def cmd_key(root, change_rel, cmd):
4061:def _delta(root, cand, cur_snap, head, change_rel, same_change, strict=False):
4085:def _baseline_candidates(root, old, key, name, full):
4102:def _pool_dir(root, sub=POOL_DIR):
4116:def _check_dir(root, change, name):
4128:def _final_env(final_ctx, ddir):
4140:def _check_env(phase, change, base_commit, cdir, final_ctx=None):
4150:def _run_check(cmd, root, env, timeout):
4171:def _check_log(cdir, phase, out):
4183:def _check_msg(head, log, out):
4191:def _final_checks(root, change_dir, checks, baseline, final_ctx=None):
4220:def _pool_order(name, entry):
4226:def _pool_read(pdir, name):
4235:def _pool_write(root, entry, sub=POOL_DIR, keep=POOL_KEEP, label="基线池"):
4275:def _anchor_key(root, change_rel, test_cmd, gate):
4284:def _anchor_write(root, entry):
4289:def _anchor_candidates(root, cmd_key, tiers_key, limit=10):
4304:def _json_sha1(obj):
4308:def _tiers_key(root, change_dir, tiers):
4321:def _tiers_detail(tiers):
4330:def _node_counts(nodeids):
4339:def _py_test_file(rel):
4343:def _global_file(rel):
4348:def _final_fps(root, change_rel, data, tiers):
4366:def _final_rec_read(root, name):
4373:def _final_rec_write(root, name, rec):
4393:def _final_reusable(root, rec, cur_snap, head, change_rel, fps):
4404:def _last_green(rec):
4414:def _impacted_anchor(root, rec, baseline, cur_snap, head, change_rel, name, fps):
4434:def _pick_anchor(root, key, tkey, cur_snap, head, change_rel, name):
4449:def _decl_rels(root, change_dir):
4455:def _unreproducible_why(root, gate):
4468:def _full_triggers(root, delta, anchor, baseline, gate, tier_rel=None, decl_rels=(), impacted=False):
4504:def _full_why(root, full, pick, baseline, snap_why, impacted=False, gate=None, tier_rel=None, decl_rels=()):
4528:def _approved_reasons(root, change_dir):
4543:def _g2_scope(err):
4548:def _final_scope_guard(root, change_dir, data, why, triggers):
4596:def _is_shell(root, rel):
4609:def _sh_refs(root, rel):
4662:def _shell_closure(root, files, memo=None):
4684:def _final_select(root, anchor, delta):
4695:def _anchor_forward(root, old, sel, d, fails, outcomes):
4714:def _pool_candidates(root, key, limit=10, sub=POOL_DIR, pred=None):
4732:def _try_reuse(root, change_dir, data, cand, cur_snap, key, rerun_cache):
4781:def _run_changes(root, change_rel, s0, s1, prev_byproducts):
4803:def _verify_paths(root, cmd, delta):
4817:def _verify_rerun(root, cmd, prev, delta):
4827:def _is_bookkeeping(rel, changes_rel):
4836:def _final_fresh(root, change_dir, final_commit):
4847:def cmd_ship(args):
4894:def cmd_scope_seed(args):
4938:def main():
```

### tests/test_scope_runtime_guard.py
```
36:def _missing(text):
43:def _undeclare(repo):
49:def _marker_plan(repo, gate_extra=None, owns=("a/**",)):
59:def _baseline(repo, d, mark):
63:def _final(repo, d, mark, *args):
68:def _builtin_repo(repo, **kw):
74:def test_baseline_refuses_unapproved_full(git_repo, tmp_path):
89:def test_baseline_runs_when_full_is_approved(git_repo, tmp_path):
101:def test_baseline_refuses_undeclared(git_repo, tmp_path):
117:def test_final_refuses_unapproved_builtin_full(git_repo, tmp_path):
133:def test_final_runs_approved_full(git_repo, tmp_path):
149:def test_final_refuses_unapproved_cmd_full(git_repo, tmp_path):
167:def test_manual_full_flag_is_exempt(git_repo, tmp_path):
181:def test_reasons_edited_after_approval_are_red(git_repo, tmp_path):
```
