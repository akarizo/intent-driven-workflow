"""基线内容指纹、同一 change 的增量复用、verify 按需重跑、preflight 按内容判过期、增量基线的 timeline 记录
（scenario: baseline-incremental-reuse#baseline-records-snapshot … #timeline-marks-incremental-baseline；摘自原仓 #65 `855b834` 并按本仓改写）。
骨架：每个 scenario 一个 strict xfail，断言是真实的；切片 S1 实现后去掉标记即解锁。护栏（preflight-passes-after-artifact-commit、
preflight-skips-content-check-after-approve、preflight-old-baseline-compatible、preflight-ignores-removed-byproduct）在 base 上已成立，不带 xfail。
本文件的夹具也供 test_baseline_pool.py（S2）与 test_baseline_skip.py（S3）复用，那两片不改本文件。"""
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from conftest import commit_all, git, load_hook, run_hook, write

PY = shlex.quote(sys.executable)
PASSING = "def test_adds():\n    assert 1 + 1 == 2\n"
OLD_RED = "def test_old_red():\n    assert False\n"
# 全量脚本：先写标记（仓外绝对路径），再跑一次 pytest；同目录有 _env.sh 时先读它（模拟 source）
FULL = (
    "import os, pathlib, sys\n"
    "import pytest\n"
    "here = os.path.dirname(os.path.abspath(__file__))\n"
    "env = os.path.join(here, '_env.sh')\n"
    "if os.path.exists(env):\n"
    "    open(env, encoding='utf-8').read()\n"
    "pathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')\n"
    "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', 'tests']))\n"
)
FULL_ANCHOR = "pathlib.Path(sys.argv[1])"
# 直接的 pytest 全量命令（S3 的 verify 推导用）
PLAIN_FULL = "%s -m pytest -q -p no:cacheprovider tests" % PY
# verify 脚本：写标记 argv[1]，再用 pytest 跑 argv[2:]
VERIFY = (
    "import pathlib, sys\n"
    "import pytest\n"
    "pathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')\n"
    "sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', *sys.argv[2:]]))\n"
)
# lint 脚本：只写标记 argv[1]
LINT = "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('ran', encoding='utf-8')\n"
XFAIL_MORE = "\n\nimport pytest\n\n\n@pytest.mark.xfail(strict=True)\ndef test_more():\n    assert False\n"
# 全量运行时插入的片段：每次把当前时间写进未跟踪的 out/report.txt（内容每次不同的运行副产物）
BYPRODUCT = (
    "import time\n"
    "pathlib.Path('out').mkdir(exist_ok=True)\n"
    "pathlib.Path('out/report.txt').write_text(repr(time.time()), encoding='utf-8')\n"
)


def full_with(snippet):
    """全量脚本：在写全量标记之前先执行 snippet。"""
    return FULL.replace(FULL_ANCHOR, snippet + FULL_ANCHOR, 1)


def marker(git_repo, name):
    """仓外标记文件路径（git_repo 的上一级目录）。"""
    return git_repo.parent / name


def counting_test(counter, name="test_adds", fail=False):
    """测试文件文本：用例每运行一次就往仓外计数文件 counter 追加一个 x；fail=True 时用例失败。"""
    return (
        "import pathlib\n\n\n"
        "def %s():\n"
        "    p = pathlib.Path(%r)\n"
        "    p.write_text((p.read_text() if p.exists() else '') + 'x')\n"
        "    assert %s\n"
    ) % (name, str(counter), "False" if fail else "True")


