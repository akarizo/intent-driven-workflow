"""test-tiers.py 的驱动 run unit、部件形态的 check、金丝雀自检 canary、probe --root / --adapter
（scenario: test-tiers-polyglot#driver-runs-every-part … #probe-cli-adapter-prefixes-root）。"""
import hashlib
import json
import shlex
import sys

from conftest import run_hook, write

PY = shlex.quote(sys.executable)

# 如实的适配器：执行 $FLIGHT_UNIT_CMD，按四个金丝雀用例报触碰（file 的样例含令牌文件路径）
HONEST = '''import json, os, subprocess, sys
rc = subprocess.call(os.environ["FLIGHT_UNIT_CMD"], shell=True)
tok, d = os.environ["FLIGHT_CANARY_TOKEN"], os.environ["FLIGHT_CANARY_DIR"]
recs = [{"probe": "start"},
        {"nodeid": "canary/c_test.go::TestFlightCanaryPure", "sec": 0.01, "hits": {}},
        {"nodeid": "canary/c_test.go::TestFlightCanaryFile", "sec": 0.01, "hits": {"文件": "open " + os.path.join(d, tok)}},
        {"nodeid": "canary/c_test.go::TestFlightCanaryProc", "sec": 0.01, "hits": {"子进程": "subprocess.Popen true"}},
        {"nodeid": "canary/c_test.go::TestFlightCanaryNet", "sec": 0.01, "hits": {"网络": "socket.bind 127.0.0.1"}}]
with open(os.environ["FLIGHT_TIER_OUT"], "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\\n")
sys.exit(rc)
'''
# 偷懒的适配器：不执行 $FLIGHT_UNIT_CMD（令牌文件不会落盘），也不报 net 用例的网络触碰
LAZY = '''import json, os
tok, d = os.environ["FLIGHT_CANARY_TOKEN"], os.environ["FLIGHT_CANARY_DIR"]
recs = [{"probe": "start"},
        {"nodeid": "canary/c_test.go::TestFlightCanaryPure", "sec": 0.01, "hits": {}},
        {"nodeid": "canary/c_test.go::TestFlightCanaryFile", "sec": 0.01, "hits": {"文件": "open " + os.path.join(d, tok)}},
        {"nodeid": "canary/c_test.go::TestFlightCanaryProc", "sec": 0.01, "hits": {"子进程": "subprocess.Popen true"}},
        {"nodeid": "canary/c_test.go::TestFlightCanaryNet", "sec": 0.01, "hits": {}}]
with open(os.environ["FLIGHT_TIER_OUT"], "a", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False) + "\\n")
'''
# 金丝雀命令：写出 $FLIGHT_CANARY_DIR/$FLIGHT_CANARY_TOKEN
CANARY = '''import os
open(os.path.join(os.environ["FLIGHT_CANARY_DIR"], os.environ["FLIGHT_CANARY_TOKEN"]), "w").write("x")
'''


def set_tiers(root, tiers):
    path = root / "openspec" / "test-tiers.json"
    write(path, json.dumps(tiers, ensure_ascii=False, indent=2))
    return path


def canary_tiers(root, adapter_src):
    """部件 go（root svc/go）：probe.cmd 运行仓库内 adapter.py，金丝雀命令运行 canary.py。返回分层文件路径。"""
    write(root / "svc" / "go" / "adapter.py", adapter_src)
    write(root / "svc" / "go" / "canary.py", CANARY)
    probe = {"cmd": "%s adapter.py" % PY, "canary": "%s canary.py" % PY, "canary_files": ["svc/go/canary/**"]}
    tiers = {"parts": {"go": {"root": "svc/go", "unit": {"paths": ["svc/go/**"], "cmd": "true", "probe": probe}}},
             "slow_allow": {}}
    return set_tiers(root, tiers)


# ---------------------------------------------------------------- run unit


def test_driver_runs_every_part(git_repo):
    # Given: 部件 a 的单元命令在当前目录写 mark 并退出 0；部件 b 的单元命令退出 1
    write(git_repo / "a" / ".keep", "")
    write(git_repo / "b" / ".keep", "")
    set_tiers(git_repo, {"parts": {
        "a": {"root": "a", "unit": {"paths": ["a/**"], "cmd": "%s -c \"open('mark', 'w').write('x')\"" % PY}},
        "b": {"root": "b", "unit": {"paths": ["b/**"], "cmd": "%s -c \"import sys; sys.exit(1)\"" % PY}},
    }, "slow_allow": {}})

    # When: 运行 test-tiers.py run unit
    p = run_hook("test-tiers", "run", "unit", cwd=git_repo)

    # Then: 退出 1；a 一行 exit 0、b 一行 exit 1；mark 出现在 a/ 下
    assert p.returncode == 1, p.stdout + p.stderr
    lines = p.stdout.splitlines()
    assert any("部件 a" in l and "exit 0" in l for l in lines), p.stdout
    assert any("部件 b" in l and "exit 1" in l for l in lines), p.stdout
    assert (git_repo / "a" / "mark").exists()


# ---------------------------------------------------------------- check


