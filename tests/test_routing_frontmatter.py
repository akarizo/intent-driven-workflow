"""routing-frontmatter 的 scenario 骨架（strict xfail；切片 S1 实现后去掉标记即解锁）。"""
import json

import pytest

from conftest import run_hook, write

CLEAN_ENV = {"CLAUDE_CODE_EFFORT_LEVEL": "", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": ""}
FORK_CMD = (
    "---\n"
    "description: d\n"
    "context: fork\n"
    "agent: general-purpose\n"
    "background: false\n"
    "model: sonnet\n"
    "effort: low\n"
    "---\n"
    "\n"
    "正文第一行\n"
    "\n"
    "model: 正文里的这一行不属于 frontmatter\n"
)
PLAIN_CMD = "---\ndescription: d\n---\n\n正文\n"


def routing(*args):
    return run_hook("model-routing", *args, env=CLEAN_ENV)


def setup(tmp_path, cmd_text, config=None):
    """造 <tmp>/commands/clean-after-merged.md 与可选的 <tmp>/openspec/model-routing.json；返回命令文件路径。"""
    cmd = write(tmp_path / "commands" / "clean-after-merged.md", cmd_text)
    (tmp_path / "openspec").mkdir(exist_ok=True)
    if config is not None:
        write(tmp_path / "openspec" / "model-routing.json", json.dumps(config))
    return cmd


def frontmatter_args(tmp_path, *extra):
    return ("frontmatter", *extra, "--commands", str(tmp_path / "commands"), "--openspec", str(tmp_path / "openspec"))


def runner(model, effort):
    return {"cleanup": {"runner": {"model": model, "effort": effort}}}


def strip_routing_lines(text):
    """去掉 frontmatter 块里的 model / effort 两行，其余各行原样返回。"""
    lines = text.split("\n")
    end = lines.index("---", 1)
    head = [l for l in lines[:end] if not l.startswith(("model:", "effort:"))]
    return head + lines[end:]


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_registry_has_cleanup_runner(tmp_path):
    # Given: 一个 openspec 根，没有 `model-routing.json`
    (tmp_path / "openspec").mkdir()

    # When: 运行 `model-routing.py show --json`
    p = routing("show", "--json", "--openspec", str(tmp_path / "openspec"))

    # Then: 退出 0，输出 11 个键，其中 `cleanup.runner` 为 sonnet · low、来源 `builtin`；配置写了 `{"cleanup": {"runner": {"model": "haiku", "effort": "medium"}}}` 后再运行，`cleanup.runner` 为 haiku · medium、来源 `repo`
    assert p.returncode == 0, p.stderr
    table = json.loads(p.stdout)
    assert len(table) == 11, table
    assert table["cleanup.runner"] == {"model": "sonnet", "effort": "low", "source": "builtin"}
    write(tmp_path / "openspec" / "model-routing.json", json.dumps(runner("haiku", "medium")))
    p2 = routing("show", "--json", "--openspec", str(tmp_path / "openspec"))
    assert p2.returncode == 0, p2.stderr
    assert json.loads(p2.stdout)["cleanup.runner"] == {"model": "haiku", "effort": "medium", "source": "repo"}


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_frontmatter_writes_effective_values(tmp_path):
    # Given: 一个命令目录里有 fork 形态的 `clean-after-merged.md`（含 `description`、`context: fork`、`agent`、`background`、`model: sonnet`、`effort: low` 与正文）；配置把 `cleanup.runner` 设为 haiku · medium
    cmd = setup(tmp_path, FORK_CMD, runner("haiku", "medium"))

    # When: 运行 `model-routing.py frontmatter --commands <该目录> --openspec <openspec 根>`
    p = routing(*frontmatter_args(tmp_path))

    # Then: 退出 0，文件的 frontmatter 里是 `model: haiku` 与 `effort: medium`；文件其余各行与原文逐字相同
    assert p.returncode == 0, p.stdout + p.stderr
    after = cmd.read_text(encoding="utf-8")
    head = after.split("\n---\n", 1)[0].split("\n")
    assert "model: haiku" in head and "effort: medium" in head, after
    assert "model: sonnet" not in head and "effort: low" not in head, after
    assert strip_routing_lines(after) == strip_routing_lines(FORK_CMD)


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_frontmatter_check_reports_drift(tmp_path):
    # Given: fork 形态的 `clean-after-merged.md` 写着 `model: sonnet`，配置把 `cleanup.runner` 设为 haiku · medium
    cmd = setup(tmp_path, FORK_CMD, runner("haiku", "medium"))

    # When: 运行 `model-routing.py frontmatter --check`
    p = routing(*frontmatter_args(tmp_path, "--check"))

    # Then: 退出 1，输出点名该文件与 `model` 的期望值 haiku、实际值 sonnet；文件内容不变；配置改回 sonnet · low 后再运行 `--check`，退出 0
    out = p.stdout + p.stderr
    assert p.returncode == 1, out
    for k in ("clean-after-merged.md", "model", "haiku", "sonnet"):
        assert k in out, (k, out)
    assert cmd.read_text(encoding="utf-8") == FORK_CMD
    write(tmp_path / "openspec" / "model-routing.json", json.dumps(runner("sonnet", "low")))
    p2 = routing(*frontmatter_args(tmp_path, "--check"))
    assert p2.returncode == 0, p2.stdout + p2.stderr
    assert cmd.read_text(encoding="utf-8") == FORK_CMD


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_frontmatter_refuses_non_fork_command(tmp_path):
    # Given: `clean-after-merged.md` 的 frontmatter 只有 `description`，没有 `context: fork`
    cmd = setup(tmp_path, PLAIN_CMD)

    # When: 运行 `model-routing.py frontmatter`
    p = routing(*frontmatter_args(tmp_path))

    # Then: 退出 2，输出说明它不是 fork 形态；文件内容不变
    out = p.stdout + p.stderr
    assert p.returncode == 2, out
    assert "fork" in out, out
    assert cmd.read_text(encoding="utf-8") == PLAIN_CMD


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_frontmatter_invalid_config_writes_nothing(tmp_path):
    # Given: fork 形态的 `clean-after-merged.md`，配置把 `cleanup.runner` 的 model 写成 `main`
    cmd = setup(tmp_path, FORK_CMD, runner("main", "low"))

    # When: 运行 `model-routing.py frontmatter`
    p = routing(*frontmatter_args(tmp_path))

    # Then: 退出 2，输出点名 `cleanup.runner`；文件内容不变
    out = p.stdout + p.stderr
    assert p.returncode == 2, out
    assert "cleanup.runner" in out, out
    assert cmd.read_text(encoding="utf-8") == FORK_CMD