def setup_change(git_repo, change="c", full_body=FULL, lint=False, slices=None, commit=True, extra=None,
                 old_red=True, gate_test=None, lint_cmd=None, cap_body=PASSING):
    """建被测仓库：src/mod.py、tests/test_cap.py（缺省通过）、tests/test_old.py（old_red 时预存红 1 条），
    change 目录下 verify/full.py 作 gate.test（写仓外标记 ran-full；gate_test 可整条替换）、gate.pytest 为本解释器；
    lint=True 时 gate.lint 写仓外标记 ran-lint（lint_cmd 可整条替换）；slices 缺省为单片 S1（verify 跑 tests/test_cap.py）；
    extra = {相对仓库根的路径: 文本} 额外写入。返回 change 目录。"""
    d = git_repo / "openspec" / "changes" / change
    rel = "openspec/changes/%s" % change
    write(git_repo / "src" / "mod.py", "x = 1\n")
    write(git_repo / "tests" / "test_cap.py", cap_body)
    if old_red:
        write(git_repo / "tests" / "test_old.py", OLD_RED)
    write(d / "verify" / "full.py", full_body)
    write(d / "verify" / "v.py", VERIFY)
    write(d / "verify" / "lint.py", LINT)
    write(d / "proposal.md", "## Why\n\n演示。\n")
    write(d / "specs" / "cap" / "spec.md", "## ADDED Requirements\n")
    write(d / "slices" / "S1.md", "# S1\n")
    if lint_cmd is None and lint:
        lint_cmd = "%s %s/verify/lint.py %s" % (PY, rel, shlex.quote(str(marker(git_repo, "ran-lint"))))
    gate = {
        "test": gate_test or "%s %s/verify/full.py %s" % (PY, rel, shlex.quote(str(marker(git_repo, "ran-full")))),
        "pytest": "%s -m pytest" % PY,
        "lint": lint_cmd,
        "typecheck": None,
        "full_suite_sec": None,
    }
    if slices is None:
        slices = [{"id": "S1", "verify": "%s -m pytest -q -p no:cacheprovider tests/test_cap.py" % PY}]
    data = {
        "version": 1, "change": change, "gate": gate,
        "slices": [dict({"title": s["id"], "scenarios": [], "owns": ["src/**"], "deps": [],
                         "packet": "slices/%s.md" % s["id"]}, **s) for s in slices],
        "scenario_tests": {},
    }
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))
    for path, text in (extra or {}).items():
        write(git_repo / path, text)
    if commit:
        commit_all(git_repo, "plan " + change)
    return d


def baseline(git_repo, d, *args):
    return run_hook("slice-gate", "baseline", "--change-dir", str(d), *args, cwd=git_repo)


def preflight(git_repo, d):
    return run_hook("slice-gate", "preflight", "--change-dir", str(d), cwd=git_repo)


def read_bl(d):
    return json.loads((d / "gate-baseline.json").read_text(encoding="utf-8"))


def read_plan(d):
    return json.loads((d / "slices.json").read_text(encoding="utf-8"))


def clear(*paths):
    for p in paths:
        if p.exists():
            p.unlink()


def append(path, text):
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def first_full(git_repo, d, *markers):
    """跑一次全量基线（须绿），再清掉全量标记与给定标记；返回基线 JSON。"""
    p = baseline(git_repo, d)
    assert p.returncode == 0, p.stdout + p.stderr
    clear(marker(git_repo, "ran-full"), *markers)
    return read_bl(d)


def two_changes(git_repo, d_full=FULL, c_env=None, d_env=None, old_red=True):
    """同一仓库里 change c 与 d（工件与门禁脚本都未提交），代码与测试已提交；可给两者各自的 verify/_env.sh。返回 (c, d)。"""
    c = setup_change(git_repo, change="c", commit=False, old_red=old_red)
    d = setup_change(git_repo, change="d", full_body=d_full, commit=False, old_red=old_red)
    git(git_repo, "add", "src", "tests")
    git(git_repo, "commit", "-q", "-m", "code")
    if c_env is not None:
        write(c / "verify" / "_env.sh", c_env)
    if d_env is not None:
        write(d / "verify" / "_env.sh", d_env)
    return c, d


def full_c(git_repo, c):
    """对 change c 跑一次全量基线（须绿），清掉全量标记；返回基线 JSON。"""
    p = baseline(git_repo, c)
    assert p.returncode == 0, p.stdout + p.stderr
    clear(marker(git_repo, "ran-full"))
    return read_bl(c)


