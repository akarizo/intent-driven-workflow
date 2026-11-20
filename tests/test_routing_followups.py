"""routing-frontmatter-hardening 的 scenario 测试（已解锁）。"""
import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import ROOT, run_hook

CLEAN_ENV = {"CLAUDE_CODE_EFFORT_LEVEL": "", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": ""}
REAL_CMD = ROOT / "template" / ".claude" / "commands" / "clean-after-merged.md"
FORK_LINES = [
    "---",
    "description: d",
    "context: fork",
    "agent: general-purpose",
    "background: false",
    "model: sonnet",
    "effort: low",
    "---",
    "",
    "正文第一行",
    "",
    "model: 正文里的这一行不属于 frontmatter",
]


def routing(*args):
    return run_hook("model-routing", *args, env=CLEAN_ENV)


def setup_bytes(tmp_path, data, config):
    """造 <tmp>/commands/clean-after-merged.md（按字节原样写）与 <tmp>/openspec/model-routing.json；返回命令文件路径。"""
    cmd = tmp_path / "commands" / "clean-after-merged.md"
    cmd.parent.mkdir(parents=True, exist_ok=True)
    cmd.write_bytes(data)
    (tmp_path / "openspec").mkdir(exist_ok=True)
    (tmp_path / "openspec" / "model-routing.json").write_text(json.dumps(config), encoding="utf-8")
    return cmd


def frontmatter_args(tmp_path):
    return ("frontmatter", "--commands", str(tmp_path / "commands"), "--openspec", str(tmp_path / "openspec"))


def runner(model, effort):
    return {"cleanup": {"runner": {"model": model, "effort": effort}}}


def routing_section(out):
    """doctor 输出里从 `[routing]` 行起、到下一个以 `[` 开头的行（或结尾）为止的段落。"""
    lines = out.splitlines()
    assert "[routing]" in lines, out
    start = lines.index("[routing]")
    seg = [lines[start]]
    for line in lines[start + 1:]:
        if line.startswith("["):
            break
        seg.append(line)
    return "\n".join(seg)


def doctor(openspec_root):
    return run_hook("flight-doctor", "doctor", "--openspec-root", str(openspec_root),
                    env=CLEAN_ENV, cwd=str(openspec_root.parent))


def test_frontmatter_keeps_crlf(tmp_path):
    # Given: 命令目录里有 fork 形态的 `clean-after-merged.md`，每行都以 CRLF 结尾，frontmatter 里是 `model: sonnet` 与 `effort: low`；配置把 `cleanup.runner` 设为 haiku · medium
    original = ("\r\n".join(FORK_LINES) + "\r\n").encode("utf-8")
    cmd = setup_bytes(tmp_path, original, runner("haiku", "medium"))

    # When: 运行 `model-routing.py frontmatter`
    p = routing(*frontmatter_args(tmp_path))

    # Then: 退出 0，frontmatter 里是 `model: haiku` 与 `effort: medium`；文件每一行仍以 CRLF 结尾，把这两行换回原值后与原文逐字节相同
    assert p.returncode == 0, p.stderr
    after = cmd.read_bytes()
    assert b"\r\nmodel: haiku\r\n" in after, after
    assert b"\r\neffort: medium\r\n" in after, after
    assert after.endswith(b"\r\n"), after
    assert after.count(b"\n") == after.count(b"\r\n"), after
    restored = after.replace(b"\r\nmodel: haiku\r\n", b"\r\nmodel: sonnet\r\n", 1).replace(
        b"\r\neffort: medium\r\n", b"\r\neffort: low\r\n", 1)
    assert restored == original


def test_frontmatter_accepts_fence_at_eof(tmp_path):
    # Given: 命令目录里的 `clean-after-merged.md` 只有 frontmatter（含 `context: fork`），文件以收尾的 `---` 结束、后面没有换行；配置把 `cleanup.runner` 设为 haiku · medium
    original = "\n".join(FORK_LINES[:8]).encode("utf-8")
    assert original.endswith(b"\n---")
    cmd = setup_bytes(tmp_path, original, runner("haiku", "medium"))

    # When: 运行 `model-routing.py frontmatter`
    p = routing(*frontmatter_args(tmp_path))

    # Then: 退出 0，frontmatter 里是 `model: haiku` 与 `effort: medium`；文件仍以 `---` 结束，后面没有补上换行
    assert p.returncode == 0, p.stdout + p.stderr
    after = cmd.read_bytes()
    lines = after.decode("utf-8").split("\n")
    assert "model: haiku" in lines and "effort: medium" in lines, after
    assert "model: sonnet" not in lines and "effort: low" not in lines, after
    assert after.endswith(b"---"), after
    assert not after.endswith(b"---\n"), after


def test_doctor_reports_frontmatter_drift(tmp_path):
    # Given: openspec 根的 `model-routing.json` 把 `cleanup.runner` 设为 haiku · medium，`clean-after-merged.md` 的 frontmatter 仍是 sonnet · low
    root = tmp_path / "openspec"
    root.mkdir()
    (root / "model-routing.json").write_text(json.dumps(runner("haiku", "medium")), encoding="utf-8")
    before = REAL_CMD.read_bytes()
    assert b"\nmodel: sonnet\n" in before and b"\neffort: low\n" in before

    # When: 运行 `flight-doctor.py doctor --openspec-root <该根>`
    p = doctor(root)

    # Then: 退出 0，输出含 `[routing]` 段，段内点名 `clean-after-merged.md` 的 `model` 期望 haiku 实际 sonnet、`effort` 期望 medium 实际 low，并给出 `model-routing.py frontmatter` 的重跑命令；`clean-after-merged.md` 的内容不变
    assert p.returncode == 0, p.stderr
    seg = routing_section(p.stdout)
    assert "clean-after-merged.md：model 期望 haiku 实际 sonnet" in seg, seg
    assert "clean-after-merged.md：effort 期望 medium 实际 low" in seg, seg
    assert "model-routing.py frontmatter" in seg, seg
    assert REAL_CMD.read_bytes() == before


def test_doctor_reports_frontmatter_in_sync(tmp_path):
    # Given: openspec 根没有 `model-routing.json`，`clean-after-merged.md` 的 frontmatter 等于 `cleanup.runner` 的内建默认
    root = tmp_path / "openspec"
    root.mkdir()

    # When: 运行 `flight-doctor.py doctor --openspec-root <该根>`
    p = doctor(root)

    # Then: 退出 0，`[routing]` 段说明 frontmatter 与路由一致，没有漂移条目
    assert p.returncode == 0, p.stderr
    seg = routing_section(p.stdout)
    assert "一致" in seg, seg
    assert "期望" not in seg, seg


def non_utf8_fork_bytes():
    """FORK_LINES 的 frontmatter 中间夹一行不是 UTF-8 的字节。"""
    head = "\n".join(FORK_LINES[:3]).encode("utf-8")
    tail = "\n".join(FORK_LINES[3:]).encode("utf-8")
    return head + b"\n\xff\xfe\n" + tail + b"\n"


def isolated_hooks(tmp_path):
    """把仓库的 hooks 复制到 <tmp>/.claude/hooks，并建 <tmp>/.claude/commands 与 <tmp>/openspec；返回 hooks 目录。"""
    hooks = tmp_path / ".claude" / "hooks"
    shutil.copytree(ROOT / "template" / ".claude" / "hooks", hooks, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / ".claude" / "commands").mkdir(parents=True, exist_ok=True)
    (tmp_path / "openspec").mkdir(exist_ok=True)
    return hooks


def run_isolated_doctor(tmp_path):
    """运行复制出来的 flight-doctor.py doctor；输出按 UTF-8 宽松解码，测试自身不因解码失败而崩。"""
    return subprocess.run(
        [sys.executable, str(tmp_path / ".claude" / "hooks" / "flight-doctor.py"), "doctor",
         "--openspec-root", str(tmp_path / "openspec")],
        cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, **CLEAN_ENV})


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_frontmatter_rejects_non_utf8_command(tmp_path):
    # Given: 命令目录里的 `clean-after-merged.md` 含 `context: fork`，frontmatter 里夹着一段不是 UTF-8 的字节；openspec 根没有 `model-routing.json`
    original = non_utf8_fork_bytes()
    cmd = tmp_path / "commands" / "clean-after-merged.md"
    cmd.parent.mkdir(parents=True)
    cmd.write_bytes(original)
    (tmp_path / "openspec").mkdir()

    # When: 运行 `model-routing.py frontmatter --check`
    p = subprocess.run(
        [sys.executable, str(ROOT / "template" / ".claude" / "hooks" / "model-routing.py"), "frontmatter", "--check",
         "--commands", str(tmp_path / "commands"), "--openspec", str(tmp_path / "openspec")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env={**os.environ, **CLEAN_ENV})

    # Then: 退出 2，stderr 点名 `cleanup.runner` 与 `clean-after-merged.md`，并说明它不是 UTF-8 文本；stderr 里没有 traceback，命令文件的字节不变
    assert p.returncode == 2, (p.returncode, p.stdout, p.stderr)
    assert "cleanup.runner" in p.stderr, p.stderr
    assert "clean-after-merged.md" in p.stderr, p.stderr
    assert "不是 UTF-8" in p.stderr, p.stderr
    assert "Traceback" not in p.stderr, p.stderr
    assert cmd.read_bytes() == original


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_doctor_reports_unreadable_command_as_unavailable(tmp_path):
    # Given: 一份独立安装的 hooks，命令目录里的 `clean-after-merged.md` 含 `context: fork` 但夹着不是 UTF-8 的字节
    isolated_hooks(tmp_path)
    (tmp_path / ".claude" / "commands" / "clean-after-merged.md").write_bytes(non_utf8_fork_bytes())

    # When: 运行该 hooks 的 `flight-doctor.py doctor --openspec-root <根>`
    p = run_isolated_doctor(tmp_path)

    # Then: 退出 0，`[routing]` 段报「不可用」并说明命令文件不是 UTF-8 文本；`[routing]` 段没有「修法」行
    assert p.returncode == 0, p.stderr
    seg = routing_section(p.stdout)
    assert "不可用" in seg, seg
    assert "不是 UTF-8" in seg, seg
    assert "修法" not in seg, seg


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_doctor_reports_crash_as_unavailable(tmp_path):
    # Given: 一份独立安装的 hooks，其中的 `model-routing.py` 一运行就抛出未捕获的 `RuntimeError: boom`
    hooks = isolated_hooks(tmp_path)
    (hooks / "model-routing.py").write_text('raise RuntimeError("boom")\n', encoding="utf-8")

    # When: 运行该 hooks 的 `flight-doctor.py doctor --openspec-root <根>`
    p = run_isolated_doctor(tmp_path)

    # Then: 退出 0，`[routing]` 段报「不可用：RuntimeError: boom」；`[routing]` 段没有「修法」行
    assert p.returncode == 0, p.stderr
    seg = routing_section(p.stdout)
    assert "不可用：RuntimeError: boom" in seg, seg
    assert "修法" not in seg, seg


@pytest.mark.xfail(strict=True, reason="S1 未实现")
def test_doctor_survives_undecodable_output(tmp_path):
    # Given: 一份独立安装的 hooks，其中的 `model-routing.py` 往 stdout 写一段不是 UTF-8 的字节和「frontmatter 与路由一致」后退出 0
    hooks = isolated_hooks(tmp_path)
    (hooks / "model-routing.py").write_text(
        'import sys\nsys.stdout.buffer.write(b"\\xff\\xfe\\n")\nsys.stdout.flush()\n'
        'print("frontmatter 与路由一致")\nsys.stdout.flush()\n', encoding="utf-8")

    # When: 运行该 hooks 的 `flight-doctor.py doctor --openspec-root <根>`
    p = run_isolated_doctor(tmp_path)

    # Then: 退出 0，输出同时含 `[runner]` 段与 `[routing]` 段；输出里没有「flight-doctor doctor 失败」
    assert p.returncode == 0, p.stderr
    lines = p.stdout.splitlines()
    assert "[runner]" in lines, p.stdout
    assert "[routing]" in lines, p.stdout
    assert "flight-doctor doctor 失败" not in p.stdout, p.stdout
