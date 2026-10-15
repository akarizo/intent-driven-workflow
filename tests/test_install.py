"""install.sh 与模板 openspec/.gitignore：飞行起飞记录 .flight 不入库（scenario: flight-record-ignore#*）。"""
import os
import shutil
import subprocess

import pytest

from conftest import ROOT

GITIGNORE = ROOT / "template" / "openspec" / ".gitignore"
RULE = "changes/*/.flight"


def run_install(tmp_path, target, *flags):
    """用本仓库的 install.sh 安装 / 升级到 target；PATH 前置 openspec 与 claude 桩，并剔除真实 claude（免改本机插件记录）。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("openspec", "claude"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    env = {**os.environ, "PATH": path_without_real_claude(bin_dir)}
    return subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(target)],
                          env=env, capture_output=True, text=True, timeout=120)


def ignored(repo, rel):
    return subprocess.run(["git", "check-ignore", "-q", rel], cwd=repo).returncode == 0


def test_template_ignores_flight_marker(git_repo):
    # Given: 一个 git 仓库，openspec/.gitignore 是本模板的原文；某个 change 目录下有 .flight，openspec/ 下有 .mini-active
    (git_repo / "openspec" / "changes" / "x").mkdir(parents=True)
    shutil.copy(GITIGNORE, git_repo / "openspec" / ".gitignore")
    (git_repo / "openspec" / "changes" / "x" / ".flight").write_text("{}", encoding="utf-8")
    (git_repo / "openspec" / ".mini-active").write_text("{}", encoding="utf-8")

    # When: 用 git check-ignore 询问这两个文件
    flight, mini = ignored(git_repo, "openspec/changes/x/.flight"), ignored(git_repo, "openspec/.mini-active")

    # Then: 两者都被忽略
    assert flight, "openspec/changes/x/.flight 未被忽略"
    assert mini, "openspec/.mini-active 未被忽略"


def test_upgrade_appends_flight_ignore_once(tmp_path):
    # Given: 一个已安装的项目，其 openspec/.gitignore 是老版本（只有 .mini-active 一条规则）
    target = tmp_path / "proj"
    first = run_install(tmp_path, target)
    ignore = target / "openspec" / ".gitignore"
    ignore.write_text("# intent-driven mini-task marker（每机瞬态，不入库）\n.mini-active\n", encoding="utf-8")

    # When: 连续两次运行 install.sh --upgrade
    runs = [run_install(tmp_path, target, "--upgrade") for _ in range(2)]

    # Then: 安装与两次升级都以 0 退出；整行 changes/*/.flight 恰好出现一次，.mini-active 仍在
    assert first.returncode == 0 and all(r.returncode == 0 for r in runs), [first.stderr] + [r.stderr for r in runs]
    lines = [l.strip() for l in ignore.read_text(encoding="utf-8").splitlines()]
    assert lines.count(RULE) == 1, lines
    assert ".mini-active" in lines


# ---------------------------------------------------------------- 安装器测试的桩与 PATH 过滤（摘自原仓 #35 #36）
# 本版安装器不调用 claude；测试仍从 PATH 里滤掉真实的 claude，免得误动开发者本机的插件记录。


import json  # noqa: E402


def path_without_real_claude(bin_dir):
    """PATH = 桩目录 + 原 PATH 中不含 claude 可执行文件的目录。"""
    keep = [p for p in os.environ.get("PATH", "").split(os.pathsep)
            if p and not os.path.exists(os.path.join(p, "claude"))]
    return os.pathsep.join([str(bin_dir)] + keep)


def run_install_stubbed(tmp_path, target, *flags, claude=True):
    """openspec 桩 + 可选的 claude 桩（逐行记录「工作目录|参数」），返回 (CompletedProcess, 调用记录)。"""
    bin_dir = tmp_path / "bin-stub"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "openspec").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_dir / "openspec").chmod(0o755)
    log = tmp_path / "claude-calls.log"
    shim = bin_dir / "claude"
    if claude:
        shim.write_text('#!/bin/sh\necho "$PWD|$*" >> "%s"\nexit 0\n' % log, encoding="utf-8")
        shim.chmod(0o755)
    elif shim.exists():
        shim.unlink()
    env = {**os.environ, "PATH": path_without_real_claude(bin_dir)}
    p = subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(target)],
                       env=env, capture_output=True, text=True, timeout=120)
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return p, calls


# ---------------------------------------------------------------- 摘自原仓 #36（flight-integrity-fixes）· scenario: installer-edition#upgrade-adds-missing-template-settings-keys


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_upgrade_adds_missing_template_settings_keys(tmp_path):
    # Given: 已安装的目标仓库，用户把 .claude/settings.json 改成 {"env": {"MY_KEY": "1"}, "custom": true}
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    settings = target / ".claude" / "settings.json"
    settings.write_text(json.dumps({"env": {"MY_KEY": "1"}, "custom": True}), encoding="utf-8")

    # When: 运行 install.sh --upgrade
    p, _ = run_install_stubbed(tmp_path, target, "--upgrade", claude=False)
    data = json.loads(settings.read_text(encoding="utf-8"))

    # Then: env 仍恰为 {"MY_KEY": "1"}、custom 仍为 true；补上了模板的 worktree 键 {"baseRef": "head"}
    assert p.returncode == 0, p.stderr
    assert data["env"] == {"MY_KEY": "1"} and data["custom"] is True, data
    assert data.get("worktree") == {"baseRef": "head"}, data


# ---------------------------------------------------------------- 摘自原仓 #38（install-from-tag）· scenario: installer-edition#pipe-* / readme-documents-pinned-install
# pipe 模式 = install.sh 文本从 stdin 喂给 bash -s（与 curl | bash 同形）；源用 file:// 目录模拟 GitHub 的 archive 路径，全程离线。
import pathlib  # noqa: E402
import re  # noqa: E402
import tarfile  # noqa: E402

INSTALLER = ROOT / "install.sh"

STUB_INSTALLER = """#!/usr/bin/env bash
# 归档里的桩 install.sh：记录收到的参数与同目录 template/VERSION，按 STUB_RC 退出
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
{ printf 'args=%s\\n' "$*"; printf 'version=%s\\n' "$(cat "$here/template/VERSION")"; } > "$STUB_LOG"
exit "${STUB_RC:-0}"
"""


def _skip_changes(info):
    """打归档时略去 template/openspec/changes（历史 change 工件，与安装无关，只会拖慢测试）。"""
    return None if "/template/openspec/changes" in info.name else info


def make_source(tmp_path, ref, kind, files):
    """在 tmp_path/src 下按 GitHub 路径放一个归档 archive/refs/<kind>/<ref>.tar.gz（kind = heads / tags），
    顶层目录 idt-<ref>/；files = {归档内相对路径: 文本 或 本地 pathlib.Path（文件或目录）}。返回 file:// 源地址。"""
    src = tmp_path / "src"
    out = src / "archive" / "refs" / kind / (ref + ".tar.gz")
    out.parent.mkdir(parents=True, exist_ok=True)
    stage = tmp_path / ("stage-%s-%s" % (kind, ref))
    top = "idt-" + ref
    with tarfile.open(out, "w:gz") as tar:
        for rel, val in files.items():
            if isinstance(val, pathlib.Path):
                tar.add(val, arcname="%s/%s" % (top, rel), filter=_skip_changes)
            else:
                p = stage / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(val, encoding="utf-8")
                tar.add(p, arcname="%s/%s" % (top, rel))
    return "file://" + str(src)