def record_approve(d):
    """在本 change 的 timeline.md 末尾记一条 approve 事件（/opsx-apply 第 4 步的格式）。"""
    path = d / "timeline.md"
    head = path.read_text(encoding="utf-8") if path.exists() else "<!-- timeline: ISO时间\t事件\t备注（由 hooks 自动追加） -->\n"
    path.write_text(head + "2026-10-15T00:00:00Z\tapprove\t人类批准证据\n", encoding="utf-8")


# ---------------------------------------------------------------- 基线记录内容指纹


@pytest.mark.xfail(strict=True, reason="S1 未实现：基线记录内容指纹")
def test_baseline_records_snapshot(git_repo):
    # Given: change c 的计划已提交；未跟踪的 tests/test_new.py 含一个 strict-xfail 用例；gate.test 是本 change 目录下的全量脚本
    d = setup_change(git_repo)
    write(git_repo / "tests" / "test_new.py", "import pytest\n" + XFAIL_MORE)

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；mode 为 full、change 为 c；snapshot 含 tests/test_new.py 且值等于 git hash-object、不含 slices.json；
    #       cmd_key 为非空字符串；verify.S1.cmd 等于 S1 的 verify 命令
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["mode"] == "full" and bl["change"] == "c", bl
    assert bl["snapshot"]["tests/test_new.py"] == git(git_repo, "hash-object", "tests/test_new.py"), bl["snapshot"]
    assert "openspec/changes/c/slices.json" not in bl["snapshot"], bl["snapshot"]
    assert isinstance(bl["cmd_key"], str) and bl["cmd_key"], bl
    assert bl["verify"]["S1"]["cmd"] == read_plan(d)["slices"][0]["verify"], bl["verify"]


@pytest.mark.xfail(strict=True, reason="S1 未实现：运行期间改动判红")
def test_baseline_red_when_tracked_file_edited_while_running(git_repo):
    # Given: gate.test 运行时会改写已跟踪的 src/mod.py
    d = setup_change(git_repo, full_body=full_with("pathlib.Path('src/mod.py').write_text('x = 2\\n')\n"))

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出非 0；reasons 有一项同时含 src/mod.py 与「重跑 baseline」
    assert p.returncode != 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert any("src/mod.py" in r and "重跑 baseline" in r for r in bl["reasons"]), bl["reasons"]


@pytest.mark.xfail(strict=True, reason="S1 未实现：运行副产物登记")
def test_baseline_tolerates_new_byproduct(git_repo):
    # Given: gate.test 运行时在仓库里新建未跟踪的 out/report.txt
    d = setup_change(git_repo, full_body=full_with(BYPRODUCT))

    # When: 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；warnings 有一项含 out/report.txt；snapshot 与 byproducts 都含 out/report.txt
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert any("out/report.txt" in w for w in bl.get("warnings") or []), bl
    assert "out/report.txt" in bl["snapshot"], bl["snapshot"]
    assert "out/report.txt" in bl["byproducts"], bl


@pytest.mark.xfail(strict=True, reason="S1 未实现：上一次的副产物被改写只警告")
def test_baseline_tolerates_rewritten_byproduct(git_repo):
    # Given: gate.test 每次运行都把当前时间写进未跟踪的 out/report.txt；change c 已有一次全量绿基线
    d = setup_change(git_repo, full_body=full_with(BYPRODUCT))
    first_full(git_repo, d)

    # When: 运行 slice-gate.py baseline --full
    p = baseline(git_repo, d, "--full")

    # Then: 退出 0；warnings 有一项含 out/report.txt；byproducts 含 out/report.txt
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert any("out/report.txt" in w for w in bl.get("warnings") or []), bl
    assert "out/report.txt" in bl["byproducts"], bl


