"""/test-tiers 的重划分脚本 test-tiers.py：probe / check / allow-slow / render
（scenario: test-tiers#probe-cli-reports-file-tiers、#check-flags-unclassified-and-ambiguous-files、
#allow-slow-requires-latest-human-message、#render-writes-approval-page）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S3 新增 test-tiers.py 后去掉标记即解锁。"""
import json

import pytest

from conftest import commit_all, run_hook, write

XF = pytest.mark.xfail(strict=True, reason="S3 尚未实现")
BIG = "tests/unit/test_a.py::test_big"


def human(text, ts):
    """转录里的一条人类消息（形状同 takeoff-gate 的判据）。"""
    return {"type": "user", "isSidechain": False, "isMeta": False, "userType": "external",
            "timestamp": ts, "message": {"role": "user", "content": text}}


def transcript(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    return path


def file_line(stdout, path):
    """probe 输出里该文件那一行（首列是层级标签）。"""
    return next(l for l in stdout.splitlines() if path in l)


@XF
def test_probe_cli_reports_file_tiers(git_repo):
    # Given: 仓库有 tests/test_pure.py（只有纯函数用例）、tests/test_io.py（用例都写临时文件）、
    #        tests/test_mixed.py（一个纯函数 test_pure、一个起子进程 test_spawns）
    write(git_repo / "pytest.ini", "[pytest]\n")
    write(git_repo / "tests" / "test_pure.py", "def test_a():\n    assert 1\n\n\ndef test_b():\n    assert 2\n")
    write(git_repo / "tests" / "test_io.py", "def test_w(tmp_path):\n    (tmp_path / 'f').write_text('x')\n")
    write(git_repo / "tests" / "test_mixed.py", """
        import subprocess
        import sys


        def test_pure():
            assert 1 + 1 == 2


        def test_spawns():
            subprocess.run([sys.executable, "-c", "pass"], check=True)
    """)
    commit_all(git_repo, "tests")
    out = git_repo.parent / "out.json"

    # When: 运行 test-tiers.py probe --json out.json
    p = run_hook("test-tiers", "probe", "--json", str(out), cwd=git_repo)

    # Then: 退出 0；三个文件的首列分别是 单元 / 集成 / 混合；
    #       out.json 里 test_mixed.py 的子进程用例带「子进程」样例，纯函数用例没有触碰
    assert p.returncode == 0, p.stdout + p.stderr
    assert file_line(p.stdout, "tests/test_pure.py").split()[0] == "单元", p.stdout
    assert file_line(p.stdout, "tests/test_io.py").split()[0] == "集成", p.stdout
    assert file_line(p.stdout, "tests/test_mixed.py").split()[0] == "混合", p.stdout
    tests = json.loads(out.read_text(encoding="utf-8"))["tests"]
    assert "子进程" in tests["tests/test_mixed.py::test_spawns"]["hits"], tests
    assert tests["tests/test_mixed.py::test_pure"]["hits"] == {}, tests


@XF
def test_check_flags_unclassified_and_ambiguous_files(git_repo):
    # Given: unit.paths 是 tests/unit/**，区域 hooks 的 paths 是 tests/integration/** 与 tests/unit/test_both.py；
    #        仓库里有 tests/unit/test_a.py、tests/unit/test_both.py、tests/test_loose.py
    tiers = {"unit": {"paths": ["tests/unit/**"], "cmd": "true"},
             "regions": {"hooks": {"paths": ["tests/integration/**", "tests/unit/test_both.py"], "covers": [], "cmd": "true"}}}
    write(git_repo / "openspec" / "test-tiers.json", json.dumps(tiers))
    for rel in ("tests/unit/test_a.py", "tests/unit/test_both.py", "tests/test_loose.py"):
        write(git_repo / rel, "def test_x():\n    assert True\n")
    commit_all(git_repo, "tests")

    # When: 运行 test-tiers.py check
    p = run_hook("test-tiers", "check", cwd=git_repo)

    # Then: 退出 1；输出点名 tests/test_loose.py（未归层）与 tests/unit/test_both.py（匹配多层），不点名 tests/unit/test_a.py
    text = p.stdout + p.stderr
    assert p.returncode == 1, text
    assert "tests/test_loose.py" in text and "tests/unit/test_both.py" in text, text
    assert "tests/unit/test_a.py" not in text, text


@XF
def test_allow_slow_requires_latest_human_message(git_repo):
    # Given: 分层文件 slow_allow 为空；转录里较早一条人类消息是「放行 test_big，fixture 要读大样本」，最新一条是「继续」
    path = git_repo / "openspec" / "test-tiers.json"
    write(path, json.dumps({"unit": {"paths": ["tests/unit/**"], "cmd": "true"}, "regions": {}, "slow_allow": {}}))
    session = git_repo.parent / "session.jsonl"
    rows = [human("放行 test_big，fixture 要读大样本", "2026-10-28T08:00:00Z"), human("继续", "2026-10-28T08:05:00Z")]
    transcript(session, rows)
    before = path.read_text(encoding="utf-8")
    args = ("allow-slow", BIG, "--reason", "读大样本", "--session", str(session))

    # When: 运行 test-tiers.py allow-slow tests/unit/test_a.py::test_big --reason 读大样本
    p1 = run_hook("test-tiers", *args, cwd=git_repo)

    # Then: 退出 3，分层文件不变；
    #       最新一条人类消息改成「放行 test_big，fixture 要读大样本」后再运行，退出 0，approved 含该消息的时间与「放行 test_big」
    assert p1.returncode == 3, p1.stdout + p1.stderr
    assert path.read_text(encoding="utf-8") == before
    transcript(session, rows + [human("放行 test_big，fixture 要读大样本", "2026-10-28T08:10:00Z")])
    p2 = run_hook("test-tiers", *args, cwd=git_repo)
    assert p2.returncode == 0, p2.stdout + p2.stderr
    entry = json.loads(path.read_text(encoding="utf-8"))["slow_allow"][BIG]
    assert entry["reason"] == "读大样本", entry
    assert "2026-10-28T08:10:00Z" in entry["approved"] and "放行 test_big" in entry["approved"], entry


@XF
def test_render_writes_approval_page(tmp_path):
    # Given: 探针结果含 tests/test_mixed.py 的纯函数用例与子进程用例；划分稿把前者移到 tests/unit/test_mixed.py、
    #        后者移到 tests/integration/hooks/test_mixed.py；tiers 里 unit 与区域 hooks 的 paths 分别覆盖这两个目录
    probe = {"total": 2, "tests": {
        "tests/test_mixed.py::test_pure": {"sec": 0.01, "hits": {}},
        "tests/test_mixed.py::test_spawns": {"sec": 0.2, "hits": {"子进程": "subprocess.Popen /usr/bin/python3"}},
    }}
    plan = {"tiers": {"unit": {"paths": ["tests/unit/**"], "cmd": "pytest -q tests/unit"},
                      "regions": {"hooks": {"paths": ["tests/integration/hooks/**"], "covers": ["src/hooks/**"],
                                            "cmd": "pytest -q tests/integration/hooks"}}},
            "moves": {"tests/test_mixed.py::test_pure": "tests/unit/test_mixed.py",
                      "tests/test_mixed.py::test_spawns": "tests/integration/hooks/test_mixed.py"}}
    probe_path, plan_path, page = tmp_path / "probe.json", tmp_path / "plan.json", tmp_path / "page.html"
    probe_path.write_text(json.dumps(probe, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    args = ("render", "--probe", str(probe_path), "--plan", str(plan_path), "--out", str(page))

    # When: 运行 test-tiers.py render
    p1 = run_hook("test-tiers", *args, cwd=tmp_path)

    # Then: 退出 0；page.html 含两个目标路径与「导出」按钮；
    #       把子进程用例的目标改成 tests/unit/test_mixed.py 后再运行，退出 1，stderr 点名该用例
    assert p1.returncode == 0, p1.stdout + p1.stderr
    html = page.read_text(encoding="utf-8")
    assert "tests/unit/test_mixed.py" in html and "tests/integration/hooks/test_mixed.py" in html, html[:500]
    assert "导出" in html
    plan["moves"]["tests/test_mixed.py::test_spawns"] = "tests/unit/test_mixed.py"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    p2 = run_hook("test-tiers", *args, cwd=tmp_path)
    assert p2.returncode == 1, p2.stdout + p2.stderr
    assert "tests/test_mixed.py::test_spawns" in p2.stderr, p2.stderr
