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
