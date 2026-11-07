"""本仓库自身的测试基座：按路径加载 template/.claude/hooks/*.py，并提供临时 git 仓库。"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import textwrap

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOKS = ROOT / "template" / ".claude" / "hooks"


def hook_path(name: str) -> pathlib.Path:
    return HOOKS / f"{name}.py"


def load_hook(name: str):
    """按文件路径导入 hook 模块（文件名含连字符，不能直接 import）。"""
    path = hook_path(name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_hook(name: str, *args: str, stdin: str = "", env=None, cwd=None):
    """以子进程方式运行 hook 脚本，返回 CompletedProcess。"""
    return subprocess.run(
        [sys.executable, str(hook_path(name)), *args],
        input=stdin, capture_output=True, text=True,
        env={**os.environ, **(env or {})}, cwd=cwd,
    )


def git(repo, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


def write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


def commit_all(repo, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


# 基座选测声明（契约 v2 必有提供方）：恒报未全选的 cmd，只起一次 sh
SCOPE_DECL = {"cmd": "printf '{\"full\": false, \"triggers\": []}' > \"$GATE_SCOPE_OUT\""}


@pytest.fixture
def git_repo(tmp_path):
    """临时 git 仓库；初始提交带 openspec/gate-scope.json = SCOPE_DECL（恒报未全选），
    让既有用例在「选测提供方必有」下保持原语义；测「未声明」/「builtin」的用例自行删改该文件。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@example.com")
    git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("# t\n", encoding="utf-8")
    (repo / "openspec").mkdir()
    (repo / "openspec" / "gate-scope.json").write_text(json.dumps(SCOPE_DECL) + "\n", encoding="utf-8")
    commit_all(repo, "init")
    return repo
