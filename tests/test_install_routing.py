"""routing-frontmatter 与 routing-frontmatter-hardening 的 scenario 测试（已解锁）。"""
import json
import os
import re
import subprocess

import pytest

from conftest import ROOT

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def path_without_real_claude(bin_dir):
    """PATH = 桩目录 + 原 PATH 中不含 claude 可执行文件的目录。"""
    keep = [p for p in os.environ.get("PATH", "").split(os.pathsep)
            if p and not os.path.exists(os.path.join(p, "claude"))]
    return os.pathsep.join([str(bin_dir)] + keep)


def run_install(tmp_path, target, *flags):
    """用本仓库的 install.sh 安装 / 升级到 target；PATH 前置 openspec 与 claude 桩，并剔除真实 claude。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in ("openspec", "claude"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    env = {**os.environ, "PATH": path_without_real_claude(bin_dir)}
    return subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(target)],
                          env=env, capture_output=True, text=True, timeout=120)


def write_routing(target, cfg):
    path = target / "openspec" / "model-routing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg), encoding="utf-8")


def frontmatter_lines(target):
    text = (target / ".claude" / "commands" / "clean-after-merged.md").read_text(encoding="utf-8")
    m = FM.match(text)
    assert m, text[:200]
    return m.group(1).splitlines()


def test_upgrade_rerenders_fork_frontmatter(tmp_path):
    # Given: 一个已安装本模板的目标仓库，`openspec/model-routing.json` 把 `cleanup.runner` 设为 haiku · medium
    target = tmp_path / "proj"
    write_routing(target, {"cleanup": {"runner": {"model": "haiku", "effort": "medium"}}})

    # When: 先运行 `install.sh <目标>`，再运行 `install.sh --upgrade <目标>`
    first = run_install(tmp_path, target)
    after_install = frontmatter_lines(target) if first.returncode == 0 else []
    second = run_install(tmp_path, target, "--upgrade")
    after_upgrade = frontmatter_lines(target) if second.returncode == 0 else []

    # Then: 两次都退出 0；每次之后目标的 `.claude/commands/clean-after-merged.md` frontmatter 都是 `model: haiku` 与 `effort: medium`
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    for lines in (after_install, after_upgrade):
        assert "model: haiku" in lines, lines
        assert "effort: medium" in lines, lines


def test_install_survives_invalid_routing(tmp_path):
    # Given: 目标仓库的 `openspec/model-routing.json` 把 `cleanup.runner` 的 model 写成 `main`
    target = tmp_path / "proj"
    assert run_install(tmp_path, target).returncode == 0
    write_routing(target, {"cleanup": {"runner": {"model": "main", "effort": "low"}}})

    # When: 运行 `install.sh --upgrade <目标>`
    p = run_install(tmp_path, target, "--upgrade")

    # Then: 退出 0，输出含 `model-routing.py frontmatter` 的手动重跑提示；目标的 `clean-after-merged.md` frontmatter 是内建默认 `model: sonnet` 与 `effort: low`
    assert p.returncode == 0, p.stderr
    assert "model-routing.py frontmatter" in p.stdout + p.stderr, p.stdout + p.stderr
    lines = frontmatter_lines(target)
    assert "model: sonnet" in lines and "effort: low" in lines, lines


def test_install_hint_offers_upgrade(tmp_path):
    # Given: 一个已安装本模板的目标仓库，它的 `.claude/commands/clean-after-merged.md` 被换成没有 `context: fork` 的旧版命令
    target = tmp_path / "proj"
    first = run_install(tmp_path, target)
    assert first.returncode == 0, first.stderr
    cmd = target / ".claude" / "commands" / "clean-after-merged.md"
    cmd.write_text("---\ndescription: old\n---\n\n正文\n", encoding="utf-8")

    # When: 不带 `--upgrade` 再运行一次 `install.sh <目标>`
    second = run_install(tmp_path, target)
    out = second.stdout + second.stderr

    # Then: 退出 0，输出报告 fork 命令路由渲染失败；补救提示同时提到 `openspec/model-routing.json` 与 `install.sh --upgrade`
    assert second.returncode == 0, out
    assert "fork 命令路由渲染失败" in out, out
    hint = [l for l in out.splitlines() if "openspec/model-routing.json" in l]
    assert hint, out
    assert any("install.sh --upgrade" in l for l in hint), hint


@pytest.mark.xfail(strict=True, reason="S3 未实现")
def test_install_seeds_routing_config(tmp_path):
    # Given: 一个还没装过本模板的目标仓库
    target = tmp_path / "target"
    target.mkdir()
    path = target / "openspec" / "model-routing.json"

    # When: 运行 `install.sh <目标>`，再把目标的 `flight.executor` 改成 haiku · low 后运行 `install.sh --upgrade <目标>`
    p1 = run_install(tmp_path, target)
    assert p1.returncode == 0, p1.stdout + p1.stderr
    assert path.is_file(), p1.stdout
    cfg = json.loads(path.read_text(encoding="utf-8"))
    entries = {"%s.%s" % (g, k): v for g, keys in cfg.items() if g != "$comment" for k, v in keys.items()}
    cfg["flight"]["executor"]["model"] = "haiku"
    cfg["flight"]["executor"]["effort"] = "low"
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    p2 = run_install(tmp_path, target, "--upgrade")

    # Then: 两次都退出 0；第一次之后目标的 `openspec/model-routing.json` 含 11 个带 `desc` 的键；升级之后 `flight.executor` 仍是 haiku · low
    assert len(entries) == 11, sorted(entries)
    for name, v in entries.items():
        assert isinstance(v.get("desc"), str) and v["desc"].strip(), name
    assert p2.returncode == 0, p2.stdout + p2.stderr
    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["flight"]["executor"]["model"] == "haiku", after["flight"]
    assert after["flight"]["executor"]["effort"] == "low", after["flight"]
