# 公开接口摘要

## S1

### template/.claude/hooks/spec_html.py
```
cx: updating 16 files...
[61]{name,kind,signature}:
  ADR_STATUS_RE,const,"ADR_STATUS_RE = re.compile(r\"(?m)^Status:\\s*(.+)$\")"
  ADR_SUPERSEDES_RE,const,"ADR_SUPERSEDES_RE = re.compile(r\"(?m)^Supersedes:\\s*(.+)$\")"
  ADR_TITLE_RE,const,"ADR_TITLE_RE = re.compile(r\"(?m)^#\\s+(.+)$\")"
  ASCII_ONLY_RE,const,"ASCII_ONLY_RE = re.compile(r\"^[\\x00-\\x7f]+$\")"
  BLOCK_NAMES,const,BLOCK_NAMES = (
  CAP_ITEM_RE,const,"CAP_ITEM_RE = re.compile(r\"^`?([^`:]+)`?\\s*:\\s*(.+)$\")"
  DECISION_RISK_RE,const,"DECISION_RISK_RE = re.compile(r\"decision|risk|trade\", re.I)"
  DEFAULT_TEMPLATE,const,DEFAULT_TEMPLATE = os.path.normpath(
  DELTA_RE,const,"DELTA_RE = re.compile(r\"^(ADDED|MODIFIED|REMOVED)\\s+Requirements$\", re.I)"
  FORECAST_TIMEOUT,const,FORECAST_TIMEOUT = 30
  GLOSSARY_ALIAS_SPLIT_RE,const,"GLOSSARY_ALIAS_SPLIT_RE = re.compile(r\"[、，,/]\")"
  GLOSSARY_AVOID_RE,const,"GLOSSARY_AVOID_RE = re.compile(r\"^避用\\s*[：:]\\s*(.+)$\")"
  GLOSSARY_TERM_RE,const,"GLOSSARY_TERM_RE = re.compile(r\"^\\*\\*([^*]+)\\*\\*\\s*[：:]\\s*\\S\")"
  HOOKS_DIR,const,HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
  JS_TEST_RE,const,"JS_TEST_RE = re.compile(r\"^\\s*(?:test|it)\\s*\\(\\s*['\\\"`](.+?)['\\\"`]\")"
  MARK_RE,const,"MARK_RE = re.compile(r\"xfail|skip\", re.I)"
  MERMAID_RE,const,"MERMAID_RE = re.compile(r\"```mermaid\\n(.*?)```\", re.S)"
  STEP_RE,const,"STEP_RE = re.compile(r\"^\\s*[-*]\\s+\\*\\*(GIVEN|WHEN|THEN|AND|BUT)\\*\\*\\s+(.*)$\", re.I)"
  TASK_ITEM_RE,const,"TASK_ITEM_RE = re.compile(r\"^\\s*-\\s+\\[( |x|X)\\]\\s+(.*)$\")"
  compute_meta_chips,fn,"def compute_meta_chips(change_dir, change_name)"
  compute_waves,fn,def compute_waves(slices)
  decorator_source,fn,"def decorator_source(source, func)"
  esc,fn,def esc(s)
  establishes_scope_decl,fn,"def establishes_scope_decl(gate_owns, change_dir)"
  extract_diagrams,fn,def extract_diagrams(design_text)
  find_def_line,fn,"def find_def_line(lines, func)"
  gate_report_passed_slices,fn,def gate_report_passed_slices(change_dir)
  glossary_files,fn,def glossary_files(change_dir)
  glossary_hits,fn,"def glossary_hits(change_dir, entries)"
  inline_md,fn,def inline_md(text)
  list_items,fn,def list_items(text)
  load_timeline_rows,fn,def load_timeline_rows(change_dir)
  main,fn,def main()
  now_iso,fn,def now_iso(now_arg)
  paragraphs,fn,def paragraphs(text)
  parse_glossary,fn,def parse_glossary(text)
  project_root,fn,def project_root(change_dir)
  read_text,fn,def read_text(path)
  render,fn,"def render(change_dir, template_path, out_path, now_arg)"
  render_capabilities,fn,def render_capabilities(proposal_text)
  render_design,fn,def render_design(design_text)
  render_diagrams,fn,def render_diagrams(design_text)
  render_flight,fn,def render_flight(change_dir)
  render_footer,fn,"def render_footer(now, section_count, diagram_count, task_count)"
  render_forecast,fn,def render_forecast(change_dir)
  render_generic_md,fn,def render_generic_md(text)
  render_glossary,fn,def render_glossary(change_dir)
  render_requirement,fn,"def render_requirement(heading, body)"
  render_scenario,fn,"def render_scenario(name, body)"
  render_scope,fn,"def render_scope(gate, change_dir, owns=())"
  render_specs,fn,def render_specs(change_dir)
  render_tasks,fn,def render_tasks(tasks_text)
  render_what,fn,def render_what(proposal_text)
  render_why,fn,def render_why(proposal_text)
  scan_adrs,fn,def scan_adrs(change_dir)
  scenario_flight_status,fn,"def scenario_flight_status(root, rel, func)"
  scope_provider,fn,"def scope_provider(gate, change_dir)"
  split_sections,fn,"def split_sections(text, level=\"##\")"
```

## S2

owns 均为文档 / schema / 测试，无源码签名；见 template/.claude/skills/grill-me/SKILL.md 与 template/openspec/schemas/intent-driven/schema.yaml 的术语表约定。
