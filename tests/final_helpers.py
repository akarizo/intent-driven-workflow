"""增量 final 测试共用的被测仓库与读取工具（incremental-final 各切片的测试共用，只读）。"""
import json
import shlex
import sys

from conftest import commit_all, git, run_hook, write

PY = shlex.quote(sys.executable)
TEST_CMD = "%s -m pytest -q -p no:cacheprovider tests" % PY
PYTEST = "%s -m pytest" % PY

SRC_A = "def a():\n    return 1\n"
TEST_A = """
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    from a import a


    def test_a():
        assert a() == 1
"""
TEST_B = """
    import json
    import os

    DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "b.json")


    def test_b():
        with open(DATA, encoding="utf-8") as f:
            assert json.load(f)["b"] == 2
"""
TOOL_C = """
    import os
    import sys

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    import c_lib

    print(c_lib.VALUE)
"""
TEST_C = """
    import os
    import subprocess
    import sys

    TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "c.py")


    def test_c():
        out = subprocess.run([sys.executable, TOOL], check=True, capture_output=True, text=True).stdout
        assert out.strip() == "3"
"""


def make_repo(repo, extra=None, gate_extra=None, scenario="tests/test_b.py::test_b", owns=("src/**",)):
    """被测仓库：src/a.py、src/c_lib.py、tools/c.py、data/b.json、scripts/helper.sh（无用例触及）；
    tests/test_a.py（静态 import src/a.py）、tests/test_b.py（读 data/b.json）、tests/test_c.py（子进程跑 tools/c.py）；
    extra = {相对路径: 内容} 追加文件；change c 单片 S1（verify 恒绿），唯一 scenario 映射到 scenario。返回 change 目录。"""
    write(repo / "pytest.ini", "[pytest]\n")
    write(repo / "src" / "a.py", SRC_A)
    write(repo / "src" / "c_lib.py", "VALUE = 3\n")
    write(repo / "tools" / "c.py", TOOL_C)
    write(repo / "data" / "b.json", '{"b": 2}\n')
    write(repo / "scripts" / "helper.sh", "echo hi\n")
    write(repo / "tests" / "test_a.py", TEST_A)
    write(repo / "tests" / "test_b.py", TEST_B)
    write(repo / "tests" / "test_c.py", TEST_C)
    for rel, text in (extra or {}).items():
        write(repo / rel, text)
    d = repo / "openspec" / "changes" / "c"
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "slices" / "S1.md", "# S1\n")
    gate = {"test": TEST_CMD, "pytest": PYTEST, "lint": None, "typecheck": None}
    gate.update(gate_extra or {})
    data = {
        "version": 1, "change": "c", "gate": gate,
        "slices": [{"id": "S1", "title": "S1", "owns": list(owns), "deps": [], "verify": "true",
                    "scenarios": ["c#s"], "packet": "slices/S1.md"}],
        "scenario_tests": {"c#s": scenario},
    }
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    commit_all(repo, "plan")
    return d


def gate_json(p):
    """slice-gate 子命令 stdout 的最后一行 JSON。"""
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    assert lines, p.stdout + p.stderr
    return json.loads(lines[-1])


def baseline(repo, d, *args):
    """跑 baseline 并提交它改写的计划 / 飞行记录文件；返回 baseline JSON。"""
    p = run_hook("slice-gate", "baseline", "--change-dir", str(d), *args, cwd=repo)
    out = gate_json(p)
    commit_all(repo, "baseline")
    return out


def final(repo, d, *args):
    """跑 final，返回 (JSON, CompletedProcess)。"""
    p = run_hook("slice-gate", "final", "--change-dir", str(d), *args, cwd=repo)
    return gate_json(p), p


def change_and_commit(repo, rel, text, msg="change"):
    write(repo / rel, text)
    return commit_all(repo, msg)


def anchors(repo):
    """锚点池 <git common dir>/flight-anchors/ 的全部条目，按 at 由旧到新。"""
    pdir = repo / ".git" / "flight-anchors"
    if not pdir.is_dir():
        return []
    out = []
    for f in pdir.glob("*.json"):
        if f.name.startswith(".tmp-"):
            continue
        out.append(json.loads(f.read_text(encoding="utf-8")))
    return sorted(out, key=lambda e: str(e.get("at") or ""))


def latest_anchor(repo):
    a = anchors(repo)
    assert a, "锚点池为空"
    return a[-1]


def timeline_rows(d, event):
    """timeline.md 里某事件的备注列表。"""
    path = d / "timeline.md"
    if not path.exists():
        return []
    rows = [l.split("\t") for l in path.read_text(encoding="utf-8").splitlines() if "\t" in l]
    return [r[2] for r in rows if len(r) >= 3 and r[1] == event]


def head(repo):
    return git(repo, "rev-parse", "HEAD")