def test_check_parts_membership(git_repo):
    # Given: 部件 py（test_files 与单元层）、go（金丝雀文件 svc/go/canary/**）、js 与 js2（root 都是 web、都没写 test_files）
    set_tiers(git_repo, {"parts": {
        "py": {"root": "svc/py", "test_files": ["svc/py/**/test_*.py"],
               "unit": {"paths": ["svc/py/tests/unit/**"], "cmd": "true"}},
        "go": {"root": "svc/go", "unit": {"paths": ["svc/go/**"], "cmd": "true",
                                          "probe": {"cmd": "sh adapter.sh", "canary": "true",
                                                    "canary_files": ["svc/go/canary/**"]}}},
        "js": {"root": "web", "unit": {"paths": ["web/**"], "cmd": "true"}},
        "js2": {"root": "web", "unit": {"paths": ["web/never/**"], "cmd": "true"}},
    }, "slow_allow": {}})
    for rel in ("svc/py/tests/unit/test_a.py", "svc/py/tests/it/test_b.py", "svc/go/x_test.go",
                "svc/go/canary/canary_test.go", "tools/y_test.go", "web/a.test.ts"):
        write(git_repo / rel, "x\n")

    # When: 运行 test-tiers.py check
    p = run_hook("test-tiers", "check", cwd=git_repo)

    # Then: 退出 1；点名 tools/y_test.go 不属于任何部件、web/a.test.ts 属于多个部件、test_b.py 未归层；不提另三个文件
    assert p.returncode == 1, p.stdout + p.stderr
    assert "不属于任何部件：tools/y_test.go" in p.stdout, p.stdout
    assert "属于多个部件：web/a.test.ts" in p.stdout, p.stdout
    assert "未归层：svc/py/tests/it/test_b.py" in p.stdout, p.stdout
    for name in ("canary_test.go", "x_test.go", "test_a.py"):
        assert name not in p.stdout, (name, p.stdout)


# ---------------------------------------------------------------- canary


def test_canary_accepts_adapter_and_records_sha(git_repo):
    # Given: 部件 go 的 probe.cmd 运行仓库内 svc/go/adapter.py；适配器执行金丝雀命令并如实报出四个用例的触碰
    path = canary_tiers(git_repo, HONEST)
    before = json.loads(path.read_text(encoding="utf-8"))

    # When: 运行 test-tiers.py canary --part go
    p = run_hook("test-tiers", "canary", "--part", "go", cwd=git_repo)

    # Then: 退出 0；probe.sha 恰为 adapter.py 的 sha256，checked 非空，checked_cmd 等于通过自检的 probe.cmd，其余键不变
    assert p.returncode == 0, p.stdout + p.stderr
    after = json.loads(path.read_text(encoding="utf-8"))
    probe = after["parts"]["go"]["unit"]["probe"]
    want = hashlib.sha256((git_repo / "svc" / "go" / "adapter.py").read_bytes()).hexdigest()
    assert probe["sha"] == {"svc/go/adapter.py": want}, probe
    assert probe["checked"], probe
    assert probe["checked_cmd"] == probe["cmd"], probe
    old = before["parts"]["go"]["unit"]["probe"]
    assert {k: probe[k] for k in old} == old, probe
    after["parts"]["go"]["unit"]["probe"] = old
    assert after == before


def test_canary_rejects_incomplete_adapter(git_repo):
    # Given: 适配器不执行金丝雀命令（令牌文件不落盘），也不报 net 用例的网络触碰
    path = canary_tiers(git_repo, LAZY)
    before = path.read_bytes()

    # When: 运行 test-tiers.py canary --part go
    p = run_hook("test-tiers", "canary", "--part", "go", cwd=git_repo)

    # Then: 退出 1；stdout 含「网络」与「落盘」；分层文件逐字节不变
    assert p.returncode == 1, p.stdout + p.stderr
    assert "网络" in p.stdout and "落盘" in p.stdout, p.stdout
    assert path.read_bytes() == before


# ---------------------------------------------------------------- probe


def test_probe_cli_adapter_prefixes_root(git_repo, tmp_path):
    # Given: svc/go 下的适配器执行测试命令，并为 a_test.go::TestA 写一条无触碰记录
    write(git_repo / "svc" / "go" / "adapter.py", '''
        import json, os, subprocess, sys
        rc = subprocess.call(os.environ["FLIGHT_UNIT_CMD"], shell=True)
        with open(os.environ["FLIGHT_TIER_OUT"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"probe": "start"}) + "\\n")
            f.write(json.dumps({"nodeid": "a_test.go::TestA", "sec": 0.01, "hits": {}}) + "\\n")
        sys.exit(rc)
        ''')
    out = tmp_path / "probe.json"

    # When: 运行 test-tiers.py probe --root svc/go --cmd true --adapter "<解释器> adapter.py" --json <路径>
    p = run_hook("test-tiers", "probe", "--root", "svc/go", "--cmd", "true",
                 "--adapter", "%s adapter.py" % PY, "--json", str(out), cwd=git_repo)

    # Then: 退出 0；有一行以「单元」开头并含 svc/go/a_test.go；JSON 的 tests 恰有 svc/go/a_test.go::TestA
    assert p.returncode == 0, p.stdout + p.stderr
    assert any(l.startswith("单元") and "svc/go/a_test.go" in l for l in p.stdout.splitlines()), p.stdout
    assert set(json.loads(out.read_text(encoding="utf-8"))["tests"]) == {"svc/go/a_test.go::TestA"}