@pytest.mark.xfail(strict=True, reason="S1 未实现：运行期改动判定排除其他 change 目录")
def test_baseline_ignores_other_change_edits_while_running(git_repo):
    # Given: 已提交的 openspec/changes/other/proposal.md；gate.test 运行时往它末尾追加一行
    other = "openspec/changes/other/proposal.md"
    d = setup_change(git_repo, full_body=full_with("open(%r, 'a', encoding='utf-8').write('more\\n')\n" % other),
                     extra={other: "## Why\n"})

    # When: 对 change c 运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；mode 为 full；reasons 与 warnings 都不含 openspec/changes/other/proposal.md
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["mode"] == "full", bl
    assert not any(other in x for x in (bl.get("reasons") or []) + (bl.get("warnings") or [])), bl


@pytest.mark.xfail(strict=True, reason="S1 未实现：软链按链接文本取 blob")
def test_baseline_records_symlink_as_git_does(git_repo):
    # Given: 仓库根有未跟踪的符号链接 data，指向不存在的 ../outside-target
    d = setup_change(git_repo)
    os.symlink("../outside-target", str(git_repo / "data"))
    want = subprocess.run(["git", "hash-object", "--stdin"], input="../outside-target", cwd=git_repo,
                          capture_output=True, text=True, check=True).stdout.strip()

    # When: 运行 slice-gate.py baseline，再把工作区全部提交，运行 slice-gate.py preflight
    p = baseline(git_repo, d)
    bl = read_bl(d)
    commit_all(git_repo, "artifacts")
    pre = preflight(git_repo, d)

    # Then: baseline 退出 0；snapshot.data 等于链接文本的 blob id；preflight 退出 0
    assert p.returncode == 0, p.stdout + p.stderr
    assert bl["snapshot"]["data"] == want, bl["snapshot"]
    assert pre.returncode == 0, pre.stderr


# ---------------------------------------------------------------- 只改测试文件时复用全量


@pytest.mark.xfail(strict=True, reason="S1 未实现：只改测试文件时增量")
def test_incremental_when_only_test_file_changed(git_repo):
    # Given: change c 已有一次全量绿基线（预存红 1 条在 tests/test_old.py）；之后只往 tests/test_cap.py 末尾追加一个 strict-xfail 用例；
    #        gate.lint 运行时写标记
    d = setup_change(git_repo, lint=True)
    first = first_full(git_repo, d, marker(git_repo, "ran-lint"))
    sec0 = read_plan(d)["gate"]["full_suite_sec"]
    append(git_repo / "tests" / "test_cap.py", XFAIL_MORE)

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；全量标记不存在、lint 标记存在；mode 为 incremental，incremental.files 为 ["tests/test_cap.py"]，from.change 为 c；
    #       test.failed 与第一次相同；gate.full_suite_sec 与第一次相同
    assert p.returncode == 0, p.stdout + p.stderr
    assert not marker(git_repo, "ran-full").exists()
    assert marker(git_repo, "ran-lint").exists()
    bl = read_bl(d)
    assert bl["mode"] == "incremental", bl
    assert bl["incremental"]["files"] == ["tests/test_cap.py"], bl["incremental"]
    assert bl["incremental"]["from"]["change"] == "c", bl["incremental"]
    assert bl["test"]["failed"] == first["test"]["failed"] and first["test"]["failed"], (bl["test"], first["test"])
    assert read_plan(d)["gate"]["full_suite_sec"] == sec0


@pytest.mark.xfail(strict=True, reason="S1 未实现：只改计划工件时增量")
def test_incremental_noop_when_only_plan_changed(git_repo):
    # Given: change c 已有一次全量绿基线；之后只改了 proposal.md、specs 下的 spec.md 与 slices/S1.md
    d = setup_change(git_repo)
    first_full(git_repo, d)
    append(d / "proposal.md", "补一句。\n")
    append(d / "specs" / "cap" / "spec.md", "\n### Requirement: R2\n")
    append(d / "slices" / "S1.md", "补一句。\n")

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: 退出 0；gate.test 没有运行；mode 为 incremental，incremental.files 为空列表
    assert p.returncode == 0, p.stdout + p.stderr
    assert not marker(git_repo, "ran-full").exists()
    bl = read_bl(d)
    assert bl["mode"] == "incremental" and bl["incremental"]["files"] == [], bl