def run_pipe(tmp_path, source, *args, ref=None, extra_env=None):
    """把本仓库 install.sh 从 stdin 喂给 bash -s；PATH 前置 openspec 桩并剔除真实 claude；ref=None 表示不设 IDT_BRANCH。"""
    bin_dir = tmp_path / "bin-pipe"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "openspec").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (bin_dir / "openspec").chmod(0o755)
    env = {**os.environ, "PATH": path_without_real_claude(bin_dir), "IDT_REPO_URL": source,
           "STUB_LOG": str(tmp_path / "stub.log")}
    env.pop("IDT_BRANCH", None)
    if ref is not None:
        env["IDT_BRANCH"] = ref
    env.update(extra_env or {})
    return subprocess.run(["bash", "-s", "--", *args], input=INSTALLER.read_text(encoding="utf-8"),
                          env=env, capture_output=True, text=True, timeout=180, cwd=tmp_path)


def stub_log(tmp_path):
    """桩 install.sh 留下的记录 {args, version}；桩没被执行则为空 dict。"""
    p = tmp_path / "stub.log"
    if not p.exists():
        return {}
    return dict(line.split("=", 1) for line in p.read_text(encoding="utf-8").splitlines() if "=" in line)


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_installs_tag_only_ref(tmp_path):
    # Given: 源里只有 tag stable-v9.9 的归档（refs/tags 下），没有同名分支；归档里是桩 install.sh 与 template/VERSION=v9.9
    source = make_source(tmp_path, "stable-v9.9", "tags", {"install.sh": STUB_INSTALLER, "template/VERSION": "v9.9"})
    target = tmp_path / "proj"

    # When: 以 IDT_BRANCH=stable-v9.9 用管道运行 install.sh
    p = run_pipe(tmp_path, source, str(target), ref="stable-v9.9")

    # Then: 以 0 退出；归档里的 install.sh 被执行，读到的 VERSION 是 v9.9
    assert p.returncode == 0, p.stdout + p.stderr
    assert stub_log(tmp_path).get("version") == "v9.9", p.stdout + p.stderr


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_default_ref_is_main_branch(tmp_path):
    # Given: 源里只有分支 main 的归档（refs/heads 下），归档里是桩 install.sh 与 template/VERSION=main
    source = make_source(tmp_path, "main", "heads", {"install.sh": STUB_INSTALLER, "template/VERSION": "main"})
    target = tmp_path / "proj"

    # When: 不设 IDT_BRANCH，用管道运行 install.sh
    p = run_pipe(tmp_path, source, str(target))

    # Then: 以 0 退出；归档里的 install.sh 被执行，读到的 VERSION 是 main
    assert p.returncode == 0, p.stdout + p.stderr
    assert stub_log(tmp_path).get("version") == "main", p.stdout + p.stderr


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_missing_ref_lists_both_urls(tmp_path):
    # Given: 源里只有分支 main 的归档
    source = make_source(tmp_path, "main", "heads", {"install.sh": STUB_INSTALLER, "template/VERSION": "main"})
    target = tmp_path / "proj"

    # When: 以 IDT_BRANCH=nope 用管道运行 install.sh
    p = run_pipe(tmp_path, source, str(target), ref="nope")

    # Then: 以 4 退出；[err] 行里同时出现 refs/heads/nope 与 refs/tags/nope；目标目录没有被创建
    err = [line for line in p.stderr.splitlines() if line.startswith("[err]")]
    assert p.returncode == 4, p.stdout + p.stderr
    assert any("refs/heads/nope" in line for line in err) and any("refs/tags/nope" in line for line in err), p.stderr
    assert not target.exists()


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_delegates_args_to_archived_installer(tmp_path):
    # Given: 源里有 tag stable-v9.9 的归档，其 install.sh 是记录参数的桩
    source = make_source(tmp_path, "stable-v9.9", "tags", {"install.sh": STUB_INSTALLER, "template/VERSION": "v9.9"})
    target = tmp_path / "proj"

    # When: 以 IDT_BRANCH=stable-v9.9 用管道运行 install.sh --upgrade <target>
    p = run_pipe(tmp_path, source, "--upgrade", str(target), ref="stable-v9.9")

    # Then: 以 0 退出，桩收到的参数恰为 "--upgrade <target>"；目标目录里没有 .claude/（引导器自身没有复制模板）
    assert p.returncode == 0, p.stdout + p.stderr
    assert stub_log(tmp_path).get("args") == "--upgrade " + str(target), p.stdout + p.stderr
    assert not (target / ".claude").exists()


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_propagates_exit_and_cleans_temp(tmp_path):
    # Given: 源里有 tag stable-v9.9 的归档，其 install.sh 是以 3 退出的桩；TMPDIR 指向一个空目录
    source = make_source(tmp_path, "stable-v9.9", "tags", {"install.sh": STUB_INSTALLER, "template/VERSION": "v9.9"})
    target = tmp_path / "proj"
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()

    # When: 以 IDT_BRANCH=stable-v9.9 用管道运行 install.sh
    p = run_pipe(tmp_path, source, str(target), ref="stable-v9.9", extra_env={"STUB_RC": "3", "TMPDIR": str(tmpdir)})

    # Then: 以 3 退出；TMPDIR 目录仍为空
    assert p.returncode == 3, p.stdout + p.stderr
    assert list(tmpdir.iterdir()) == []


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_archive_without_template_exits_4(tmp_path):
    # Given: 源里有 tag stable-v9.9 的归档，里面只有记录调用的桩 install.sh，没有 template/
    #   （用桩而非真实 install.sh：修复前真实脚本会无界递归下载，测试不能触发它）
    source = make_source(tmp_path, "stable-v9.9", "tags", {"install.sh": STUB_INSTALLER})
    target = tmp_path / "proj"

    # When: 以 IDT_BRANCH=stable-v9.9 用管道运行 install.sh
    p = run_pipe(tmp_path, source, str(target), ref="stable-v9.9")

    # Then: 以 4 退出，[err] 行指出归档里没有 template/；桩没有被执行，目标目录没有被创建
    err = [line for line in p.stderr.splitlines() if line.startswith("[err]")]
    assert p.returncode == 4, p.stdout + p.stderr
    assert any("template/" in line for line in err), p.stderr
    assert stub_log(tmp_path) == {}, stub_log(tmp_path)
    assert not target.exists()


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_pipe_real_installer_runs_local_mode(tmp_path):
    # Given: 源里分支 main 的归档由本仓库当前的 install.sh 与 template/ 打成；PATH 上有 openspec 桩，没有 claude
    source = make_source(tmp_path, "main", "heads", {"install.sh": INSTALLER, "template": ROOT / "template"})
    target = tmp_path / "proj"

    # When: 用管道运行 install.sh <target>
    p = run_pipe(tmp_path, source, str(target))
    out = p.stdout + p.stderr

    # Then: 以 0 退出，目标含 .claude/hooks/intent-gate.py，CLAUDE.md 含 intent-driven:begin 段；只下载一次，且交接后按本地模式运行
    assert p.returncode == 0, out
    assert (target / ".claude" / "hooks" / "intent-gate.py").is_file()
    assert "intent-driven:begin" in (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert out.count("pipe 模式：下载") == 1, out
    assert "模式: local" in out, out


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_readme_documents_pinned_install():
    # Given: README.md 与 install.sh --help 的输出
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    help_out = subprocess.run(["bash", str(INSTALLER), "--help"], capture_output=True, text=True, timeout=30).stdout

    # When: 取 README 中「### 安装指定版本」到下一个二级或三级标题之间的内容
    rest = readme[readme.index("### 安装指定版本") + 1:]
    m = re.search(r"\n#{2,3} ", rest)
    section = rest[: m.start()] if m else rest

    # Then: 这段含本仓 main 的 install.sh 地址、IDT_BRANCH=stable-v2.0、--branch stable-v2.0 与「降级」；--help 输出含「分支或 tag」
    #       README 另有一段写明 Mod 版仓库与卸载 flight 插件的命令
    assert "raw.githubusercontent.com/akarizo/intent-driven-workflow/main/install.sh" in section, section
    assert "IDT_BRANCH=stable-v2.0" in section, section
    assert "--branch stable-v2.0" in section, section
    assert "降级" in section, section
    assert "分支或 tag" in help_out, help_out
    assert "akarizo/intent-driven-claude-code" in readme
    assert "claude plugin uninstall flight@intent-driven -s project" in readme


# ---------------------------------------------------------------- 摘自原仓 #55（install-openspec-seeds）· scenario: installer-edition#fresh-install-ships-only-seeds / upgrade-adds-no-dev-artifacts / upgrade-keeps-user-seed-edits / upgrade-lists-suspected-dev-artifacts


# 骨架（workflow-edition S4）：实现后逐条去掉 xfail 标记；在基底上已通过的不带标记。
TEMPLATE_OPENSPEC = ROOT / "template" / "openspec"
OPENSPEC_SEEDS = {".gitignore", "config.yaml", "changes/.gitkeep", "adr/.gitkeep", "superpower/.gitkeep"}
SUSPECT_HINT = "旧版安装器"


def _files_under(root):
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _dev_artifact_names():
    """本仓自己的开发工件各取一个名字：template/openspec/changes 下的 change 目录、adr 下的 DRAFT ADR。"""
    change = sorted(p.name for p in (TEMPLATE_OPENSPEC / "changes").iterdir() if p.is_dir())[0]
    adr = sorted(p.name for p in (TEMPLATE_OPENSPEC / "adr").glob("DRAFT-*.md"))[0]
    return change, adr


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_fresh_install_ships_only_seeds(tmp_path):
    # Given: 一个空目录
    target = tmp_path / "proj"

    # When: 运行 install.sh <目录>
    p, _ = run_install_stubbed(tmp_path, target, claude=False)

    # Then: 以 0 退出；openspec/ 里的文件恰为种子清单加上模板 openspec/schemas/ 下的全部文件
    assert p.returncode == 0, p.stderr
    schemas = {"schemas/" + rel for rel in _files_under(TEMPLATE_OPENSPEC / "schemas")}
    assert _files_under(target / "openspec") == OPENSPEC_SEEDS | schemas


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_upgrade_adds_no_dev_artifacts(tmp_path):
    # Given: 用 install.sh 装好的项目；用户自己建了 change my-change（含 proposal.md）与 ADR 0001-mine.md
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    for f in (target / "openspec" / "changes" / "my-change" / "proposal.md", target / "openspec" / "adr" / "0001-mine.md"):
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# mine\n", encoding="utf-8")

    # When: 运行 install.sh --upgrade <项目>
    p, _ = run_install_stubbed(tmp_path, target, "--upgrade", claude=False)

    # Then: 以 0 退出；changes/ 下只有 .gitkeep 与 my-change，adr/ 下只有 .gitkeep 与 0001-mine.md；输出不含「旧版安装器」
    assert p.returncode == 0, p.stderr
    assert {x.name for x in (target / "openspec" / "changes").iterdir()} == {".gitkeep", "my-change"}
    assert {x.name for x in (target / "openspec" / "adr").iterdir()} == {".gitkeep", "0001-mine.md"}
    assert SUSPECT_HINT not in p.stdout, p.stdout


def test_upgrade_keeps_user_seed_edits(tmp_path):
    # Given: 用 install.sh 装好的项目；用户改过 openspec/config.yaml，openspec/schemas/intent-driven/schema.yaml 被本地改坏
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    config = target / "openspec" / "config.yaml"
    schema = target / "openspec" / "schemas" / "intent-driven" / "schema.yaml"
    config.write_text("schema: intent-driven\n# mine\n", encoding="utf-8")
    schema.write_text("broken\n", encoding="utf-8")

    # When: 运行 install.sh --upgrade <项目>
    p, _ = run_install_stubbed(tmp_path, target, "--upgrade", claude=False)

    # Then: 以 0 退出；config.yaml 仍是用户的内容；schema.yaml 恢复为模板原文
    assert p.returncode == 0, p.stderr
    assert config.read_text(encoding="utf-8") == "schema: intent-driven\n# mine\n"
    assert schema.read_bytes() == (TEMPLATE_OPENSPEC / "schemas" / "intent-driven" / "schema.yaml").read_bytes()


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_upgrade_lists_suspected_dev_artifacts(tmp_path):
    # Given: 已装项目里有与模板 change 目录同名的目录、与模板 DRAFT ADR 同名的文件（模拟旧版安装器误拷），另有用户自己的 my-change
    change, adr = _dev_artifact_names()
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    planted = [target / "openspec" / "changes" / change / "proposal.md", target / "openspec" / "adr" / adr,
               target / "openspec" / "changes" / "my-change" / "proposal.md"]
    for f in planted:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# old copy\n", encoding="utf-8")

    # When: 运行 install.sh --upgrade <项目>
    p, _ = run_install_stubbed(tmp_path, target, "--upgrade", claude=False)

    # Then: 以 0 退出；输出含「旧版安装器」与「安装器不代删」；提示段列出那个 change 目录与那份 ADR，不列 my-change；三者都仍在
    assert p.returncode == 0, p.stderr
    assert SUSPECT_HINT in p.stdout and "安装器不代删" in p.stdout, p.stdout
    hint = p.stdout[p.stdout.index(SUSPECT_HINT):]
    assert "openspec/changes/%s" % change in hint and "openspec/adr/%s" % adr in hint, hint
    assert "my-change" not in hint, hint
    assert all(f.exists() for f in planted)


# ---------------------------------------------------------------- 本仓新增 · scenario: installer-edition#help-names-workflow-repo / upgrade-reregisters-v2-hooks / upgrade-warns-enabled-flight-plugin / upgrade-lists-mod-leftovers


V2_HOOKS = (
    'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/takeoff-gate.py"',
    'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/slice-gate.py" checkpoint',
    'python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/stop-gate.py"',
)
UNINSTALL = "claude plugin uninstall flight@intent-driven -s project"
MARKET_REMOVE = "claude plugin marketplace remove intent-driven --scope project"


def _hook_commands(settings):
    data = json.loads(settings.read_text(encoding="utf-8"))
    return {h.get("command") for entries in (data.get("hooks") or {}).values()
            for e in entries for h in e.get("hooks") or []}


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_help_names_workflow_repo():
    # Given: 本仓的 install.sh
    # When: 运行 install.sh --help
    out = subprocess.run(["bash", str(INSTALLER), "--help"], capture_output=True, text=True, timeout=30).stdout

    # Then: IDT_REPO_URL 的缺省值是本仓地址；IDT_BRANCH 的说明含「分支或 tag」
    repo_line = next(l for l in out.splitlines() if "IDT_REPO_URL" in l)
    assert "https://github.com/akarizo/intent-driven-workflow" in repo_line, out
    branch_line = next(l for l in out.splitlines() if "IDT_BRANCH" in l)
    assert "分支或 tag" in branch_line, out


def test_upgrade_reregisters_v2_hooks(tmp_path):
    # Given: 已安装的目标仓库，其 settings.json 里没有 takeoff-gate、slice-gate.py checkpoint、stop-gate 三条注册（Mod 版安装器升级时移除过）
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    settings = target / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    for event in list(data.get("hooks") or {}):
        kept = []
        for e in data["hooks"][event]:
            hs = [h for h in e.get("hooks") or [] if h.get("command") not in V2_HOOKS]
            if hs:
                kept.append(dict(e, hooks=hs))
        if kept:
            data["hooks"][event] = kept
        else:
            del data["hooks"][event]
    settings.write_text(json.dumps(data), encoding="utf-8")
    assert not set(V2_HOOKS) & _hook_commands(settings)

    # When: 运行 install.sh --upgrade
    p, _ = run_install_stubbed(tmp_path, target, "--upgrade", claude=False)

    # Then: 三条注册都回到 settings.json 的 hooks 里
    assert p.returncode == 0, p.stderr
    assert set(V2_HOOKS) <= _hook_commands(settings), _hook_commands(settings)


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_upgrade_warns_enabled_flight_plugin(tmp_path):
    # Given: 已安装的目标仓库，其 settings.json 的 enabledPlugins 含 "flight@intent-driven": true
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    settings = target / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    data["enabledPlugins"] = {"flight@intent-driven": True}
    settings.write_text(json.dumps(data), encoding="utf-8")

    # When: 运行 install.sh --upgrade
    p, calls = run_install_stubbed(tmp_path, target, "--upgrade")

    # Then: 以 0 退出；输出含插件名与两条卸载命令；没有代为调用 claude；enabledPlugins 原样保留
    out = p.stdout + p.stderr
    assert p.returncode == 0, p.stderr
    assert "flight@intent-driven" in out and UNINSTALL in out and MARKET_REMOVE in out, out
    assert calls == [], calls
    assert json.loads(settings.read_text(encoding="utf-8"))["enabledPlugins"] == {"flight@intent-driven": True}


@pytest.mark.xfail(strict=True, reason="workflow-edition S4 尚未实现")
def test_upgrade_lists_mod_leftovers(tmp_path):
    # Given: 已安装的目标仓库里有 Mod 版留下的 .claude/hooks/ledger.py 与 .claude/hooks/plan_fp.py
    target = tmp_path / "proj"
    first, _ = run_install_stubbed(tmp_path, target, claude=False)
    assert first.returncode == 0, first.stderr
    leftovers = [target / ".claude" / "hooks" / "ledger.py", target / ".claude" / "hooks" / "plan_fp.py"]
    for f in leftovers:
        f.write_text("# Mod 版遗留\n", encoding="utf-8")

    # When: 运行 install.sh --upgrade
    p, _ = run_install_stubbed(tmp_path, target, "--upgrade", claude=False)

    # Then: 输出列出这两个文件并提示可手动删除；两个文件都仍在
    out = p.stdout + p.stderr
    assert p.returncode == 0, p.stderr
    assert ".claude/hooks/ledger.py" in out and ".claude/hooks/plan_fp.py" in out, out
    assert "手动删除" in out, out
    assert all(f.exists() for f in leftovers)