@pytest.mark.xfail(strict=True, reason="S1 未实现：非测试改动回全量并记理由")
def test_full_when_non_test_file_changed(git_repo):
    # Given: change c 已有一次全量绿基线；之后改了 src/mod.py
    d = setup_change(git_repo)
    first_full(git_repo, d)
    write(git_repo / "src" / "mod.py", "x = 2\n")

    # When: 再运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；mode 为 full；reuse_skipped 有一项的 change 为 c、理由含 src/mod.py
    assert marker(git_repo, "ran-full").exists()
    bl = read_bl(d)
    assert bl["mode"] == "full", bl
    assert any(s.get("change") == "c" and "src/mod.py" in (s.get("reason") or "")
               for s in bl.get("reuse_skipped") or []), bl


@pytest.mark.xfail(strict=True, reason="S1 未实现：补跑红回全量")
def test_full_when_changed_test_file_fails(git_repo):
    # Given: change c 已有一次全量绿基线；之后往 tests/test_cap.py 追加一个会失败的用例（不带 xfail）
    d = setup_change(git_repo)
    first_full(git_repo, d)
    append(git_repo / "tests" / "test_cap.py", "\n\ndef test_bad():\n    assert False\n")

    # When: 再运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；mode 为 full；test.failed 含新用例
    assert marker(git_repo, "ran-full").exists()
    bl = read_bl(d)
    assert bl["mode"] == "full", bl
    assert any(f.endswith("::test_bad") for f in bl["test"]["failed"]), bl["test"]


@pytest.mark.xfail(strict=True, reason="S1 未实现：改到预存红所在文件回全量")
def test_full_when_test_file_had_preexisting_red(git_repo):
    # Given: change c 已有一次全量绿基线（预存红 1 条在 tests/test_old.py）；之后往 tests/test_old.py 追加一个通过的用例
    d = setup_change(git_repo)
    first_full(git_repo, d)
    append(git_repo / "tests" / "test_old.py", "\n\ndef test_old_green():\n    assert True\n")

    # When: 再运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；mode 为 full
    assert marker(git_repo, "ran-full").exists()
    assert read_bl(d)["mode"] == "full"


@pytest.mark.xfail(strict=True, reason="S1 未实现：--full")
def test_full_flag_forces_full(git_repo):
    # Given: change c 已有一次全量绿基线，之后没有任何改动
    d = setup_change(git_repo)
    first_full(git_repo, d)

    # When: 运行 slice-gate.py baseline --full
    p = baseline(git_repo, d, "--full")

    # Then: 退出 0；gate.test 运行了；mode 为 full
    assert p.returncode == 0, p.stdout + p.stderr
    assert marker(git_repo, "ran-full").exists()
    assert read_bl(d)["mode"] == "full"


@pytest.mark.xfail(strict=True, reason="S1 未实现：门禁脚本内容变了回全量")
def test_full_when_gate_script_changed(git_repo):
    # Given: change c 已有一次全量绿基线；之后改了 gate.test 引用的本 change 目录下全量脚本的内容（命令文本不变）
    d = setup_change(git_repo)
    first_full(git_repo, d)
    append(d / "verify" / "full.py", "# 改了一行注释\n")

    # When: 再运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；mode 为 full
    assert marker(git_repo, "ran-full").exists()
    assert read_bl(d)["mode"] == "full"


@pytest.mark.xfail(strict=True, reason="S1 未实现：跨 change 脚本不同则全量")
def test_cross_change_refused_when_script_differs(git_repo):
    # Given: change c 跑过一次全量绿基线，没有预存红；change d 的全量脚本比 c 的多一行注释
    c, d = two_changes(git_repo, d_full=FULL + "# d 自己的一行注释\n", old_red=False)
    full_c(git_repo, c)

    # When: 对 d 运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；mode 为 full
    assert marker(git_repo, "ran-full").exists()
    assert read_bl(d)["mode"] == "full"


@pytest.mark.xfail(strict=True, reason="S1 未实现：跨 change 候选有预存红则全量")
def test_cross_change_refused_when_candidate_has_preexisting_red(git_repo):
    # Given: change c 跑过一次全量绿基线，预存红 1 条；change d 的全量脚本与 c 的内容相同，代码树与 c 所测的相同
    c, d = two_changes(git_repo, old_red=True)
    bc = full_c(git_repo, c)
    assert bc["test"].get("failed"), bc

    # When: 对 d 运行 slice-gate.py baseline
    baseline(git_repo, d)

    # Then: gate.test 运行了；d 的 mode 为 full
    assert marker(git_repo, "ran-full").exists()
    assert read_bl(d)["mode"] == "full"


# ---------------------------------------------------------------- verify 按需重跑


def three_slices(git_repo):
    """S1 verify 只跑 tests/test_a.py、S2 只跑 tests/test_b.py、S3 命令里没有路径；各写自己的仓外标记 v1 / v2 / v3。"""
    rel = "openspec/changes/c"
    m = {k: shlex.quote(str(marker(git_repo, k))) for k in ("v1", "v2", "v3")}
    v3 = "%s -c %s" % (PY, shlex.quote("import pathlib; pathlib.Path(%r).write_text('ran')" % str(marker(git_repo, "v3"))))
    return [
        {"id": "S1", "verify": "%s %s/verify/v.py %s tests/test_a.py" % (PY, rel, m["v1"])},
        {"id": "S2", "verify": "%s %s/verify/v.py %s tests/test_b.py" % (PY, rel, m["v2"])},
        {"id": "S3", "verify": v3},
    ]


def setup_three(git_repo):
    return setup_change(git_repo, slices=three_slices(git_repo),
                        extra={"tests/test_a.py": PASSING, "tests/test_b.py": PASSING})


@pytest.mark.xfail(strict=True, reason="S1 未实现：verify 只重跑受影响的片")
def test_verify_rerun_only_covering_slices(git_repo):
    # Given: S1 verify 只跑 tests/test_a.py、S2 只跑 tests/test_b.py、S3 命令里没有路径，各写自己的标记；
    #        已有一次全量绿基线，之后只往 tests/test_a.py 追加一个 strict-xfail 用例，并清掉三个标记
    d = setup_three(git_repo)
    ms = [marker(git_repo, k) for k in ("v1", "v2", "v3")]
    first_full(git_repo, d, *ms)
    append(git_repo / "tests" / "test_a.py", XFAIL_MORE)

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: mode 为 incremental；S1、S3 的标记存在，S2 的不存在；verify.S2.reused 为 true、exit 为 0
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["mode"] == "incremental", bl
    assert ms[0].exists() and ms[2].exists() and not ms[1].exists()
    assert bl["verify"]["S2"].get("reused") is True and bl["verify"]["S2"]["exit"] == 0, bl["verify"]


@pytest.mark.xfail(strict=True, reason="S1 未实现：verify 命令变了重跑")
def test_verify_rerun_when_command_changed(git_repo):
    # Given: 同上的三片与一次全量绿基线；之后只把 S2 的 verify 命令改成多带一个 -q，并清掉三个标记
    d = setup_three(git_repo)
    ms = [marker(git_repo, k) for k in ("v1", "v2", "v3")]
    first_full(git_repo, d, *ms)
    data = read_plan(d)
    data["slices"][1]["verify"] += " -q"
    write(d / "slices.json", json.dumps(data, ensure_ascii=False, indent=1))

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: mode 为 incremental；S2 的标记存在；verify.S2 没有 reused
    assert p.returncode == 0, p.stdout + p.stderr
    bl = read_bl(d)
    assert bl["mode"] == "incremental", bl
    assert ms[1].exists()
    assert "reused" not in bl["verify"]["S2"], bl["verify"]


# ---------------------------------------------------------------- preflight 按内容判过期


@pytest.mark.xfail(strict=True, reason="S1 未实现：preflight 按内容判过期")
def test_preflight_stale_when_test_file_changed_after_baseline(git_repo):
    # Given: change c 有一次全量绿基线，之后往 tests/test_cap.py 追加了一个用例；gate 与 verify 命令都没变
    d = setup_change(git_repo)
    first_full(git_repo, d)
    append(git_repo / "tests" / "test_cap.py", XFAIL_MORE)

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出非 0；stderr 含「基线过期」与 tests/test_cap.py
    assert p.returncode != 0
    assert "基线过期" in p.stderr and "tests/test_cap.py" in p.stderr, p.stderr


def test_preflight_passes_after_artifact_commit(git_repo):
    # Given: change c 在未跟踪的 tests/test_new.py 存在时跑过一次全量绿基线；之后把工作区全部提交，内容不变
    d = setup_change(git_repo)
    write(git_repo / "tests" / "test_new.py", "import pytest\n" + XFAIL_MORE)
    first_full(git_repo, d)
    commit_all(git_repo, "artifacts")

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


def test_preflight_skips_content_check_after_approve(git_repo):
    # Given: change c 有一次全量绿基线；timeline.md 里已有一条 approve 事件并已提交；之后改了 src/mod.py 并提交
    d = setup_change(git_repo)
    first_full(git_repo, d)
    record_approve(d)
    commit_all(git_repo, "chore(flight): approve")
    write(git_repo / "src" / "mod.py", "x = 2\n")
    commit_all(git_repo, "S1")

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


def test_preflight_old_baseline_compatible(git_repo):
    # Given: gate-baseline.json 是旧格式（commit、ok、plan_sha，没有 snapshot），plan_sha 与当前计划一致；之后改了 tests/test_cap.py
    d = setup_change(git_repo)
    sg = load_hook("slice-gate")
    write(d / "gate-baseline.json", json.dumps({
        "commit": git(git_repo, "rev-parse", "HEAD"),
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plan_sha": sg.plan_sha(read_plan(d)), "ok": True, "reasons": [], "test": {"exit": 0, "sec": 1.0},
    }))
    append(git_repo / "tests" / "test_cap.py", XFAIL_MORE)

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


def test_preflight_ignores_removed_byproduct(git_repo):
    # Given: change c 有一次全量绿基线，期间 gate.test 新建了未跟踪的 out/report.txt；之后人删掉了 out/report.txt
    d = setup_change(git_repo, full_body=full_with(BYPRODUCT))
    first_full(git_repo, d)
    (git_repo / "out" / "report.txt").unlink()

    # When: 运行 slice-gate.py preflight
    p = preflight(git_repo, d)

    # Then: 退出 0
    assert p.returncode == 0, p.stderr


# ---------------------------------------------------------------- 记录


@pytest.mark.xfail(strict=True, reason="S1 未实现：timeline 标出增量基线")
def test_timeline_marks_incremental_baseline(git_repo):
    # Given: change alpha 已有一次全量绿基线；之后只往 tests/test_cap.py 追加一个 strict-xfail 用例
    d = setup_change(git_repo, change="alpha")
    first_full(git_repo, d)
    append(git_repo / "tests" / "test_cap.py", XFAIL_MORE)

    # When: 再运行 slice-gate.py baseline
    p = baseline(git_repo, d)

    # Then: timeline.md 的最后一行 baseline 记录同时含「增量」与 alpha
    assert p.returncode == 0, p.stdout + p.stderr
    rows = [l for l in (d / "timeline.md").read_text(encoding="utf-8").splitlines() if "\tbaseline\t" in l]
    assert rows and "增量" in rows[-1] and "alpha" in rows[-1], rows
